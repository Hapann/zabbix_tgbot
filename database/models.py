from sqlalchemy import Column, String, Integer, BigInteger, Text, Enum, TIMESTAMP
from sqlalchemy.orm import declarative_base
import enum

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