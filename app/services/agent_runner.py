"""
Agent Runner Service (ReAct Orchestrator & Tracing).

Implements:
  1. ReAct Loop (Reasoning -> Action -> Observation -> Final Synthesis)
  2. Dynamic Tool Registry for Gemini and OpenAI
  3. Pre-execution Validation (Slot filling & JSON Schema)
  4. Action Gateway integration with 6.0s timeout & 4KB cap
  5. Console & Database Tracing (Observability)
"""

import json
import time
import uuid
from typing import Any

import httpx

from app.models.agent import Agent, AITier
from app.models.agent_tool import AgentTool
from app.services.tool_executor import execute_tool
from app.services.tool_validator import validate_arguments


# ---------------------------------------------------------------------------
# Tracing & Observability Collector
# ---------------------------------------------------------------------------
class TraceCollector:
    """Collects real-time execution steps of an Agent run."""

    def __init__(self, query: str):
        self.trace_id = f"tr_{uuid.uuid4().hex[:8]}"
        self.query = query
        self.start_time = time.perf_counter()
        self.steps: list[dict[str, Any]] = []

    def add_thought(self, model: str, decision: str, thought: str, latency_ms: float):
        self.steps.append({
            "step_index": len(self.steps) + 1,
            "phase": "REASONING",
            "model": model,
            "decision": decision,
            "thought": thought,
            "latency_ms": latency_ms,
        })

    def add_validation(self, tool_name: str, passed: bool, error: str | None = None):
        self.steps.append({
            "step_index": len(self.steps) + 1,
            "phase": "VALIDATION",
            "tool_name": tool_name,
            "passed": passed,
            "error": error,
        })

    def add_tool_call(
        self,
        tool_name: str,
        endpoint: str,
        method: str,
        status_code: int | None,
        latency_ms: float,
        payload: Any,
        error: str | None = None,
    ):
        self.steps.append({
            "step_index": len(self.steps) + 1,
            "phase": "TOOL_EXECUTION",
            "tool_name": tool_name,
            "endpoint": endpoint,
            "method": method,
            "http_status": status_code,
            "latency_ms": latency_ms,
            "response_data": payload,
            "error": error,
        })

    def add_synthesis(self, model: str, latency_ms: float, text_snippet: str):
        self.steps.append({
            "step_index": len(self.steps) + 1,
            "phase": "RESPONSE_SYNTHESIS",
            "model": model,
            "latency_ms": latency_ms,
            "text_snippet": text_snippet[:150],
        })

    def to_dict(self) -> dict[str, Any]:
        total_latency = round((time.perf_counter() - self.start_time) * 1000, 2)
        tool_count = sum(1 for s in self.steps if s["phase"] == "TOOL_EXECUTION")
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "total_latency_ms": total_latency,
            "tool_calls_count": tool_count,
            "steps": self.steps,
        }

    def print_console_summary(self):
        """Prints a human-readable ladder trace to the backend console for developer debugging."""
        total_latency = round((time.perf_counter() - self.start_time) * 1000, 2)
        print("\n" + "=" * 65)
        print(f"[AGENT TRACE: {self.trace_id}] Total Latency: {total_latency}ms")
        print(f"User Query: \"{self.query}\"")
        print("-" * 65)
        for s in self.steps:
            phase = s["phase"]
            idx = s["step_index"]
            if phase == "REASONING":
                print(f" ├─ [{idx}. THOUGHT]: {s.get('decision')} | {s.get('thought')[:80]} ({s.get('latency_ms')}ms)")
            elif phase == "VALIDATION":
                status_str = "PASSED" if s.get("passed") else f"FAILED ({s.get('error')})"
                print(f" ├─ [{idx}. VALIDATION]: Tool '{s.get('tool_name')}' -> {status_str}")
            elif phase == "TOOL_EXECUTION":
                print(f" ├─ [{idx}. ACTION GATEWAY]: {s.get('method')} {s.get('endpoint')} -> HTTP {s.get('http_status')} ({s.get('latency_ms')}ms)")
                if s.get("error"):
                    print(f" │    └─ [ERROR]: {s.get('error')}")
            elif phase == "RESPONSE_SYNTHESIS":
                print(f" └─ [{idx}. SYNTHESIS]: Generated answer via {s.get('model')} ({s.get('latency_ms')}ms)")
        print("=" * 65 + "\n")


# ---------------------------------------------------------------------------
# Format Tool Declarations for LLMs
# ---------------------------------------------------------------------------
def format_tools_for_gemini(tools: list[AgentTool]) -> list[dict[str, Any]]:
    """Format tools into Gemini functionDeclarations format."""
    declarations = []
    for t in tools:
        declarations.append({
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters_schema if t.parameters_schema else {"type": "object", "properties": {}},
        })
    return [{"functionDeclarations": declarations}] if declarations else []


def format_tools_for_openai(tools: list[AgentTool]) -> list[dict[str, Any]]:
    """Format tools into OpenAI tools parameter format."""
    openai_tools = []
    for t in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema if t.parameters_schema else {"type": "object", "properties": {}},
            },
        })
    return openai_tools


# ---------------------------------------------------------------------------
# ReAct Execution Core (Gemini implementation)
# ---------------------------------------------------------------------------
async def run_react_agent_gemini(
    api_key: str,
    model_name: str,
    system_instruction: str,
    query: str,
    tools: list[AgentTool],
    trace: TraceCollector | None = None,
    max_loops: int = 3,
) -> tuple[str, dict[str, Any]]:
    """
    Executes ReAct reasoning loop with Google Gemini API:
      1. Send conversation + tool declarations
      2. If Gemini requests function call:
           - Validate arguments
           - Execute tool via Action Gateway
           - Add Observation to conversation
           - Loop again
      3. Return final answer and trace dict.
    """
    if trace is None:
        trace = TraceCollector(query=query)

    target_model = model_name or "gemini-3.6-flash"
    if target_model.startswith("models/"):
        target_model = target_model[len("models/"):]
    if target_model in ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-flash"]:
        target_model = "gemini-3.6-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"

    tool_map = {t.name: t for t in tools}
    gemini_tools = format_tools_for_gemini(tools)

    # Initial conversation content
    contents: list[dict[str, Any]] = [
        {
            "role": "user",
            "parts": [{"text": f"{system_instruction}\n\nCÂU HỎI CỦA KHÁCH: {query}"}],
        }
    ]

    final_text = ""
    loops = 0

    async with httpx.AsyncClient(timeout=45.0) as client:
        while loops < max_loops:
            loops += 1
            payload: dict[str, Any] = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                },
            }
            if gemini_tools:
                payload["tools"] = gemini_tools

            call_start = time.perf_counter()
            res = await client.post(url, json=payload)
            call_latency = round((time.perf_counter() - call_start) * 1000, 2)

            if res.status_code != 200:
                trace.add_thought(target_model, "ERROR", f"Gemini API error {res.status_code}", call_latency)
                return f"Xin lỗi, hệ thống AI tạm thời gặp sự cố ({res.status_code}).", trace.to_dict()

            res_data = res.json()
            candidates = res_data.get("candidates", [])
            if not candidates:
                trace.add_thought(target_model, "NO_OUTPUT", "Không nhận được phản hồi từ AI", call_latency)
                return "Xin lỗi, hiện tại tôi không thể sinh câu trả lời.", trace.to_dict()

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            # Check for Function Calls
            function_call = None
            text_response = ""
            for p in parts:
                if "functionCall" in p:
                    function_call = p["functionCall"]
                if "text" in p:
                    text_response += p["text"]

            # Case A: LLM decided to call a Tool
            if function_call:
                tool_name = function_call.get("name")
                arguments = function_call.get("args", {})

                trace.add_thought(
                    target_model,
                    "CALL_TOOL",
                    f"Kích hoạt công cụ '{tool_name}' với tham số: {json.dumps(arguments, ensure_ascii=False)}",
                    call_latency,
                )

                tool = tool_map.get(tool_name)
                if not tool:
                    # Tool does not exist in registry
                    observation = {"error": f"Công cụ '{tool_name}' không tồn tại hoặc đã bị vô hiệu hóa."}
                    trace.add_validation(tool_name, False, "Tool not in registry")
                else:
                    # 1. Validate arguments
                    valid, val_err = validate_arguments(tool.parameters_schema, arguments)
                    trace.add_validation(tool_name, valid, val_err)

                    if not valid:
                        observation = {"error": f"Lỗi tham số: {val_err}. Vui lòng tự sửa lại tham số hoặc hỏi lại khách."}
                    else:
                        # 2. Execute tool via Action Gateway (timeout=6.0s, cap=4KB)
                        exec_res = await execute_tool(tool, arguments, timeout=6.0)
                        trace.add_tool_call(
                            tool_name=tool.name,
                            endpoint=tool.endpoint_url,
                            method=tool.http_method.value,
                            status_code=exec_res["status_code"],
                            latency_ms=exec_res["latency_ms"],
                            payload=exec_res["data"],
                            error=exec_res["error"],
                        )
                        observation = exec_res["data"] if exec_res["success"] else {"error": exec_res["error"]}

                # Append assistant model response containing function call
                contents.append(content)
                # Append tool observation response back to Gemini (Gemini 3.x requires role='user' for functionResponse)
                fn_response_payload: dict[str, Any] = {
                    "name": tool_name,
                    "response": {"output": observation},
                }
                if "id" in function_call:
                    fn_response_payload["id"] = function_call["id"]

                contents.append({
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": fn_response_payload
                        }
                    ],
                })
                # Loop continues to generate natural response from observation
                continue

            # Case B: LLM produced final text answer
            final_text = text_response.strip()
            trace.add_synthesis(target_model, call_latency, final_text)
            break

    trace.print_console_summary()
    return final_text, trace.to_dict()
