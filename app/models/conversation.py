"""
Conversation & Chat Message Models.

Stores persistent chat sessions and detailed transcripts between visitors and AI agents.
Each visitor on a service has a continuous conversation thread.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    # --- Primary Key ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Foreign Keys ---
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The service/agent this conversation belongs to",
    )

    # --- Visitor & Metadata ---
    visitor_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Anonymous visitor unique identifier generated on client browser",
    )
    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Short summary or first question of the customer",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        nullable=False,
        index=True,
        comment="active | resolved | needs_support",
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total messages exchanged in this session",
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Timestamp of latest message sent",
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # --- Relationships ---
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="conversations",
    )
    messages: Mapped[list["ChatMessageRecord"]] = relationship(
        "ChatMessageRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessageRecord.created_at.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_conv_service_visitor", "service_id", "visitor_id"),
    )

    def __repr__(self) -> str:
        return f"<ConversationSession(id={self.id}, visitor='{self.visitor_id}', count={self.message_count})>"


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    # --- Primary Key ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Foreign Key ---
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Message Content ---
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'user' or 'assistant'",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full message text",
    )
    sources: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="RAG retrieved sources metadata cited for this message",
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    # --- Relationship ---
    session: Mapped["ConversationSession"] = relationship(
        "ConversationSession",
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"<ChatMessageRecord(id={self.id}, role='{self.role}')>"

