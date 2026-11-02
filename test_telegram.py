
import asyncio
from telegram import Bot
from config import BOT_TOKEN, CHANNEL_ID


async def main():
    async with Bot(BOT_TOKEN) as bot:
        me = await bot.get_me()
        print("CONEXIÓN CON TELEGRAM: CORRECTA")
        print("Nombre del bot:", me.first_name)
        print("Usuario:", f"@{me.username}")

        chat = await bot.get_chat(CHANNEL_ID)
        print("\nCANAL ENCONTRADO:", chat.title)
        print("ID del canal:", chat.id)

        member = await bot.get_chat_member(chat.id, me.id)
        print("Permisos del bot:", member.status)

        if member.status == "administrator":
            print("\nPRUEBA TELEGRAM SUPERADA")
        else:
            print("\nATENCIÓN: el bot no es administrador del canal.")


if __name__ == "__main__":
    asyncio.run(main())
