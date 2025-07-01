from datetime import datetime
import asyncpg
from database.queries import (
    CREATE_TABLE_INCIDENTS,
    INSERT_INCIDENT,
    UPDATE_STATUS,
    CLOSE_INCIDENT,
    REJECT_INCIDENT
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
            logger.error(f"Database connection error: {e}", exc_info=True)
            return False

    async def _init_db(self):
        """Инициализация структуры базы данных"""
        async with self.pool.acquire() as conn:
            try:
                # Создаем схему public если она не существует
                await conn.execute("CREATE SCHEMA IF NOT EXISTS public")
                
                # Даем все права на схему public
                await conn.execute("GRANT ALL ON SCHEMA public TO public")
                
                # Проверяем существование таблицы
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
                logger.error(f"Database initialization error: {e}", exc_info=True)
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
                    data.get("details", ""),
                    data.get("assigned_to_username"),
                    data.get("assigned_to_user_id"),
                    data.get("closed_by_username"),
                    data.get("closed_by_user_id"),
                    data.get("message_id")  # Добавляем 11-й параметр
                )
                incident_id = result["id"]
                logger.info(f"Created incident ID: {incident_id}")
                return incident_id
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error creating incident: {e}\n"
                f"Query: {INSERT_INCIDENT}\n"
                f"Params: {data}",
                exc_info=True
            )
            return -1

    async def get_incident(self, incident_id: int) -> dict:
        """Получение данных об инциденте"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM incidents WHERE id = $1",
                    incident_id
                )
                if row:
                    return dict(row)
                logger.warning(f"Incident #{incident_id} not found")
                return None
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error getting incident #{incident_id}: {e}\n"
                f"Query: SELECT * FROM incidents WHERE id = $1",
                exc_info=True
            )
            return None

    async def update_incident(
        self,
        incident_id: int,
        status: str = None,
        assigned_to_username: str = None,
        assigned_to_user_id: int = None,
        closed_by_username: str = None,
        closed_by_user_id: int = None,
        closed_at: datetime = None,
        comment: str = None,
        message_id: int = None
    ) -> bool:
        """Обновление данных инцидента"""
        try:
            async with self.pool.acquire() as conn:
                query = "UPDATE incidents SET "
                params = []
                updates = []
                index = 1

                if status is not None:
                    updates.append(f"status = ${index}")
                    params.append(status)
                    index += 1
                if assigned_to_username is not None:
                    updates.append(f"assigned_to_username = ${index}")
                    params.append(assigned_to_username)
                    index += 1
                if assigned_to_user_id is not None:
                    updates.append(f"assigned_to_user_id = ${index}")
                    params.append(assigned_to_user_id)
                    index += 1
                if closed_by_username is not None:
                    updates.append(f"closed_by_username = ${index}")
                    params.append(closed_by_username)
                    index += 1
                if closed_by_user_id is not None:
                    updates.append(f"closed_by_user_id = ${index}")
                    params.append(closed_by_user_id)
                    index += 1
                if closed_at is not None:
                    updates.append(f"closed_at = ${index}")
                    params.append(closed_at)
                    index += 1
                if comment is not None:
                    updates.append(f"comment = ${index}")
                    params.append(comment)
                    index += 1
                if message_id is not None:
                    updates.append(f"message_id = ${index}")
                    params.append(message_id)
                    index += 1

                if not updates:
                    logger.warning(f"No updates provided for incident #{incident_id}")
                    return False

                query += ", ".join(updates)
                query += f", updated_at = NOW() WHERE id = ${index}"
                params.append(incident_id)

                result = await conn.execute(query, *params)
                if "UPDATE 1" not in result:
                    logger.error(f"Update failed for incident #{incident_id}")
                    return False

                logger.info(f"Updated incident #{incident_id}")
                return True
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error updating incident #{incident_id}: {e}\n"
                f"Query: {query}\n"
                f"Params: {params}",
                exc_info=True
            )
            return False
