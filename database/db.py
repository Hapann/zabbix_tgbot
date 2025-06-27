import asyncpg
from .queries import CREATE_TABLE_INCIDENTS
from globals import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            min_size=1,
            max_size=5
        )
        async with self.pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_INCIDENTS)

    async def add_incident(self, event, node, trigger, status, severity, details):
        async with self.pool.acquire() as conn:
            incident_id = await conn.fetchval(
                "INSERT INTO incidents (event, node, trigger, status, severity, details) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
                event, node, trigger, status, severity, details
            )
            return incident_id

    async def update_status(self, incident_id, status, assigned_to, comment):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE incidents SET status=$1, updated_at=NOW(), assigned_to=$2, comments=array_append(coalesce(comments, '{}'), $3) WHERE id=$4",
                status, assigned_to, comment, incident_id
            )

    async def close_incident(self, incident_id, closed_by, comment):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE incidents SET status='closed', closed_by=$1, closed_at=NOW(), comments=array_append(coalesce(comments, '{}'), $2), updated_at=NOW() WHERE id=$3",
                closed_by, comment, incident_id
            )

    async def reject_incident(self, incident_id, rejected_by, comment):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE incidents SET status='rejected', closed_by=$1, closed_at=NOW(), comments=array_append(coalesce(comments, '{}'), $2), updated_at=NOW() WHERE id=$3",
                rejected_by, comment, incident_id
            )