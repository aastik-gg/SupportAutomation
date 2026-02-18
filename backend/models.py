from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from .database import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("gmail_message_id", name="uq_gmail_message"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    email = Column(String(255))
    subject = Column(String(500))
    message = Column(Text)
    ai_reply = Column(Text)
    status = Column(String(50), default="pending", index=True)
    gmail_message_id = Column(String(255), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
