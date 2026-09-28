"""
Company Model.

Root entity in the multi-tenant hierarchy.
Every User, Service, Agent, and KnowledgeChunk traces back here.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Company(Base):
    __tablename__ = "companies"

    # --- Primary Key (UUID) ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique company identifier",
    )

    # --- Fields ---
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Company display name",
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
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    services: Mapped[list["Service"]] = relationship(
        "Service",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}')>"

