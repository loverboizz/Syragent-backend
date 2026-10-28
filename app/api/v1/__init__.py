"""
API v1 Router Aggregator.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.companies import router as companies_router
from app.api.v1.services import router as services_router
from app.api.v1.agents import router as agents_router
from app.api.v1.documents import router as documents_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.agent_tools import router as agent_tools_router
from app.api.v1.sandbox_erp import router as sandbox_erp_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(companies_router)
api_v1_router.include_router(services_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(agent_tools_router)
api_v1_router.include_router(sandbox_erp_router)
