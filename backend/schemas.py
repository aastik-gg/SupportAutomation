from datetime import datetime
from pydantic import BaseModel, Field


class TicketSchema(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    subject: str | None = None
    message: str | None = None
    ai_reply: str | None = None
    status: str
    gmail_message_id: str | None = None
    submittedAt: datetime = Field(alias="created_at")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        from_attributes = True
