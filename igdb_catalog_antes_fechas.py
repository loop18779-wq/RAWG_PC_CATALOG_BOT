import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from html import unescape

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Importar después de cargar .env
import database_nueva as database


# =========================================================
# CONFIGURACIÓN
# =========================================================

CLIENT_ID = os.getenv("IGDB_CLIENT_ID")
CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET")

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4/games"

BATCH_SIZE = 50
MAX_BATCHES = 5

# Solo tipos de juego completos:
# 0 Main Game, 8 Remake, 9 Remaster, 11 Port
ALLOWED_GAME_TYPES = (0, 8, 9, 11)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("IGDB")


# =========================================================
# SEGURIDAD DE BASE DE DATOS
# =========================================================

def check_database_safety():
    original_db = (ROOT / "data" / "rawg_catalog.db").resolve()
    configured_db = Path(database.DB).resolve()

    print("\nBASE DE DATOS SELECCIONADA:")
    print(configured_db)

    if configured_db == original_db:
        raise RuntimeError(
            "SEGURIDAD: el programa está apuntando a la base de datos "
            "original. Configura CATALOG_DB_PATH en .env con la copia migrada."
        )

    if not configured_db.exists():
        raise FileNotFoundError(
            f"No existe la base de datos configurada: {configured_db}"
        )

    print("Seguridad: se utilizará una copia, no la base original.")


# =========================================================
# AUTENTICACIÓN
# =========================================================

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
        timeout=30
    )

    response.raise_for_status()

    token = response.json().get("access_token")

    if not token:
        raise RuntimeError("Twitch no devolvió un token de acceso.")

    return token


# =========================================================
# CONSULTA IGDB
# =========================================================

def query_games(token, last_id):
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain"
    }

    query = f"""
        fields
            id,
            name,
            slug,
            first_release_date,
            genres.name,
            involved_companies.company.name,
            summary,
            storyline,
            cover.url,
            rating,
            rating_count,
            platforms.name,
            game_type;
        where
            id > {int(last_id)}
            & platforms = (6)
            & game_type = {ALLOWED_GAME_TYPES};
        sort id asc;
        limit {BATCH_SIZE};
    """

    response = requests.post(
        API_URL,
        headers=headers,
        data=query,
        timeout=60
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# TRANSFORMACIÓN DE DATOS
# =========================================================

def timestamp_to_date(timestamp):
    if not timestamp:
        return None

    return datetime.fromtimestamp(
        timestamp,
        timezone.utc
    ).date().isoformat()


def extract_company(companies):
    if not companies:
        return None

    for item in companies:
        company = item.get("company", {})

        if company and company.get("name"):
            return company["name"]

    return None


def transform_game(game):
    release_date = timestamp_to_date(
        game.get("first_release_date")
    )

    genres = [
        item.get("name")
        for item in game.get("genres", [])
        if item.get("name")
    ]

    platforms = [
        item.get("name")
        for item in game.get("platforms", [])
        if item.get("name")
    ]

    cover = game.get("cover") or {}
    image = cover.get("url")

    if image:
        image = image.replace(
            "t_thumb",
            "t_cover_big"
        )

        if image.startswith("//"):
            image = "https:" + image

    description = (
        game.get("summary")
        or game.get("storyline")
        or ""
    )

    description = unescape(description)

    return {
        "igdb_id": game["id"],
        "name": game.get("name"),
        "slug": game.get("slug"),
        "release_date": release_date,
        "genres": ", ".join(genres),
        "developer": extract_company(
            game.get("involved_companies", [])
        ),
        "description": description,
        "image": image,
        "rating": game.get("rating"),
        "ratings_count": game.get("rating_count"),
        "platforms": ", ".join(platforms),
        "discovered_at": datetime.now(
            timezone.utc
        ).isoformat()
    }


# =========================================================
# IMPORTACIÓN
# =========================================================

def import_catalog():
    print("=" * 60)
    print("IMPORTADOR DE VIDEOJUEGOS IGDB")
    print("=" * 60)

    check_database_safety()

    database.init()

    token = get_access_token()

    print("\nAutenticación IGDB correcta.")

    last_id = int(
        database.setting("igdb_last_id", "0")
    )

    print(f"Último ID procesado: {last_id}")

    total_received = 0
    total_valid = 0
    total_future = 0
    total_missing_date = 0

    today = datetime.now(timezone.utc).date()

    for batch_number in range(1, MAX_BATCHES + 1):

        print(
            f"\nConsultando lote {batch_number}/{MAX_BATCHES}..."
        )

        games = query_games(token, last_id)

        if not games:
            print("IGDB no devuelve más resultados.")
            database.set_setting(
                "igdb_catalog_finished",
                "1"
            )
            break

        total_received += len(games)

        valid_games = []

        for game in games:

            game_id = game.get("id")

            if not game_id:
                continue

            last_id = max(last_id, int(game_id))

            release_timestamp = game.get(
                "first_release_date"
            )

            if not release_timestamp:
                total_missing_date += 1
                continue

            release_date = datetime.fromtimestamp(
                release_timestamp,
                timezone.utc
            ).date()

            if release_date > today:
                total_future += 1
                continue

            transformed = transform_game(game)

            if not transformed.get("name"):
                continue

            valid_games.append(transformed)

        if valid_games:
            inserted = database.upsert_igdb_games(
                valid_games
            )

            total_valid += len(valid_games)

            print(
                f"Juegos válidos enviados a la base de datos: "
                f"{len(valid_games)}"
            )
        else:
            print("Este lote no contiene juegos válidos.")

        database.set_setting(
            "igdb_last_id",
            str(last_id)
        )

        database.set_setting(
            "igdb_last_sync",
            datetime.now(timezone.utc).isoformat()
        )

        if len(games) < BATCH_SIZE:
            database.set_setting(
                "igdb_catalog_finished",
                "1"
            )
            print("Se alcanzó el final del catálogo disponible.")
            break

    print("\n" + "=" * 60)
    print("RESUMEN DE IMPORTACIÓN")
    print("=" * 60)

    print(f"Registros recibidos: {total_received}")
    print(f"Juegos válidos enviados: {total_valid}")
    print(f"Juegos futuros excluidos: {total_future}")
    print(f"Juegos sin fecha excluidos: {total_missing_date}")
    print(f"Último ID IGDB: {last_id}")

    print("\nEstadísticas de la base de datos:")
    print(database.stats())

    print("\nIMPORTACIÓN FINALIZADA.")


# =========================================================
# EJECUCIÓN
# =========================================================

if __name__ == "__main__":

    try:
        import_catalog()

    except requests.RequestException as error:
        logger.exception("Error de conexión con IGDB: %s", error)

    except Exception as error:
        logger.exception("Error durante la importación: %s", error)