import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from globals import BOT_TOKEN
from database.db import Database
from handlers import commands, fsm_handlers, unknown
from logger import logger

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    db = Database()
    await db.connect()

    dp['db'] = db

    dp.include_router(commands.router)
    dp.include_router(fsm_handlers.router)
    dp.include_router(unknown.router)

    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())