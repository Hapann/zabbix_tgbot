import asyncio
import logging
from aiogram import Dispatcher
from database import db
from handlers import callbacks
from services.zabbix_api import zabbix_api  # Импортируем API
from services.message_utils import bot  # Импортируем бота

# Настройка логирования
logging.basicConfig(level=logging.INFO)

async def main():
    # Инициализация базы данных
    await db.create_pool()
    await db.create_tables()
    
    # Авторизация в Zabbix API
    if not await zabbix_api.login():
        logging.error("Не удалось авторизоваться в Zabbix API! Проверьте настройки.")
        return
    
    # Инициализация диспетчера
    dp = Dispatcher()
    dp.include_router(callbacks.router)
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())