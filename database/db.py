import asyncpg
from .queries import CREATE_TABLE_INCIDENTS
from globals import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
from logger import logger

class Database:
    def __init__(self):
        self.pool = None
        logger.info(f"Инициализация базы данных: {DB_NAME}@{DB_HOST}:{DB_PORT}")

    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                min_size=1,
                max_size=5
            )
            logger.info(f"Успешно подключен к базе данных: {DB_NAME}@{DB_HOST}:{DB_PORT}")
            
            async with self.pool.acquire() as conn:
                try:
                    # Проверяем существование таблицы
                    await conn.fetch("SELECT 1 FROM incidents LIMIT 1")
                    logger.info("Таблица incidents существует")
                except asyncpg.UndefinedTableError:
                    logger.warning("Таблица incidents не найдена, создаем...")
                    await conn.execute(CREATE_TABLE_INCIDENTS)
                    logger.info("Таблица incidents успешно создана")
                except Exception as e:
                    logger.error(f"Ошибка при проверке таблицы: {str(e)}")
                    raise

        except asyncpg.InvalidCatalogNameError:
            logger.error(f"База данных {DB_NAME} не существует")
            raise
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {str(e)}")
            raise

    async def add_incident(self, event, node, trigger, status, severity, details):
        try:
            async with self.pool.acquire() as conn:
                incident_id = await conn.fetchval(
                    "INSERT INTO incidents (event, node, trigger, status, severity, details) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
                    event, node, trigger, status, severity, details
                )
                logger.info(f"Добавлен новый инцидент ID: {incident_id}")
                return incident_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении инцидента: {str(e)}")
            raise

    async def update_status(self, incident_id, status, assigned_to, comment):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE incidents SET status=$1, updated_at=NOW(), assigned_to=$2, comments=array_append(coalesce(comments, '{}'), $3) WHERE id=$4",
                    status, assigned_to, comment, incident_id
                )
                logger.info(f"Обновлен статус инцидента {incident_id} на '{status}'")
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса инцидента {incident_id}: {str(e)}")
            raise

    async def close_incident(self, incident_id, closed_by, comment):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE incidents SET status='closed', closed_by=$1, closed_at=NOW(), comments=array_append(coalesce(comments, '{}'), $2), updated_at=NOW() WHERE id=$3",
                    closed_by, comment, incident_id
                )
                logger.info(f"Инцидент {incident_id} закрыт пользователем {closed_by}")
        except Exception as e:
            logger.error(f"Ошибка при закрытии инцидента {incident_id}: {str(e)}")
            raise

    async def reject_incident(self, incident_id, rejected_by, comment):
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE incidents SET status='rejected', closed_by=$1, closed_at=NOW(), comments=array_append(coalesce(comments, '{}'), $2), updated_at=NOW() WHERE id=$3",
                    rejected_by, comment, incident_id
                )
                logger.info(f"Инцидент {incident_id} отклонен пользователем {rejected_by}")
        except Exception as e:
            logger.error(f"Ошибка при отклонении инцидента {incident_id}: {str(e)}")
            raise