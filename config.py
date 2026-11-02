import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def required(name):
    value = os.getenv(name, "").strip()
    if not value or value.startswith("PEGA_AQUI") or value.startswith("@TU_") or value.startswith("CAMBIA_ESTE"):
        raise RuntimeError(f"Falta configurar {name} en el archivo .env")
    return value


BOT_TOKEN = required("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = required("TELEGRAM_CHANNEL_ID")
RAWG_API_KEY = required("RAWG_API_KEY")
ADMIN_SETUP_CODE = required("ADMIN_SETUP_CODE")
PUBLICATIONS_PER_DAY = int(os.getenv("PUBLICATIONS_PER_DAY", "20"))
PUBLISH_START_HOUR = int(os.getenv("PUBLISH_START_HOUR", "9"))
PUBLISH_END_HOUR = int(os.getenv("PUBLISH_END_HOUR", "21"))
PUBLISH_INTERVAL_MINUTES = int(os.getenv("PUBLISH_INTERVAL_MINUTES", "36"))
RAWG_PAGE_SIZE = min(40, max(1, int(os.getenv("RAWG_PAGE_SIZE", "40"))))
RAWG_FETCH_INTERVAL_SECONDS = max(60, int(os.getenv("RAWG_FETCH_INTERVAL_SECONDS", "240")))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Madrid")

if PUBLICATIONS_PER_DAY < 1 or PUBLISH_INTERVAL_MINUTES < 1:
    raise RuntimeError("PUBLICATIONS_PER_DAY e INTERVAL deben ser positivos.")
if not 0 <= PUBLISH_START_HOUR <= 23 or not 1 <= PUBLISH_END_HOUR <= 24:
    raise RuntimeError("Horario inválido: inicio 0-23 y fin 1-24.")
