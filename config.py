
import os
from pathlib import Path
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")


# --------------------------------------------------
# FUNCIONES DE CONFIGURACIÓN
# --------------------------------------------------

def required(name):

    value = os.getenv(name, "").strip()

    if (
        not value
        or value.startswith("PEGA_AQUI")
        or value.startswith("@TU_")
        or value.startswith("CAMBIA_ESTE")
    ):
        raise RuntimeError(
            f"Falta configurar {name} en el archivo .env"
        )

    return value


def optional(name, default=""):

    return os.getenv(name, default).strip()


# --------------------------------------------------
# TELEGRAM
# --------------------------------------------------

BOT_TOKEN = required("TELEGRAM_BOT_TOKEN")

CHANNEL_ID = required("TELEGRAM_CHANNEL_ID")

ADMIN_SETUP_CODE = required("ADMIN_SETUP_CODE")


# --------------------------------------------------
# BASE DE DATOS
# --------------------------------------------------

CATALOG_DB_PATH = optional("CATALOG_DB_PATH")

# Si está definido en .env, queda disponible para database_nueva.py.
# Si está vacío, se utilizará su ruta predeterminada.


# --------------------------------------------------
# IGDB
# --------------------------------------------------

IGDB_CLIENT_ID = optional("IGDB_CLIENT_ID")

IGDB_CLIENT_SECRET = optional("IGDB_CLIENT_SECRET")

IGDB_ENABLED = bool(
    IGDB_CLIENT_ID and IGDB_CLIENT_SECRET
)

IGDB_FETCH_INTERVAL_SECONDS = max(
    300,
    int(os.getenv("IGDB_FETCH_INTERVAL_SECONDS", "3600"))
)

IGDB_PAGE_SIZE = min(
    500,
    max(1, int(os.getenv("IGDB_PAGE_SIZE", "50")))
)


# --------------------------------------------------
# STEAM
# --------------------------------------------------

STEAM_FETCH_INTERVAL_SECONDS = max(
    300,
    int(os.getenv("STEAM_FETCH_INTERVAL_SECONDS", "3600"))
)


# --------------------------------------------------
# RAWG
# --------------------------------------------------

RAWG_API_KEY = optional("RAWG_API_KEY")

RAWG_ENABLED = bool(RAWG_API_KEY)

RAWG_PAGE_SIZE = min(
    40,
    max(1, int(os.getenv("RAWG_PAGE_SIZE", "40")))
)

RAWG_FETCH_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("RAWG_FETCH_INTERVAL_SECONDS", "240"))
)


# --------------------------------------------------
# PUBLICACIONES
# --------------------------------------------------

PUBLICATIONS_PER_DAY = int(
    os.getenv("PUBLICATIONS_PER_DAY", "20")
)

PUBLISH_START_HOUR = int(
    os.getenv("PUBLISH_START_HOUR", "9")
)

PUBLISH_END_HOUR = int(
    os.getenv("PUBLISH_END_HOUR", "21")
)

PUBLISH_INTERVAL_MINUTES = int(
    os.getenv("PUBLISH_INTERVAL_MINUTES", "36")
)

TIMEZONE = optional(
    "TIMEZONE",
    "Europe/Madrid"
)


# --------------------------------------------------
# REINTENTOS
# --------------------------------------------------

PROVIDER_ERROR_BACKOFF_SECONDS = max(
    60,
    int(os.getenv("PROVIDER_ERROR_BACKOFF_SECONDS", "300"))
)


# --------------------------------------------------
# VALIDACIONES
# --------------------------------------------------

if PUBLICATIONS_PER_DAY < 1:
    raise RuntimeError(
        "PUBLICATIONS_PER_DAY debe ser positivo."
    )

if PUBLISH_INTERVAL_MINUTES < 1:
    raise RuntimeError(
        "PUBLISH_INTERVAL_MINUTES debe ser positivo."
    )

if not 0 <= PUBLISH_START_HOUR <= 23:
    raise RuntimeError(
        "PUBLISH_START_HOUR debe estar entre 0 y 23."
    )

if not 1 <= PUBLISH_END_HOUR <= 24:
    raise RuntimeError(
        "PUBLISH_END_HOUR debe estar entre 1 y 24."
    )

if PUBLISH_END_HOUR <= PUBLISH_START_HOUR:
    raise RuntimeError(
        "La hora de finalización debe ser posterior a la de inicio."
    )

if bool(IGDB_CLIENT_ID) != bool(IGDB_CLIENT_SECRET):
    raise RuntimeError(
        "IGDB requiere configurar IGDB_CLIENT_ID e "
        "IGDB_CLIENT_SECRET conjuntamente."
    )
