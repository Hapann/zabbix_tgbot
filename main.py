import asyncio
from aiogram import Dispatcher
from config import config
from database import db
from handlers import callbacks, commands

async def main():
    await db.init_db()
    
    dp = Dispatcher()
    dp.include_router(callbacks.router)
    dp.include_router(commands.router)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())