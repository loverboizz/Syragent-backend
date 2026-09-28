"""
Pydantic Schemas for Agent entity.

Contains the critical @model_validator that enforces the AI Billing rules:
  - FREE tier  → api_key is ignored / set to None
  - BYOK tier  → api_key MUST be provided
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums (mirrors the SQLAlchemy enum but lives in the schema layer)
# ---------------------------------------------------------------------------
class AITierEnum(str, Enum):
    FREE = "FREE"
    BYOK = "BYOK"


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------
class AgentCreate(BaseModel):
    """
    Schema for creating/configuring an Agent for a Service.

    Core validation rule (enforced by @model_validator):
      - If ai_tier == 'FREE':  api_key is silently set to None.
      - If ai_tier == 'BYOK':  api_key MUST be a non-empty string.

    This ensures we never accidentally store a key for free-tier agents,
    and we always have a key before enabling BYOK billing.
    """

    service_id: uuid.UUID = Field(
        ...,
        description="The Service this Agent belongs to (1-to-1)",
    )
    llm_provider: str = Field(
        ...,
        min_length=1,
        max_length=50,
        examples=["google", "openai", "anthropic"],
    )
    model_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        examples=["gemini-1.5-flash", "gpt-4o", "claude-3.5-sonnet"],
    )
    ai_tier: AITierEnum = Field(
        default=AITierEnum.FREE,
        description="FREE uses global API key; BYOK requires customer's own key",
    )
    api_key: str | None = Field(
        default=None,
        description="Plaintext API key (will be encrypted before storage). "
                    "Required for BYOK, ignored for FREE.",
    )

    @model_validator(mode="after")
    def validate_api_key_by_tier(self) -> "AgentCreate":
        """
        Enforce the AI billing strategy:

        1. BYOK tier → api_key is mandatory.
           If missing or empty, raise a clear validation error.

        2. FREE tier → api_key is forcibly cleared to None.
           Even if the client accidentally sends a key, we discard it
           so it's never stored or processed.
        """
        if self.ai_tier == AITierEnum.BYOK:
            if not self.api_key or not self.api_key.strip():
                raise ValueError(
                    "api_key is required when ai_tier is 'BYOK'. "
                    "Please provide your API key for the selected provider."
                )
            # Strip whitespace from the key
            self.api_key = self.api_key.strip()
        else:
            # FREE tier — discard any accidentally provided key
            self.api_key = None

        return self


class AgentUpdate(BaseModel):
    """
    Partial update schema for Agent configuration.
    Same tier/key validation applies.
    """

    llm_provider: str | None = Field(default=None, min_length=1, max_length=50)
    model_name: str | None = Field(default=None, min_length=1, max_length=100)
    ai_tier: AITierEnum | None = None
    api_key: str | None = None

    @model_validator(mode="after")
    def validate_api_key_by_tier(self) -> "AgentUpdate":
        """
        Same BYOK/FREE rule, but only triggers when ai_tier is
        explicitly included in the update payload.
        """
        if self.ai_tier is not None:
            if self.ai_tier == AITierEnum.BYOK:
                if not self.api_key or not self.api_key.strip():
                    raise ValueError(
                        "api_key is required when switching to BYOK tier."
                    )
                self.api_key = self.api_key.strip()
            else:
                self.api_key = None

        return self


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------
class AgentResponse(BaseModel):
    """
    Schema returned to the client.
    NEVER exposes the encrypted_api_key — only whether one is configured.
    """

    id: uuid.UUID
    service_id: uuid.UUID
    llm_provider: str
    model_name: str
    ai_tier: AITierEnum
    has_api_key: bool = Field(
        description="True if a BYOK key is configured (never exposes the actual key)",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

