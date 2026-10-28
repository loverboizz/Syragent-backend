"""
Pydantic Schemas for Document Ingestion & RAG Queries.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingestion Schemas
# ---------------------------------------------------------------------------
class DocumentIngestTextRequest(BaseModel):
    """Payload for directly submitting raw text or Markdown as knowledge."""

    content: str = Field(
        ...,
        min_length=10,
        description="Full text or markdown content to be chunked and vectorized",
        examples=["Chính sách hoàn tiền: Khách hàng được hoàn 100% trong vòng 14 ngày..."],
    )
    source: str = Field(
        default="manual_input",
        max_length=2048,
        description="Identifier or title of the source document for citation",
        examples=["Chinh_sach_hoan_tien.pdf"],
    )


class IngestResponse(BaseModel):
    """Summary returned after ingesting and vectorizing a single document."""

    agent_id: uuid.UUID
    chunks_created: int
    source: str
    message: str


class FileIngestResult(BaseModel):
    """Result of processing an individual file in a batch upload."""

    filename: str
    chunks_created: int
    status: str = "success"
    error: str | None = None


class BatchIngestResponse(BaseModel):
    """Summary returned after batch uploading multiple documents."""

    agent_id: uuid.UUID
    total_chunks_created: int
    files_processed: list[FileIngestResult]
    message: str


# ---------------------------------------------------------------------------
# Knowledge Chunk Schemas
# ---------------------------------------------------------------------------
class KnowledgeChunkResponse(BaseModel):
    """Schema for returning a vectorized knowledge chunk without the raw 768-d vector."""

    id: uuid.UUID
    agent_id: uuid.UUID
    content: str
    source: str | None = None
    chunk_index: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# RAG Query Schemas (Chat)
# ---------------------------------------------------------------------------
class RAGQueryRequest(BaseModel):
    """User message / question submitted to the RAG chat agent."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The customer's inquiry or prompt",
        examples=["Chính sách đổi trả hàng áp dụng trong bao lâu?"],
    )
    visitor_id: str | None = Field(
        default=None,
        max_length=100,
        description="Anonymous visitor identifier stored on client browser",
    )


class RAGQueryResponse(BaseModel):
    """AI Agent generated answer accompanied by citation sources."""

    answer: str
    sources: list[str] = Field(
        default_factory=list,
        description="List of document sources referenced to construct the answer",
    )
    traces: dict[str, Any] | None = Field(
        default=None,
        description="Detailed ReAct execution trace (Reasoning, Tool Calls, Latencies)",
    )

