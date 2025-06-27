import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from globals import BOT_TOKEN
from database.db import Database
from handlers import commands, fsm_handlers, unknown
from logger import logger

async def main():
    try:
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        logger.info("Инициализация базы данных...")
        db = Database()
        await db.connect()

        dp['db'] = db

        dp.include_router(commands.router)
        dp.include_router(fsm_handlers.router)
        dp.include_router(unknown.router)

        logger.info("Бот запущен и готов к работе")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.critical(f"Ошибка при запуске бота: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}")