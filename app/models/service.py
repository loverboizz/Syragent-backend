"""
Service Model.

Each Company can have multiple Services.
Each Service has a dedicated AI Agent (1-to-1).
`service_url` is used for CORS whitelisting the chat widget origin.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Service(Base):
    __tablename__ = "services"

    # --- Primary Key (UUID) ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Tenant FK ---
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant isolation key",
    )

    # --- Fields ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable service name",
    )
    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Machine-friendly unique code (e.g., 'acme-support')",
    )
    service_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Landing page URL — used for CORS/domain whitelisting",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    widget_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Custom widget appearance, colors, greeting, avatar and starter prompts",
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
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="services",
    )
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="service",
        uselist=False,  # 1-to-1: one Service → one Agent
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    conversations: Mapped[list["ConversationSession"]] = relationship(
        "ConversationSession",
        back_populates="service",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, code='{self.code}')>"

