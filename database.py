# database.py
import asyncpg
from asyncpg import Pool
from config import config


class Database:
    def __init__(self):
        self.pool: Pool = None

    async def create_pool(self):
        self.pool = await asyncpg.create_pool(
            dsn=config.DB_URL, min_size=5, max_size=20, command_timeout=60
        )

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def create_tables(self):
        await self.execute(
            """
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
        """
        )


db = Database()
