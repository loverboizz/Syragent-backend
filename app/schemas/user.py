"""
Pydantic Schemas for User & Authentication.

Handles:
  - User registration (creates Company + SUPER_ADMIN)
  - User login (returns JWT token)
  - Sub-Admin creation by Super Admin
  - User profile & status updates
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


# ---------------------------------------------------------------------------
# Auth Request Schemas
# ---------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    """Payload for registering a new Company along with its initial Super Admin."""

    company_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Company / Organization display name",
        examples=["Acme Corporation"],
    )
    email: EmailStr = Field(
        ...,
        description="Super Admin email address",
        examples=["admin@acme.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Strong password (minimum 8 characters)",
        examples=["SecurePass#2026"],
    )


class UserLoginRequest(BaseModel):
    """Payload for authenticating an existing user."""

    email: EmailStr = Field(..., examples=["admin@acme.com"])
    password: str = Field(..., examples=["SecurePass#2026"])


class TokenResponse(BaseModel):
    """JWT Access Token response returned after successful registration or login."""

    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# User Management Schemas (Super Admin managing Sub Admins)
# ---------------------------------------------------------------------------
class SubAdminCreate(BaseModel):
    """Super Admin payload to create a new Sub-Admin in their company."""

    email: EmailStr = Field(..., examples=["staff@acme.com"])
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        examples=["StaffPass#2026"],
    )


class UserStatusUpdate(BaseModel):
    """Super Admin payload to activate or revoke (deactivate) a Sub-Admin."""

    is_active: bool = Field(
        ...,
        description="Set False to revoke access, True to re-enable",
    )


# ---------------------------------------------------------------------------
# User Response Schemas
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    """User profile response. Password hash is never exposed."""

    id: uuid.UUID
    company_id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

