"""
KnowledgeChunk Model.

Stores vectorized document chunks for RAG retrieval.
Each chunk is scoped to an Agent via agent_id FK, ensuring
strict data isolation between tenants' AI agents.

Uses pgvector for the embedding column with an HNSW index
for fast approximate nearest-neighbor search.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Gemini text-embedding-004 produces 768-dimensional vectors
EMBEDDING_DIMENSION = 768


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    # --- Primary Key (UUID) ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Agent FK (data isolation boundary) ---
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="RAG data isolation — each agent sees only its own chunks",
    )

    # --- Content ---
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The raw text chunk extracted from a document",
    )
    source: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="Source document filename or URL for citation",
    )
    chunk_index: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Position of this chunk within its source document",
    )

    # --- Vector Embedding ---
    embedding = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
        comment=f"pgvector embedding ({EMBEDDING_DIMENSION}d, Gemini text-embedding-004)",
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # --- Relationships ---
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="knowledge_chunks",
    )

    # --- Table Args ---
    __table_args__ = (
        # HNSW index for fast ANN vector similarity search.
        # cosine distance is the default metric for Gemini embeddings.
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if self.content else ""
        return f"<KnowledgeChunk(id={self.id}, preview='{preview}')>"

