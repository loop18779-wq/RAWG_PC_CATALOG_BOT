
import logging
import re
import time
from datetime import datetime, timedelta
from html import unescape

from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

import database
from config import RAWG_API_KEY, RAWG_PAGE_SIZE


log = logging.getLogger(__name__)

API_URL = "https://api.rawg.io/api/games"

session = requests.Session()
session.headers.update({
    "User-Agent": "RAWG-PC-Catalog-TelegramBot/2.0",
    "Accept": "application/json",
})

# Pausa breve entre consultas de fichas individuales.
DETAIL_REQUEST_DELAY = 0.15

RATING_LABELS = {
    "exceptional": "Excepcional",
    "recommended": "Recomendado",
    "meh": "Meh",
    "skip": "Saltar",
}


# ============================================================
# LIMPIEZA DE TEXTO
# ============================================================

def clean_text(value):
    if not value:
        return ""

    soup = BeautifulSoup(unescape(str(value)), "html.parser")

    for br in soup.find_all("br"):
        br.replace_with("\n")

    for li in soup.find_all("li"):
        li.insert_before("• ")
        li.append("\n")

    text = soup.get_text("\n", strip=True)

    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.splitlines()
    ]

    result = "\n".join(line for line in lines if line)

    return re.sub(r"\n{3,}", "\n\n", result).strip()


def names_from_list(items):
    if not isinstance(items, list):
        return ""

    names = []

    for item in items:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]).strip())

    return ", ".join(dict.fromkeys(names))


# ============================================================
# REQUISITOS DEL SISTEMA
# ============================================================

def extract_pc_requirements(platforms):
    for item in platforms or []:
        if not isinstance(item, dict):
            continue

        platform = item.get("platform") or {}

        slug = str(platform.get("slug") or "").lower()
        name = str(platform.get("name") or "").lower()

        if slug in {"pc", "windows"} or name in {"pc", "windows"}:
            requirements = item.get("requirements") or {}

            if isinstance(requirements, str):
                return clean_text(requirements), ""

            if isinstance(requirements, dict):
                minimum = clean_text(requirements.get("minimum"))
                recommended = clean_text(requirements.get("recommended"))

                return minimum, recommended

    return "", ""


# ============================================================
# VALORACIONES
# ============================================================

def normalize_ratings(ratings):
    if not isinstance(ratings, list):
        return ""

    result = []

    for item in ratings:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").lower()
        label = RATING_LABELS.get(
            title,
            item.get("title") or "Otra"
        )

        count = item.get("count", 0)

        result.append(f"{label}: {count}")

    return " | ".join(result)


# ============================================================
# NORMALIZACIÓN DE LA FICHA
# ============================================================

def normalize_game(item):
    platforms = item.get("platforms") or []

    minimum, recommended = extract_pc_requirements(platforms)

    slug = item.get("slug") or ""

    platform_names = []

    for entry in platforms:
        if not isinstance(entry, dict):
            continue

        platform = entry.get("platform") or {}
        platform_name = platform.get("name")

        if platform_name:
            platform_names.append(platform_name)

    platform_names = ", ".join(dict.fromkeys(platform_names))

    tags = names_from_list(item.get("tags"))

    esrb_data = item.get("esrb_rating") or {}
    esrb = esrb_data.get("name", "") if isinstance(esrb_data, dict) else ""

    description = clean_text(
        item.get("description_raw")
        or item.get("description")
    )

    developers = names_from_list(item.get("developers"))
    publishers = names_from_list(item.get("publishers"))
    genres = names_from_list(item.get("genres"))

    rating = item.get("rating")
    ratings_count = item.get("ratings_count") or 0

    try:
        ratings_count = int(ratings_count)
    except (TypeError, ValueError):
        ratings_count = 0

    metacritic = item.get("metacritic")

    try:
        if metacritic is not None:
            metacritic = int(metacritic)
    except (TypeError, ValueError):
        metacritic = None

    ratings = normalize_ratings(item.get("ratings"))

    return {
        "id": item.get("id"),
        "slug": slug,
        "name": item.get("name") or "",

        "release_date": item.get("released") or "",

        "genres": genres,
        "developer": developers,
        "publisher": publishers,

        "description": description,

        "minimum": minimum,
        "recommended": recommended,

        "image": (
            item.get("background_image")
            or item.get("background_image_additional")
            or ""
        ),

        "url": (
            f"https://rawg.io/games/{slug}"
            if slug
            else "https://rawg.io/"
        ),

        "rating": str(rating) if rating is not None else "",
        "ratings_count": ratings_count,
        "rating_breakdown": ratings,

        "metacritic": metacritic,

        "platforms": platform_names,
        "esrb_rating": esrb,
        "tags": tags,
    }


# ============================================================
# PETICIONES A RAWG
# ============================================================

def request_rawg(url, params=None):
    if not RAWG_API_KEY:
        raise RuntimeError(
            "No se encuentra RAWG_API_KEY. Revisa el archivo .env."
        )

    request_params = dict(params or {})
    request_params["key"] = RAWG_API_KEY

    response = session.get(
        url,
        params=request_params,
        timeout=45,
    )

    if response.status_code in (401, 403):
        raise RuntimeError(
            f"RAWG respondió HTTP {response.status_code}. "
            "Comprueba la API key y sus permisos."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "RAWG ha alcanzado temporalmente su límite de peticiones. "
            "El proceso se ha detenido para evitar seguir consumiendo solicitudes."
        )

    response.raise_for_status()

    return response.json()


def fetch_game_details(game_id):
    """
    Recupera la ficha individual de un videojuego.
    RAWG permite consultar /games/{id}.
    """

    if not game_id:
        return None

    url = f"{API_URL}/{game_id}"

    try:
        data = request_rawg(url)

        if not isinstance(data, dict):
            return None

        return data

    except RuntimeError:
        raise

    except requests.RequestException as error:
        log.warning(
            "No se pudo recuperar el detalle RAWG %s: %s",
            game_id,
            error,
        )
        return None

    except ValueError as error:
        log.warning(
            "Respuesta JSON no válida para RAWG %s: %s",
            game_id,
            error,
        )
        return None


# ============================================================
# ENRIQUECIMIENTO DE JUEGOS ANTIGUOS
# ============================================================

def enrich_old_games(limit=5):
    """
    Recupera las fichas individuales de juegos antiguos
    que todavía no han sido revisados.
    """

    games = database.games_needing_details(limit)
    processed = 0
    updated = 0
    failed = 0

    for row in games:
        game_id = row["rawg_id"]

        try:
            details = fetch_game_details(game_id)

        except RuntimeError:
            # Detener el proceso si RAWG devuelve un error
            # de autenticación o límite de solicitudes.
            raise

        if not details:
            failed += 1
            continue

        # Asegurar que tenemos identificador y nombre.
        details["id"] = details.get("id") or game_id
        details["name"] = details.get("name") or row["name"]

        game = normalize_game(details)

        if not game.get("id") or not game.get("name"):
            failed += 1
            continue

        # Completar únicamente los campos vacíos.
        database.add_games([game])

        # Marcar como revisado incluso si RAWG no proporciona
        # algún dato opcional, para no repetir la consulta.
        database.mark_details_checked(game_id)

        processed += 1

        time.sleep(DETAIL_REQUEST_DELAY)

    if processed or failed:
        log.info(
            "Enriquecimiento antiguo: %s fichas revisadas; "
            "%s fallidas; %s pendientes.",
            processed,
            failed,
            database.details_pending_count(),
        )

    return processed

# ============================================================
# PAGINACIÓN
# ============================================================

def _next_page(next_url):
    if not next_url:
        return None

    try:
        page = parse_qs(
            urlparse(next_url).query
        ).get("page", [0])[0]

        return int(page) or None

    except (TypeError, ValueError):
        return None


# ============================================================
# COMPROBACIÓN DE PLATAFORMA PC
# ============================================================

def is_pc_game(item):
    for entry in item.get("platforms") or []:
        if not isinstance(entry, dict):
            continue

        platform = entry.get("platform") or {}

        slug = str(platform.get("slug") or "").lower()
        name = str(platform.get("name") or "").lower()

        if slug in {"pc", "windows"} or name in {"pc", "windows"}:
            return True

    return False


# ============================================================
# DESCARGA Y ACTUALIZACIÓN DEL CATÁLOGO
# ============================================================

def fetch_page(page):
    params = {
        "parent_platforms": "1",
        "ordering": "-added",
        "page": page,
        "page_size": RAWG_PAGE_SIZE,
    }

    payload = request_rawg(API_URL, params)

    results = payload.get("results") or []

    games = []

    eligible = 0
    details_ok = 0
    details_failed = 0

    for item in results:

        if not is_pc_game(item):
            continue

        eligible += 1

        game_id = item.get("id")

        if not game_id:
            continue

        # Consulta individual para obtener más información.
        try:
            details = fetch_game_details(game_id)

        except RuntimeError:
            # No continuar haciendo peticiones si RAWG
            # rechaza la API key o limita las solicitudes.
            raise

        if details:
            details_ok += 1

            # Pausa breve para no realizar peticiones consecutivas
            # demasiado rápidamente.
            time.sleep(DETAIL_REQUEST_DELAY)

            # Si el detalle no incluye plataformas, conservamos
            # las plataformas del listado general.
            if not details.get("platforms"):
                details["platforms"] = item.get("platforms") or []

            # Conservamos datos generales si faltan en el detalle.
            for field in (
                "name",
                "slug",
                "released",
                "background_image",
                "rating",
                "ratings_count",
                "ratings",
                "metacritic",
                "genres",
                "tags",
                "developers",
                "publishers",
                "esrb_rating",
            ):
                if not details.get(field) and item.get(field):
                    details[field] = item[field]

            game = normalize_game(details)

        else:
            details_failed += 1

            # Si falla la ficha individual, no perdemos el juego:
            # utilizamos los datos del listado general.
            game = normalize_game(item)

        if game.get("id") and game.get("name"):
            games.append(game)

    inserted = database.add_games(games)

    next_page = _next_page(payload.get("next"))

    log.info(
        "RAWG página %s: %s juegos PC; "
        "%s fichas individuales correctas; "
        "%s fallidas; %s registros insertados o actualizados.",
        page,
        eligible,
        details_ok,
        details_failed,
        inserted,
    )

    return inserted, next_page, eligible


# ============================================================
# ACTUALIZACIÓN AUTOMÁTICA
# ============================================================


def refresh_if_needed(interval_seconds):
    last = database.setting("rawg_last_fetch")

    if last:
        try:
            previous = datetime.fromisoformat(last)

            if datetime.now() - previous < timedelta(
                seconds=interval_seconds
            ):
                return 0

        except ValueError:
            pass

    page = int(database.setting("rawg_next_page") or "1")

    try:
        inserted, next_page, eligible = fetch_page(page)

    except Exception as exc:
        response = getattr(exc, "response", None)
        response_url = getattr(response, "url", "")
        status_code = getattr(response, "status_code", None)

        parsed = urlparse(response_url)
        requested_page = parse_qs(parsed.query).get(
            "page", [None]
        )[0]

        invalid_page = (
            status_code == 404
            and parsed.path.rstrip("/").endswith("/games")
            and requested_page == str(page)
            and page > 1
        )

        if not invalid_page:
            raise

        log.warning(
            "RAWG no permite consultar la página %s. "
            "Reiniciando el recorrido desde la página 1.",
            page,
        )

        page = 1

        database.set_setting("rawg_next_page", "1")
        database.set_setting("rawg_catalog_finished", "0")

        inserted, next_page, eligible = fetch_page(page)

    database.set_setting(
        "rawg_last_fetch",
        datetime.now().isoformat(timespec="seconds"),
    )

    if next_page:
        database.set_setting("rawg_next_page", str(next_page))
        database.set_setting("rawg_catalog_finished", "0")
    else:
        database.set_setting("rawg_next_page", "1")
        database.set_setting("rawg_catalog_finished", "1")

    log.info(
        "Actualización RAWG terminada. Página: %s. "
        "Juegos PC revisados: %s. Nuevos o actualizados: %s.",
        page,
        eligible,
        inserted,
    )

    enriched = enrich_old_games(limit=5)

    if enriched:
        log.info(
            "Se han enriquecido %s videojuegos antiguos.",
            enriched,
        )

    return inserted
