"""
Async Database Engine & Session Factory.

Uses SQLAlchemy 2.0 async API with asyncpg driver to connect
to Supabase PostgreSQL (with pgvector extension).
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ---------------------------------------------------------------------------
# Engine — single connection pool shared across the application
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_development,  # Log SQL in dev mode
    pool_pre_ping=True,            # Verify connections before checkout
    pool_recycle=300,              # Recycle connections every 5 mins to prevent stale cloud sockets
    pool_size=10,
    max_overflow=20,
)

# ---------------------------------------------------------------------------
# Session factory — produces scoped AsyncSession instances
# ---------------------------------------------------------------------------
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
)


# ---------------------------------------------------------------------------
# Declarative Base — all ORM models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    Provides the metadata registry that Alembic uses for migrations.
    """
    pass


# ---------------------------------------------------------------------------
# Dependency — yields an AsyncSession per request (FastAPI Depends)
# ---------------------------------------------------------------------------
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a database session.
    Commits on success, rolls back on exception, and always closes.

    Usage:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

