"""
AgentTool Model: Stores custom Function Calling / Action definitions per Agent.
Stateless Action Gateway: Does not store business data, only endpoint specifications.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HttpMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class ToolActionType(str, enum.Enum):
    SYNC = "SYNC"                  # Tra cứu tức thời (lookup_order, check_stock)
    ASYNC_TICKET = "ASYNC_TICKET"  # Tạo phiếu chờ duyệt (refund, warranty)


class AgentTool(Base):
    __tablename__ = "agent_tools"

    # --- Primary Key ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Foreign Key ---
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Link to the parent Agent",
    )

    # --- Tool Specification for LLM ---
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tên hàm nhận dạng (vd: lookup_order, check_stock)",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Mô tả khi nào Agent nên gọi hàm này",
    )
    parameters_schema: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="JSON Schema định nghĩa tham số đầu vào của hàm",
    )
    action_type: Mapped[ToolActionType] = mapped_column(
        Enum(ToolActionType, name="tool_action_type"),
        nullable=False,
        default=ToolActionType.SYNC,
        comment="SYNC (tức thời) hoặc ASYNC_TICKET (chờ duyệt)",
    )

    # --- Enterprise Execution Endpoint ---
    endpoint_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="URL API của doanh nghiệp (hỗ trợ cả http và https, cho phép private IP)",
    )
    http_method: Mapped[HttpMethod] = mapped_column(
        Enum(HttpMethod, name="http_method"),
        nullable=False,
        default=HttpMethod.POST,
        comment="Phương thức HTTP (GET, POST, PUT, DELETE)",
    )
    encrypted_headers: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Fernet-encrypted Auth headers / API key của doanh nghiệp",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Bật / Tắt công cụ này",
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

    # --- Relationship ---
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="tools",
    )

    def __repr__(self) -> str:
        return f"<AgentTool(id={self.id}, name='{self.name}', method='{self.http_method}', active={self.is_active})>"

