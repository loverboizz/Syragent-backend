"""
RAG Service: Semantic Search & LLM Response Generation.

Handles:
  - Vector similarity search with pgvector (cosine distance on HNSW index)
  - Strict tenant isolation (filtering by agent_id)
  - Prompt construction with retrieved context & sources
  - Multi-provider LLM response generation (Gemini Free Tier & BYOK OpenAI/Gemini/Anthropic)
"""

import json
import uuid
from typing import Any
from typing import Any, AsyncIterator
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_api_key
from app.models.agent import Agent, AITier
from app.models.agent_tool import AgentTool
from app.models.knowledge_chunk import KnowledgeChunk
from app.services.embedding import get_embedding
from app.services.agent_runner import TraceCollector, run_react_agent_gemini


# ---------------------------------------------------------------------------
# 1. Vector Retrieval (Semantic Search)
# ---------------------------------------------------------------------------
async def search_relevant_chunks(
    db: AsyncSession,
    agent_id: uuid.UUID,
    query_text: str,
    top_k: int = 4,
) -> list[KnowledgeChunk]:
    """
    Search for the most semantically relevant knowledge chunks for a given query:
      1. Converts `query_text` into a 768-d vector embedding via Gemini.
      2. Runs approximate nearest neighbor (ANN) vector search on pgvector
         using cosine distance on the HNSW index.
      3. Strictly filters by `agent_id` for multi-tenant data isolation.
    """
    # Generate query embedding
    query_vector = await get_embedding(query_text)

    # Perform cosine similarity search filtered by agent_id
    stmt = (
        select(KnowledgeChunk)
        .where(
            KnowledgeChunk.agent_id == agent_id,
            KnowledgeChunk.embedding.is_not(None),
        )
        .order_by(KnowledgeChunk.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 2. LLM Call Helpers (Gemini & OpenAI)
# ---------------------------------------------------------------------------
async def _call_gemini_generate(
    api_key: str,
    model_name: str,
    prompt: str,
) -> str:
    """Call Google Gemini generateContent API."""
    target_model = model_name or "gemini-3.6-flash"
    if target_model.startswith("models/"):
        target_model = target_model[len("models/"):]
    
    # Automatically map legacy or generic flash models to modern available version
    if target_model in ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-flash"]:
        target_model = "gemini-3.6-flash"
    elif target_model in ["gemini-1.5-pro", "gemini-2.5-pro", "gemini-pro"]:
        target_model = "gemini-3.1-pro-preview"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024,
            "maxOutputTokens": 4096,
        }
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await client.post(url, json=payload)
        if res.status_code != 200:
            raise RuntimeError(f"Gemini API Error ({res.status_code}): {res.text}")
        data = res.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return "Xin lỗi, hiện tại tôi không thể sinh câu trả lời. Vui lòng thử lại sau."
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()


async def _call_openai_generate(
    api_key: str,
    model_name: str,
    prompt: str,
) -> str:
    """Call OpenAI Chat Completions API."""
    target_model = model_name if model_name else "gpt-4o"
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": target_model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await client.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            raise RuntimeError(f"OpenAI API Error ({res.status_code}): {res.text}")
        data = res.json()
        choices = data.get("choices", [])
        if not choices:
            return "Xin lỗi, hiện tại không thể kết nối tới mô hình AI."
        return choices[0].get("message", {}).get("content", "").strip()


async def _call_gemini_stream(
    api_key: str,
    model_name: str,
    prompt: str,
) -> AsyncIterator[str]:
    """Call Google Gemini streamGenerateContent API via SSE."""
    target_model = model_name or "gemini-3.6-flash"
    if target_model.startswith("models/"):
        target_model = target_model[len("models/"):]

    # Automatically map legacy or generic flash models to modern available version
    if target_model in ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-flash"]:
        target_model = "gemini-3.6-flash"
    elif target_model in ["gemini-1.5-pro", "gemini-2.5-pro", "gemini-pro"]:
        target_model = "gemini-3.1-pro-preview"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:streamGenerateContent?alt=sse&key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                err_body = await response.aread()
                raise RuntimeError(
                    f"Gemini Streaming Error ({response.status_code}): {err_body.decode('utf-8', errors='ignore')}"
                )

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                json_str = line[6:].strip()
                if not json_str:
                    continue
                try:
                    chunk = json.loads(json_str)
                    candidates = chunk.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                yield text
                except json.JSONDecodeError:
                    continue


async def _call_openai_stream(
    api_key: str,
    model_name: str,
    prompt: str,
) -> AsyncIterator[str]:
    """Call OpenAI Chat Completions API with streaming enabled."""
    target_model = model_name if model_name else "gpt-4o"
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": target_model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code != 200:
                err_body = await response.aread()
                raise RuntimeError(
                    f"OpenAI Streaming Error ({response.status_code}): {err_body.decode('utf-8', errors='ignore')}"
                )

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue


# ---------------------------------------------------------------------------
# 3. Prompt Construction & Full RAG Pipeline
# ---------------------------------------------------------------------------
def build_rag_prompt(
    service_name: str,
    query: str,
    chunks: list[KnowledgeChunk],
    chat_history: list[dict] | None = None,
) -> str:
    """Construct a grounding prompt with system instructions, conversation history, and retrieved context."""
    if chunks:
        context_sections = []
        for i, chunk in enumerate(chunks, 1):
            src = f" [Nguồn: {chunk.source}]" if chunk.source else ""
            context_sections.append(f"--- Đoạn {i}{src} ---\n{chunk.content}")
        context_text = "\n\n".join(context_sections)
    else:
        context_text = "(Chưa có tài liệu nội bộ nào được cung cấp cho dịch vụ này)"

    history_text = ""
    if chat_history:
        history_lines = []
        for msg in chat_history:
            speaker = "Khách hàng" if msg.get("role") == "user" else "Trợ lý AI"
            history_lines.append(f"- {speaker}: {msg.get('content', '').strip()}")
        if history_lines:
            history_text = "\n\nLỊCH SỬ TRÒ CHUYỆN GẦN ĐÂY:\n" + "\n".join(history_lines)

    prompt = f"""Bạn là Trợ lý AI chuyên nghiệp đại diện cho dịch vụ "{service_name}".
Hãy sử dụng LỊCH SỬ TRÒ CHUYỆN và NGỮ CẢNH TÀI LIỆU DƯỚI ĐÂY để trả lời câu hỏi của khách hàng một cách lịch sự, chính xác và súc tích.

QUY TẮC BẮT BUỘC:
1. Chỉ trả lời dựa trên thông tin có trong NGỮ CẢNH TÀI LIỆU và diễn biến câu chuyện trước đó.
2. Nếu ngữ cảnh không có thông tin để trả lời, hãy thông báo lịch sự rằng hiện bạn chưa có thông tin về vấn đề này và đề xuất khách hàng liên hệ đội ngũ hỗ trợ, TUYỆT ĐỐI KHÔNG TỰ BỊA ĐẶT THÔNG TIN.
3. Nếu khách hàng hỏi nối tiếp câu trước (ví dụ: "giá bao nhiêu", "cái đó có bảo hành không", "ưu điểm của nó"), hãy kết hợp với LỊCH SỬ TRÒ CHUYỆN để hiểu đúng đối tượng khách đang đề cập.
4. Giữ giọng văn thân thiện, hỗ trợ và chuyên nghiệp.{history_text}

NGỮ CẢNH TÀI LIỆU:
{context_text}

CÂU HỎI CỦA KHÁCH HÀNG:
{query}

CÂU TRẢ LỜI:"""
    return prompt


async def answer_rag_query(
    db: AsyncSession,
    agent: Agent,
    service_name: str,
    query: str,
    top_k: int = 4,
    chat_history: list[dict] | None = None,
) -> tuple[str, list[str], dict[str, Any]]:
    """
    Execute full ReAct / RAG pipeline:
      1. Vector retrieval of top_k relevant chunks
      2. Fetch active tools configured for the Agent
      3. Format grounding prompt with chat history
      4. Execute ReAct reasoning loop (with tool execution & tracing if tools exist)
      5. Returns (answer, list_of_cited_sources, trace_dict)
    """
    # 1. Retrieve relevant chunks
    chunks = await search_relevant_chunks(
        db=db,
        agent_id=agent.id,
        query_text=query,
        top_k=top_k,
    )

    sources: list[str] = []
    for c in chunks:
        if c.source and c.source not in sources:
            sources.append(c.source)

    # 2. Retrieve active tools for this agent
    tool_stmt = select(AgentTool).where(
        AgentTool.agent_id == agent.id,
        AgentTool.is_active.is_(True),
    )
    tools = list((await db.execute(tool_stmt)).scalars().all())

    # 3. Build Prompt
    prompt = build_rag_prompt(
        service_name=service_name,
        query=query,
        chunks=chunks,
        chat_history=chat_history,
    )

    trace = TraceCollector(query=query)

    # 4. Resolve API Key & Provider
    if agent.ai_tier == AITier.FREE:
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is not configured for FREE tier.")
        provider = "google"
        model_name = agent.model_name or "gemini-3.6-flash"
    elif agent.ai_tier == AITier.BYOK:
        if not agent.encrypted_api_key:
            raise ValueError("Agent is configured as BYOK but has no API key stored.")
        api_key = decrypt_api_key(agent.encrypted_api_key)
        provider = (agent.llm_provider or "google").lower()
        model_name = agent.model_name or "gemini-3.6-flash"
    else:
        return "Không thể xác định cấu hình gói AI của dịch vụ.", sources, trace.to_dict()

    # 5. Execute ReAct Loop if tools exist, or standard generation
    if tools and provider == "google":
        answer, trace_dict = await run_react_agent_gemini(
            api_key=api_key,
            model_name=model_name,
            system_instruction=prompt,
            query=query,
            tools=tools,
            trace=trace,
        )
        return answer, sources, trace_dict

    # Standard fallback if no tools or non-gemini
    if provider == "openai":
        answer = await _call_openai_generate(
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
        )
    else:
        answer = await _call_gemini_generate(
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
        )

    trace.add_synthesis(model_name, 0.0, answer)
    return answer, sources, trace.to_dict()


async def stream_rag_query(
    db: AsyncSession,
    agent: Agent,
    service_name: str,
    query: str,
    top_k: int = 4,
    chat_history: list[dict] | None = None,
    on_complete: Any = None,
) -> AsyncIterator[str]:
    """
    Execute RAG / ReAct pipeline with real-time SSE streaming.
    If Agent uses custom tools, executes ReAct loop and streams the synthesized response.
    """
    try:
        # 1. Retrieve relevant chunks
        chunks = await search_relevant_chunks(
            db=db,
            agent_id=agent.id,
            query_text=query,
            top_k=top_k,
        )

        sources: list[str] = []
        for c in chunks:
            if c.source and c.source not in sources:
                sources.append(c.source)

        # 2. Yield sources first so the UI knows citations early
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

        # 3. Retrieve active tools
        tool_stmt = select(AgentTool).where(
            AgentTool.agent_id == agent.id,
            AgentTool.is_active.is_(True),
        )
        tools = list((await db.execute(tool_stmt)).scalars().all())

        # If tools are configured, run ReAct loop to allow tool execution
        if tools:
            answer, sources, trace_dict = await answer_rag_query(
                db=db,
                agent=agent,
                service_name=service_name,
                query=query,
                top_k=top_k,
                chat_history=chat_history,
            )

            # Stream tokens of the final synthesized answer
            words = answer.split(" ")
            for i, word in enumerate(words):
                token = word if i == len(words) - 1 else word + " "
                yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

            # Execute on_complete callback with trace
            if on_complete and callable(on_complete):
                try:
                    await on_complete(answer, sources, trace_dict)
                except Exception as save_err:
                    print(f"[CHAT_SAVE_ERROR] Failed to save conversation message: {save_err}")

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return

        # 4. Standard Streaming if no tools
        prompt = build_rag_prompt(
            service_name=service_name,
            query=query,
            chunks=chunks,
            chat_history=chat_history,
        )

        full_answer_parts: list[str] = []

        if agent.ai_tier == AITier.FREE:
            api_key = settings.GOOGLE_API_KEY
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Chưa cấu hình GOOGLE_API_KEY cho gói FREE.'}, ensure_ascii=False)}\n\n"
                return

            async for token in _call_gemini_stream(
                api_key=api_key,
                model_name=agent.model_name or "gemini-3.6-flash",
                prompt=prompt,
            ):
                full_answer_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        elif agent.ai_tier == AITier.BYOK:
            if not agent.encrypted_api_key:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Trợ lý AI chưa có API Key.'}, ensure_ascii=False)}\n\n"
                return
            user_key = decrypt_api_key(agent.encrypted_api_key)

            provider = (agent.llm_provider or "google").lower()
            if provider == "openai":
                async for token in _call_openai_stream(
                    api_key=user_key,
                    model_name=agent.model_name,
                    prompt=prompt,
                ):
                    full_answer_parts.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
            else:
                async for token in _call_gemini_stream(
                    api_key=user_key,
                    model_name=agent.model_name or "gemini-3.6-flash",
                    prompt=prompt,
                ):
                    full_answer_parts.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"

        completed_answer = "".join(full_answer_parts).strip()
        if on_complete and callable(on_complete):
            try:
                await on_complete(completed_answer, sources, None)
            except Exception as save_err:
                print(f"[CHAT_SAVE_ERROR] Failed to save conversation message: {save_err}")

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"


