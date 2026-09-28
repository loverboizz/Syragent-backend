"""
Vector Embedding Service.

Uses Google Gemini Embedding API (gemini-embedding-001) configured
with outputDimensionality=768 to generate dense semantic vector representations
compatible with the pgvector column `vector(768)` on Supabase.
"""

import asyncio
from typing import Any
import httpx

from app.core.config import settings

EMBEDDING_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
)
EMBEDDING_DIMENSION = 768


async def get_embedding(
    text: str,
    api_key: str | None = None,
) -> list[float]:
    """
    Generate a 768-dimensional vector embedding for a single text.
    Falls back to settings.GOOGLE_API_KEY if no custom key is provided.
    """
    key = api_key or settings.GOOGLE_API_KEY
    if not key:
        raise ValueError(
            "GOOGLE_API_KEY is not configured. Please set it in .env or provide an API key."
        )

    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": EMBEDDING_DIMENSION,
    }

    url = f"{EMBEDDING_API_URL}?key={key}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini Embedding API Error ({response.status_code}): {response.text}"
            )
        data = response.json()
        embedding_values = data.get("embedding", {}).get("values", [])

        if len(embedding_values) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSION} dimensions, but got {len(embedding_values)}"
            )

        return embedding_values


async def get_embeddings_batch(
    texts: list[str],
    api_key: str | None = None,
    concurrency_limit: int = 5,
) -> list[list[float]]:
    """
    Generate embeddings for multiple texts concurrently with a semaphore limit
    to respect Google Gemini rate limits.
    """
    semaphore = asyncio.Semaphore(concurrency_limit)

    async def _embed_with_semaphore(t: str) -> list[float]:
        async with semaphore:
            return await get_embedding(t, api_key=api_key)

    tasks = [_embed_with_semaphore(t) for t in texts]
    return await asyncio.gather(*tasks)

