import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from globals import BOT_TOKEN
from database.db import Database
from handlers import commands, unknown
from handlers import fsm_handlers
from logger import logger

async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    db = Database()
    await db.connect()

    # Передаем db в роутеры через middleware или через контекст (упрощу, можно глобально)
    # Для учебного примера можно сделать dp['db'] = db и получать из dp

    dp.include_router(commands.router)
    dp.include_router(unknown.router)
    dp.include_router(fsm_handlers.router)

    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
