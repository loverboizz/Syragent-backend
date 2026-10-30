"""
Public Chat Endpoint for Embedded Widget & RAG Inference.

Handles:
  - POST /api/v1/chat/{service_code} : Ask a question to a Service's AI Agent
  - Origin / Domain Whitelist security validation against service.service_url
  - Vector similarity search (HNSW Cosine) + LLM Response Generation
"""

from urllib.parse import urlparse
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.agent import Agent
from app.models.company import Company
from app.models.service import Service
from app.models.user import User
from app.models.conversation import ConversationSession, ChatMessageRecord
from app.schemas.document import RAGQueryRequest, RAGQueryResponse
from app.schemas.conversation import VisitorHistoryResponse, ChatMessageResponse
from app.services.rag_service import answer_rag_query, stream_rag_query

router = APIRouter(prefix="/chat", tags=["Chat"])


async def _build_authenticated_user_context(
    authorization: str | None,
    db: AsyncSession,
) -> str:
    """
    If the widget visitor is logged into the Syragent dashboard and passes a valid
    Bearer JWT token, resolve their User, Company, and owned Services so the AI Agent
    automatically knows who they are and which service_codes belong to them.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return ""
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return ""

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return ""

    try:
        import uuid as _uuid
        user_id = _uuid.UUID(str(payload["sub"]))
        user_res = await db.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        if not user:
            return ""

        comp_res = await db.execute(select(Company).where(Company.id == user.company_id))
        company = comp_res.scalar_one_or_none()

        svc_res = await db.execute(select(Service).where(Service.company_id == user.company_id))
        services = svc_res.scalars().all()

        svc_descriptions = [
            f"{s.code} (Tên: '{s.name}', Trạng thái: {'Đang bật' if s.is_active else 'Tạm ngưng'}, URL: {s.service_url})"
            for s in services
        ]
        svc_str = "; ".join(svc_descriptions) if svc_descriptions else "Chưa tạo dịch vụ nào"

        return (
            f"[NGỮ CẢNH HỆ THỐNG - NGƯỜI DÙNG SYRAGENT ĐANG ĐĂNG NHẬP: "
            f"Email='{user.email}', Công ty='{company.name if company else 'N/A'}', "
            f"Danh sách dịch vụ sở hữu (service_code): {svc_str}. "
            f"Nếu người dùng hỏi kiểm tra dịch vụ hoặc lấy mã nhúng của họ mà không ghi rõ mã, "
            f"hãy chủ động dùng service_code trong danh sách trên để gọi công cụ hỗ trợ.]\n"
        )
    except Exception:
        return ""


def _verify_origin_whitelist(
    origin: str | None,
    referer: str | None,
    allowed_service_url: str,
) -> bool:
    """
    Validate that the incoming request originates from the domain whitelisted
    in `service.service_url`.
    """
    # In development mode, allow direct client calls, local files (file:// or origin: null), and localhost
    if settings.is_development:
        if not origin and not referer:
            return True
        if origin == "null" or (origin and origin.startswith("file:")):
            return True
        if referer and referer.startswith("file:"):
            return True

    caller_header = origin or referer
    if not caller_header:
        # If neither Origin nor Referer is provided in production, reject
        return False

    caller_netloc = urlparse(caller_header).netloc.lower()
    allowed_netloc = urlparse(allowed_service_url).netloc.lower()

    # In development, allow requests from localhost / 127.0.0.1 on any port (e.g. 5500, 8000, 3000)
    if settings.is_development:
        caller_host = caller_netloc.split(":")[0]
        if caller_host in ("localhost", "127.0.0.1"):
            return True

    # Allow exact match or port differences in development (e.g. localhost:3000)
    if caller_netloc == allowed_netloc:
        return True

    # Strip port numbers for comparison (e.g., mysite.com:443 -> mysite.com)
    caller_host = caller_netloc.split(":")[0]
    allowed_host = allowed_netloc.split(":")[0]
    return caller_host == allowed_host


@router.post(
    "/{service_code}",
    response_model=RAGQueryResponse,
    summary="Ask a question to the AI Agent of a Service (Public Chat Widget endpoint)",
)
async def chat_with_service_agent(
    service_code: str,
    payload: RAGQueryRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    origin: Annotated[str | None, Header()] = None,
    referer: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
):
    """
    Public Chat Endpoint:
      1. Resolves the Service by its unique slug `service_code`.
      2. Enforces active status (`is_active=True`).
      3. Validates Origin/Referer against `service.service_url` to prevent widget abuse.
      4. Executes RAG search on `knowledge_chunks` filtered by `agent_id`.
      5. Calls the LLM to generate an accurate, grounded answer with source citations.
    """
    # 1. Fetch Service with attached Agent
    query = (
        select(Service)
        .options(selectinload(Service.agent))
        .where(
            Service.code == service_code,
            Service.is_active.is_(True),
        )
    )
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found or is currently inactive.",
        )

    # 2. Check Origin Whitelist
    if not settings.is_development:
        if not _verify_origin_whitelist(origin, referer, service.service_url):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request origin is not authorized to interact with this service widget.",
            )

    # 3. Verify Agent configuration
    agent = service.agent
    if not agent:
        return RAGQueryResponse(
            answer="Dịch vụ này hiện chưa được kích hoạt Trợ lý AI. Vui lòng liên hệ quản trị viên.",
            sources=[],
        )

    # 4. Run RAG Pipeline (with automatic logged-in Syragent user context if token provided)
    user_ctx = await _build_authenticated_user_context(authorization, db)
    enriched_query = f"{user_ctx}{payload.question}" if user_ctx else payload.question

    try:
        answer, sources, traces = await answer_rag_query(
            db=db,
            agent=agent,
            service_name=service.name,
            query=enriched_query,
        )
    except Exception as exc:
        if settings.is_development:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"RAG Inference failed: {str(exc)}",
            )
        return RAGQueryResponse(
            answer="Hệ thống đang bận hoặc gặp sự cố khi xử lý câu hỏi. Vui lòng thử lại sau.",
            sources=[],
            traces=None,
        )

    return RAGQueryResponse(answer=answer, sources=sources, traces=traces)


@router.post(
    "/{service_code}/stream",
    summary="Ask a question and receive real-time SSE stream tokens (Public Chat Widget streaming endpoint)",
)
async def chat_stream_with_service_agent(
    service_code: str,
    payload: RAGQueryRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    origin: Annotated[str | None, Header()] = None,
    referer: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
):
    """
    Real-Time Streaming Chat Endpoint (Server-Sent Events):
      1. Resolves Service by unique slug `service_code`.
      2. Enforces active status (`is_active=True`).
      3. Validates Origin/Referer whitelist against `service.service_url` in production.
      4. Streams vector citations and LLM-generated tokens as SSE events.
    """
    # 1. Fetch Service with attached Agent
    query = (
        select(Service)
        .options(selectinload(Service.agent))
        .where(
            Service.code == service_code,
            Service.is_active.is_(True),
        )
    )
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found or is currently inactive.",
        )

    # 2. Check Origin Whitelist
    if not settings.is_development:
        if not _verify_origin_whitelist(origin, referer, service.service_url):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request origin is not authorized to interact with this service widget.",
            )

    # 3. Verify Agent configuration
    agent = service.agent
    if not agent:
        async def no_agent_stream():
            import json
            yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'token': 'Dịch vụ này hiện chưa được kích hoạt Trợ lý AI. Vui lòng liên hệ quản trị viên.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            no_agent_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 4. Manage Session and Conversation History
    visitor_id = (payload.visitor_id or "").strip()
    if not visitor_id:
        import uuid as _uuid
        visitor_id = f"visitor_{_uuid.uuid4().hex[:12]}"

    # Find existing session for this (service_id, visitor_id)
    session_stmt = (
        select(ConversationSession)
        .where(
            ConversationSession.service_id == service.id,
            ConversationSession.visitor_id == visitor_id,
        )
    )
    session_res = await db.execute(session_stmt)
    session = session_res.scalar_one_or_none()

    if not session:
        session = ConversationSession(
            service_id=service.id,
            visitor_id=visitor_id,
            title=payload.question[:120].strip(),
            status="active",
            message_count=1,
        )
        db.add(session)
        await db.flush()
    else:
        session.message_count += 1
        if not session.title or session.title.startswith("Khách #"):
            session.title = payload.question[:120].strip()

    # Load last 6 messages for multi-turn context
    history_stmt = (
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == session.id)
        .order_by(ChatMessageRecord.created_at.desc())
        .limit(6)
    )
    history_res = await db.execute(history_stmt)
    prior_records = list(reversed(history_res.scalars().all()))
    chat_history = [{"role": m.role, "content": m.content} for m in prior_records]

    # Save user message
    user_record = ChatMessageRecord(
        session_id=session.id,
        role="user",
        content=payload.question.strip(),
    )
    db.add(user_record)
    await db.commit()

    session_id = session.id

    # Async callback to persist assistant response when streaming finishes
    async def save_assistant_reply(
        full_text: str,
        cited_sources: list[str],
        traces: dict | None = None,
    ):
        if not full_text:
            return
        from app.core.database import async_session_factory
        from sqlalchemy import update
        async with async_session_factory() as s_db:
            sources_json = [{"source": s} for s in cited_sources] if cited_sources else None
            assistant_record = ChatMessageRecord(
                session_id=session_id,
                role="assistant",
                content=full_text,
                sources=sources_json,
                traces=traces,
            )
            s_db.add(assistant_record)
            sess_update = (
                update(ConversationSession)
                .where(ConversationSession.id == session_id)
                .values(
                    message_count=ConversationSession.message_count + 1,
                    last_active_at=func.now(),
                )
            )
            await s_db.execute(sess_update)
            await s_db.commit()

    # 5. Stream RAG Pipeline (with automatic logged-in Syragent user context if token provided)
    user_ctx = await _build_authenticated_user_context(authorization, db)
    enriched_query = f"{user_ctx}{payload.question}" if user_ctx else payload.question

    return StreamingResponse(
        stream_rag_query(
            db=db,
            agent=agent,
            service_name=service.name,
            query=enriched_query,
            chat_history=chat_history,
            on_complete=save_assistant_reply,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{service_code}/history",
    response_model=VisitorHistoryResponse,
    summary="Public endpoint: Get message history for a visitor",
)
async def get_visitor_chat_history(
    service_code: str,
    visitor_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    origin: Annotated[str | None, Header()] = None,
    referer: Annotated[str | None, Header()] = None,
):
    """
    Public endpoint for widget.js to restore previous conversation messages
    when returning to the site.
    """
    query = select(Service).where(Service.code == service_code)
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service or not service.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found or inactive.",
        )

    if not _verify_origin_whitelist(origin, referer, service.service_url):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Domain not whitelisted.",
        )

    if not visitor_id or not visitor_id.strip():
        return VisitorHistoryResponse(session_id=None, status="active", messages=[])

    session_stmt = (
        select(ConversationSession)
        .options(selectinload(ConversationSession.messages))
        .where(
            ConversationSession.service_id == service.id,
            ConversationSession.visitor_id == visitor_id.strip(),
        )
    )
    session_res = await db.execute(session_stmt)
    session = session_res.scalar_one_or_none()

    if not session:
        return VisitorHistoryResponse(session_id=None, status="active", messages=[])

    sorted_messages = sorted(session.messages, key=lambda m: m.created_at)
    return VisitorHistoryResponse(
        session_id=session.id,
        status=session.status,
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


@router.get(
    "/{service_code}/config",
    summary="Public endpoint: Get Widget visual configuration for a Service",
)
async def get_widget_config(
    service_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    origin: Annotated[str | None, Header()] = None,
    referer: Annotated[str | None, Header()] = None,
):
    """
    Public configuration endpoint for widget.js.
    Returns theme colors, greeting, avatar, title, and starter prompts.
    """
    query = select(Service).where(Service.code == service_code)
    result = await db.execute(query)
    service = result.scalar_one_or_none()

    if not service or not service.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found or is currently paused.",
        )

    # Origin verification
    if not _verify_origin_whitelist(origin, referer, service.service_url):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Domain not whitelisted for this service.",
        )

    default_cfg = {
        "agent_name": service.name or "Trợ Lý AI",
        "avatar_type": "emoji",
        "avatar_value": "🤖",
        "primary_color": "#0284c7",
        "subtitle": "Trực tuyến • Phản hồi 24/7",
        "greeting": f"Xin chào Quý khách! 👋 Em là Trợ lý AI của {service.name}. Quý khách cần hỗ trợ thông tin gì ạ?",
        "position": "right",
        "starter_prompts": ["Báo giá dịch vụ", "Chính sách bảo hành", "Liên hệ tư vấn viên"],
    }

    cfg = service.widget_config or {}
    merged = {**default_cfg, **cfg}

    return {
        "service_code": service.code,
        "service_name": service.name,
        "is_active": service.is_active,
        "widget_config": merged,
    }


