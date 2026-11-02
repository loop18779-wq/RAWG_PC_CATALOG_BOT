
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import database
import rawg_catalog
from publisher import publish, next_time
from config import (
    BOT_TOKEN,
    TIMEZONE,
    RAWG_FETCH_INTERVAL_SECONDS,
    CHANNEL_ID,
    ADMIN_SETUP_CODE,
)

# --------------------------------------------------
# CONFIGURACIÓN GENERAL
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
(ROOT / "logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(
            ROOT / "logs" / "bot.log",
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

log = logging.getLogger("rawg_catalog")
TZ = ZoneInfo(TIMEZONE)


# --------------------------------------------------
# COMPROBACIÓN DE CHAT PRIVADO
# --------------------------------------------------

def is_private(update):
    return (
        update.effective_chat is not None
        and update.effective_chat.type == "private"
    )


# --------------------------------------------------
# COMANDO /START
# --------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_private(update):
        return

    uid = update.effective_user.id
    admin = database.setting("admin_chat_id")

    if admin and admin != str(uid):
        await update.message.reply_text(
            "Este bot ya tiene configurado otro administrador."
        )
        return

    if not admin:

        supplied = context.args[0] if context.args else ""

        if not supplied or supplied != ADMIN_SETUP_CODE:
            await update.message.reply_text(
                "Para vincular este chat como administrador, "
                "ejecuta /start seguido del código "
                "ADMIN_SETUP_CODE configurado en el archivo .env."
            )
            return

        database.set_setting("admin_chat_id", str(uid))

    await update.message.reply_text(
        "¡Bot conectado! Este chat recibirá los avisos privados "
        "de catálogo agotado.\n\n"
        "Comandos disponibles:\n"
        "/estado — resumen del catálogo\n"
        "/pendientes — lista de juegos e IDs\n"
        "/enlace ID_RAWG URL — asignar enlace al botón de descarga\n\n"
        "Ejemplo:\n"
        "/enlace 3498 https://tu-enlace.example/juego"
    )


# --------------------------------------------------
# CONTROL DE ADMINISTRADOR
# --------------------------------------------------

async def admin_only(update):

    if not is_private(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "Usa este comando en el chat privado del bot."
            )
        return False

    if database.setting("admin_chat_id") != str(update.effective_user.id):
        await update.message.reply_text(
            "Primero configura el chat administrador con /start."
        )
        return False

    return True


# --------------------------------------------------
# COMANDO /ESTADO
# --------------------------------------------------

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    s = database.stats()

    await update.message.reply_text(
        f"📊 Catálogo RAWG\n\n"
        f"Total: {s['total']}\n"
        f"Pendientes: {s['pending']}\n"
        f"Publicados: {s['published']}\n\n"
        f"Canal configurado: {CHANNEL_ID}"
    )


# --------------------------------------------------
# COMANDO /PENDIENTES
# --------------------------------------------------

async def pending_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    games = database.pending_games(20)

    if not games:
        await update.message.reply_text(
            "No hay juegos pendientes en este momento."
        )
        return

    lines = [
        "🎮 Próximos juegos pendientes (ID para /enlace):"
    ]

    lines.extend(
        f"{g['rawg_id']} — {g['name']}"
        for g in games
    )

    lines.append(
        "\nEjemplo: /enlace ID https://tu-enlace.example"
    )

    await update.message.reply_text("\n".join(lines))


# --------------------------------------------------
# COMANDO /ENLACE
# --------------------------------------------------

async def link_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Formato: /enlace ID_RAWG URL\n"
            "Ejemplo: /enlace 3498 https://tu-enlace.example/juego"
        )
        return

    try:
        rawg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "El ID de RAWG debe ser un número."
        )
        return

    url = context.args[1].strip()
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        await update.message.reply_text(
            "El enlace debe comenzar por https:// o http:// "
            "y ser una URL válida."
        )
        return

    game = database.find_game(rawg_id)

    if not game:
        await update.message.reply_text(
            f"No encuentro el juego con ID RAWG {rawg_id}. "
            "Consulta /estado o revisa el ID."
        )
        return

    database.set_download_link(rawg_id, url)

    await update.message.reply_text(
        f"Enlace guardado para: {game['name']} "
        f"(ID {rawg_id}). El botón aparecerá si todavía no se ha publicado."
    )


# --------------------------------------------------
# ENRIQUECIMIENTO ANTES DE PUBLICAR
# --------------------------------------------------

def enrich_game_if_needed(game):
    """
    Comprueba si el siguiente videojuego tiene su ficha detallada.

    Si todavía no se ha consultado RAWG, recupera sus datos,
    los guarda en SQLite y marca la ficha como revisada.

    Devuelve True cuando el juego puede pasar a publicación.
    """

    rawg_id = int(game["rawg_id"])

    # Ya se ha consultado anteriormente.
    if game["details_checked_at"]:
        return True

    log.info(
        "Ficha pendiente de enriquecer: %s (RAWG ID %s).",
        game["name"],
        rawg_id
    )

    try:
        details = rawg_catalog.fetch_game_details(rawg_id)

        if not details:
            log.warning(
                "RAWG no devolvió detalles para %s (ID %s). "
                "Se aplaza su publicación.",
                game["name"],
                rawg_id
            )
            return False

        details["id"] = details.get("id") or rawg_id
        details["name"] = details.get("name") or game["name"]

        normalized = rawg_catalog.normalize_game(details)

        if not normalized.get("id") or not normalized.get("name"):
            log.warning(
                "Ficha RAWG incompleta para ID %s. "
                "Se aplaza la publicación.",
                rawg_id
            )
            return False

        database.add_games([normalized])

        database.mark_details_checked(rawg_id)

        log.info(
            "Ficha enriquecida correctamente: %s (ID %s).",
            game["name"],
            rawg_id
        )

        return True

    except Exception:
        log.exception(
            "Error enriqueciendo %s (RAWG ID %s).",
            game["name"],
            rawg_id
        )
        return False


# --------------------------------------------------
# AVISO DE CATÁLOGO AGOTADO
# --------------------------------------------------

async def notify_exhausted(app):

    admin = database.setting("admin_chat_id")

    if not admin:
        return

    if database.setting("exhaustion_notified") == "1":
        return

    s = database.stats()

    if (
        s["total"] == 0
        or s["pending"] > 0
        or s["published"] == 0
    ):
        return

    await app.bot.send_message(
        chat_id=int(admin),
        text=(
            "⚠️ CATÁLOGO AGOTADO\n\n"
            "Se han publicado todos los juegos que había pendientes. "
            "Las publicaciones quedan pausadas y no se repetirán juegos.\n\n"
            "Seguiré consultando RAWG para detectar nuevos títulos "
            "compatibles con PC/Windows. Cuando entren juegos nuevos, "
            "reanudaré las publicaciones automáticamente."
        )
    )

    database.set_setting("exhaustion_notified", "1")

    log.info("Aviso privado de catálogo agotado enviado.")


# --------------------------------------------------
# PLANIFICADOR PRINCIPAL
# --------------------------------------------------

async def scheduler(app):

    log.info("Tarea de publicaciones iniciada.")

    while True:

        try:

            # Consultar RAWG cuando corresponda.
            added = await asyncio.to_thread(
                rawg_catalog.refresh_if_needed,
                RAWG_FETCH_INTERVAL_SECONDS
            )

            if added:

                database.set_setting(
                    "exhaustion_notified",
                    "0"
                )

                log.info(
                    "Se han incorporado %s juegos nuevos.",
                    added
                )

            pending = database.pending_count()

            if pending == 0:

                await notify_exhausted(app)

            else:

                now = datetime.now(TZ)
                scheduled_time = next_time(now)

                if now >= scheduled_time:

                    log.info(
                        "Hora de publicación alcanzada. "
                        "Juegos pendientes: %s",
                        pending
                    )

                    # Obtener el juego que se publicaría a continuación.
                    game = database.next_game()

                    if not game:
                        await asyncio.sleep(10)
                        continue

                    # Comprobar y enriquecer antes de publicar.
                    ready = await asyncio.to_thread(
                        enrich_game_if_needed,
                        game
                    )

                    if not ready:
                        log.warning(
                            "Publicación aplazada para %s. "
                            "Se volverá a comprobar más tarde.",
                            game["name"]
                        )

                        await asyncio.sleep(60)
                        continue

                    # Solo llega aquí si la ficha está revisada.
                    await publish(app.bot)

                    if database.pending_count() == 0:
                        await notify_exhausted(app)

        except asyncio.CancelledError:

            log.info(
                "Cancelación solicitada. Cerrando planificador."
            )

            raise

        except Exception:

            log.exception(
                "Error del programador. "
                "Se reintentará en el siguiente ciclo."
            )

        await asyncio.sleep(10)


# --------------------------------------------------
# INICIO DEL PLANIFICADOR
# --------------------------------------------------

async def post_init(app):

    log.info("Inicializando planificador.")

    task = asyncio.create_task(
        scheduler(app),
        name="catalog-scheduler"
    )

    app.bot_data["scheduler_task"] = task


# --------------------------------------------------
# CIERRE ORDENADO DEL PLANIFICADOR
# --------------------------------------------------

async def post_stop(app):

    task = app.bot_data.get("scheduler_task")

    if task is None:
        return

    if not task.done():

        log.info("Solicitando cierre del planificador.")

        task.cancel()

        await asyncio.gather(
            task,
            return_exceptions=True
        )

    log.info("Planificador cerrado correctamente.")


# --------------------------------------------------
# FUNCIÓN PRINCIPAL
# --------------------------------------------------

def main():

    database.init()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("estado", status))
    app.add_handler(CommandHandler("pendientes", pending_command))
    app.add_handler(CommandHandler("enlace", link_command))

    log.info(
        "Arrancando bot. Canal destino configurado: %s",
        CHANNEL_ID
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# --------------------------------------------------
# EJECUCIÓN
# --------------------------------------------------

if __name__ == "__main__":
    main()
