# main.py
import asyncio
from aiogram import Dispatcher
from database import db
from handlers import callbacks, commands
from config import config

async def main():
    # Инициализация базы данных
    await db.create_pool()
    await db.create_tables()
    
    dp = Dispatcher()
    dp.include_router(callbacks.router)
    dp.include_router(commands.router)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())