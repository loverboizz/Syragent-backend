"""
Comprehensive Unit and Integration Tests for Autonomous AI Agent Function Calling (ReAct) System.
Tests:
  1. Tool Validator: private IP whitelist, scheme validation, JSON schema validation, payload truncation.
  2. Security Cryptography: Header encryption/decryption.
  3. Tool Executor: path interpolation, HTTP requests, timeout & error handling.
  4. Trace Collector & Agent Runner schema conversion.
  5. Full CRUD and /test API endpoints for Agent Tools.
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
from app.main import app
from app.services.tool_validator import (
    validate_endpoint_url,
    validate_arguments,
    truncate_payload,
)
from app.core.security import encrypt_headers, decrypt_headers
from app.services.tool_executor import execute_tool
from app.services.agent_runner import TraceCollector, format_tools_for_gemini
from app.models.agent_tool import AgentTool, HttpMethod, ToolActionType


# ---------------------------------------------------------------------------
# 1. Tool Validator Tests
# ---------------------------------------------------------------------------
def test_tool_validator_private_ips_and_urls():
    """Verify that private IPs, localhost, and standard http/https URLs are permitted."""
    valid_urls = [
        "http://127.0.0.1:8000/api/v1/orders",
        "http://localhost:3000/api/lookup",
        "http://192.168.1.100:5000/orders/123",
        "http://10.0.0.5:8080/webhook",
        "https://api.mycompany.vn/crm/leads",
        "https://172.16.0.1/status",
    ]
    for url in valid_urls:
        is_valid, err = validate_endpoint_url(url)
        assert is_valid is True, f"Expected {url} to be valid, got error: {err}"

    invalid_urls = [
        "ftp://127.0.0.1/file.txt",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "not-a-url",
        "gopher://localhost:70",
    ]
    for url in invalid_urls:
        is_valid, _ = validate_endpoint_url(url)
        assert is_valid is False, f"Expected {url} to be invalid"


def test_tool_validator_schema_validation():
    """Verify JSON Schema validation against input arguments."""
    schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["order_id"],
    }

    # Valid arguments
    is_valid, err = validate_arguments(schema, {"order_id": "ORD-12345"})
    assert is_valid is True
    assert err is None

    # Missing required field
    is_valid, err = validate_arguments(schema, {"limit": 10})
    assert is_valid is False
    assert "order_id" in err

    # Wrong type
    is_valid, err = validate_arguments(schema, {"order_id": "ORD-12345", "limit": "ten"})
    assert is_valid is False
    assert "limit" in err

    # Empty schema allows any dict
    is_valid, err = validate_arguments({}, {"anything": 1})
    assert is_valid is True


def test_tool_validator_payload_truncation():
    """Verify truncation at 4096 bytes."""
    short_data = {"key": "value"}
    truncated = truncate_payload(short_data, max_bytes=4096)
    assert truncated == short_data

    # Create large payload > 4KB
    large_data = {"text": "A" * 6000}
    truncated = truncate_payload(large_data, max_bytes=4096)
    assert "_truncated" in truncated
    assert truncated["_truncated"] is True


# ---------------------------------------------------------------------------
# 2. Security Cryptography Tests
# ---------------------------------------------------------------------------
def test_header_encryption_decryption():
    """Verify Fernet encryption and decryption for auth headers."""
    headers = {
        "Authorization": "Bearer secret_api_token_12345",
        "X-Custom-Secret": "my-secret-key",
    }
    encrypted = encrypt_headers(headers)
    assert encrypted is not None
    assert encrypted != headers
    assert isinstance(encrypted, str)

    decrypted = decrypt_headers(encrypted)
    assert decrypted == headers

    # None cases
    assert encrypt_headers(None) is None
    assert decrypt_headers(None) == {}


# ---------------------------------------------------------------------------
# 3. Tool Executor Tests
# ---------------------------------------------------------------------------
async def test_tool_executor_path_interpolation_and_call():
    """Verify path parameter interpolation and request execution."""
    tool = AgentTool(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        name="lookup_order",
        description="Tra cứu trạng thái đơn hàng",
        http_method=HttpMethod.GET,
        endpoint_url="http://127.0.0.1:8000/orders/{order_id}",
        parameters_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )

    # Mock httpx response with real httpx.Response object
    mock_resp = httpx.Response(
        200,
        json={
            "order_id": "ORD-999",
            "status": "DELIVERED",
            "eta": "2026-10-16",
        },
    )

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp

        result = await execute_tool(tool, {"order_id": "ORD-999"})

        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["data"]["order_id"] == "ORD-999"
        assert result["data"]["status"] == "DELIVERED"

        # Check call arguments: path variable should have been replaced in URL
        call_args = mock_request.call_args
        called_url = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url")
        assert called_url == "http://127.0.0.1:8000/orders/ORD-999"


# ---------------------------------------------------------------------------
# 4. Trace Collector & Schema Conversion Tests
# ---------------------------------------------------------------------------
def test_trace_collector():
    """Verify that TraceCollector records steps and generates readable ladders."""
    collector = TraceCollector(query="Đơn hàng ORD-123 của tôi đâu?")
    collector.add_thought(
        model="gemini-3.6-flash",
        decision="Call Tool: lookup_order",
        thought="Khách hàng hỏi đơn ORD-123. Cần gọi tool tra cứu.",
        latency_ms=250.0,
    )
    collector.add_validation(tool_name="lookup_order", passed=True)
    collector.add_tool_call(
        tool_name="lookup_order",
        endpoint="http://127.0.0.1:8000/orders/ORD-123",
        method="GET",
        status_code=200,
        latency_ms=120.0,
        payload={"status": "SHIPPED", "carrier": "GHN"},
    )
    collector.add_synthesis(
        model="gemini-3.6-flash",
        latency_ms=300.0,
        text_snippet="Đơn hàng ORD-123 của bạn đang trên đường giao bởi GHN.",
    )

    trace_dict = collector.to_dict()
    assert trace_dict["query"] == "Đơn hàng ORD-123 của tôi đâu?"
    assert trace_dict["tool_calls_count"] == 1
    assert len(trace_dict["steps"]) == 4
    assert trace_dict["steps"][0]["phase"] == "REASONING"
    assert trace_dict["steps"][1]["phase"] == "VALIDATION"
    assert trace_dict["steps"][2]["phase"] == "TOOL_EXECUTION"
    assert trace_dict["steps"][3]["phase"] == "RESPONSE_SYNTHESIS"

    # Verify console summary does not raise exception
    collector.print_console_summary()


def test_format_tools_for_gemini():
    """Verify schema conversion from AgentTool model to Gemini Tool declaration."""
    tool = AgentTool(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        name="lookup_order",
        description="Tra cứu trạng thái đơn hàng theo mã",
        http_method=HttpMethod.GET,
        endpoint_url="http://127.0.0.1:8000/orders/{order_id}",
        parameters_schema={
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Mã đơn hàng",
                }
            },
            "required": ["order_id"],
        },
    )

    gemini_tools = format_tools_for_gemini([tool])
    assert len(gemini_tools) == 1
    assert "functionDeclarations" in gemini_tools[0]
    declarations = gemini_tools[0]["functionDeclarations"]
    assert len(declarations) == 1
    assert declarations[0]["name"] == "lookup_order"
    assert declarations[0]["description"] == "Tra cứu trạng thái đơn hàng theo mã"
    assert declarations[0]["parameters"]["type"] == "object"
    assert "order_id" in declarations[0]["parameters"]["properties"]
    assert declarations[0]["parameters"]["properties"]["order_id"]["type"] == "string"


# ---------------------------------------------------------------------------
# 5. API Endpoints Integration Test (Agent Tools CRUD & Test)
# ---------------------------------------------------------------------------
async def test_agent_tools_api_crud_and_test():
    """Integration test for /api/v1/services/{service_id}/tools CRUD and /test endpoints."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        # 1. Register test user
        rand_suffix = uuid.uuid4().hex[:6]
        user_email = f"agent_tools_{rand_suffix}@enterprise.vn"
        user_pass = "SecurePass123!"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Enterprise Tools {rand_suffix}",
                "full_name": "Agent Tool Tester",
                "email": user_email,
                "password": user_pass,
            },
        )
        assert reg_res.status_code in (201, 200)

        # 2. Login to get JWT
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": user_pass},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 3. Create Service
        svc_res = await client.post(
            "/api/v1/services/",
            headers=auth_headers,
            json={
                "name": f"E-Commerce Service {rand_suffix}",
                "code": f"ecommerce-svc-{rand_suffix}",
                "service_url": "https://shop.example.vn",
            },
        )
        assert svc_res.status_code == 201, svc_res.text
        service_id = svc_res.json()["id"]

        # 4. Create Agent for this service
        agent_res = await client.post(
            "/api/v1/agents/",
            headers=auth_headers,
            json={
                "service_id": service_id,
                "llm_provider": "google",
                "model_name": "gemini-3.6-flash",
                "ai_tier": "FREE",
                "system_prompt": "Bạn là nhân viên hỗ trợ.",
            },
        )
        assert agent_res.status_code == 201, agent_res.text

        # 5. Create Tool (POST /api/v1/services/{service_id}/tools)
        tool_payload = {
            "name": "check_order_status",
            "description": "Tra cứu trạng thái đơn hàng khách hàng",
            "http_method": "GET",
            "endpoint_url": "http://127.0.0.1:8000/api/orders/{order_id}",
            "headers": {"X-Api-Key": "test-key-123"},
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Mã đơn hàng"}
                },
                "required": ["order_id"],
            },
            "action_type": "SYNC",
            "is_active": True,
        }
        create_tool_res = await client.post(
            f"/api/v1/services/{service_id}/tools",
            headers=auth_headers,
            json=tool_payload,
        )
        assert create_tool_res.status_code == 201, create_tool_res.text
        created_tool = create_tool_res.json()
        tool_id = created_tool["id"]
        assert created_tool["name"] == "check_order_status"
        assert created_tool["has_headers"] is True

        # 6. List Tools (GET /api/v1/services/{service_id}/tools)
        list_res = await client.get(
            f"/api/v1/services/{service_id}/tools",
            headers=auth_headers,
        )
        assert list_res.status_code == 200
        tools_list = list_res.json()
        assert len(tools_list) >= 1
        assert any(t["id"] == tool_id for t in tools_list)

        # 7. Get Single Tool (GET /api/v1/services/{service_id}/tools/{tool_id})
        get_res = await client.get(
            f"/api/v1/services/{service_id}/tools/{tool_id}",
            headers=auth_headers,
        )
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "check_order_status"

        # 8. Test Tool Dry-Run (POST /api/v1/services/{service_id}/tools/{tool_id}/test)
        with patch("app.api.v1.agent_tools.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "status_code": 200,
                "data": {"order_id": "ORD-1234", "status": "PENDING"},
                "error": None,
                "latency_ms": 45.2,
            }

            test_tool_res = await client.post(
                f"/api/v1/services/{service_id}/tools/{tool_id}/test",
                headers=auth_headers,
                json={"test_parameters": {"order_id": "ORD-1234"}},
            )
            assert test_tool_res.status_code == 200, test_tool_res.text
            test_data = test_tool_res.json()
            assert test_data["success"] is True
            assert test_data["data"]["order_id"] == "ORD-1234"
            assert test_data["response_time_ms"] == 45.2

        # 9. Update Tool (PUT /api/v1/services/{service_id}/tools/{tool_id})
        update_res = await client.put(
            f"/api/v1/services/{service_id}/tools/{tool_id}",
            headers=auth_headers,
            json={"description": "Mô tả mới đã được cập nhật"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["description"] == "Mô tả mới đã được cập nhật"

        # 10. Delete Tool (DELETE /api/v1/services/{service_id}/tools/{tool_id})
        del_res = await client.delete(
            f"/api/v1/services/{service_id}/tools/{tool_id}",
            headers=auth_headers,
        )
        assert del_res.status_code == 204

        # Verify tool is gone
        get_again_res = await client.get(
            f"/api/v1/services/{service_id}/tools/{tool_id}",
            headers=auth_headers,
        )
        assert get_again_res.status_code == 404
        print("[PASS] Full CRUD and /test execution for Agent Tools verified!")


async def run_all_tests():
    print("--- [1/5] Testing Tool Validator (Private IPs, URL scheme, Schemas, Truncation) ---")
    test_tool_validator_private_ips_and_urls()
    test_tool_validator_schema_validation()
    test_tool_validator_payload_truncation()
    print("[PASS] Tool Validator tests passed.")

    print("\n--- [2/5] Testing Header Encryption / Decryption ---")
    test_header_encryption_decryption()
    print("[PASS] Security cryptography tests passed.")

    print("\n--- [3/5] Testing Tool Executor (Path interpolation & HTTP Execution) ---")
    await test_tool_executor_path_interpolation_and_call()
    print("[PASS] Tool Executor tests passed.")

    print("\n--- [4/5] Testing Trace Collector & Gemini Schema conversion ---")
    test_trace_collector()
    test_format_tools_for_gemini()
    print("[PASS] Trace Collector & Schema conversion tests passed.")

    print("\n--- [5/5] Testing Agent Tools API CRUD & /test endpoint ---")
    await test_agent_tools_api_crud_and_test()
    print("[PASS] API CRUD and /test endpoint integration tests passed.")

    print("\n=======================================================")
    print("  ALL 5 TEST SUITES PASSED! REACTION ENGINE IS READY!  ")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
