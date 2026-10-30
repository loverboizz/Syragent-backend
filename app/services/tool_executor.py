"""
Tool Executor Service (Stateless Action Gateway).

Executes outbound HTTP requests to enterprise endpoints on behalf of the AI Agent.
Enforces:
  - 6.0s Hard Timeout (Pillar 5A)
  - 4KB Payload Cap & truncation (Pillar 5B)
  - URL path parameter interpolation (e.g. /orders/{order_id})
  - Fernet header decryption
  - Structured error handling (Timeout, 404, 500)
"""

import time
from typing import Any
import httpx

from app.core.security import decrypt_headers
from app.models.agent_tool import AgentTool, HttpMethod
from app.services.tool_validator import truncate_payload


async def execute_tool(
    tool: AgentTool,
    arguments: dict[str, Any],
    timeout: float = 6.0,
) -> dict[str, Any]:
    """
    Execute an enterprise API tool with given arguments.

    Returns a standardized dictionary:
      {
          "success": bool,
          "status_code": int | None,
          "data": Any,
          "latency_ms": float,
          "error": str | None,
      }
    """
    start_time = time.perf_counter()
    args = dict(arguments or {})

    # 1. Decrypt headers if configured
    headers = {}
    if tool.encrypted_headers:
        try:
            headers = decrypt_headers(tool.encrypted_headers)
        except Exception as e:
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "latency_ms": elapsed,
                "error": f"Không thể giải mã Auth Headers của Tool: {str(e)}",
            }

    # Ensure JSON accept header
    if "Accept" not in headers:
        headers["Accept"] = "application/json"

    # 2. Fast-path internal Syragent / Sandbox endpoints (avoids self-HTTP loopback & Render cold-start latency)
    raw_url = tool.endpoint_url or ""
    if "/api/v1/sandbox/" in raw_url:
        try:
            from fastapi import HTTPException
            from app.core.database import async_session_factory
            from app.api.v1.sandbox_erp import (
                syragent_account_lookup,
                syragent_diagnose_service,
                syragent_get_embed_code,
                sandbox_lookup_order,
                sandbox_search_inventory,
                sandbox_create_ticket,
                CreateTicketPayload,
            )

            res_data = None
            if "/syragent/account-lookup" in raw_url:
                kw = str(args.get("keyword", "")).strip()
                async with async_session_factory() as db:
                    res_data = await syragent_account_lookup(db=db, keyword=kw)
            elif "/syragent/diagnose/" in raw_url:
                sc = str(args.get("service_code", "")).strip()
                async with async_session_factory() as db:
                    res_data = await syragent_diagnose_service(service_code=sc, db=db)
            elif "/syragent/embed-code/" in raw_url:
                sc = str(args.get("service_code", "")).strip()
                async with async_session_factory() as db:
                    res_data = await syragent_get_embed_code(service_code=sc, db=db)
            elif "/sandbox/orders/" in raw_url:
                oid = str(args.get("order_id", "")).strip()
                res_data = await sandbox_lookup_order(order_id=oid)
            elif "/sandbox/inventory/search" in raw_url:
                pname = str(args.get("product_name", "")).strip()
                res_data = await sandbox_search_inventory(product_name=pname)
            elif "/sandbox/tickets/create" in raw_url:
                res_data = await sandbox_create_ticket(
                    CreateTicketPayload(
                        order_id=str(args.get("order_id", "")),
                        customer_phone=str(args.get("customer_phone", "0901234567")),
                        reason=str(args.get("reason", "")),
                    )
                )

            if res_data is not None:
                elapsed = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "success": True,
                    "status_code": 200,
                    "data": truncate_payload(res_data, max_bytes=4096),
                    "latency_ms": elapsed,
                    "error": None,
                }
        except HTTPException as http_exc:
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "status_code": http_exc.status_code,
                "data": http_exc.detail if isinstance(http_exc.detail, dict) else {"detail": str(http_exc.detail)},
                "latency_ms": elapsed,
                "error": str(http_exc.detail),
            }
        except Exception:
            # Fall back to standard HTTP execution below
            pass

    # 3. Interpolate path parameters (e.g., https://api.shop.com/v1/orders/{order_id})
    endpoint_url = tool.endpoint_url
    for key in list(args.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in endpoint_url:
            endpoint_url = endpoint_url.replace(placeholder, str(args.pop(key)))

    # 3. Perform HTTP request via httpx
    method_str = tool.http_method.value if isinstance(tool.http_method, HttpMethod) else str(tool.http_method)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method_str == "GET":
                response = await client.get(endpoint_url, params=args, headers=headers)
            elif method_str == "POST":
                response = await client.post(endpoint_url, json=args, headers=headers)
            elif method_str == "PUT":
                response = await client.put(endpoint_url, json=args, headers=headers)
            elif method_str == "DELETE":
                response = await client.delete(endpoint_url, params=args, headers=headers)
            else:
                response = await client.request(method_str, endpoint_url, json=args, headers=headers)

            elapsed = round((time.perf_counter() - start_time) * 1000, 2)

            # Try parsing JSON response
            try:
                res_data = response.json()
            except Exception:
                res_data = {"raw_text": response.text}

            # 4. Truncate payload if it exceeds 4KB cap
            safe_data = truncate_payload(res_data, max_bytes=4096)

            if response.status_code >= 400:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "data": safe_data,
                    "latency_ms": elapsed,
                    "error": f"API Doanh nghiệp trả về mã lỗi HTTP {response.status_code}",
                }

            return {
                "success": True,
                "status_code": response.status_code,
                "data": safe_data,
                "latency_ms": elapsed,
                "error": None,
            }

    except httpx.TimeoutException:
        elapsed = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": False,
            "status_code": 408,
            "data": None,
            "latency_ms": elapsed,
            "error": f"TIMEOUT: Hệ thống doanh nghiệp không phản hồi sau {timeout}s",
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": False,
            "status_code": None,
            "data": None,
            "latency_ms": elapsed,
            "error": f"Lỗi kết nối tới endpoint doanh nghiệp: {str(e)}",
        }

