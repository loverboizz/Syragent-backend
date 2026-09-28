"""
Service Management Endpoints (Multi-Tenant Scoped).

Handles:
  - POST   /api/v1/services/             : Create a new Service (Super Admin only)
  - GET    /api/v1/services/             : List all Services of the caller's company
  - GET    /api/v1/services/{service_id} : Get Service details with attached AI Agent
  - PATCH  /api/v1/services/{service_id} : Update Service details (Super Admin only)
  - DELETE /api/v1/services/{service_id} : Deactivate / soft-delete Service (Super Admin only)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.models.agent import Agent
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.service import Service
from app.models.user import User
from app.schemas.service import (
    ServiceCreate,
    ServiceDetailResponse,
    ServiceResponse,
    ServiceUpdate,
)

router = APIRouter(prefix="/services", tags=["Services"])


@router.post(
    "/",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Service (Super Admin only)",
)
async def create_service(
    payload: ServiceCreate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new Service for the authenticated company:
      - Validates unique service code
      - Enforces service_url format for CORS whitelisting
      - Associates service with current_admin.company_id
    """
    # 1. Check if unique code is already taken
    existing_code = await db.execute(
        select(Service).where(Service.code == payload.code)
    )
    if existing_code.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service code '{payload.code}' is already taken.",
        )

    # 2. Create Service
    service = Service(
        company_id=current_admin.company_id,
        name=payload.name,
        code=payload.code,
        service_url=str(payload.service_url),
        is_active=payload.is_active,
        widget_config=payload.widget_config or {},
    )
    db.add(service)
    await db.flush()
    await db.refresh(service)

    return service


@router.get(
    "/",
    response_model=list[ServiceDetailResponse],
    summary="List all Services in the company",
)
async def list_services(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all services belonging to the authenticated user's company."""
    query = (
        select(Service)
        .options(selectinload(Service.agent))
        .where(Service.company_id == current_user.company_id)
        .order_by(Service.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/stats",
    summary="Get aggregated statistics for overview dashboard",
)
async def get_services_stats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns aggregated metrics for the company in high-performance single queries:
    - total_services
    - active_services
    - configured_agents
    - total_chunks
    """
    cid = current_user.company_id

    # 1. Total and active services
    srv_query = select(
        func.count(Service.id).label("total"),
        func.count(Service.id).filter(Service.is_active == True).label("active"),
    ).where(Service.company_id == cid)
    srv_res = await db.execute(srv_query)
    total_srv, active_srv = srv_res.one()

    # 2. Configured agents
    agent_query = (
        select(func.count(Agent.id))
        .join(Service, Agent.service_id == Service.id)
        .where(Service.company_id == cid)
    )
    agent_res = await db.execute(agent_query)
    total_agents = agent_res.scalar() or 0

    # 3. Total chunks
    chunk_query = (
        select(func.count(KnowledgeChunk.id))
        .join(Agent, KnowledgeChunk.agent_id == Agent.id)
        .join(Service, Agent.service_id == Service.id)
        .where(Service.company_id == cid)
    )
    chunk_res = await db.execute(chunk_query)
    total_chunks = chunk_res.scalar() or 0

    return {
        "total_services": total_srv or 0,
        "active_services": active_srv or 0,
        "configured_agents": total_agents,
        "total_chunks": total_chunks,
    }


@router.get(
    "/{service_id}",
    response_model=ServiceDetailResponse,
    summary="Get Service details and attached AI Agent",
)
async def get_service(
    service_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Retrieve service details including its dedicated AI Agent (if configured).
    Strict multi-tenant security: rejects access to other companies' services.
    """
    query = (
        select(Service)
        .options(selectinload(Service.agent))
        .where(
            Service.id == service_id,
            Service.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found in your organization.",
        )

    return service


@router.patch(
    "/{service_id}",
    response_model=ServiceResponse,
    summary="Update Service details (Super Admin only)",
)
async def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update service name, code, service_url, or active status."""
    # 1. Fetch service ensuring tenant ownership
    query = select(Service).where(
        Service.id == service_id,
        Service.company_id == current_admin.company_id,
    )
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found in your organization.",
        )

    # 2. Check code uniqueness if being changed
    if payload.code and payload.code != service.code:
        existing_code = await db.execute(
            select(Service).where(
                Service.code == payload.code,
                Service.id != service_id,
            )
        )
        if existing_code.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service code '{payload.code}' is already in use.",
            )
        service.code = payload.code

    # 3. Apply optional updates
    if payload.name is not None:
        service.name = payload.name
    if payload.service_url is not None:
        service.service_url = str(payload.service_url)
    if payload.is_active is not None:
        service.is_active = payload.is_active
    if payload.widget_config is not None:
        service.widget_config = payload.widget_config

    await db.flush()
    await db.refresh(service)

    return service


@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate Service (Super Admin only)",
)
async def deactivate_service(
    service_id: uuid.UUID,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Soft-delete / deactivate a Service.
    Widgets embedded on external landing pages will be denied access.
    """
    query = select(Service).where(
        Service.id == service_id,
        Service.company_id == current_admin.company_id,
    )
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found in your organization.",
        )

    service.is_active = False
    await db.flush()
    return None

