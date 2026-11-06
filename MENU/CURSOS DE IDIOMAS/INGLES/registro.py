
import logging
import os
import re
import sqlite3

from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

from dotenv import load_dotenv

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update
)

from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)


# =========================================================
# CONFIGURACION
# =========================================================

load_dotenv()

logger = logging.getLogger(__name__)

STORAGE_CHAT_ID = int(os.getenv("ENGLISH_STORAGE_CHAT_ID", "0"))
ADMIN_USER_ID = int(os.getenv("ENGLISH_ADMIN_ID", "0"))

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DB_PATH = PROJECT_ROOT / "data" / "ingles_catalog.db"

CODE_PATTERN = re.compile(
    r"(?<![A-Z0-9])(AI_[123]_\d{3})(?!\d)",
    re.IGNORECASE
)


# =========================================================
# BASE DE DATOS EXCLUSIVA PARA INGLES
# =========================================================

def get_connection():

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


@contextmanager
def database_connection():

    conn = get_connection()

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def init_english_database():

    with database_connection() as conn:

        conn.executescript("""

        CREATE TABLE IF NOT EXISTS lessons (

            class_code TEXT PRIMARY KEY,

            level INTEGER NOT NULL,

            lesson_number INTEGER NOT NULL,

            file_name TEXT NOT NULL,

            file_unique_id TEXT NOT NULL UNIQUE,

            file_id TEXT NOT NULL,

            storage_chat_id INTEGER NOT NULL,

            storage_message_id INTEGER NOT NULL,

            registered_at TEXT NOT NULL,

            updated_at TEXT NOT NULL

        );


        CREATE TABLE IF NOT EXISTS lesson_history (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            class_code TEXT NOT NULL,

            file_name TEXT NOT NULL,

            file_unique_id TEXT NOT NULL,

            file_id TEXT NOT NULL,

            storage_chat_id INTEGER NOT NULL,

            storage_message_id INTEGER NOT NULL,

            archived_at TEXT NOT NULL,

            reason TEXT NOT NULL

        );


        CREATE TABLE IF NOT EXISTS replacement_requests (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            class_code TEXT NOT NULL,

            file_name TEXT NOT NULL,

            file_unique_id TEXT NOT NULL,

            file_id TEXT NOT NULL,

            storage_chat_id INTEGER NOT NULL,

            storage_message_id INTEGER NOT NULL,

            requested_at TEXT NOT NULL,

            status TEXT DEFAULT 'pending',

            reviewed_at TEXT

        );


        CREATE INDEX IF NOT EXISTS idx_lessons_level

        ON lessons(level);


        CREATE INDEX IF NOT EXISTS idx_replacement_status

        ON replacement_requests(status);

        """)


# =========================================================
# UTILIDADES
# =========================================================

def current_time():

    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def extract_media(message):

    # Video enviado como video normal

    if message.video:

        media = message.video

        file_name = media.file_name or ""

        return (
            file_name,
            media.file_unique_id,
            media.file_id
        )


    # Video enviado como documento

    if message.document:

        media = message.document

        file_name = media.file_name or ""

        mime_type = (
            media.mime_type or ""
        ).lower()

        if (
            mime_type.startswith("video/")
            or file_name.lower().endswith(
                (
                    ".mp4",
                    ".mov",
                    ".mkv",
                    ".avi",
                    ".webm",
                    ".mpeg",
                    ".mpg"
                )
            )
        ):

            return (
                file_name,
                media.file_unique_id,
                media.file_id
            )

    return None


def extract_class_code(file_name):

    match = CODE_PATTERN.search(
        Path(file_name).name.upper()
    )

    if not match:
        return None

    code = match.group(1).upper()

    _, level_text, number_text = code.split("_")

    level = int(level_text)

    number = int(number_text)

    if not 1 <= number <= 195:
        return None

    return code, level, number


# =========================================================
# AVISOS PRIVADOS AL ADMINISTRADOR
# =========================================================

async def notify_admin(
    context,
    message,
    keyboard=None
):

    if not ADMIN_USER_ID:

        logger.error(
            "ENGLISH_ADMIN_ID no configurado."
        )

        return False

    try:

        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=message,
            reply_markup=keyboard
        )

        return True

    except Exception:

        logger.exception(
            "No se pudo enviar aviso privado."
        )

        return False


# =========================================================
# REGISTRO AUTOMATICO DE VIDEOS
# =========================================================

async def handle_storage_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    media_data = extract_media(message)

    if not media_data:
        return

    file_name, file_unique_id, file_id = media_data

    parsed = extract_class_code(file_name)

    if not parsed:

        await notify_admin(
            context,

            "⚠️ VIDEO NO IDENTIFICADO\n\n"
            f"Nombre: {file_name or 'Sin nombre'}\n\n"
            "Formato esperado:\n"
            "AI_1_001 hasta AI_1_195\n"
            "AI_2_001 hasta AI_2_195\n"
            "AI_3_001 hasta AI_3_195"
        )

        return

    class_code, level, lesson_number = parsed

    chat_id = message.chat_id

    message_id = message.message_id

    now = current_time()

    init_english_database()

    with database_connection() as conn:

        # -------------------------------------------------
        # COMPROBAR SI EL ARCHIVO YA ESTA REGISTRADO
        # -------------------------------------------------

        same_file = conn.execute(

            """
            SELECT class_code
            FROM lessons
            WHERE file_unique_id = ?
            """,

            (file_unique_id,)

        ).fetchone()


        if same_file and same_file["class_code"] != class_code:

            await notify_admin(

                context,

                "⚠️ ARCHIVO DUPLICADO CON OTRO CODIGO\n\n"

                f"Archivo: {file_name}\n"

                f"Código actual: {class_code}\n"

                f"Código anterior: {same_file['class_code']}\n\n"

                "No se ha modificado ningún registro."

            )

            return


        # -------------------------------------------------
        # BUSCAR CLASE POR CODIGO
        # -------------------------------------------------

        existing = conn.execute(

            """
            SELECT *
            FROM lessons
            WHERE class_code = ?
            """,

            (class_code,)

        ).fetchone()


        # -------------------------------------------------
        # CASO 1: CLASE NUEVA
        # -------------------------------------------------

        if existing is None:

            conn.execute(

                """
                INSERT INTO lessons (

                    class_code,
                    level,
                    lesson_number,
                    file_name,
                    file_unique_id,
                    file_id,
                    storage_chat_id,
                    storage_message_id,
                    registered_at,
                    updated_at

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,

                (
                    class_code,
                    level,
                    lesson_number,
                    file_name,
                    file_unique_id,
                    file_id,
                    chat_id,
                    message_id,
                    now,
                    now
                )

            )

            await notify_admin(

                context,

                "✅ NUEVA CLASE REGISTRADA\n\n"

                f"Código: {class_code}\n"

                f"Archivo: {file_name}\n"

                f"Nivel: {level}\n"

                f"Número de clase: {lesson_number}\n"

                f"Mensaje: {message_id}"

            )

            logger.info(
                "Clase registrada: %s",
                class_code
            )

            return


        # -------------------------------------------------
        # CASO 2: MISMO ARCHIVO SUBIDO OTRA VEZ
        # -------------------------------------------------

        if existing["file_unique_id"] == file_unique_id:

            conn.execute(

                """
                INSERT INTO lesson_history (

                    class_code,
                    file_name,
                    file_unique_id,
                    file_id,
                    storage_chat_id,
                    storage_message_id,
                    archived_at,
                    reason

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,

                (
                    class_code,
                    existing["file_name"],
                    existing["file_unique_id"],
                    existing["file_id"],
                    existing["storage_chat_id"],
                    existing["storage_message_id"],
                    now,
                    "Referencia anterior del mismo archivo"
                )

            )


            conn.execute(

                """
                UPDATE lessons

                SET
                    file_name = ?,
                    file_id = ?,
                    storage_chat_id = ?,
                    storage_message_id = ?,
                    updated_at = ?

                WHERE class_code = ?
                """,

                (
                    file_name,
                    file_id,
                    chat_id,
                    message_id,
                    now,
                    class_code
                )

            )


            await notify_admin(

                context,

                "♻️ VIDEO RECONOCIDO\n\n"

                f"Clase: {class_code}\n\n"

                "El archivo es el mismo según "
                "file_unique_id.\n\n"

                "He actualizado su referencia al "
                "nuevo mensaje de Telegram."

            )

            return


        # -------------------------------------------------
        # CASO 3: MISMO CODIGO, VIDEO DIFERENTE
        # -------------------------------------------------

        pending = conn.execute(

            """
            SELECT id
            FROM replacement_requests

            WHERE
                class_code = ?
                AND file_unique_id = ?
                AND status = 'pending'
            """,

            (
                class_code,
                file_unique_id
            )

        ).fetchone()


        if pending:

            request_id = pending["id"]

        else:

            cursor = conn.execute(

                """
                INSERT INTO replacement_requests (

                    class_code,
                    file_name,
                    file_unique_id,
                    file_id,
                    storage_chat_id,
                    storage_message_id,
                    requested_at,
                    status

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,

                (
                    class_code,
                    file_name,
                    file_unique_id,
                    file_id,
                    chat_id,
                    message_id,
                    now
                )

            )

            request_id = cursor.lastrowid


    keyboard = InlineKeyboardMarkup(

        [[

            InlineKeyboardButton(

                "✅ SUSTITUIR VIDEO",

                callback_data=f"eng_replace:{request_id}"

            ),

            InlineKeyboardButton(

                "❌ CONSERVAR ACTUAL",

                callback_data=f"eng_keep:{request_id}"

            )

        ]]

    )


    await notify_admin(

        context,

        "🔄 SOLICITUD DE SUSTITUCIÓN\n\n"

        f"Clase: {class_code}\n"

        f"Nuevo archivo: {file_name}\n\n"

        "El código ya existe, pero el contenido "
        "del archivo es diferente.\n\n"

        "No se ha sustituido automáticamente.\n\n"

        "Elige qué hacer:",

        keyboard

    )


# =========================================================
# APROBAR O RECHAZAR SUSTITUCIONES
# =========================================================

async def handle_replacement_decision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    if query.from_user.id != ADMIN_USER_ID:

        await query.answer(
            "No tienes autorización.",
            show_alert=True
        )

        return

    await query.answer()

    try:

        action, request_id_text = query.data.split(":", 1)

        request_id = int(request_id_text)

    except (ValueError, AttributeError):

        await query.edit_message_text(
            "Solicitud no válida."
        )

        return

    init_english_database()

    now = current_time()

    with database_connection() as conn:

        request = conn.execute(

            """
            SELECT *
            FROM replacement_requests
            WHERE id = ?
            """,

            (request_id,)

        ).fetchone()


        if not request or request["status"] != "pending":

            await query.edit_message_text(
                "Esta solicitud ya fue revisada o no existe."
            )

            return


        # ---------------------------------------------
        # RECHAZAR
        # ---------------------------------------------

        if action == "eng_keep":

            conn.execute(

                """
                UPDATE replacement_requests

                SET
                    status = 'rejected',
                    reviewed_at = ?

                WHERE id = ?
                """,

                (now, request_id)

            )

            result_text = (

                "❌ SUSTITUCIÓN RECHAZADA\n\n"

                f"Se conserva el vídeo actual de "
                f"{request['class_code']}."

            )


        # ---------------------------------------------
        # APROBAR
        # ---------------------------------------------

        elif action == "eng_replace":

            current = conn.execute(

                """
                SELECT *
                FROM lessons
                WHERE class_code = ?
                """,

                (request["class_code"],)

            ).fetchone()


            if current:

                conn.execute(

                    """
                    INSERT INTO lesson_history (

                        class_code,
                        file_name,
                        file_unique_id,
                        file_id,
                        storage_chat_id,
                        storage_message_id,
                        archived_at,
                        reason

                    )

                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,

                    (
                        current["class_code"],
                        current["file_name"],
                        current["file_unique_id"],
                        current["file_id"],
                        current["storage_chat_id"],
                        current["storage_message_id"],
                        now,
                        "Sustituido por autorización del administrador"
                    )

                )


                conn.execute(

                    """
                    UPDATE lessons

                    SET
                        file_name = ?,
                        file_unique_id = ?,
                        file_id = ?,
                        storage_chat_id = ?,
                        storage_message_id = ?,
                        updated_at = ?

                    WHERE class_code = ?
                    """,

                    (
                        request["file_name"],
                        request["file_unique_id"],
                        request["file_id"],
                        request["storage_chat_id"],
                        request["storage_message_id"],
                        now,
                        request["class_code"]
                    )

                )


            else:

                level = int(
                    request["class_code"].split("_")[1]
                )

                number = int(
                    request["class_code"].split("_")[2]
                )


                conn.execute(

                    """
                    INSERT INTO lessons (

                        class_code,
                        level,
                        lesson_number,
                        file_name,
                        file_unique_id,
                        file_id,
                        storage_chat_id,
                        storage_message_id,
                        registered_at,
                        updated_at

                    )

                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,

                    (
                        request["class_code"],
                        level,
                        number,
                        request["file_name"],
                        request["file_unique_id"],
                        request["file_id"],
                        request["storage_chat_id"],
                        request["storage_message_id"],
                        now,
                        now
                    )

                )


            conn.execute(

                """
                UPDATE replacement_requests

                SET
                    status = 'approved',
                    reviewed_at = ?

                WHERE id = ?
                """,

                (now, request_id)

            )


            result_text = (

                "✅ VIDEO SUSTITUIDO CORRECTAMENTE\n\n"

                f"Clase: {request['class_code']}\n\n"

                "La versión anterior se conserva "
                "en el historial."

            )

        else:

            result_text = "Acción desconocida."


    await query.edit_message_text(
        result_text
    )


# =========================================================
# COMANDO DE COMPROBACION
# =========================================================

async def english_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_USER_ID:
        return

    init_english_database()

    await update.effective_message.reply_text(

        "✅ REGISTRO DE INGLÉS ACTIVO\n\n"

        f"Base de datos:\n{DB_PATH}\n\n"

        f"Grupo configurado:\n{STORAGE_CHAT_ID}\n\n"

        "El sistema está preparado para registrar "
        "las clases del curso."

    )


# =========================================================
# REGISTRAR HANDLERS EN EL BOT PRINCIPAL
# =========================================================

def register_english_storage_handlers(
    application: Application
):

    if not STORAGE_CHAT_ID:

        raise RuntimeError(
            "Falta ENGLISH_STORAGE_CHAT_ID en .env"
        )

    if not ADMIN_USER_ID:

        raise RuntimeError(
            "Falta ENGLISH_ADMIN_ID en .env"
        )

    init_english_database()


    # Recibir vídeos y documentos del grupo privado

    application.add_handler(

        MessageHandler(

            filters.Chat(
                chat_id=STORAGE_CHAT_ID
            )
            & (filters.VIDEO | filters.Document.ALL),

            handle_storage_video

        )

    )


    # Aprobar o rechazar sustituciones

    application.add_handler(

        CallbackQueryHandler(

            handle_replacement_decision,

            pattern=r"^eng_(replace|keep):\d+$"

        )

    )


    # Comando privado de comprobación

    application.add_handler(

        MessageHandler(

            filters.ChatType.PRIVATE
            & filters.COMMAND
            & filters.Regex(r"^/ingles$"),

            english_start

        )

    )


    logger.info(
        "Registro de inglés activado. DB: %s",
        DB_PATH
    )
