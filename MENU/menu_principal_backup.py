
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 Catálogo de videojuegos",
                callback_data="main_games"
            )
        ],
        [
            InlineKeyboardButton(
                "📚 Cursos de idiomas",
                callback_data="main_languages"
            )
        ],
    ])


def languages_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🇬🇧 Inglés",
                callback_data="languages_english"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Volver al menú principal",
                callback_data="main_home"
            )
        ],
    ])


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_chat.type != "private":
        return

    await update.effective_message.reply_text(
        "🏠 MENÚ PRINCIPAL\n\n"
        "Selecciona la sección que deseas consultar:",
        reply_markup=main_menu_keyboard()
    )


async def main_menu_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "main_home":
        await query.edit_message_text(
            "🏠 MENÚ PRINCIPAL\n\n"
            "Selecciona una sección:",
            reply_markup=main_menu_keyboard()
        )

    elif query.data == "main_languages":
        await query.edit_message_text(
            "📚 CURSOS DE IDIOMAS\n\n"
            "Selecciona un idioma:",
            reply_markup=languages_menu_keyboard()
        )

    elif query.data == "main_games":
        await query.answer(
            "El catálogo de videojuegos se conectará a esta sección.",
            show_alert=True
        )


def register_main_menu_handlers(application: Application):
    application.add_handler(
        CommandHandler("menu", show_main_menu)
    )

    application.add_handler(
        CallbackQueryHandler(
            main_menu_router,
            pattern=r"^(main_home|main_languages|main_games)$"
        )
    )
