"""
Pydantic Schemas for Company entity.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CompanyUpdate(BaseModel):
    """Payload for updating company information."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        examples=["Acme Technologies Inc."],
    )


class CompanyResponse(BaseModel):
    """Company public profile response."""

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

