import asyncpg
from datetime import datetime
from typing import Optional, Dict, List
from logger.logger import logger
from globals import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

CREATE_TABLE_INCIDENTS = """
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    event TEXT NOT NULL,
    node TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    severity TEXT NOT NULL,
    details TEXT,
    assigned_to TEXT,
    closed_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE,
    comments JSONB DEFAULT '[]'::jsonb
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_assigned_to ON incidents(assigned_to);
"""

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.pool.Pool] = None

    async def connect(self):
        """Устанавливает соединение с базой данных и создает таблицы при необходимости"""
        try:
            self.pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logger.info(f"Успешное подключение к базе данных {DB_NAME}")

            async with self.pool.acquire() as conn:
                await conn.execute(CREATE_TABLE_INCIDENTS)
                await conn.execute(CREATE_INDEXES)
                logger.info("Таблица incidents и индексы успешно созданы/проверены")

        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise

    async def add_incident(
        self,
        event: str,
        node: str,
        trigger: str,
        severity: str,
        details: str
    ) -> int:
        """Добавляет новый инцидент в базу данных"""
        try:
            async with self.pool.acquire() as conn:
                incident_id = await conn.fetchval(
                    """
                    INSERT INTO incidents (event, node, trigger, severity, details)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    event, node, trigger, severity, details
                )
                logger.info(f"Добавлен новый инцидент ID: {incident_id}")
                return incident_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении инцидента: {e}")
            raise

    async def update_incident(
        self,
        incident_id: int,
        status: str,
        assigned_to: Optional[str] = None,
        closed_by: Optional[str] = None,
        comment: Optional[str] = None
    ) -> None:
        """Обновляет статус инцидента и добавляет комментарий"""
        try:
            async with self.pool.acquire() as conn:
                # Формируем динамический запрос в зависимости от переданных параметров
                query = "UPDATE incidents SET status = $1, updated_at = NOW()"
                params = [status]
                
                if assigned_to:
                    query += ", assigned_to = $2"
                    params.append(assigned_to)
                
                if closed_by:
                    query += ", closed_by = $3, closed_at = NOW()"
                    params.append(closed_by)
                
                if comment:
                    query += ", comments = comments || $4::jsonb"
                    params.append([{"user": assigned_to or closed_by, 
                                  "text": comment, 
                                  "timestamp": datetime.now().isoformat()}])
                
                query += " WHERE id = $" + str(len(params) + 1)
                params.append(incident_id)
                
                await conn.execute(query, *params)
                logger.info(f"Инцидент {incident_id} обновлен: status={status}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении инцидента {incident_id}: {e}")
            raise

    async def get_incident(self, incident_id: int) -> Optional[Dict]:
        """Возвращает информацию об инциденте по ID"""
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(
                    "SELECT * FROM incidents WHERE id = $1", 
                    incident_id
                )
                return dict(record) if record else None
        except Exception as e:
            logger.error(f"Ошибка при получении инцидента {incident_id}: {e}")
            return None

    async def get_incident_stats(self) -> Dict[str, int]:
        """Возвращает статистику по инцидентам"""
        try:
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new,
                        SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                        SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed,
                        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
                    FROM incidents
                    """
                )
                return {
                    "total": stats["total"],
                    "new": stats["new"],
                    "in_progress": stats["in_progress"],
                    "closed": stats["closed"],
                    "rejected": stats["rejected"]
                }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {
                "total": 0,
                "new": 0,
                "in_progress": 0,
                "closed": 0,
                "rejected": 0
            }

    async def get_user_stats(self, user_id: str) -> Dict[str, int]:
        """Возвращает статистику по действиям пользователя"""
        try:
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow(
                    """
                    SELECT 
                        SUM(CASE WHEN assigned_to LIKE $1 || '%' THEN 1 ELSE 0 END) as taken,
                        SUM(CASE WHEN closed_by LIKE $1 || '%' AND status = 'closed' THEN 1 ELSE 0 END) as closed,
                        SUM(CASE WHEN closed_by LIKE $1 || '%' AND status = 'rejected' THEN 1 ELSE 0 END) as rejected
                    FROM incidents
                    """,
                    f"{user_id}"
                )
                return {
                    "taken": stats["taken"] or 0,
                    "closed": stats["closed"] or 0,
                    "rejected": stats["rejected"] or 0
                }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики пользователя {user_id}: {e}")
            return {
                "taken": 0,
                "closed": 0,
                "rejected": 0
            }

    async def get_recent_incidents(self, limit: int = 10) -> List[Dict]:
        """Возвращает последние инциденты"""
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT $1",
                    limit
                )
                return [dict(record) for record in records]
        except Exception as e:
            logger.error(f"Ошибка при получении последних инцидентов: {e}")
            return []

    async def close(self):
        """Закрывает соединение с базой данных"""
        if self.pool:
            await self.pool.close()
            logger.info("Соединение с базой данных закрыто")