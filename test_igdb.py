
import os
import json
import logging
import requests

from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# ============================================================
# 1. CONFIGURACIÓN
# ============================================================

ROOT = Path(__file__).resolve().parent

# Cargar las credenciales antes de importar la base de datos.
load_dotenv(ROOT / ".env")

CLIENT_ID = os.getenv("IGDB_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET", "").strip()

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_URL = "https://api.igdb.com/v4/games"

WINDOWS_PLATFORM_ID = 6

ALLOWED_GAME_TYPES = (0, 8, 9, 11)

BATCH_SIZE = 50

# Número máximo de páginas por ejecución.
MAX_BATCHES = 5

REQUEST_TIMEOUT = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | IGDB | %(levelname)s | %(message)s"
)

logger = logging.getLogger("igdb_catalog")


# ============================================================
# 2. IMPORTAR BASE DE DATOS
# ============================================================

import database_nueva as database


# ============================================================
# 3. PROTECCIÓN DE LA BASE DE DATOS ORIGINAL
# ============================================================

ORIGINAL_DB = (
    ROOT / "data" / "rawg_catalog.db"
).resolve()


def check_database_safety():

    selected_db = Path(database.DB).resolve()

    if selected_db == ORIGINAL_DB:

        raise RuntimeError(
            "\nPROTECCIÓN ACTIVADA.\n"
            "IGDB no puede importar datos directamente "
            "en la base de datos original.\n\n"
            "Configura CATALOG_DB_PATH en el archivo .env "
            "para utilizar la copia migrada."
        )

    logger.info("Base de datos seleccionada: %s", selected_db)
    logger.info("Protección de base de datos original: ACTIVADA")


# ============================================================
# 4. AUTENTICACIÓN TWITCH
# ============================================================

def get_access_token():

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "Faltan IGDB_CLIENT_ID o IGDB_CLIENT_SECRET en .env"
        )

    response = requests.post(
        TOKEN_URL,
        params={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    token = response.json().get("access_token")

    if not token:
        raise RuntimeError(
            "Twitch no ha devuelto un token de acceso."
        )

    logger.info("Autenticación IGDB correcta.")

    return token


# ============================================================
# 5. CONSULTA DE JUEGOS
# ============================================================

def build_query(last_id):

    types = ",".join(
        str(value) for value in ALLOWED_GAME_TYPES
    )

    return f"""
        fields
            id,
            name,
            slug,
            game_type,
            first_release_date,
            platforms.name,
            genres.name,
            summary,
            rating,
            rating_count,
            cover.url;

        where
            id > {int(last_id)}
            & platforms = ({WINDOWS_PLATFORM_ID})
            & game_type = ({types});

        sort id asc;

        limit {BATCH_SIZE};
    """


def fetch_games(token, last_id):

    query = build_query(last_id)

    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain"
    }

    response = requests.post(
        IGDB_URL,
        headers=headers,
        data=query,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    games = response.json()

    if not isinstance(games, list):
        raise RuntimeError(
            "IGDB ha devuelto una respuesta inesperada."
        )

    return games


# ============================================================
# 6. CONVERSIÓN DE DATOS
# ============================================================

def format_release_date(timestamp):

    if timestamp is None:
        return None

    try:

        return datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc
        ).date().isoformat()

    except (ValueError, TypeError, OSError, OverflowError):

        return None


def format_cover(cover):

    if not cover:
        return None

    url = cover.get("url")

    if not url:
        return None

    if url.startswith("//"):
        url = "https:" + url

    return url.replace(
        "/t_thumb/",
        "/t_cover_big/"
    )


def normalize_game(game):

    platforms = [
        item.get("name")
        for item in game.get("platforms", [])
        if item.get("name")
    ]

    genres = [
        item.get("name")
        for item in game.get("genres", [])
        if item.get("name")
    ]

    release_date = format_release_date(
        game.get("first_release_date")
    )

    # No se importan juegos sin fecha verificable.
    if not release_date:
        return None

    # No se importan juegos cuyo lanzamiento sea futuro.
    today = datetime.now(timezone.utc).date()

    release = datetime.strptime(
        release_date,
        "%Y-%m-%d"
    ).date()

    if release > today:
        return None

    return {
        "igdb_id": int(game["id"]),
        "name": game.get("name"),
        "slug": game.get("slug"),
        "release_date": release_date,
        "genres": ", ".join(genres) if genres else None,
        "description": game.get("summary"),
        "image": format_cover(game.get("cover")),
        "rating": game.get("rating"),
        "ratings_count": game.get("rating_count"),
        "platforms": json.dumps(
            platforms,
            ensure_ascii=False
        ),
        "discovered_at": datetime.now().isoformat()
    }


# ============================================================
# 7. FILTRO DE TIPOS DE JUEGO
# ============================================================

def valid_game_type(game):

    game_type = game.get("game_type")

    return game_type in ALLOWED_GAME_TYPES


# ============================================================
# 8. IMPORTACIÓN A SQLITE
# ============================================================

def import_batch(games):

    valid_games = []
    rejected_types = 0
    future_games = 0
    missing_dates = 0

    for game in games:

        if not valid_game_type(game):
            rejected_types += 1
            continue

        normalized = normalize_game(game)

        if normalized is None:

            if not game.get("first_release_date"):
                missing_dates += 1
            else:
                future_games += 1

            continue

        valid_games.append(normalized)

    if valid_games:

        # La función de la base de datos identifica los registros
        # por igdb_id y evita insertarlos dos veces.
        database.upsert_igdb_games(valid_games)

    return {
        "received": len(games),
        "imported_or_matched": len(valid_games),
        "rejected_types": rejected_types,
        "future": future_games,
        "missing_dates": missing_dates
    }


# ============================================================
# 9. SINCRONIZACIÓN COMPLETA
# ============================================================

def sync_catalog(max_batches=MAX_BATCHES):

    check_database_safety()

    if max_batches < 1:
        raise ValueError("max_batches debe ser mayor que cero.")

    database.init()

    token = get_access_token()

    last_id = int(
        database.setting("igdb_last_id", "0")
    )

    totals = {
        "received": 0,
        "imported_or_matched": 0,
        "rejected_types": 0,
        "future": 0,
        "missing_dates": 0,
        "batches": 0
    }

    logger.info("Último ID procesado: %s", last_id)

    for batch_number in range(1, max_batches + 1):

        logger.info(
            "Consultando lote %s de %s...",
            batch_number,
            max_batches
        )

        games = fetch_games(token, last_id)

        if not games:

            logger.info(
                "No hay más resultados después del ID %s.",
                last_id
            )

            database.set_setting(
                "igdb_catalog_finished",
                "1"
            )

            break

        result = import_batch(games)

        for key in (
            "received",
            "imported_or_matched",
            "rejected_types",
            "future",
            "missing_dates"
        ):
            totals[key] += result[key]

        totals["batches"] += 1

        # Los resultados están ordenados por ID ascendente.
        # Avanzamos únicamente después de procesar el lote.
        new_last_id = max(
            int(game["id"]) for game in games
        )

        database.set_setting(
            "igdb_last_id",
            new_last_id
        )

        last_id = new_last_id

        logger.info(
            "Lote %s: recibidos=%s | importados/coincidentes=%s "
            "| tipos rechazados=%s | futuros=%s | sin fecha=%s",
            batch_number,
            result["received"],
            result["imported_or_matched"],
            result["rejected_types"],
            result["future"],
            result["missing_dates"]
        )

        if len(games) < BATCH_SIZE:
            database.set_setting(
                "igdb_catalog_finished",
                "1"
            )
            break

    database.set_setting(
        "igdb_last_sync",
        datetime.now().isoformat()
    )

    stats = database.stats()

    logger.info("=" * 55)
    logger.info("RESUMEN DE IMPORTACIÓN IGDB")
    logger.info("=" * 55)

    for key, value in totals.items():
        logger.info("%s: %s", key, value)

    logger.info("BASE DE DATOS")
    logger.info("Total de juegos: %s", stats["total"])
    logger.info("Pendientes: %s", stats["pending"])
    logger.info("Publicados: %s", stats["published"])

    logger.info(
        "Último ID IGDB procesado: %s",
        last_id
    )

    return totals


# ============================================================
# 10. EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":

    try:

        print("=" * 65)
        print("IMPORTADOR IGDB - CATÁLOGO DE JUEGOS WINDOWS")
        print("=" * 65)

        result = sync_catalog()

        print("\nIMPORTACIÓN FINALIZADA.")

        print(
            "Juegos importados o coincidentes:",
            result["imported_or_matched"]
        )

    except Exception:

        logger.exception(
            "ERROR DURANTE LA IMPORTACIÓN IGDB"
        )

        raise
