"""
Pydantic Schemas for Service entity.

Handles validation of service_url using Pydantic's built-in
HttpUrl type to ensure only valid URLs are accepted.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------
class ServiceCreate(BaseModel):
    """
    Schema for creating a new Service.

    `service_url` uses Pydantic's HttpUrl validator to ensure the
    landing page URL is well-formed. This URL is later used for
    CORS/domain whitelisting when the chat widget makes requests.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["ACME Customer Support"],
    )
    code: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",  # slug format
        description="Unique machine-friendly code (lowercase, hyphens only)",
        examples=["acme-support"],
    )
    service_url: HttpUrl = Field(
        ...,
        description="Landing page URL where the chat widget will be embedded",
        examples=["https://support.acme.com"],
    )
    is_active: bool = Field(default=True)
    widget_config: dict | None = Field(default=None, description="Custom widget styling, greeting, avatar, and prompts")


class ServiceUpdate(BaseModel):
    """Partial update schema — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    service_url: HttpUrl | None = None
    is_active: bool | None = None
    widget_config: dict | None = None


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------
class ServiceResponse(BaseModel):
    """Schema returned to the client after Service CRUD operations."""

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    service_url: str  # Serialized as plain string for JSON responses
    is_active: bool
    widget_config: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


from app.schemas.agent import AgentResponse  # noqa: E402


class ServiceDetailResponse(ServiceResponse):
    """Detailed Service schema including the 1-to-1 attached AI Agent (if configured)."""

    agent: AgentResponse | None = None

