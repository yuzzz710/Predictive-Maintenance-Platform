"""
DeepSeek API Client — OpenAI-compatible chat completion with tool calling.
Supports both streaming and non-streaming modes.

DeepSeek API is OpenAI-compatible:
  - Base URL: https://api.deepseek.com
  - Tool format: OpenAI function calling
  - Streaming: SSE (text/event-stream)
"""
import json
import httpx
from typing import AsyncGenerator

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS


MAX_TURNS = 3  # Keep last N user-assistant conversation turns for context


def _trim_history(messages: list) -> list:
    """Keep only the last MAX_TURNS user turns (with all intervening messages)."""
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_indices) <= MAX_TURNS:
        return messages
    keep_from = user_indices[-(MAX_TURNS)]
    return messages[keep_from:]


def _build_payload(messages: list, stream: bool = True) -> dict:
    """Build the request payload for DeepSeek API."""
    return {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *messages,
        ],
        "tools": TOOLS,
        "stream": stream,
        "temperature": 0.3,
        "max_tokens": 4096,
    }


async def chat_stream(messages: list) -> AsyncGenerator[dict, None]:
    """
    Stream chat with DeepSeek, handling tool calls automatically.

    Yields SSE event dicts:
      {"type": "text_delta", "text": "..."}
      {"type": "tool_call", "name": "...", "arguments": "..."}
      {"type": "tool_result", "name": "...", "result": "..."}
      {"type": "error", "message": "..."}
      {"type": "done"}
    """
    if not DEEPSEEK_API_KEY:
        yield {"type": "error", "message": "DEEPSEEK_API_KEY 未配置。请设置环境变量 DEEPSEEK_API_KEY。"}
        return

    # Trim to last N turns to keep context manageable
    messages = _trim_history(messages)

    url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    # ── Phase 1: First call to DeepSeek ──
    payload = _build_payload(messages, stream=True)

    tool_calls = []  # accumulated tool calls from this round
    assistant_text = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield {"type": "error", "message": f"DeepSeek API error ({response.status_code}): {error_text.decode()[:500]}"}
                    return

                # Parse SSE stream, accumulate tool call fragments
                tool_call_buffers = {}  # index -> {id, name, arguments_str}

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    # Text delta
                    if "content" in delta and delta["content"]:
                        text = delta["content"]
                        assistant_text += text
                        yield {"type": "text_delta", "text": text}

                    # Tool call delta (OpenAI streaming format)
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments_str": "",
                                }
                            buf = tool_call_buffers[idx]
                            if tc.get("id"):
                                buf["id"] = tc["id"]
                            func = tc.get("function", {})
                            if func.get("name"):
                                buf["name"] = func["name"]
                            if func.get("arguments"):
                                buf["arguments_str"] += func["arguments"]

                # Finalize tool calls
                for idx in sorted(tool_call_buffers.keys()):
                    buf = tool_call_buffers[idx]
                    tool_calls.append({
                        "id": buf["id"],
                        "name": buf["name"],
                        "arguments_str": buf["arguments_str"],
                    })

    except httpx.TimeoutException:
        yield {"type": "error", "message": "DeepSeek API 请求超时，请稍后重试。"}
        return
    except Exception as e:
        yield {"type": "error", "message": f"DeepSeek API 连接异常: {str(e)}"}
        return

    # ── Phase 2: If DeepSeek called tools, execute them and continue ──
    if tool_calls:
        from .tools import execute_tool

        # Build tool call objects for OpenAI-compatible API
        tool_call_objects = []
        for tc in tool_calls:
            # Parse the JSON arguments
            try:
                args = json.loads(tc["arguments_str"])
            except json.JSONDecodeError:
                args = {}

            yield {
                "type": "tool_call",
                "name": tc["name"],
                "arguments": tc["arguments_str"],
            }

            tool_call_objects.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments_str"],
                }
            })

        # Add assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_call_objects,
        })

        # Execute tools and add results
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments_str"])
            except json.JSONDecodeError:
                args = {}

            result_str = execute_tool(tc["name"], args)

            # Check for embedded chart_data in tool result
            chart_data = None
            try:
                result_obj = json.loads(result_str)
                chart_data = result_obj.get("chart_data")
            except (json.JSONDecodeError, TypeError):
                pass

            yield {
                "type": "tool_result",
                "name": tc["name"],
                "summary": result_str[:300] + ("..." if len(result_str) > 300 else ""),
            }

            # Emit natural-language tool result text for direct rendering
            text_summary = result_obj.get("text_summary") or result_obj.get("summary_text", "")
            if text_summary:
                yield {
                    "type": "tool_result_text",
                    "text": "\n\n" + text_summary,
                }

            if chart_data:
                print(f"[chart] tool={tc['name']} chart_type={chart_data.get('chart_type')} series={len(chart_data.get('series',[]))} xAxis={len(chart_data.get('xAxis',[]))} has_thresholds={bool(chart_data.get('thresholds'))}", flush=True)
                yield {
                    "type": "chart",
                    "name": tc["name"],
                    "chart_data": chart_data,
                }
            else:
                print(f"[chart] tool={tc['name']} — NO chart_data in result", flush=True)

            # Check for report generation
            if tc["name"] == "generate_maintenance_report" and result_obj.get("success"):
                print(f"[report] HTML: {result_obj.get('html_url')} ({result_obj.get('html_size_kb')} KB)"
                      + (f" PDF: {result_obj.get('pdf_url')} ({result_obj.get('pdf_size_kb')} KB)"
                         if result_obj.get('pdf_url') else " (PDF unavailable)"), flush=True)
                yield {
                    "type": "report",
                    "name": tc["name"],
                    "html_url": result_obj["html_url"],
                    "html_size_kb": result_obj.get("html_size_kb", 0),
                    "pdf_url": result_obj.get("pdf_url"),
                    "pdf_size_kb": result_obj.get("pdf_size_kb", 0),
                    "report_type": result_obj.get("report_type", "weekly"),
                }

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

        # ── Phase 3: Follow-up call with tool results ──
        payload2 = _build_payload(messages, stream=True)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                async with client.stream("POST", url, headers=headers, json=payload2) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        yield {"type": "error", "message": f"DeepSeek API error ({response.status_code}): {error_text.decode()[:500]}"}
                        return

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield {"type": "text_delta", "text": delta["content"]}

        except Exception as e:
            yield {"type": "error", "message": f"DeepSeek API follow-up error: {str(e)}"}
            return

    yield {"type": "done"}
