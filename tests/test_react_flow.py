"""
End-to-End Test for the ReAct Autonomous AI Agent Execution Loop.
Simulates:
  Turn 1: Gemini decides to call tool `lookup_order(order_id='ORD-777')`.
  Action Gateway: Executes tool against endpoint, validates parameters, captures observation.
  Turn 2: Gemini synthesizes the final answer with tool observation grounded facts.
  Verify: Full trace ladder is captured in traces dict.
"""

import sys
import os
import asyncio
import uuid
import httpx
from unittest.mock import patch, AsyncMock

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath("."))
from app.models.agent_tool import AgentTool, HttpMethod, ToolActionType
from app.services.agent_runner import run_react_agent_gemini, TraceCollector


async def test_end_to_end_react_flow():
    print("\n--- Testing End-to-End Autonomous ReAct Function Calling Flow ---")

    tool = AgentTool(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        name="lookup_order",
        description="Tra cứu tình trạng đơn hàng của khách hàng theo mã",
        http_method=HttpMethod.GET,
        endpoint_url="http://127.0.0.1:8000/orders/{order_id}",
        parameters_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Mã đơn hàng"}
            },
            "required": ["order_id"],
        },
        action_type=ToolActionType.SYNC,
    )

    tools = [tool]
    user_query = "Kiểm tra giúp tôi đơn hàng ORD-777 đang ở đâu rồi?"

    # Mock Gemini Responses:
    # Call 1: Model requests tool call
    mock_gemini_turn1 = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "lookup_order",
                                "args": {"order_id": "ORD-777"},
                            }
                        }
                    ]
                }
            }
        ]
    }

    # Call 2: Model receives tool observation and answers user
    mock_gemini_turn2 = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Đơn hàng ORD-777 của bạn đã được đóng gói và đang được vận chuyển bởi Viettel Post, dự kiến giao vào ngày 17/10/2026."
                        }
                    ]
                }
            }
        ]
    }

    # Mock tool endpoint response
    mock_tool_api_resp = httpx.Response(
        200,
        json={
            "order_id": "ORD-777",
            "status": "IN_TRANSIT",
            "carrier": "Viettel Post",
            "expected_delivery": "2026-10-17",
        },
    )

    # Patch httpx to route Gemini API calls and Tool API calls
    async def mock_http_post(url, *args, **kwargs):
        if "generativelanguage.googleapis.com" in url:
            json_body = kwargs.get("json", {})
            contents = json_body.get("contents", [])
            # If contents has functionResponse, it's Turn 2
            has_fn_response = any(
                any("functionResponse" in p for p in c.get("parts", []))
                for c in contents
            )
            resp_data = mock_gemini_turn2 if has_fn_response else mock_gemini_turn1
            return httpx.Response(200, json=resp_data)
        elif "127.0.0.1" in url or "orders" in url:
            return mock_tool_api_resp
        return httpx.Response(404, json={"error": "not found"})

    async def mock_http_request(method, url, *args, **kwargs):
        if "127.0.0.1" in url or "orders" in url:
            return mock_tool_api_resp
        return httpx.Response(404, json={"error": "not found"})

    with patch("httpx.AsyncClient.post", side_effect=mock_http_post), \
         patch("httpx.AsyncClient.request", side_effect=mock_http_request):

        answer, trace_dict = await run_react_agent_gemini(
            api_key="mock_test_key_gemini",
            model_name="gemini-3.6-flash",
            system_instruction="Bạn là trợ lý chăm sóc khách hàng thông minh.",
            query=user_query,
            tools=tools,
        )

        print("\n=== AGENT RESPONSE ===")
        print(answer)
        print("\n=== EXECUTION TRACE DICT ===")
        print(f"Trace ID: {trace_dict['trace_id']}")
        print(f"Total Latency: {trace_dict['total_latency_ms']}ms")
        print(f"Tool Calls Count: {trace_dict['tool_calls_count']}")
        print(f"Total Steps: {len(trace_dict['steps'])}")

        # Verifications
        assert "ORD-777" in answer
        assert "Viettel Post" in answer
        assert trace_dict["tool_calls_count"] == 1
        assert len(trace_dict["steps"]) >= 4

        step_phases = [s["phase"] for s in trace_dict["steps"]]
        assert "REASONING" in step_phases
        assert "VALIDATION" in step_phases
        assert "TOOL_EXECUTION" in step_phases
        assert "RESPONSE_SYNTHESIS" in step_phases

        print("\n[PASS] End-to-End Autonomous ReAct Function Calling flow is 100% operational!")


if __name__ == "__main__":
    asyncio.run(test_end_to_end_react_flow())

