
import asyncio
import logging
from MENU import register_menu_handlers
from pathlib import Path
from MENU.menu_principal import show_main_menu
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from importlib import import_module

english_module = import_module(
    "MENU.CURSOS DE IDIOMAS.INGLES.registro"
)

register_english_storage_handlers = (
    english_module.register_english_storage_handlers
)
publicity_module = import_module(
    "MENU.CURSOS DE IDIOMAS.PUBLICIDAD.router"
)

register_publicity_handlers = (
    publicity_module.register_publicity_handlers
)
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import (
    BOT_TOKEN,
    TIMEZONE,
    RAWG_FETCH_INTERVAL_SECONDS,
    CHANNEL_ID,
    ADMIN_SETUP_CODE,
)
import database_nueva as database
import rawg_catalog
import igdb_catalog

from publisher import publish, next_time




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

log = logging.getLogger("pc_game_catalog")

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


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_private(update):
        return

    uid = update.effective_user.id
    admin = database.setting("admin_chat_id")

    # USUARIO NORMAL: acceso al menú sin permisos administrativos.
    if admin and admin != str(uid):
        await show_main_menu(update, context)
        return

    # PRIMERA CONFIGURACIÓN DEL ADMINISTRADOR.
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

    # ADMINISTRADOR.
    await update.message.reply_text(
        "¡Bot conectado como administrador!\n\n"
        "Tienes acceso al menú principal y a las funciones "
        "administrativas.\n\n"
        "Comandos administrativos:\n"
        "/estado — resumen del catálogo\n"
        "/pendientes — lista de juegos e identificadores\n"
        "/enlace GAME_ID URL — asignar enlace a un videojuego\n"
        "/menu — abrir el menú principal"
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

    if database.setting("admin_chat_id") != str(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "Primero configura el chat administrador con /start."
        )

        return False

    return True


# --------------------------------------------------
# COMANDO /ESTADO
# --------------------------------------------------

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    s = database.stats()

    await update.message.reply_text(
        "📊 CATÁLOGO DE VIDEOJUEGOS\n\n"
        f"Total: {s['total']}\n"
        f"Pendientes: {s['pending']}\n"
        f"Publicados: {s['published']}\n\n"
        f"Canal configurado: {CHANNEL_ID}\n\n"
        "Base de datos: catálogo unificado"
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
        "🎮 PRÓXIMOS JUEGOS PENDIENTES",
        "",
        "El primer número es el game_id interno."
    ]

    for g in games:

        identifiers = []

        if g["rawg_id"] is not None:
            identifiers.append(f"RAWG: {g['rawg_id']}")

        if g["igdb_id"] is not None:
            identifiers.append(f"IGDB: {g['igdb_id']}")

        if g["steam_app_id"] is not None:
            identifiers.append(f"Steam: {g['steam_app_id']}")

        source_text = (
            " | ".join(identifiers)
            if identifiers
            else "Sin identificador externo"
        )

        lines.append(
            f"\n{g['game_id']} — {g['name']}\n"
            f"   {source_text}"
        )

    lines.append(
        "\nPara asignar un enlace:\n"
        "/enlace GAME_ID URL"
    )

    await update.message.reply_text(
        "\n".join(lines)
    )


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
            "Formato:\n"
            "/enlace GAME_ID URL\n\n"
            "Ejemplo:\n"
            "/enlace 10001 https://store.steampowered.com/"
        )

        return

    try:
        game_id = int(context.args[0])

    except ValueError:

        await update.message.reply_text(
            "El GAME_ID debe ser un número."
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

    game = database.find_game_by_game_id(game_id)

    if not game:

        await update.message.reply_text(
            f"No encuentro ningún videojuego con game_id {game_id}."
        )

        return

    database.set_download_link_by_game_id(
        game_id,
        url
    )

    await update.message.reply_text(
        f"Enlace guardado correctamente.\n\n"
        f"Juego: {game['name']}\n"
        f"GAME_ID: {game_id}\n\n"
        "El botón utilizará este enlace cuando se publique."
    )


# --------------------------------------------------
# ENRIQUECIMIENTO DE VIDEOJUEGOS
# --------------------------------------------------

def enrich_game_if_needed(game):
    """
    Enriquece los registros RAWG cuando sea posible.

    Los juegos procedentes exclusivamente de IGDB o Steam
    no necesitan tener rawg_id para poder publicarse.
    """

    rawg_id = game["rawg_id"]

    # Un juego sin RAWG puede publicarse con los datos disponibles.
    if rawg_id is None:

        log.info(
            "Juego independiente de RAWG: %s (game_id %s).",
            game["name"],
            game["game_id"]
        )

        return True

    rawg_id = int(rawg_id)

    # La ficha ya fue consultada anteriormente.
    if game["details_checked_at"]:
        return True

    log.info(
        "Ficha RAWG pendiente: %s (RAWG ID %s).",
        game["name"],
        rawg_id
    )

    try:

        details = rawg_catalog.fetch_game_details(rawg_id)

        if not details:

            log.warning(
                "RAWG no devolvió detalles para %s. "
                "Se publicará con la información disponible.",
                game["name"]
            )

            return True

        details["id"] = details.get("id") or rawg_id

        details["name"] = (
            details.get("name")
            or game["name"]
        )

        normalized = rawg_catalog.normalize_game(details)

        if not normalized.get("id") or not normalized.get("name"):

            log.warning(
                "Ficha RAWG incompleta para %s. "
                "Se utilizará la información existente.",
                game["name"]
            )

            return True

        database.add_games([normalized])

        database.mark_details_checked(rawg_id)

        log.info(
            "Ficha RAWG enriquecida: %s (ID %s).",
            game["name"],
            rawg_id
        )

        return True

    except Exception:

        log.exception(
            "Error enriqueciendo %s (RAWG ID %s). "
            "Se continuará con los datos disponibles.",
            game["name"],
            rawg_id
        )

        return True


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

    if s["total"] == 0 or s["pending"] > 0:
        return

    if s["future"] > 0 or s["without_date"] > 0:

        message = (
            "ℹ️ SIN JUEGOS PUBLICABLES ACTUALMENTE\n\n"
            f"Juegos publicados: {s['published']}\n"
            f"Juegos futuros: {s['future']}\n"
            f"Juegos sin fecha válida: {s['without_date']}\n\n"
            "Las publicaciones quedan pausadas temporalmente. "
            "El sistema continuará comprobando las fechas de "
            "lanzamiento y las fuentes de catálogo configuradas. "
            "Los juegos futuros podrán publicarse automáticamente "
            "cuando llegue su fecha de lanzamiento."
        )

    else:

        message = (
            "⚠️ CATÁLOGO AGOTADO\n\n"
            "Se han publicado todos los videojuegos disponibles.\n\n"
            "El sistema continuará comprobando las fuentes "
            "de catálogo configuradas. Cuando se incorporen "
            "nuevos videojuegos compatibles con PC/Windows, "
            "las publicaciones podrán reanudarse automáticamente."
        )

    await app.bot.send_message(
        chat_id=int(admin),
        text=message
    )

    database.set_setting(
        "exhaustion_notified",
        "1"
    )

    log.info("Aviso de estado del catálogo enviado.")
# --------------------------------------------------
# --------------------------------------------------
# CONSULTA AUTOMÁTICA DE IGDB
# --------------------------------------------------

async def refresh_igdb():

    now = datetime.now(TZ)

    # Evitar repetir consultas si IGDB ha fallado.
    last_attempt = database.setting("igdb_last_attempt")

    if last_attempt:
        try:
            last_dt = datetime.fromisoformat(last_attempt)

            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=TZ)

            if (now - last_dt).total_seconds() < 900:
                return 0

        except (ValueError, TypeError):
            pass

    # Consultar IGDB como máximo una vez cada 24 horas.
    last_success = database.setting("igdb_last_check")

    if last_success:
        try:
            last_dt = datetime.fromisoformat(last_success)

            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=TZ)

            if (now - last_dt).total_seconds() < 86400:
                return 0

        except (ValueError, TypeError):
            pass

    database.set_setting(
        "igdb_last_attempt",
        now.isoformat()
    )

    try:

        before = database.stats()["total"]

        log.info("Iniciando actualización del catálogo IGDB.")

        await asyncio.to_thread(
            igdb_catalog.import_catalog
        )

        after = database.stats()["total"]

        database.set_setting(
            "igdb_last_check",
            datetime.now(TZ).isoformat()
        )

        added = max(0, after - before)

        if added:

            database.set_setting(
                "exhaustion_notified",
                "0"
            )

        log.info(
            "Actualización IGDB finalizada. Nuevos registros: %s",
            added
        )

        return added

    except Exception:

        log.exception(
            "Error consultando IGDB. "
            "Se reintentará posteriormente."
        )

        return 0
# CONSULTA DE RAWG
# --------------------------------------------------

async def refresh_rawg():

    try:

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
                "RAWG ha incorporado %s videojuegos.",
                added
            )

        return added or 0

    except Exception:

        log.exception(
            "Error consultando RAWG. "
            "El planificador continuará funcionando."
        )

        return 0


# --------------------------------------------------
# PLANIFICADOR PRINCIPAL
# --------------------------------------------------

async def scheduler(app):

    log.info("Planificador de publicaciones iniciado.")

    while True:

        try:

            # Consultar RAWG de manera independiente.
            # Un error de RAWG no detiene las publicaciones.

            await refresh_igdb()

            await refresh_rawg()

            pending = database.pending_count()

            if pending == 0:

                await notify_exhausted(app)

            else:

                # Hay juegos publicables: permitir futuros avisos.
                if database.setting("exhaustion_notified") == "1":
                    database.set_setting(
                        "exhaustion_notified",
                        "0"
                    )

                now = datetime.now(TZ)

                scheduled_time = next_time(now)

                if now >= scheduled_time:

                    log.info(
                        "Hora de publicación alcanzada. "
                        "Pendientes: %s",
                        pending
                    )

                    game = database.next_game()

                    if not game:

                        await asyncio.sleep(10)
                        continue

                    ready = await asyncio.to_thread(
                        enrich_game_if_needed,
                        game
                    )

                    if not ready:

                        await asyncio.sleep(30)
                        continue

                    published = await publish(app.bot)

                    if published:

                        log.info(
                            "Publicación completada: %s "
                            "(game_id %s).",
                            game["name"],
                            game["game_id"]
                        )

                        if database.pending_count() == 0:
                            await notify_exhausted(app)

                    else:

                        log.warning(
                            "No se pudo completar la publicación "
                            "de %s. Se reintentará posteriormente.",
                            game["name"]
                        )

                        await asyncio.sleep(60)

        except asyncio.CancelledError:

            log.info(
                "Cancelación solicitada. Cerrando planificador."
            )

            raise

        except Exception:

            log.exception(
                "Error del planificador. "
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
    # Registrar el sistema de publicidad
    register_publicity_handlers(app)

    # Registrar el almacenamiento del curso de inglés
    register_english_storage_handlers(app)

    # Registrar los menús principales
    register_menu_handlers(app)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("estado", status))
    app.add_handler(CommandHandler("pendientes", pending_command))
    app.add_handler(CommandHandler("enlace", link_command))

    log.info(
        "Arrancando catálogo de videojuegos. Canal: %s",
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
