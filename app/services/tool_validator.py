"""
Tool Validator Service.

Handles:
  1. URL validation: Supports http/https, allows private IP / localhost (on-premise & dev/demo).
  2. JSON Schema validation: Ensures LLM-generated arguments conform to the tool's schema.
  3. Payload truncation: Ensures return payloads do not exceed 4KB to protect LLM context windows.
"""

import json
from typing import Any
from urllib.parse import urlsplit

import jsonschema


def validate_endpoint_url(url: str) -> tuple[bool, str | None]:
    """
    Validate that the endpoint URL is a syntactically valid HTTP/HTTPS URL.
    Explicitly supports private IPs (127.0.0.1, localhost, 192.168.x.x, 10.x.x.x)
    for on-premise deployments, internal company services, and local dev/testing.
    """
    if not url or not isinstance(url, str):
        return False, "URL không được để trống."

    url = url.strip()
    try:
        parts = urlsplit(url)
    except Exception as e:
        return False, f"Định dạng URL không hợp lệ: {str(e)}"

    if parts.scheme.lower() not in ("http", "https"):
        return False, f"Giao thức URL phải là http:// hoặc https:// (hiện tại: '{parts.scheme}')."

    if not parts.netloc:
        return False, "URL thiếu tên miền (hostname) hoặc địa chỉ IP."

    return True, None


def validate_arguments(parameters_schema: dict[str, Any] | None, arguments: dict[str, Any] | None) -> tuple[bool, str | None]:
    """
    Validate LLM-generated arguments against the tool's JSON Schema.

    Returns:
      (True, None) if arguments are valid.
      (False, error_message) if invalid, suitable for LLM self-correction feedback.
    """
    if not parameters_schema:
        # If tool defined no parameters schema, arguments can be empty or anything
        return True, None

    args = arguments or {}

    try:
        jsonschema.validate(instance=args, schema=parameters_schema)
        return True, None
    except jsonschema.exceptions.ValidationError as e:
        field = ".".join(str(p) for p in e.absolute_path) or (e.validator_value if e.validator == "required" else "payload")
        msg = f"Lỗi tham số đầu vào '{field}': {e.message}"
        return False, msg
    except Exception as e:
        return False, f"Lỗi kiểm tra JSON Schema: {str(e)}"


def truncate_payload(data: Any, max_bytes: int = 4096) -> Any:
    """
    Safely truncate oversized responses (Pillar 5B: 4KB Payload Cap).
    - If data is a list, keeps the first 5 elements and annotates truncation.
    - If stringified JSON exceeds max_bytes, truncates text to protect LLM context window.
    """
    if data is None:
        return None

    # If it's a list with many items, limit to top 5
    if isinstance(data, list) and len(data) > 5:
        data = {
            "items": data[:5],
            "_truncated": f"Đã thu gọn danh sách (chỉ hiển thị 5/{len(data)} bản ghi để tối ưu bộ nhớ)"
        }

    # Serialize to check size
    try:
        raw_json = json.dumps(data, ensure_ascii=False)
        if len(raw_json.encode("utf-8")) > max_bytes:
            truncated_text = raw_json[:max_bytes]
            return {
                "_raw_snippet": truncated_text,
                "_truncated": True,
                "_warning": f"Dữ liệu phản hồi vượt quá {max_bytes} bytes và đã được tự động cắt ngắn."
            }
    except Exception:
        pass

    return data

