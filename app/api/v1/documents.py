"""
Document Ingestion & Knowledge Base Management Endpoints.

Handles:
  - POST   /api/v1/agents/{agent_id}/documents/text   : Ingest raw text/markdown
  - POST   /api/v1/agents/{agent_id}/documents/upload : Upload document files (.txt, .md, .pdf, .docx, .xlsx, .html)
  - GET    /api/v1/agents/{agent_id}/documents        : List knowledge chunks of an Agent
  - DELETE /api/v1/agents/{agent_id}/documents/{id}   : Delete a single chunk
  - DELETE /api/v1/agents/{agent_id}/documents        : Wipe all chunks for an Agent
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_super_admin
from app.models.agent import Agent
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.service import Service
from app.models.user import User
from app.schemas.document import (
    BatchIngestResponse,
    DocumentIngestTextRequest,
    FileIngestResult,
    IngestResponse,
    KnowledgeChunkResponse,
)
from app.services.document_processor import extract_text_from_file, split_text
from app.services.embedding import get_embeddings_batch

router = APIRouter(prefix="/agents/{agent_id}/documents", tags=["Knowledge Base"])


async def _verify_agent_tenant(
    agent_id: uuid.UUID,
    company_id: uuid.UUID,
    db: AsyncSession,
) -> Agent:
    """Helper to verify agent exists and belongs to the caller's company."""
    query = (
        select(Agent)
        .join(Service, Agent.service_id == Service.id)
        .where(
            Agent.id == agent_id,
            Service.company_id == company_id,
        )
    )
    result = await db.execute(query)
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found in your organization.",
        )
    return agent


@router.post(
    "/text",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest raw text or markdown into Agent's knowledge base",
)
async def ingest_text(
    agent_id: uuid.UUID,
    payload: DocumentIngestTextRequest,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Ingest plaintext/markdown:
      1. Chunks content semantically (~600 chars with 100 char overlap).
      2. Generates 768-d vector embeddings concurrently via Gemini.
      3. Saves to knowledge_chunks with agent_id isolation.
    """
    await _verify_agent_tenant(agent_id, current_admin.company_id, db)

    # 1. Chunk text
    chunks = split_text(payload.content)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text content is empty or contains only whitespace.",
        )

    # 2. Generate embeddings
    embeddings = await get_embeddings_batch(chunks)

    # 3. Store chunks
    for idx, (chunk_text, vector) in enumerate(zip(chunks, embeddings)):
        db_chunk = KnowledgeChunk(
            agent_id=agent_id,
            content=chunk_text,
            source=payload.source,
            chunk_index=idx,
            embedding=vector,
        )
        db.add(db_chunk)

    await db.flush()

    return IngestResponse(
        agent_id=agent_id,
        chunks_created=len(chunks),
        source=payload.source,
        message=f"Successfully vectorized and stored {len(chunks)} chunks.",
    )


@router.post(
    "/upload",
    response_model=BatchIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more files (.pdf, .docx, .xlsx, .html, .txt) to Agent's knowledge base",
)
async def upload_documents(
    agent_id: uuid.UUID,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    files: list[UploadFile] = File(None),
    file: UploadFile | None = File(None),
):
    """
    Upload and parse one or multiple files in batch:
      - Supports PDF, Word (.docx), Excel (.xlsx, .xls), Markdown, HTML, and TXT files
      - Extracts text, performs semantic chunking, and batch-embeds vectors
      - Fully backward compatible with single 'file' and multi 'files' form data
    """
    await _verify_agent_tenant(agent_id, current_admin.company_id, db)

    # Collect all provided files
    target_files: list[UploadFile] = []
    if files:
        target_files.extend(files)
    if file:
        target_files.append(file)

    if not target_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files were provided for upload.",
        )

    files_processed: list[FileIngestResult] = []
    all_chunks_to_embed: list[str] = []
    chunk_metadata: list[tuple[str, int]] = []  # (filename, chunk_index)

    for upload_file in target_files:
        fname = upload_file.filename or "unknown"
        try:
            content = await upload_file.read()
            if not content:
                files_processed.append(
                    FileIngestResult(
                        filename=fname,
                        chunks_created=0,
                        status="error",
                        error="File is empty",
                    )
                )
                continue

            raw_text = extract_text_from_file(fname, content)
            if not raw_text:
                files_processed.append(
                    FileIngestResult(
                        filename=fname,
                        chunks_created=0,
                        status="error",
                        error="No readable text extracted",
                    )
                )
                continue

            chunks = split_text(raw_text)
            if not chunks:
                files_processed.append(
                    FileIngestResult(
                        filename=fname,
                        chunks_created=0,
                        status="error",
                        error="File produced no valid chunks",
                    )
                )
                continue

            for idx, c in enumerate(chunks):
                all_chunks_to_embed.append(c)
                chunk_metadata.append((fname, idx))

            files_processed.append(
                FileIngestResult(
                    filename=fname,
                    chunks_created=len(chunks),
                    status="success",
                )
            )
        except Exception as e:
            files_processed.append(
                FileIngestResult(
                    filename=fname,
                    chunks_created=0,
                    status="error",
                    error=str(e),
                )
            )

    if not all_chunks_to_embed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="None of the uploaded files could be parsed or chunked.",
        )

    # Batch embed all chunks across all files
    embeddings = await get_embeddings_batch(all_chunks_to_embed)

    # Save all chunks to database
    for chunk_text, vector, (filename, chunk_idx) in zip(
        all_chunks_to_embed, embeddings, chunk_metadata
    ):
        db_chunk = KnowledgeChunk(
            agent_id=agent_id,
            content=chunk_text,
            source=filename,
            chunk_index=chunk_idx,
            embedding=vector,
        )
        db.add(db_chunk)

    await db.flush()

    total_chunks = len(all_chunks_to_embed)
    success_count = sum(1 for f in files_processed if f.status == "success")

    return BatchIngestResponse(
        agent_id=agent_id,
        total_chunks_created=total_chunks,
        files_processed=files_processed,
        message=f"Đã vector hóa thành công {total_chunks} đoạn tri thức từ {success_count}/{len(target_files)} file.",
    )



@router.get(
    "",
    response_model=list[KnowledgeChunkResponse],
    summary="List all knowledge chunks for an Agent",
)
async def list_agent_chunks(
    agent_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Retrieve chunks belonging to the agent (multi-tenant isolated)."""
    await _verify_agent_tenant(agent_id, current_user.company_id, db)

    query = (
        select(KnowledgeChunk)
        .where(KnowledgeChunk.agent_id == agent_id)
        .order_by(KnowledgeChunk.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.delete(
    "/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single knowledge chunk",
)
async def delete_chunk(
    agent_id: uuid.UUID,
    chunk_id: uuid.UUID,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a specific chunk belonging to the agent."""
    await _verify_agent_tenant(agent_id, current_admin.company_id, db)

    stmt = delete(KnowledgeChunk).where(
        KnowledgeChunk.id == chunk_id,
        KnowledgeChunk.agent_id == agent_id,
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found.",
        )
    return None


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Wipe all knowledge chunks or delete by source document",
)
async def delete_all_chunks(
    agent_id: uuid.UUID,
    current_admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source: str | None = Query(default=None, description="Optional: delete only chunks from this source document"),
):
    """Delete all chunks belonging to an agent or filter by source."""
    await _verify_agent_tenant(agent_id, current_admin.company_id, db)

    stmt = delete(KnowledgeChunk).where(KnowledgeChunk.agent_id == agent_id)
    if source:
        stmt = stmt.where(KnowledgeChunk.source == source)

    await db.execute(stmt)
    return None
