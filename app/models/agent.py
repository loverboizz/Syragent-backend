"""
Agent Model.

Each Service has exactly one AI Agent (1-to-1 via UNIQUE FK).
Stores LLM configuration and the optional encrypted BYOK API key.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AITier(str, enum.Enum):
    """Billing tier for AI usage."""
    FREE = "FREE"
    BYOK = "BYOK"  # Bring Your Own Key


class Agent(Base):
    __tablename__ = "agents"

    # --- Primary Key (UUID) ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Service FK (UNIQUE → enforces 1-to-1) ---
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # ← Critical: ensures 1 Agent per Service
        comment="1-to-1 link to the parent Service",
    )

    # --- LLM Configuration ---
    llm_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g., 'google', 'openai', 'anthropic'",
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g., 'gemini-1.5-flash', 'gpt-4o', 'claude-3.5-sonnet'",
    )
    ai_tier: Mapped[AITier] = mapped_column(
        Enum(AITier, name="ai_tier", create_constraint=True),
        nullable=False,
        default=AITier.FREE,
        comment="FREE uses global key; BYOK uses customer's encrypted key",
    )
    encrypted_api_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Fernet-encrypted API key (only populated for BYOK tier)",
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
        back_populates="agent",
    )
    knowledge_chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tools: Mapped[list["AgentTool"]] = relationship(
        "AgentTool",
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def has_api_key(self) -> bool:
        """Check if an encrypted API key is present without decrypting it."""
        return bool(self.encrypted_api_key and self.encrypted_api_key.strip())

    def __repr__(self) -> str:
        return (
            f"<Agent(id={self.id}, model='{self.model_name}', "
            f"tier={self.ai_tier})>"
        )

