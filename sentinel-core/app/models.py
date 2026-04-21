"""Pydantic v2 message envelope models."""
from pydantic import BaseModel, Field


class MessageEnvelope(BaseModel):
    """Incoming message from any interface."""
    content: str = Field(..., min_length=1, max_length=32_000)
    user_id: str = Field(
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    source: str | None = None          # Interface identifier (e.g., "discord", "imessage")
    channel_id: str | None = None      # Interface-specific channel identifier
    # id, timestamp, attachments, metadata: reserved for future expansion — not currently in use


class ResponseEnvelope(BaseModel):
    """Outgoing AI response."""
    content: str
    model: str
