"""
FastAPI Application Entry Point.

Configures:
  - FastAPI app with metadata
  - CORS middleware (using origins from settings)
  - Lifespan events (DB engine startup/shutdown)
  - Health check endpoint
  - API router mounting point (v1)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine

# Import all models so SQLAlchemy metadata is fully populated.
# This is essential for Alembic migration auto-generation.
import app.models  # noqa: F401


# ---------------------------------------------------------------------------
# Lifespan — manages async resources (DB engine pool)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Log connection info (engine is already created at import time).
    Shutdown: Dispose the connection pool cleanly.
    """
    print(f"[STARTUP] Starting {settings.APP_NAME} ({settings.APP_ENV})")
    print(f"[DATABASE] Connected: {settings.DATABASE_URL[:40]}...")
    yield
    # Shutdown — close all pooled connections
    await engine.dispose()
    print("[SHUTDOWN] Database connections closed. Goodbye!")


# ---------------------------------------------------------------------------
# FastAPI App Instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Multi-Tenant AI Agent Platform for Service Management. "
        "Each service gets a dedicated RAG-based AI agent with "
        "Freemium + BYOK billing."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)


# ---------------------------------------------------------------------------
# CORS Middleware (Allow all origins for embeddable public widget)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health Check & Static Files
# ---------------------------------------------------------------------------
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health", tags=["System"])
async def health_check():
    """Simple health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }


@app.get("/widget.js", include_in_schema=False)
async def get_widget_js():
    """Direct URL to serve the embeddable chat widget script."""
    widget_path = STATIC_DIR / "widget.js"
    return FileResponse(widget_path, media_type="application/javascript")


# ---------------------------------------------------------------------------
# API Routers
# ---------------------------------------------------------------------------
from app.api.v1 import api_v1_router

app.include_router(api_v1_router, prefix="/api/v1")

