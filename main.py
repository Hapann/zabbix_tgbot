import asyncio
import signal
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from globals import BOT_TOKEN
from database.db import Database
from handlers import commands, fsm_handlers, unknown
from logger import logger

class GracefulExit(SystemExit):
    pass

def handle_sigint(signum, frame):
    raise GracefulExit()

async def shutdown(bot: Bot = None):
    """Корректное завершение работы"""
    logger.info("Завершение работы бота...")
    if bot:
        await bot.session.close()
    logger.info("Бот остановлен")

async def main():
    bot = None
    try:
        # Устанавливаем обработчик SIGINT
        signal.signal(signal.SIGINT, handle_sigint)
        
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
        
        # Создаем задачу для поллинга
        polling_task = asyncio.create_task(dp.start_polling(bot))
        
        # Ждем либо завершения поллинга, либо KeyboardInterrupt
        try:
            await polling_task
        except asyncio.CancelledError:
            logger.info("Получен сигнал остановки (Ctrl+C)")
        except Exception as e:
            logger.error(f"Ошибка в работе бота: {str(e)}")
            raise

    except GracefulExit:
        logger.info("Бот был вручную остановлен (SIGINT)")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}")
        raise
    finally:
        await shutdown(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Уже обработано в main()
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {str(e)}")