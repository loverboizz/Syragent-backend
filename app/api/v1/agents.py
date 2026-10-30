"""
AI Agent Management Endpoints.

Handles:
  - GET   /api/v1/agents/models         : List available Syragent Managed AI models
  - POST  /api/v1/agents/               : Configure Agent for a Service (1-to-1)
  - GET   /api/v1/agents/by-service/{id}: Retrieve Agent configured for a Service
  - PATCH /api/v1/agents/{agent_id}     : Update managed LLM configuration
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.models.agent import Agent, AITier
from app.models.service import Service
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter(prefix="/agents", tags=["Agents"])

MANAGED_MODELS_CATALOG = [
    {
        "provider": "google",
        "provider_label": "Google DeepMind",
        "model_name": "models/gemini-3.6-flash",
        "display_name": "Gemini 3.6 Flash",
        "badge": "Mặc định • Tốc độ cao",
        "description": "Tối ưu cho hội thoại RAG thời gian thực và thực thi ReAct Action Gateway độ trễ cực thấp.",
    },
    {
        "provider": "google",
        "provider_label": "Google DeepMind",
        "model_name": "models/gemini-3.1-pro-preview",
        "display_name": "Gemini 3.1 Pro",
        "badge": "Suy luận chuyên sâu",
        "description": "Phân tích tài liệu kỹ thuật dài, suy luận đa bước phức tạp và độ chính xác ngữ nghĩa cao.",
    },
    {
        "provider": "openai",
        "provider_label": "OpenAI",
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "badge": "Phản hồi nhanh",
        "description": "Mô hình gọn nhẹ của OpenAI, phản hồi mượt mà cho các tác vụ chăm sóc khách hàng đa ngôn ngữ.",
    },
    {
        "provider": "openai",
        "provider_label": "OpenAI",
        "model_name": "gpt-4o",
        "display_name": "GPT-4o Flagship",
        "badge": "Đa năng cao cấp",
        "description": "Mô hình flagship của OpenAI với khả năng tổng hợp thông tin và tuân thủ chỉ thị xuất sắc.",
    },
    {
        "provider": "anthropic",
        "provider_label": "Anthropic",
        "model_name": "claude-3-5-sonnet-latest",
        "display_name": "Claude 3.5 Sonnet",
        "badge": "Văn phong tự nhiên",
        "description": "Nổi bật với văn phong tư vấn tự nhiên, lịch sự và bám sát tuyệt đối ngữ cảnh tài liệu.",
    },
    {
        "provider": "deepseek",
        "provider_label": "DeepSeek AI",
        "model_name": "deepseek-chat",
        "display_name": "DeepSeek V3",
        "badge": "Hiệu năng cao",
        "description": "Mô hình ngôn ngữ lớn thế hệ mới tối ưu cho bài toán phân tích dữ liệu và hỏi đáp nghiệp vụ.",
    },
]


@router.get(
    "/models",
    summary="List available Syragent Managed AI models",
)
async def list_managed_models():
    """Return the curated catalog of LLM models managed by Syragent."""
    return MANAGED_MODELS_CATALOG


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
    Initialize and link a managed AI Agent to a Service (enforcing 1-to-1):
      - Verifies that the Service belongs to the caller's company
      - Verifies that the Service does not already have an Agent configured
      - Uses Syragent Managed AI infrastructure
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

    # 3. Create Agent on Syragent Managed AI infrastructure
    agent = Agent(
        service_id=payload.service_id,
        llm_provider=payload.llm_provider,
        model_name=payload.model_name,
        ai_tier=AITier.FREE,
        encrypted_api_key=None,
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
    summary="Update Agent managed LLM configuration (Super Admin only)",
)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update managed LLM provider and model name for an Agent.
    """
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

    if payload.llm_provider is not None:
        agent.llm_provider = payload.llm_provider
    if payload.model_name is not None:
        agent.model_name = payload.model_name

    # Ensure managed defaults
    agent.ai_tier = AITier.FREE
    agent.encrypted_api_key = None

    await db.flush()
    await db.refresh(agent)

    return agent
