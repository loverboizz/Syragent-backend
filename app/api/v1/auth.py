"""
Authentication Endpoints.

Handles:
  - POST /api/v1/auth/register: Register Company + Super Admin
  - POST /api/v1/auth/login: Authenticate user & issue JWT
  - GET  /api/v1/auth/me: Retrieve current authenticated user profile
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.company import Company
from app.models.user import User, UserRole
from app.schemas.user import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new Company & Super Admin",
)
async def register(
    payload: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Bootstrap a new Company with its initial Super Admin account:
      - Ensures company name is unique
      - Ensures user email is unique
      - Hashes password using bcrypt
      - Creates Company and User atomically
      - Returns JWT access token
    """
    # 1. Check if email already registered
    email_check = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if email_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    # 2. Check if company name already registered
    company_check = await db.execute(
        select(Company).where(Company.name == payload.company_name)
    )
    if company_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A company with this name already exists.",
        )

    # 3. Create Company
    company = Company(name=payload.company_name)
    db.add(company)
    await db.flush()  # Generates company.id

    # 4. Create Super Admin User
    user = User(
        company_id=company.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # 5. Issue JWT Token
    access_token = create_access_token(subject=user.id)
    return TokenResponse(access_token=access_token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain JWT token",
)
async def login(
    payload: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Authenticate user credentials:
      - Validates email & password
      - Checks if user account is active
      - Issues new JWT access token
    """
    result = await db.execute(
        select(User).where(User.email == payload.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact your administrator.",
        )

    access_token = create_access_token(subject=user.id)
    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Return the profile data for the authenticated user."""
    return current_user

