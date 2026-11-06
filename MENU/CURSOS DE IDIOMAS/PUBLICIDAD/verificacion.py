import random

from telegram.error import TelegramError

from . import base_datos


class VerificationError(Exception):
    pass


def is_member(member):
    status = member.status

    if status in ("member", "administrator", "creator"):
        return True

    if status == "restricted":
        return bool(getattr(member, "is_member", False))

    return False


async def check_access(bot, user_id):
    """
    Comprueba todos los grupos y canales activos.

    Devuelve:
        {
            "allowed": True/False,
            "pending": grupo pendiente o None
        }

    Si Telegram no permite verificar algún grupo,
    lanza VerificationError. Nunca concede acceso
    basándose en una comprobación fallida.
    """

    groups = base_datos.get_active_groups()

    pending_groups = []

    for group in groups:

        try:
            member = await bot.get_chat_member(
                chat_id=int(group["chat_id"]),
                user_id=int(user_id)
            )

            if not is_member(member):
                pending_groups.append(dict(group))

        except TelegramError as error:

            raise VerificationError(
                f"No se pudo verificar el grupo "
                f"{group['title']}: {error}"
            ) from error

    if not pending_groups:
        return {
            "allowed": True,
            "pending": None
        }

    selected_group = random.choice(pending_groups)

    return {
        "allowed": False,
        "pending": selected_group
    }