
import logging
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlencode
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError

import database_nueva as database

from config import (
    CHANNEL_ID,
    TIMEZONE,
    PUBLICATIONS_PER_DAY,
    PUBLISH_START_HOUR,
    PUBLISH_END_HOUR,
    PUBLISH_INTERVAL_MINUTES,
)


log = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)

TELEGRAM_MESSAGE_LIMIT = 3900
TELEGRAM_CAPTION_LIMIT = 1000


# ============================================================
# UTILIDADES
# ============================================================

def _value(g, key, default=""):
    try:
        return g[key] or default
    except (KeyError, IndexError, TypeError):
        return default


def _rating_text(value):
    try:
        return f"{float(value):.1f}/5"
    except (TypeError, ValueError):
        return ""


def _valid_url(value):
    if not value:
        return ""

    value = str(value).strip()

    try:
        parsed = urlparse(value)

        if parsed.scheme not in ("http", "https"):
            return ""

        if not parsed.netloc:
            return ""

        return value

    except ValueError:
        return ""


def _split_long_line(line, limit):
    if len(line) <= limit:
        return [line]

    chunks = []

    while len(line) > limit:
        cut = line.rfind(" ", 0, limit)

        if cut <= 0:
            cut = limit

        chunks.append(line[:cut])
        line = line[cut:].lstrip()

    if line:
        chunks.append(line)

    return chunks


def split_message(message, limit=TELEGRAM_MESSAGE_LIMIT):
    """Divide mensajes largos en fragmentos."""

    lines = message.split("\n")
    chunks = []
    current = ""

    for original_line in lines:
        line_parts = _split_long_line(original_line, limit)

        for line in line_parts:
            candidate = line if not current else current + "\n" + line

            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)

                current = line

    if current:
        chunks.append(current)

    return chunks


# ============================================================
# CONSTRUCCIÓN DE LA PUBLICACIÓN
# ============================================================

def build_post(g):
    name = escape(str(_value(g, "name", "Videojuego")))

    parts = [
        f"🎮 <b>{name}</b>"
    ]

    release = _value(g, "release_date")

    if release:
        parts.append(
            f"📅 <b>Lanzamiento:</b> {escape(str(release))}"
        )

    genres = _value(g, "genres")

    if genres:
        parts.append(
            f"🎭 <b>Géneros:</b> {escape(str(genres))}"
        )

    platforms = _value(g, "platforms")

    if platforms:
        parts.append(
            f"🖥 <b>Plataformas:</b> {escape(str(platforms))}"
        )

    developer = _value(g, "developer")

    if developer:
        parts.append(
            f"🧑‍💻 <b>Desarrollador:</b> {escape(str(developer))}"
        )

    publisher = _value(g, "publisher")

    if publisher:
        parts.append(
            f"🏢 <b>Editor:</b> {escape(str(publisher))}"
        )

    esrb_rating = _value(g, "esrb_rating")

    if esrb_rating:
        parts.append(
            f"🔞 <b>Clasificación por edad:</b> "
            f"{escape(str(esrb_rating))}"
        )

    # Valoración general, independientemente del proveedor.
    rating = _rating_text(_value(g, "rating"))

    try:
        ratings_count = int(_value(g, "ratings_count", 0))
    except (TypeError, ValueError):
        ratings_count = 0

    if rating or ratings_count:
        line = "⭐ <b>Valoración:</b> "
        line += escape(rating or "Sin nota")

        if ratings_count:
            line += (
                f" · {ratings_count:,} valoraciones"
                .replace(",", ".")
            )

        parts.append(line)

    rating_breakdown = _value(g, "rating_breakdown")

    if rating_breakdown:
        parts.append(
            f"📊 <b>Distribución de valoraciones:</b> "
            f"{escape(str(rating_breakdown))}"
        )

    metacritic = _value(g, "metacritic")

    if metacritic:
        parts.append(
            f"🎯 <b>Metascore:</b> {escape(str(metacritic))}/100"
        )

    tags = _value(g, "tags")

    if tags:
        parts.extend([
            "",
            f"🏷 <b>Etiquetas:</b> {escape(str(tags))}",
        ])

    minimum = _value(g, "minimum")
    recommended = _value(g, "recommended")

    if minimum:
        parts.extend([
            "",
            "🖥 <b>REQUISITOS MÍNIMOS</b>",
            escape(str(minimum).strip()),
        ])

    if recommended:
        parts.extend([
            "",
            "🖥 <b>REQUISITOS RECOMENDADOS</b>",
            escape(str(recommended).strip()),
        ])

    return "\n".join(parts)


# ============================================================
# BOTONES DE TELEGRAM
# ============================================================


def build_keyboard(g):
    game_name = str(_value(g, "name", "Videojuego"))

    # Chat privado con mensaje preparado.
    private_message = "Quiero el juego completo y gratis listo para descargar."

    access_url = (
        "https://t.me/Jhonscompany?text="
        + quote(private_message)
    )

    share_url = "https://t.me/share/url?" + urlencode({
        "url": access_url,
        "text": f"🎮 {game_name}",
    })

    buttons = [
        InlineKeyboardButton(
            "🎮 VER JUEGO",
            url=access_url,
        ),
        InlineKeyboardButton(
            "📤 COMPARTIR",
            url=share_url,
        ),
    ]

    return InlineKeyboardMarkup([buttons])



# ============================================================
# DESCARGA DE IMÁGENES
# ============================================================

def download_image(image_url):
    """Descarga una imagen en memoria, sin guardar archivos."""

    if not image_url:
        return None

    try:
        response = requests.get(
            image_url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 PC-Game-Catalog"
            },
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if not content_type.startswith("image/"):
            log.warning(
                "El proveedor no devolvió una imagen válida: %s",
                content_type,
            )
            return None

        return response.content

    except requests.RequestException as error:
        log.warning(
            "No se pudo descargar la imagen: %s",
            error,
        )
        return None


# ============================================================
# PUBLICACIÓN EN TELEGRAM
# ============================================================

async def publish(bot):
    g = database.next_game()

    if not g:
        log.info("No hay videojuegos pendientes.")
        return False

    game_id = int(g["game_id"])
    rawg_id = _value(g, "rawg_id", None)

    game_name = _value(g, "name", "Videojuego")
    image_url = _value(g, "image")

    text = build_post(g)
    messages = split_message(text)
    keyboard = build_keyboard(g)

    try:
        photo_sent = False

        # Descargar imagen
        image_data = download_image(image_url)

        # ----------------------------------------------------
        # IMAGEN + FICHA EN UNA SOLA PUBLICACIÓN
        # ----------------------------------------------------

        if image_data and len(text) <= TELEGRAM_CAPTION_LIMIT:
            try:
                await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_data,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

                photo_sent = True

            except TelegramError as error:
                log.warning(
                    "No se pudo publicar la imagen con texto: %s",
                    error,
                )

        # ----------------------------------------------------
        # IMAGEN CON TÍTULO Y FICHA EN MENSAJES SEPARADOS
        # ----------------------------------------------------

        elif image_data:
            try:
                await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_data,
                    caption=f"🎮 <b>{escape(str(game_name))}</b>",
                    parse_mode="HTML",
                )

                photo_sent = True

            except TelegramError as error:
                log.warning(
                    "No se pudo enviar la imagen de %s: %s",
                    game_name,
                    error,
                )

        # ----------------------------------------------------
        # PUBLICACIÓN DEL TEXTO COMPLETO
        # ----------------------------------------------------

        if not (photo_sent and len(text) <= TELEGRAM_CAPTION_LIMIT):

            for index, message in enumerate(messages):
                current_keyboard = keyboard if index == 0 else None

                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=current_keyboard,
                    disable_web_page_preview=True,
                )

        # ----------------------------------------------------
        # MARCAR COMO PUBLICADO MEDIANTE game_id
        # ----------------------------------------------------

        timestamp = datetime.now(TZ).isoformat(timespec="seconds")

        database.mark_published_by_game_id(
            game_id,
            timestamp,
        )

        log.info(
            "Publicado %s (game_id %s, RAWG ID %s). "
            "Imagen enviada: %s. Mensajes de texto: %s.",
            game_name,
            game_id,
            rawg_id if rawg_id is not None else "No disponible",
            photo_sent,
            0 if photo_sent and len(text) <= TELEGRAM_CAPTION_LIMIT
            else len(messages),
        )

        return True

    except RetryAfter as error:
        log.warning(
            "Telegram solicita esperar %s segundos.",
            error.retry_after,
        )
        return False

    except (TimedOut, NetworkError) as error:
        log.warning(
            "Error temporal de red al publicar %s: %s",
            game_name,
            error,
        )
        return False

    except TelegramError as error:
        log.error(
            "Telegram rechazó la publicación game_id %s: %s",
            game_id,
            error,
        )
        return False

    except Exception:
        log.exception(
            "Error inesperado al publicar game_id %s (%s).",
            game_id,
            game_name,
        )
        return False


# ============================================================
# PROGRAMACIÓN DE PUBLICACIONES
# ============================================================

def next_time(now=None):
    now = now or datetime.now(TZ)

    day = now.date().isoformat()
    tomorrow = now.date() + timedelta(days=1)

    # Límite diario o fin del horario de publicación.
    if (
        database.published_today(day) >= PUBLICATIONS_PER_DAY
        or now.hour >= PUBLISH_END_HOUR
    ):
        return datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            PUBLISH_START_HOUR,
            tzinfo=TZ,
        )

    start = datetime(
        now.year,
        now.month,
        now.day,
        PUBLISH_START_HOUR,
        tzinfo=TZ,
    )

    if now < start:
        return start

    # La nueva función last_published() no recibe argumentos.
    last = database.last_published()

    if last:
        try:
            last_datetime = datetime.fromisoformat(last)

            if last_datetime.tzinfo is None:
                last_datetime = last_datetime.replace(tzinfo=TZ)

            # Solo considerar la última publicación del día actual.
            if last_datetime.date() == now.date():
                return max(
                    now,
                    last_datetime + timedelta(
                        minutes=PUBLISH_INTERVAL_MINUTES
                    ),
                )

        except (TypeError, ValueError):
            log.warning(
                "No se pudo interpretar la fecha de publicación: %s",
                last,
            )

    return now
