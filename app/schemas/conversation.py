"""
Pydantic Schemas for Conversation Management.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ChatMessageResponse(BaseModel):
    """Schema for individual message in transcript."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    sources: list[dict] | None = None
    traces: dict | None = None
    created_at: datetime


class ConversationSessionResponse(BaseModel):
    """Summary schema for conversation session listing."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    service_name: str | None = None
    service_code: str | None = None
    visitor_id: str
    title: str | None = None
    status: str
    message_count: int
    last_active_at: datetime
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None


class ConversationDetailResponse(ConversationSessionResponse):
    """Full detail schema including entire message transcript."""
    messages: list[ChatMessageResponse] = []


class ConversationUpdate(BaseModel):
    """Update conversation session status or title."""
    status: str | None = Field(None, pattern=r"^(active|resolved|needs_support)$")
    title: str | None = Field(None, max_length=255)


class VisitorHistoryResponse(BaseModel):
    """Schema returned to the public widget when loading visitor history."""
    session_id: uuid.UUID | None = None
    status: str = "active"
    messages: list[ChatMessageResponse] = []

