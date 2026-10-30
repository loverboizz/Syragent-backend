"""
Pydantic Schemas for Agent entity (Syragent Managed AI Infrastructure).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------
class AgentCreate(BaseModel):
    """
    Schema for creating/configuring a managed AI Agent for a Service.
    All LLM execution runs through Syragent's centralized infrastructure.
    """

    service_id: uuid.UUID = Field(
        ...,
        description="The Service this Agent belongs to (1-to-1)",
    )
    llm_provider: str = Field(
        default="google",
        min_length=1,
        max_length=50,
        examples=["google", "openai", "anthropic", "deepseek", "groq"],
    )
    model_name: str = Field(
        default="models/gemini-3.6-flash",
        min_length=1,
        max_length=100,
        examples=[
            "models/gemini-3.6-flash",
            "models/gemini-3.1-pro-preview",
            "gpt-4o-mini",
            "gpt-4o",
            "claude-3-5-sonnet-latest",
            "deepseek-chat",
        ],
    )


class AgentUpdate(BaseModel):
    """
    Partial update schema for Agent managed LLM configuration.
    """

    llm_provider: str | None = Field(default=None, min_length=1, max_length=50)
    model_name: str | None = Field(default=None, min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------
class AgentResponse(BaseModel):
    """
    Schema returned to the client for a configured Agent.
    """

    id: uuid.UUID
    service_id: uuid.UUID
    llm_provider: str
    model_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
