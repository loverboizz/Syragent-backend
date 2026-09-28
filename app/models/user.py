"""
User Model.

Represents platform users (SUPER_ADMIN or SUB_ADMIN).
Scoped to a Company via company_id FK for multi-tenancy.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    """Access control roles."""
    SUPER_ADMIN = "SUPER_ADMIN"
    SUB_ADMIN = "SUB_ADMIN"


class User(Base):
    __tablename__ = "users"

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
    email: Mapped[str] = mapped_column(
        String(320),  # RFC 5321 max email length
        nullable=False,
        unique=True,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
        default=UserRole.SUB_ADMIN,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Super admin can deactivate sub-admins",
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
        back_populates="users",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role={self.role})>"

