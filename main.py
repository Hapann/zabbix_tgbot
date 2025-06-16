from aiogram import Bot, Dispatcher
import asyncio
import os
from dotenv import load_dotenv
from database import db

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Ошибка: Токен бота не найден. Проверьте файл .env")
    exit(1)

# Создание бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def main():
    await db.init_db()
    # Регистрация обработчиков и т.д.
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
