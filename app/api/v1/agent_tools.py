"""
Agent Tools Management Endpoints.

Handles:
  - GET    /api/v1/services/{service_id}/tools            : List tools for an Agent
  - POST   /api/v1/services/{service_id}/tools            : Register a new custom Tool
  - GET    /api/v1/services/{service_id}/tools/{tool_id}  : Get tool detail
  - PUT    /api/v1/services/{service_id}/tools/{tool_id}  : Update tool configuration
  - DELETE /api/v1/services/{service_id}/tools/{tool_id}  : Delete a tool
  - POST   /api/v1/services/{service_id}/tools/{tool_id}/test : Live test execution of a tool
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.core.security import encrypt_headers
from app.models.agent import Agent
from app.models.agent_tool import AgentTool, HttpMethod, ToolActionType
from app.models.service import Service
from app.models.user import User
from app.schemas.agent_tool import (
    AgentToolCreate,
    AgentToolResponse,
    AgentToolTestRequest,
    AgentToolTestResponse,
    AgentToolUpdate,
)
from app.services.tool_executor import execute_tool
from app.services.tool_validator import validate_endpoint_url

router = APIRouter(prefix="/services/{service_id}/tools", tags=["Agent Tools"])


async def _get_service_agent(
    service_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> tuple[Service, Agent]:
    """Helper to verify tenant ownership and get the Service's Agent."""
    stmt = (
        select(Service)
        .where(
            Service.id == service_id,
            Service.company_id == user.company_id,
        )
    )
    result = await db.execute(stmt)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dịch vụ không tồn tại trong tổ chức của bạn.",
        )

    agent_stmt = select(Agent).where(Agent.service_id == service_id)
    agent_res = await db.execute(agent_stmt)
    agent = agent_res.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dịch vụ này chưa được khởi tạo AI Agent. Vui lòng cấu hình Agent trước.",
        )

    return service, agent


@router.get(
    "",
    response_model=list[AgentToolResponse],
    summary="List all tools configured for a service's agent",
)
async def list_agent_tools(
    service_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve all active and inactive tools configured for the service's Agent."""
    _, agent = await _get_service_agent(service_id, current_user, db)

    stmt = (
        select(AgentTool)
        .where(AgentTool.agent_id == agent.id)
        .order_by(AgentTool.created_at.desc())
    )
    result = await db.execute(stmt)
    tools = list(result.scalars().all())

    # Build response models with has_headers flag
    responses = []
    for t in tools:
        resp = AgentToolResponse.model_validate(t)
        resp.has_headers = bool(t.encrypted_headers)
        responses.append(resp)

    return responses


@router.post(
    "",
    response_model=AgentToolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new custom tool for the Agent",
)
async def create_agent_tool(
    service_id: uuid.UUID,
    payload: AgentToolCreate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Register a new custom tool / action for the Agent.
    - Validates endpoint URL syntax (allows private IPs and http/https).
    - Encrypts authentication headers using Fernet before saving.
    """
    _, agent = await _get_service_agent(service_id, current_admin, db)

    # 1. Validate endpoint URL
    is_valid_url, url_err = validate_endpoint_url(payload.endpoint_url)
    if not is_valid_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=url_err,
        )

    # 2. Check for duplicate tool name in the same agent
    dup_stmt = select(AgentTool).where(
        AgentTool.agent_id == agent.id,
        AgentTool.name == payload.name.strip(),
    )
    dup = (await db.execute(dup_stmt)).scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Công cụ có tên '{payload.name}' đã tồn tại cho Agent này.",
        )

    # 3. Encrypt headers if provided
    enc_headers = None
    if payload.headers:
        enc_headers = encrypt_headers(payload.headers)

    # 4. Create record
    tool = AgentTool(
        agent_id=agent.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        parameters_schema=payload.parameters_schema,
        action_type=ToolActionType(payload.action_type.value),
        endpoint_url=payload.endpoint_url.strip(),
        http_method=HttpMethod(payload.http_method.value),
        encrypted_headers=enc_headers,
        is_active=payload.is_active,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    resp = AgentToolResponse.model_validate(tool)
    resp.has_headers = bool(tool.encrypted_headers)
    return resp


@router.get(
    "/{tool_id}",
    response_model=AgentToolResponse,
    summary="Get single tool details",
)
async def get_agent_tool(
    service_id: uuid.UUID,
    tool_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get single tool details by tool_id."""
    _, agent = await _get_service_agent(service_id, current_user, db)

    stmt = select(AgentTool).where(
        AgentTool.id == tool_id,
        AgentTool.agent_id == agent.id,
    )
    tool = (await db.execute(stmt)).scalar_one_or_none()

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Công cụ không tồn tại.",
        )

    resp = AgentToolResponse.model_validate(tool)
    resp.has_headers = bool(tool.encrypted_headers)
    return resp


@router.put(
    "/{tool_id}",
    response_model=AgentToolResponse,
    summary="Update tool configuration",
)
async def update_agent_tool(
    service_id: uuid.UUID,
    tool_id: uuid.UUID,
    payload: AgentToolUpdate,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update configuration of an existing tool."""
    _, agent = await _get_service_agent(service_id, current_admin, db)

    stmt = select(AgentTool).where(
        AgentTool.id == tool_id,
        AgentTool.agent_id == agent.id,
    )
    tool = (await db.execute(stmt)).scalar_one_or_none()

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Công cụ không tồn tại.",
        )

    # Validate URL if changed
    if payload.endpoint_url is not None:
        is_valid_url, url_err = validate_endpoint_url(payload.endpoint_url)
        if not is_valid_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=url_err,
            )
        tool.endpoint_url = payload.endpoint_url.strip()

    if payload.name is not None:
        tool.name = payload.name.strip()
    if payload.description is not None:
        tool.description = payload.description.strip()
    if payload.parameters_schema is not None:
        tool.parameters_schema = payload.parameters_schema
    if payload.action_type is not None:
        tool.action_type = ToolActionType(payload.action_type.value)
    if payload.http_method is not None:
        tool.http_method = HttpMethod(payload.http_method.value)
    if payload.is_active is not None:
        tool.is_active = payload.is_active

    if payload.headers is not None:
        tool.encrypted_headers = encrypt_headers(payload.headers) if payload.headers else None

    await db.commit()
    await db.refresh(tool)

    resp = AgentToolResponse.model_validate(tool)
    resp.has_headers = bool(tool.encrypted_headers)
    return resp


@router.delete(
    "/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tool",
)
async def delete_agent_tool(
    service_id: uuid.UUID,
    tool_id: uuid.UUID,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a tool from the Agent."""
    _, agent = await _get_service_agent(service_id, current_admin, db)

    stmt = select(AgentTool).where(
        AgentTool.id == tool_id,
        AgentTool.agent_id == agent.id,
    )
    tool = (await db.execute(stmt)).scalar_one_or_none()

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Công cụ không tồn tại.",
        )

    await db.delete(tool)
    await db.commit()


@router.post(
    "/{tool_id}/test",
    response_model=AgentToolTestResponse,
    summary="Live test an enterprise tool with sample parameters",
)
async def test_agent_tool(
    service_id: uuid.UUID,
    tool_id: uuid.UUID,
    payload: AgentToolTestRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Simulate a live tool call directly from the dashboard to verify connectivity
    and parameters handling against the enterprise API.
    """
    _, agent = await _get_service_agent(service_id, current_user, db)

    stmt = select(AgentTool).where(
        AgentTool.id == tool_id,
        AgentTool.agent_id == agent.id,
    )
    tool = (await db.execute(stmt)).scalar_one_or_none()

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Công cụ không tồn tại.",
        )

    # Execute tool via Action Gateway
    result = await execute_tool(tool, payload.test_parameters)

    return AgentToolTestResponse(
        success=result["success"],
        status_code=result["status_code"],
        response_time_ms=result["latency_ms"],
        data=result["data"],
        error=result["error"],
    )

