from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Integer, BigInteger, Text, Enum, TIMESTAMP
import enum
from config import config

Base = declarative_base()

class IncidentStatus(enum.Enum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"
    rejected = "rejected"

class Incident(Base):
    __tablename__ = 'incidents'
    
    event_id = Column(String(50), primary_key=True)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    thread_id = Column(Integer)
    status = Column(Enum(IncidentStatus), nullable=False, default=IncidentStatus.open)
    assigned_to = Column(String(100))
    resolution_comment = Column(Text)
    original_text = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default='now()')
    updated_at = Column(TIMESTAMP, server_default='now()', onupdate='now()')

# Используем прямой адрес PostgreSQL
DB_URL = config.DB_URL.replace("postgresql+asyncpg", "postgresql+asyncpg")
engine = create_async_engine(DB_URL)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)