"""
Conversation Management Endpoints (Multi-Tenant Scoped).

Allows Company Admins and Staff to view, filter, track and manage chat transcripts
between their website visitors and their AI agents.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, desc
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.conversation import ConversationSession, ChatMessageRecord
from app.models.service import Service
from app.models.user import User
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationSessionResponse,
    ConversationUpdate,
    ChatMessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get(
    "/",
    response_model=list[ConversationSessionResponse],
    summary="List conversations for caller's company",
)
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service_id: uuid.UUID | None = Query(None, description="Filter by service"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status (active/resolved/needs_support)"),
    search: str | None = Query(None, alias="q", description="Search by title, visitor ID, or keywords"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List all conversation sessions scoped strictly to the current user's company.
    Supports filtering by service, status, and text search.
    """
    stmt = (
        select(ConversationSession)
        .join(Service, ConversationSession.service_id == Service.id)
        .where(Service.company_id == current_user.company_id)
        .options(joinedload(ConversationSession.service))
        .order_by(desc(ConversationSession.last_active_at))
    )

    if service_id:
        stmt = stmt.where(ConversationSession.service_id == service_id)

    if status_filter:
        stmt = stmt.where(ConversationSession.status == status_filter)

    if search:
        search_pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            (ConversationSession.title.ilike(search_pattern))
            | (ConversationSession.visitor_id.ilike(search_pattern))
        )

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    response: list[ConversationSessionResponse] = []
    for s in sessions:
        # Get preview of last user or assistant message if available
        last_msg_stmt = (
            select(ChatMessageRecord.content)
            .where(ChatMessageRecord.session_id == s.id)
            .order_by(desc(ChatMessageRecord.created_at))
            .limit(1)
        )
        last_msg_res = await db.execute(last_msg_stmt)
        last_preview = last_msg_res.scalar_one_or_none()
        if last_preview and len(last_preview) > 120:
            last_preview = last_preview[:117] + "..."

        response.append(
            ConversationSessionResponse(
                id=s.id,
                service_id=s.service_id,
                service_name=s.service.name if s.service else None,
                service_code=s.service.code if s.service else None,
                visitor_id=s.visitor_id,
                title=s.title or f"Khách #{s.visitor_id[:8]}",
                status=s.status,
                message_count=s.message_count,
                last_active_at=s.last_active_at,
                created_at=s.created_at,
                updated_at=s.updated_at,
                last_message_preview=last_preview,
            )
        )

    return response


@router.get(
    "/{session_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation details and full transcript",
)
async def get_conversation(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get full transcript of a single conversation session.
    """
    stmt = (
        select(ConversationSession)
        .join(Service, ConversationSession.service_id == Service.id)
        .where(
            ConversationSession.id == session_id,
            Service.company_id == current_user.company_id,
        )
        .options(
            joinedload(ConversationSession.service),
            selectinload(ConversationSession.messages),
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation session '{session_id}' not found.",
        )

    # Sort messages chronologically
    sorted_messages = sorted(session.messages, key=lambda m: m.created_at)

    return ConversationDetailResponse(
        id=session.id,
        service_id=session.service_id,
        service_name=session.service.name if session.service else None,
        service_code=session.service.code if session.service else None,
        visitor_id=session.visitor_id,
        title=session.title or f"Khách #{session.visitor_id[:8]}",
        status=session.status,
        message_count=session.message_count,
        last_active_at=session.last_active_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            ChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                sources=m.sources,
                created_at=m.created_at,
            )
            for m in sorted_messages
        ],
    )


@router.patch(
    "/{session_id}",
    response_model=ConversationSessionResponse,
    summary="Update conversation status or title",
)
async def update_conversation(
    session_id: uuid.UUID,
    payload: ConversationUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update the status (active, resolved, needs_support) or title of a session.
    """
    stmt = (
        select(ConversationSession)
        .join(Service, ConversationSession.service_id == Service.id)
        .where(
            ConversationSession.id == session_id,
            Service.company_id == current_user.company_id,
        )
        .options(joinedload(ConversationSession.service))
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation session '{session_id}' not found.",
        )

    if payload.status is not None:
        session.status = payload.status
    if payload.title is not None:
        session.title = payload.title

    await db.commit()
    await db.refresh(session)

    return ConversationSessionResponse(
        id=session.id,
        service_id=session.service_id,
        service_name=session.service.name if session.service else None,
        service_code=session.service.code if session.service else None,
        visitor_id=session.visitor_id,
        title=session.title or f"Khách #{session.visitor_id[:8]}",
        status=session.status,
        message_count=session.message_count,
        last_active_at=session.last_active_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation session and all its messages",
)
async def delete_conversation(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a conversation session and its messages (cascade).
    """
    stmt = (
        select(ConversationSession)
        .join(Service, ConversationSession.service_id == Service.id)
        .where(
            ConversationSession.id == session_id,
            Service.company_id == current_user.company_id,
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation session '{session_id}' not found.",
        )

    await db.delete(session)
    await db.commit()
    return None

