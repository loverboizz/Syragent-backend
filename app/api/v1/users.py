"""
User Management Endpoints (Multi-Tenant Scoped).

Allows:
  - GET   /api/v1/users/                : List all users in the caller's company
  - POST  /api/v1/users/                : Super Admin creates Sub-Admin in company
  - PATCH /api/v1/users/{user_id}/status : Super Admin activates/deactivates Sub-Admin
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import SubAdminCreate, UserResponse, UserStatusUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/",
    response_model=list[UserResponse],
    summary="List all users in the current company",
)
async def list_company_users(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Fetch all users belonging to the caller's company.
    Strict tenant isolation enforced via `company_id`.
    """
    query = (
        select(User)
        .where(User.company_id == current_user.company_id)
        .order_by(User.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Sub-Admin in the company (Super Admin only)",
)
async def create_sub_admin(
    payload: SubAdminCreate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Super Admin creates a new Sub-Admin user within their own company:
      - Validates that email is not already in use
      - Hashes the password
      - Assigns role SUB_ADMIN and the caller's company_id
    """
    # 1. Check if email already exists globally
    email_check = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if email_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    # 2. Create Sub-Admin user
    new_user = User(
        company_id=current_admin.company_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.SUB_ADMIN,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    return new_user


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Activate or deactivate a user (Super Admin only)",
)
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update active status of a user in the company:
      - Prevents Super Admin from deactivating their own account
      - Enforces tenant boundary (cannot modify users belonging to other companies)
    """
    # 1. Prevent self-deactivation
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change the active status of your own account.",
        )

    # 2. Query target user within the same company
    query = select(User).where(
        User.id == user_id,
        User.company_id == current_admin.company_id,
    )
    result = await db.execute(query)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your organization.",
        )

    # 3. Update status
    target_user.is_active = payload.is_active
    await db.flush()
    await db.refresh(target_user)

    return target_user

