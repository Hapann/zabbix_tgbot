import asyncio
import signal
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import FastAPI
import uvicorn
from database.db import Database
from handlers import commands, fsm_handlers, unknown, zabbix_api, vpn
from handlers import logs_pm  # 👈 добавлено: наш новый модуль логов
from logger.logger import logger
from globals.config import BOT_TOKEN, DB_DSN
from middlewares.admin_filter import AdminAccessMiddleware

# --- FastAPI-приложение (API сервер) ---
app = FastAPI()
app.include_router(zabbix_api.router)


class Application:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.db = None
        self.server = None
        self.tasks = []

    async def start(self):
        """Запуск приложения"""
        try:
            logger.info("Starting application...")

            # --- Инициализация базы данных ---
            logger.info("Initializing database...")
            self.db = Database()
            if not await self.db.connect(DB_DSN):
                raise RuntimeError("Database connection failed")

            # сохраняем БД в FastAPI-состояние
            app.state.db = self.db

            # --- Подготовка и запуск основных задач ---
            self.tasks.append(asyncio.create_task(self.run_bot()))
            self.tasks.append(asyncio.create_task(self.run_api()))

            # дожидаемся завершения обеих
            await asyncio.gather(*self.tasks)

        except Exception as e:
            logger.critical(f"Application failed: {str(e)}", exc_info=True)
            await self.stop()

    async def run_bot(self):
        """Запуск Telegram бота"""
        try:
            self.bot = Bot(
                token=BOT_TOKEN,
                default=DefaultBotProperties(parse_mode="HTML")
            )
            storage = MemoryStorage()
            self.dp = Dispatcher(storage=storage)

            self.dp["db"] = self.db

            # --- Middleware ---
            self.dp.message.middleware(AdminAccessMiddleware())
            self.dp.callback_query.middleware(AdminAccessMiddleware())

            # --- Подключение всех обработчиков ---
            self.dp.include_router(commands.router)
            self.dp.include_router(fsm_handlers.router)
            self.dp.include_router(vpn.router)
            logs_pm.register_logs_pm_handler(self.dp)  # 👈 Подключаем /logs
            self.dp.include_router(unknown.router)

            logger.info("Telegram bot started and ready")
            await self.dp.start_polling(self.bot)

        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        except Exception as e:
            logger.critical(f"Bot failed: {str(e)}", exc_info=True)
            await self.stop()

    async def run_api(self):
        """Запуск API сервера"""
        try:
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=7000,
                log_level="info",
                access_log=False,
            )
            self.server = uvicorn.Server(config)
            logger.info("API server started")
            await self.server.serve()
        except asyncio.CancelledError:
            logger.info("API task cancelled")
        except Exception as e:
            logger.critical(f"API failed: {str(e)}", exc_info=True)
            await self.stop()

    async def stop(self):
        """Корректное завершение работы"""
        logger.info("Stopping application...")

        # Останавливаем все активные задачи
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Закрываем сессию Telegram‑бота
        if self.bot:
            await self.bot.session.close()
            logger.info("Telegram bot stopped")

        # Закрываем БД
        if self.db and self.db.pool:
            await self.db.pool.close()
            logger.info("Database connection closed")

        logger.info("Application stopped")


# --- Обработчик SIGINT (Ctrl+C) ---
def handle_sigint(signum, frame):
    logger.info("Received SIGINT, stopping application...")
    for task in asyncio.all_tasks():
        task.cancel()


# --- Основная точка входа ---
async def main():
    signal.signal(signal.SIGINT, handle_sigint)

    app_instance = Application()
    try:
        await app_instance.start()
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
        await app_instance.stop()
    except Exception as e:
        logger.critical(f"Unexpected error: {str(e)}", exc_info=True)
        await app_instance.stop()
    finally:
        await app_instance.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting")