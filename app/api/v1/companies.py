"""
Company Management Endpoints.

Handles:
  - GET   /api/v1/companies/me : Retrieve the caller's company profile
  - PATCH /api/v1/companies/me : Update company name (Super Admin only)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyResponse, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get(
    "/me",
    response_model=CompanyResponse,
    summary="Get current company details",
)
async def get_my_company(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve the company profile of the authenticated user."""
    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )
    return company


@router.patch(
    "/me",
    response_model=CompanyResponse,
    summary="Update company details (Super Admin only)",
)
async def update_my_company(
    payload: CompanyUpdate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update the company name. Enforces uniqueness across companies."""
    # Check if new name is already taken by another company
    existing = await db.execute(
        select(Company).where(
            Company.name == payload.name,
            Company.id != current_admin.company_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A company with this name already exists.",
        )

    result = await db.execute(
        select(Company).where(Company.id == current_admin.company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    company.name = payload.name
    await db.flush()
    await db.refresh(company)

    return company

