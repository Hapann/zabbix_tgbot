import asyncpg
import logging
from config import config, get_logger

logger = get_logger()

class Database:
    def __init__(self):
        self.pool = None

    async def create_pool(self):
        try:
            self.pool = await asyncpg.create_pool(
                dsn=config.DB_URL,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info(f"Пул соединений с БД создан: {config.DB_URL}")
        except Exception as e:
            logger.error(f"Ошибка создания пула соединений: {str(e)}")
            raise

    async def execute(self, query: str, *args):
        """Выполнение SQL-запроса без возврата результатов"""
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            get_logger.error(f"Ошибка выполнения запроса: {query} | {str(e)}")
            raise

    async def create_tables(self):
        """Создание таблиц в базе данных"""
        await self.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                event_id VARCHAR(50) PRIMARY KEY,
                message_id INTEGER NOT NULL,
                chat_id BIGINT NOT NULL,
                thread_id INTEGER,
                status VARCHAR(20) NOT NULL CHECK (status IN ('open', 'in_progress', 'closed', 'rejected')),
                assigned_to VARCHAR(100),
                resolution_comment TEXT,
                original_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        get_logger.info("Таблица incidents создана/проверена")

db = Database()