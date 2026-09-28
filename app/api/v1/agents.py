"""
AI Agent Management Endpoints.

Handles:
  - POST  /api/v1/agents/               : Configure Agent for a Service (1-to-1)
  - GET   /api/v1/agents/by-service/{id}: Retrieve Agent configured for a Service
  - PATCH /api/v1/agents/{agent_id}     : Update LLM config & manage BYOK / FREE billing tiers
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.core.security import encrypt_api_key
from app.models.agent import Agent, AITier
from app.models.service import Service
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate, AITierEnum

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post(
    "/",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure an AI Agent for a Service (Super Admin only)",
)
async def create_agent(
    payload: AgentCreate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Initialize and link an AI Agent to a Service (enforcing 1-to-1):
      - Verifies that the Service belongs to the caller's company
      - Verifies that the Service does not already have an Agent configured
      - Billing Strategy:
          * FREE: Uses global system key from .env (no key stored in DB)
          * BYOK: Encrypts the customer's API key with Fernet before saving
    """
    # 1. Verify Service belongs to the tenant
    service_query = select(Service).where(
        Service.id == payload.service_id,
        Service.company_id == current_admin.company_id,
    )
    result = await db.execute(service_query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found in your organization.",
        )

    # 2. Check 1-to-1 relationship constraint
    existing_agent = await db.execute(
        select(Agent).where(Agent.service_id == payload.service_id)
    )
    if existing_agent.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This Service already has an AI Agent configured. Use PATCH to update it.",
        )

    # 3. Apply encryption based on tier
    encrypted_key = None
    if payload.ai_tier == AITierEnum.BYOK:
        # Note: payload validator guarantees api_key is non-empty for BYOK
        encrypted_key = encrypt_api_key(payload.api_key)

    # 4. Create Agent
    agent = Agent(
        service_id=payload.service_id,
        llm_provider=payload.llm_provider,
        model_name=payload.model_name,
        ai_tier=AITier(payload.ai_tier.value),
        encrypted_api_key=encrypted_key,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)

    return agent


@router.get(
    "/by-service/{service_id}",
    response_model=AgentResponse,
    summary="Get AI Agent configured for a Service",
)
async def get_agent_by_service(
    service_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve the AI Agent associated with a specific service."""
    # Verify service ownership first
    service_query = select(Service).where(
        Service.id == service_id,
        Service.company_id == current_user.company_id,
    )
    service_res = await db.execute(service_query)
    if not service_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found in your organization.",
        )

    # Fetch agent
    agent_query = select(Agent).where(Agent.service_id == service_id)
    agent_res = await db.execute(agent_query)
    agent = agent_res.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AI Agent has been configured for this Service yet.",
        )

    return agent


@router.patch(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update Agent configuration & AI Tier (Super Admin only)",
)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update LLM provider, model name, or switch billing tiers:
      - Switching FREE → BYOK requires a new api_key
      - Switching BYOK → FREE wipes the stored encrypted_api_key
      - Staying on BYOK can optionally rotate the api_key
    """
    # 1. Fetch Agent with its Service to verify tenant ownership
    query = (
        select(Agent)
        .join(Service, Agent.service_id == Service.id)
        .where(
            Agent.id == agent_id,
            Service.company_id == current_admin.company_id,
        )
    )
    result = await db.execute(query)
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found in your organization.",
        )

    # 2. Update basic fields
    if payload.llm_provider is not None:
        agent.llm_provider = payload.llm_provider
    if payload.model_name is not None:
        agent.model_name = payload.model_name

    # 3. Handle Tier & API Key updates
    if payload.ai_tier is not None:
        target_tier = AITier(payload.ai_tier.value)

        if target_tier == AITier.FREE:
            # Switching to FREE: erase encrypted key
            agent.ai_tier = AITier.FREE
            agent.encrypted_api_key = None
        elif target_tier == AITier.BYOK:
            agent.ai_tier = AITier.BYOK
            if payload.api_key:
                agent.encrypted_api_key = encrypt_api_key(payload.api_key)
            elif not agent.encrypted_api_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="An API key is required when activating BYOK tier.",
                )
    elif payload.api_key:
        # User is keeping current tier but rotating key
        if agent.ai_tier == AITier.BYOK:
            agent.encrypted_api_key = encrypt_api_key(payload.api_key)

    await db.flush()
    await db.refresh(agent)

    return agent

