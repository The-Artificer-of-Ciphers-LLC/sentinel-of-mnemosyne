"""Pydantic v2 message envelope models."""
from pydantic import BaseModel, Field


class MessageEnvelope(BaseModel):
    """Incoming message from any interface."""
    content: str = Field(..., min_length=1, max_length=32_000)
    user_id: str = Field(default="default", max_length=64)


class ResponseEnvelope(BaseModel):
    """Outgoing AI response."""
    content: str
    model: str
