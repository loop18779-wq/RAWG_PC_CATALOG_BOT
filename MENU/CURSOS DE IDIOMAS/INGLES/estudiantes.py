
import logging
import os
import sqlite3
from pathlib import Path
from importlib import import_module
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

log = logging.getLogger(__name__)
publicity_module = import_module(
    "MENU.CURSOS DE IDIOMAS.PUBLICIDAD.verificacion"
)

check_publicity_access = publicity_module.check_access
VerificationError = publicity_module.VerificationError
# Mantener la base de datos actual del registro.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "ingles_catalog.db"

LEVEL_NAMES = {
    1: "BÁSICO",
    2: "INTERMEDIO",
    3: "AVANZADO",
}


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def get_lessons(level):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT class_code, lesson_number
            FROM lessons
            WHERE level = ?
            ORDER BY lesson_number ASC
            """,
            (level,)
        ).fetchall()


def get_lesson(class_code):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT class_code, level, lesson_number,
                   storage_chat_id, storage_message_id
            FROM lessons
            WHERE class_code = ?
            LIMIT 1
            """,
            (class_code,)
        ).fetchone()


def levels_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📗 Básico",
                callback_data="english_level_1"
            )
        ],
        [
            InlineKeyboardButton(
                "📘 Intermedio",
                callback_data="english_level_2"
            )
        ],
        [
            InlineKeyboardButton(
                "📕 Avanzado",
                callback_data="english_level_3"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Menú principal",
                callback_data="main_home"
            )
        ],
    ])


async def show_levels(query):
    await query.edit_message_text(
        "🇬🇧 CURSO DE INGLÉS\n\n"
        "Selecciona el nivel que deseas estudiar:",
        reply_markup=levels_keyboard()
    )

async def send_navigation_menu(bot, user_id):
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "📚 CURSO DE INGLÉS\n\n"
                "¿Qué nivel deseas continuar estudiando?"
            ),
            reply_markup=levels_keyboard()
        )

    except TelegramError:
        log.exception(
            "No se pudo mostrar el menú de navegación al usuario %s",
            user_id
        )
async def show_blocks(query, level):
    if level not in LEVEL_NAMES:
        await query.answer("Nivel no válido.", show_alert=True)
        return

    lessons = get_lessons(level)

    if not lessons:
        await query.edit_message_text(
            f"📚 INGLÉS — {LEVEL_NAMES[level]}\n\n"
            "Todavía no hay unidades disponibles.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Volver a niveles",
                        callback_data="languages_english"
                    )
                ]
            ])
        )
        return

    blocks = {}

    for lesson in lessons:
        number = int(lesson["lesson_number"])
        unit_number = (number - 1) // 20 + 1
        blocks[unit_number] = blocks.get(unit_number, 0) + 1

    buttons = []

    for unit_number, count in sorted(blocks.items()):
        buttons.append([
            InlineKeyboardButton(
                f"📚 Unidad {unit_number} · {count} lecciones",
                callback_data=f"english_block_{level}_{unit_number}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Volver a niveles",
            callback_data="languages_english"
        )
    ])

    await query.edit_message_text(
        f"🇬🇧 INGLÉS — {LEVEL_NAMES[level]}\n\n"
        f"📖 {len(lessons)} lecciones disponibles\n\n"
        "Selecciona una unidad:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_block(query, level, block_number):
    if level not in LEVEL_NAMES or block_number < 1:
        await query.answer("Selección no válida.", show_alert=True)
        return

    start = (block_number - 1) * 20 + 1
    end = block_number * 20

    with get_connection() as connection:
        lessons = connection.execute(
            """
            SELECT class_code, lesson_number
            FROM lessons
            WHERE level = ?
              AND lesson_number BETWEEN ? AND ?
            ORDER BY lesson_number ASC
            """,
            (level, start, end)
        ).fetchall()

    if not lessons:
        await query.answer(
            "No hay lecciones disponibles.",
            show_alert=True
        )
        return

    buttons = []

    for lesson in lessons:
        number = int(lesson["lesson_number"])

        buttons.append([
            InlineKeyboardButton(
                f"🎬 Lección {number}",
                callback_data=f"english_class_{lesson['class_code']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Volver a unidades",
            callback_data=f"english_level_{level}"
        )
    ])

    await query.edit_message_text(
        f"🇬🇧 INGLÉS — {LEVEL_NAMES[level]}\n\n"
        f"📚 UNIDAD {block_number}\n"
        f"Lecciones {start}–{end}\n\n"
        "Selecciona la lección que deseas estudiar:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def advertising_keyboard(group, class_code):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Unirme al grupo o canal",
                url=group["invite_url"]
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Verificar y continuar",
                callback_data=f"pubv|{class_code}"
            )
        ]
    ])


async def show_advertisement(query, class_code, group):
    message_text = (
        "📢 PARA CONTINUAR CON TU CURSO\n\n"
        "Debes unirte al siguiente grupo o canal:\n\n"
        f"📌 {group['title']}\n\n"
        "1. Pulsa el botón para unirte.\n"
        "2. Una vez dentro, vuelve aquí.\n"
        "3. Pulsa «Verificar y continuar».\n\n"
        "Comprobaremos tu membresía automáticamente."
    )

    try:
        await query.edit_message_text(
            message_text,
            reply_markup=advertising_keyboard(
                group,
                class_code
            )
        )

    except BadRequest as error:
        if "Message is not modified" not in str(error):
            raise

        await query.message.reply_text(
            "⚠️ Todavía no detectamos que pertenezcas "
            "al grupo o canal indicado.\n\n"
            "Únete primero y vuelve a pulsar "
            "«Verificar y continuar»."
        )
async def send_lesson(query, context, class_code):

    lesson = get_lesson(class_code)

    if not lesson:
        await query.answer(
            "Esta clase no está disponible.",
            show_alert=True
        )
        return

    storage_chat_id = lesson["storage_chat_id"]
    message_id = lesson["storage_message_id"]

    if not storage_chat_id or not message_id:
        await query.answer(
            "No se encontró el vídeo almacenado.",
            show_alert=True
        )
        return

    lesson_number = int(lesson["lesson_number"])

    # PUBLICIDAD: comprobar las lecciones pares.
    if lesson_number % 2 == 0:

        try:
            result = await check_publicity_access(
                context.bot,
                query.from_user.id
            )

        except VerificationError:

            log.exception(
                "No se pudo verificar la publicidad "
                "para el usuario %s.",
                query.from_user.id
            )

            await query.answer(
                "No podemos verificar tu membresía ahora. "
                "Inténtalo más tarde.",
                show_alert=True
            )
            return

        if not result["allowed"]:

            group = result["pending"]

            await query.answer()

            await show_advertisement(
                query,
                class_code,
                group
            )

            return

    # Si no necesita publicidad o ya cumple todos los requisitos,
    # entregar directamente el vídeo.
    await query.answer("Enviando tu clase...")

    try:
        await context.bot.copy_message(
            chat_id=query.from_user.id,
            from_chat_id=int(storage_chat_id),
            message_id=int(message_id)
        )

        log.info(
            "Clase %s enviada al usuario %s",
            class_code,
            query.from_user.id
        )
        await send_navigation_menu(
            context.bot,
            query.from_user.id
        )

    except TelegramError:

        log.exception(
            "Error enviando la clase %s al usuario %s",
            class_code,
            query.from_user.id
        )

        await query.message.reply_text(
            "No ha sido posible enviar esta clase. "
            "Inténtalo más tarde."
        )
async def verify_ad_callback(update, context):

    query = update.callback_query

    class_code = query.data.split("|", 1)[1]

    lesson = get_lesson(class_code)

    if not lesson:
        await query.answer(
            "Esta clase ya no está disponible.",
            show_alert=True
        )
        return

    lesson_number = int(lesson["lesson_number"])

    if lesson_number % 2 != 0:
        await query.answer(
            "Esta clase no requiere verificación.",
            show_alert=True
        )
        return

    await query.answer("Comprobando tu membresía...")

    try:
        result = await check_publicity_access(
            context.bot,
            query.from_user.id
        )

    except VerificationError:

        log.exception(
            "Error verificando publicidad del usuario %s.",
            query.from_user.id
        )

        await query.edit_message_text(
            "No ha sido posible comprobar tu membresía.\n\n"
            "Inténtalo de nuevo más tarde."
        )
        return

    # Todavía quedan grupos pendientes.
    if not result["allowed"]:

        await show_advertisement(
            query,
            class_code,
            result["pending"]
        )

        return

    # Todos los grupos están superados.
    await query.edit_message_text(
        "✅ VERIFICACIÓN COMPLETADA\n\n"
        "Tu acceso ha sido autorizado.\n"
        "Estamos preparando tu lección..."
    )

    try:
        await context.bot.copy_message(
            chat_id=query.from_user.id,
            from_chat_id=int(lesson["storage_chat_id"]),
            message_id=int(lesson["storage_message_id"])
        )

        log.info(
            "Publicidad superada. Clase %s entregada a %s.",
            class_code,
            query.from_user.id
        )
        await send_navigation_menu(
            context.bot,
            query.from_user.id
        )

    except TelegramError:

        log.exception(
            "No se pudo entregar la clase %s tras verificar.",
            class_code
        )

        await query.message.reply_text(
            "La verificación ha sido correcta, "
            "pero no se pudo enviar el vídeo. "
            "Inténtalo de nuevo."
        )
async def english_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if query.message.chat.type != "private":
        await query.answer()
        return

    data = query.data
    if data.startswith("pubv|"):
        await verify_ad_callback(update, context)
        return
    try:
        if data == "languages_english":
            await query.answer()
            await show_levels(query)

        elif data.startswith("english_level_"):
            level = int(data.rsplit("_", 1)[1])
            await query.answer()
            await show_blocks(query, level)


        elif data.startswith("english_block_"):

            _, _, level, block_number = data.split("_")
            await query.answer()
            await show_block(
                query,
                int(level),
                int(block_number)
            )

        elif data.startswith("english_class_"):
            class_code = data.replace("english_class_", "", 1)
            await send_lesson(query, context, class_code)

    except (ValueError, sqlite3.Error):
        log.exception("Error procesando el menú de inglés")
        await query.answer(
            "Ha ocurrido un error consultando las clases.",
            show_alert=True
        )


def register_english_menu_handlers(application: Application):
    application.add_handler(
        CallbackQueryHandler(
            english_router,
            pattern=(
                r"^(languages_english|"
                r"english_level_[123]|"
                r"english_block_[123]_[0-9]+|"
                r"english_class_AI_[123]_[0-9]{3}|"
                r"pubv\|AI_[123]_[0-9]{3})$"
            )
        )
    )
