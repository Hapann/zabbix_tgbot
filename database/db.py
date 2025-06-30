import asyncpg
import logging
from database.queries import (
    CREATE_TABLE_INCIDENTS,
    INSERT_INCIDENT
)
from logger.logger import logger

class Database:
    def __init__(self):
        self.pool = None
        
    async def connect(self, dsn: str):
        """Установка соединения с базой данных"""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info("Database connection pool created")
            await self._init_db()
            return True
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            return False
            
    async def _init_db(self):
        """Инициализация структуры базы данных"""
        async with self.pool.acquire() as conn:
            try:
                # Проверяем существование таблицы incidents
                table_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'incidents')"
                )
                
                if not table_exists:
                    logger.info("Creating database tables...")
                    await conn.execute(CREATE_TABLE_INCIDENTS)
                    logger.info("Database tables created")
                else:
                    logger.info("Database tables already exist")
                    
            except Exception as e:
                logger.error(f"Database initialization error: {e}")
                raise

    async def create_incident(self, data: dict) -> int:
        """Создание нового инцидента"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(
                    INSERT_INCIDENT,
                    data["event"],
                    data["node"],
                    data["trigger"],
                    data.get("status", "open"),
                    data["severity"],
                    data.get("details", "")
                )
                incident_id = result["id"]
                logger.info(f"Created incident ID: {incident_id}")
                return incident_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error creating incident: {e}")
            return -1

    async def update_incident_status(self, incident_id: int, status: str, user: str, comment: str) -> bool:
        """Обновление статуса инцидента"""
        try:
            async with self.pool.acquire() as conn:
                if status == "closed":
                    await conn.execute(
                        CLOSE_INCIDENT,
                        user,
                        comment,
                        incident_id
                    )
                elif status == "rejected":
                    await conn.execute(
                        REJECT_INCIDENT,
                        user,
                        comment,
                        incident_id
                    )
                else:
                    await conn.execute(
                        UPDATE_STATUS,
                        status,
                        user,
                        comment,
                        incident_id
                    )
                logger.info(f"Updated incident #{incident_id} to {status}")
                return True
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating incident #{incident_id}: {e}")
            return False

    async def get_incident(self, incident_id: int) -> dict:
        """Получение данных об инциденте"""
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchrow(
                    "SELECT * FROM incidents WHERE id = $1",
                    incident_id
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error getting incident #{incident_id}: {e}")
            return None