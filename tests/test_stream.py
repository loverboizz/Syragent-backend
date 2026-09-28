"""
Integration test for Chat SSE Streaming Endpoint.
"""

import json
import sys
import httpx

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
sys.path.insert(0, os.path.abspath("."))

from app.main import app


async def test_chat_stream_endpoint():
    """Test that POST /api/v1/chat/{service_code}/stream returns SSE events progressively."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=45.0) as client:
        async with client.stream(
            "POST",
            "/api/v1/chat/s0257/stream",
            json={"question": "GasColaE là gì?"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            received_sources = False
            token_count = 0
            received_done = False
            full_text = ""

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                event = json.loads(data_str)
                event_type = event.get("type")

                if event_type == "sources":
                    received_sources = True
                    print(f"[TEST] Sources received: {event.get('sources')}")
                elif event_type == "token":
                    token_count += 1
                    token = event.get("token", "")
                    full_text += token
                elif event_type == "done":
                    received_done = True
                    print(f"[TEST] Done received. Total tokens: {token_count}")
                elif event_type == "error":
                    raise RuntimeError(f"Received error event from stream: {event.get('error')}")

            assert received_sources is True, "Stream should have emitted sources event first"
            assert token_count > 0, "Stream should have emitted tokens"
            assert received_done is True, "Stream should have emitted done event"
            assert len(full_text) > 10, f"Full response text is too short: {full_text}"
            print(f"[TEST PASS] Generated response length: {len(full_text)} chars")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_chat_stream_endpoint())


