from urllib.parse import urlparse

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database_nueva as database

from . import base_datos


# ==========================================================
# ESTADOS DEL PROCESO PARA AÑADIR UN CANAL
# ==========================================================

WAITING_CHAT_ID = 1
WAITING_INVITE_LINK = 2


# ==========================================================
# COMPROBAR ADMINISTRADOR
# ==========================================================

async def is_admin(update: Update):

    if not update.effective_chat:
        return False

    if update.effective_chat.type != "private":

        if update.effective_message:
            await update.effective_message.reply_text(
                "Utiliza la administración en el chat privado del bot."
            )

        return False

    admin_id = database.setting("admin_chat_id")

    if (
        not admin_id
        or str(update.effective_user.id) != str(admin_id)
    ):

        if update.callback_query:
            await update.callback_query.answer(
                "No tienes permisos de administrador.",
                show_alert=True,
            )

        elif update.effective_message:
            await update.effective_message.reply_text(
                "No tienes permisos para administrar la publicidad."
            )

        return False

    return True


# ==========================================================
# TECLADO PRINCIPAL
# ==========================================================

def main_keyboard():

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Añadir canal o grupo",
                callback_data="pub:add",
            )
        ],
        [
            InlineKeyboardButton(
                "📋 Ver canales registrados",
                callback_data="pub:list",
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Estadísticas",
                callback_data="pub:stats",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ==========================================================
# MOSTRAR PANEL PRINCIPAL
# ==========================================================

async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    text = (
        "📢 ADMINISTRACIÓN DE PUBLICIDAD\n\n"
        "Selecciona una opción:\n\n"
        "➕ Añadir nuevos grupos o canales.\n"
        "📋 Consultar y administrar los registrados.\n"
        "📊 Consultar estadísticas."
    )

    if update.callback_query:

        query = update.callback_query
        await query.answer()

        await query.edit_message_text(
            text,
            reply_markup=main_keyboard(),
        )

    else:

        await update.effective_message.reply_text(
            text,
            reply_markup=main_keyboard(),
        )


# ==========================================================
# COMANDO /PUB
# ==========================================================

async def pub_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await show_panel(update, context)


# ==========================================================
# AÑADIR GRUPO: PRIMER PASO
# ==========================================================

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return ConversationHandler.END

    if update.callback_query:

        query = update.callback_query
        await query.answer()

        await query.edit_message_text(
            "➕ AÑADIR GRUPO O CANAL\n\n"
            "Paso 1 de 2\n\n"
            "Envíame el CHAT_ID del grupo o canal.\n\n"
            "Ejemplo:\n"
            "-1001234567890\n\n"
            "Pulsa Cancelar si deseas salir.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ Cancelar",
                        callback_data="pub:cancel",
                    )
                ]
            ]),
        )

    else:

        await update.effective_message.reply_text(
            "➕ AÑADIR GRUPO O CANAL\n\n"
            "Paso 1 de 2\n\n"
            "Envíame el CHAT_ID del grupo o canal.\n\n"
            "Ejemplo:\n"
            "-1001234567890"
        )

    context.user_data.pop("pub_chat_id", None)

    return WAITING_CHAT_ID


# ==========================================================
# AÑADIR GRUPO: RECIBIR CHAT_ID
# ==========================================================

async def receive_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = update.message.text.strip()

    try:
        chat_id = int(value)

    except ValueError:

        await update.message.reply_text(
            "❌ El CHAT_ID no es válido.\n\n"
            "Envíame solamente el número.\n"
            "Ejemplo: -1001234567890"
        )

        return WAITING_CHAT_ID

    context.user_data["pub_chat_id"] = chat_id

    await update.message.reply_text(
        "✅ CHAT_ID recibido.\n\n"
        "Paso 2 de 2\n\n"
        "Ahora envíame el enlace de invitación del grupo "
        "o canal.\n\n"
        "Ejemplo:\n"
        "https://t.me/mi_canal\n\n"
        "También puedes utilizar enlaces privados de invitación."
    )

    return WAITING_INVITE_LINK


# ==========================================================
# AÑADIR GRUPO: RECIBIR ENLACE Y REGISTRAR
# ==========================================================

async def receive_invite_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    invite_url = update.message.text.strip()

    parsed = urlparse(invite_url)

    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() not in ("t.me", "www.t.me")
        or not parsed.path.strip("/")
    ):

        await update.message.reply_text(
            "❌ El enlace no parece válido.\n\n"
            "Debe ser un enlace de Telegram que comience por:\n"
            "https://t.me/\n\n"
            "Inténtalo de nuevo."
        )

        return WAITING_INVITE_LINK

    chat_id = context.user_data.get("pub_chat_id")

    if chat_id is None:

        await update.message.reply_text(
            "No encuentro el CHAT_ID. "
            "Inicia de nuevo el proceso con /pub."
        )

        return ConversationHandler.END

    try:

        chat = await context.bot.get_chat(chat_id)

        if chat.type not in ("group", "supergroup", "channel"):

            await update.message.reply_text(
                "❌ El chat indicado no es un grupo ni un canal."
            )

            return ConversationHandler.END

        bot_member = await context.bot.get_chat_member(
            chat_id=chat.id,
            user_id=context.bot.id,
        )

        if bot_member.status not in ("administrator", "creator"):

            await update.message.reply_text(
                "❌ El bot no es administrador de ese grupo o canal.\n\n"
                "Dale permisos de administrador y vuelve a intentarlo."
            )

            return ConversationHandler.END

        base_datos.add_group(
            chat_id=chat.id,
            title=chat.title or "Grupo sin nombre",
            invite_url=invite_url,
        )

        await update.message.reply_text(
            "✅ GRUPO REGISTRADO CORRECTAMENTE\n\n"
            f"Nombre: {chat.title or 'Sin nombre'}\n"
            f"ID: {chat.id}\n"
            f"Enlace: {invite_url}\n\n"
            "El grupo queda ACTIVO y será obligatorio "
            "para los estudiantes cuando corresponda.",
            reply_markup=main_keyboard(),
        )

    except TelegramError as error:

        await update.message.reply_text(
            "❌ No se pudo registrar el grupo o canal.\n\n"
            "Comprueba que:\n"
            "1. El CHAT_ID sea correcto.\n"
            "2. El bot esté dentro del grupo o canal.\n"
            "3. El bot sea administrador.\n\n"
            f"Información: {error}"
        )

    except Exception:

        await update.message.reply_text(
            "❌ Ha ocurrido un error al guardar el grupo."
        )

    context.user_data.pop("pub_chat_id", None)

    return ConversationHandler.END


# ==========================================================
# CANCELAR PROCESO
# ==========================================================

async def cancel_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.callback_query:

        query = update.callback_query
        await query.answer()

        await query.edit_message_text(
            "Operación cancelada.",
            reply_markup=main_keyboard(),
        )

    else:

        await update.message.reply_text(
            "Operación cancelada.",
            reply_markup=main_keyboard(),
        )

    context.user_data.pop("pub_chat_id", None)

    return ConversationHandler.END


# ==========================================================
# LISTAR GRUPOS Y CANALES
# ==========================================================

async def show_groups(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_admin(update):
        return

    groups = base_datos.get_all_groups()

    keyboard = []

    if not groups:

        text = (
            "📋 GRUPOS Y CANALES\n\n"
            "Todavía no hay grupos registrados."
        )

    else:

        text = "📋 GRUPOS Y CANALES REGISTRADOS\n\n"

        for group in groups:

            active = bool(group["active"])

            status = "🟢 ACTIVO" if active else "🔴 INACTIVO"

            text += (
                f"📢 {group['title']}\n"
                f"ID: {group['chat_id']}\n"
                f"Estado: {status}\n"
                f"Enlace: {group['invite_url']}\n\n"
            )

            if active:

                toggle_text = "🔴 Desactivar"

            else:

                toggle_text = "🟢 Activar"

            keyboard.append([
                InlineKeyboardButton(
                    toggle_text,
                    callback_data=(
                        f"pub:toggle:{group['chat_id']}:{0 if active else 1}"
                    ),
                ),
                InlineKeyboardButton(
                    "🗑 Eliminar",
                    callback_data=f"pub:delete:{group['chat_id']}",
                ),
            ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Añadir canal",
            callback_data="pub:add",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Volver al panel",
            callback_data="pub:menu",
        )
    ])

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:

        query = update.callback_query
        await query.answer()

        await query.edit_message_text(
            text,
            reply_markup=markup,
        )

    else:

        await update.effective_message.reply_text(
            text,
            reply_markup=markup,
        )


# ==========================================================
# ACTIVAR / DESACTIVAR
# ==========================================================

async def toggle_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_admin(update):
        return

    query = update.callback_query

    parts = query.data.split(":")

    chat_id = int(parts[2])
    active = int(parts[3])

    changed = base_datos.set_group_active(
        chat_id,
        active,
    )

    if not changed:
        await query.answer(
            "No se encontró el grupo.",
            show_alert=True,
        )
        return

    await show_groups(update, context)


# ==========================================================
# CONFIRMAR ELIMINACIÓN
# ==========================================================

async def confirm_delete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_admin(update):
        return

    query = update.callback_query
    await query.answer()

    chat_id = int(query.data.split(":")[2])

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Sí, eliminar",
                callback_data=f"pub:confirm_delete:{chat_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancelar",
                callback_data="pub:list",
            )
        ],
    ])

    await query.edit_message_text(
        "⚠️ CONFIRMAR ELIMINACIÓN\n\n"
        f"ID del grupo: {chat_id}\n\n"
        "¿Seguro que deseas eliminar este grupo de la publicidad?",
        reply_markup=keyboard,
    )


async def delete_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_admin(update):
        return

    query = update.callback_query
    await query.answer()

    chat_id = int(query.data.split(":")[2])

    deleted = base_datos.delete_group(chat_id)

    if deleted:

        await query.edit_message_text(
            "🗑 Grupo eliminado correctamente."
        )

    else:

        await query.edit_message_text(
            "No se encontró el grupo."
        )


# ==========================================================
# ESTADÍSTICAS
# ==========================================================

async def show_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_admin(update):
        return

    query = update.callback_query
    await query.answer()

    groups = base_datos.get_all_groups()

    total = len(groups)

    active = sum(
        1 for group in groups if group["active"]
    )

    inactive = total - active

    text = (
        "📊 ESTADÍSTICAS DE PUBLICIDAD\n\n"
        f"📢 Total de grupos y canales: {total}\n"
        f"🟢 Activos: {active}\n"
        f"🔴 Inactivos: {inactive}\n\n"
        "Los grupos activos forman parte de los requisitos "
        "de acceso cuando se solicite una clase protegida."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📋 Ver grupos",
                callback_data="pub:list",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Volver al panel",
                callback_data="pub:menu",
            )
        ],
    ])

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
    )


# ==========================================================
# REGISTRO DE LOS BOTONES Y COMANDOS
# ==========================================================

def register_administration_handlers(application: Application):

    add_conversation = ConversationHandler(

        entry_points=[
            CallbackQueryHandler(
                add_start,
                pattern=r"^pub:add$",
            ),
            CommandHandler(
                "pub_add",
                add_start,
            ),
        ],

        states={

            WAITING_CHAT_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_chat_id,
                )
            ],

            WAITING_INVITE_LINK: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_invite_link,
                )
            ],

        },

        fallbacks=[
            CallbackQueryHandler(
                cancel_add,
                pattern=r"^pub:cancel$",
            ),
            CommandHandler(
                "cancel",
                cancel_add,
            ),
        ],

        allow_reentry=True,
    )

    application.add_handler(add_conversation)

    application.add_handler(
        CommandHandler("pub", pub_menu)
    )

    application.add_handler(
        CommandHandler("pub_help", pub_menu)
    )

    application.add_handler(
        CommandHandler("pub_list", show_groups)
    )

    application.add_handler(
        CallbackQueryHandler(
            show_panel,
            pattern=r"^pub:menu$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            show_groups,
            pattern=r"^pub:list$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            show_stats,
            pattern=r"^pub:stats$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            toggle_group,
            pattern=r"^pub:toggle:-?\d+:[01]$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_delete,
            pattern=r"^pub:delete:-?\d+$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_group,
            pattern=r"^pub:confirm_delete:-?\d+$",
        )
    )