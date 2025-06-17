import asyncio
from aiogram import Dispatcher
from database import db
from handlers import callbacks
from services.zabbix_api import zabbix_api
from services.message_utils import bot
from config import app_logger, config


async def main():
    app_logger.info("Запуск Zabbix Telegram Bot")

    # Инициализация базы данных
    try:
        await db.create_pool()
        await db.create_tables()
        app_logger.info("База данных успешно инициализирована")
    except Exception as e:
        app_logger.error(f"Ошибка инициализации БД: {str(e)}")
        return

    # Авторизация в Zabbix API
    try:
        if not await zabbix_api.login():
            app_logger.error(
                "Не удалось авторизоваться в Zabbix API! Проверьте настройки."
            )
            return
        app_logger.info("Успешная аутентификация в Zabbix API")
    except Exception as e:
        app_logger.error(f"Ошибка подключения к Zabbix API: {str(e)}")
        return

    # Инициализация диспетчера
    dp = Dispatcher()
    dp.include_router(callbacks.router)

    # Запуск бота
    app_logger.info("Бот запущен и ожидает сообщений")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
