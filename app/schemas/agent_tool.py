"""
Pydantic Schemas for AgentTool entity.
Used for creating, updating, querying, and testing custom enterprise API tools.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class HttpMethodEnum(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class ToolActionTypeEnum(str, Enum):
    SYNC = "SYNC"                  # Real-time / Read (lookup_order, check_stock)
    ASYNC_TICKET = "ASYNC_TICKET"  # Delayed / Approval required (refund, warranty)


# ---------------------------------------------------------------------------
# Base & Create/Update Schemas
# ---------------------------------------------------------------------------
class AgentToolBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Tên hàm nhận dạng (vd: lookup_order, check_stock)",
        examples=["lookup_order"],
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Mô tả công dụng và khi nào Agent nên gọi hàm này",
        examples=["Tra cứu thông tin trạng thái và người giao hàng của đơn hàng"],
    )
    parameters_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema chuẩn mô tả các tham số đầu vào của hàm",
        examples=[{
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Mã đơn hàng cần tra cứu (vd: #DH123)"}
            },
            "required": ["order_id"]
        }],
    )
    action_type: ToolActionTypeEnum = Field(
        default=ToolActionTypeEnum.SYNC,
        description="SYNC (tức thời) hoặc ASYNC_TICKET (tạo phiếu chờ duyệt)",
    )
    endpoint_url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="URL API của doanh nghiệp (hỗ trợ cả http và https, chấp nhận IP Private/Localhost)",
        examples=["https://api.shop.com/v1/orders/{order_id}", "http://127.0.0.1:8001/orders"],
    )
    http_method: HttpMethodEnum = Field(
        default=HttpMethodEnum.POST,
        description="Phương thức HTTP",
    )
    is_active: bool = Field(
        default=True,
        description="Trạng thái kích hoạt công cụ",
    )


class AgentToolCreate(AgentToolBase):
    headers: dict[str, str] | None = Field(
        default=None,
        description="Headers xác thực (Authorization: Bearer ..., X-API-Key) dạng plaintext. Sẽ được mã hóa Fernet trước khi lưu.",
    )


class AgentToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1)
    parameters_schema: dict[str, Any] | None = None
    action_type: ToolActionTypeEnum | None = None
    endpoint_url: str | None = Field(default=None, min_length=1, max_length=2048)
    http_method: HttpMethodEnum | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------
class AgentToolResponse(AgentToolBase):
    id: uuid.UUID
    agent_id: uuid.UUID
    has_headers: bool = Field(
        default=False,
        description="True nếu công cụ có cấu hình Auth Headers (không lộ token ra ngoài)",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Test Tool Schemas
# ---------------------------------------------------------------------------
class AgentToolTestRequest(BaseModel):
    test_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Các tham số mẫu để test thử kết nối API doanh nghiệp",
        examples=[{"order_id": "DH12345"}],
    )


class AgentToolTestResponse(BaseModel):
    success: bool
    status_code: int | None = None
    response_time_ms: float | None = None
    data: Any = None
    error: str | None = None

