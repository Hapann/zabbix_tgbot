import asyncio
import signal
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import FastAPI
import uvicorn
from database.db import Database
from handlers import commands, fsm_handlers, unknown, zabbix_api
from logger import logger
from globals import BOT_TOKEN, DB_DSN

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
            
            # Инициализация базы данных
            logger.info("Initializing database...")
            self.db = Database()
            if not await self.db.connect(DB_DSN):
                raise RuntimeError("Database connection failed")
            
            # Сохраняем базу данных в состоянии приложения FastAPI
            app.state.db = self.db
            
            # Запуск Telegram бота
            self.tasks.append(asyncio.create_task(self.run_bot()))
            
            # Запуск API сервера
            self.tasks.append(asyncio.create_task(self.run_api()))
            
            # Ожидаем завершения всех задач
            await asyncio.gather(*self.tasks)
            
        except Exception as e:
            logger.critical(f"Application failed: {str(e)}")
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

            self.dp['db'] = self.db

            # Подключаем все обработчики
            self.dp.include_router(commands.router)  # commands.router - экземпляр
            self.dp.include_router(fsm_handlers.router)  # fsm_handlers.router - экземпляр
            self.dp.include_router(unknown.router)  # unknown.router - экземпляр
            print(f"commands.router type: {type(commands.router)}")
            print(f"fsm_handlers.router type: {type(fsm_handlers.router)}")
            print(f"unknown.router type: {type(unknown.router)}")

            logger.info("Telegram bot started and ready")
            await self.dp.start_polling(self.bot)
        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        except Exception as e:
            logger.critical(f"Bot failed: {str(e)}")
            await self.stop()

    async def run_api(self):
        """Запуск API сервера"""
        try:
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=7000,
                log_level="info",
                access_log=False
            )
            self.server = uvicorn.Server(config)
            logger.info("API server started")
            await self.server.serve()
        except asyncio.CancelledError:
            logger.info("API task cancelled")
        except Exception as e:
            logger.critical(f"API failed: {str(e)}")
            await self.stop()

    async def stop(self):
        """Корректное завершение работы"""
        logger.info("Stopping application...")
        
        # Отменяем все задачи
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Останавливаем бот
        if self.bot:
            await self.bot.session.close()
            logger.info("Telegram bot stopped")
        
        # Закрываем соединение с БД
        if self.db and self.db.pool:
            await self.db.pool.close()
            logger.info("Database connection closed")
        
        logger.info("Application stopped")

def handle_sigint(signum, frame):
    """Обработчик сигнала SIGINT (Ctrl+C)"""
    logger.info("Received SIGINT, stopping application...")
    # Отправляем сигнал остановки в главный цикл
    for task in asyncio.all_tasks():
        task.cancel()

async def main():
    """Основная асинхронная функция"""
    # Устанавливаем обработчик сигнала
    signal.signal(signal.SIGINT, handle_sigint)
    
    app_instance = Application()
    try:
        await app_instance.start()
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
        await app_instance.stop()
    except Exception as e:
        logger.critical(f"Unexpected error: {str(e)}")
        await app_instance.stop()
    finally:
        # Гарантируем остановку при любом сценарии
        await app_instance.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting")