"""
DeepSeek API Client — OpenAI-compatible chat completion with tool calling.
Supports iterative multi-tool conversations: the model can call tools across
multiple rounds until it has enough data to compose a complete answer.

DeepSeek API is OpenAI-compatible:
  - Base URL: https://api.deepseek.com
  - Tool format: OpenAI function calling
  - Streaming: SSE (text/event-stream)
"""
import json
import httpx
from typing import AsyncGenerator, List

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS, execute_tool
from .health_summary import get_health_context_text


MAX_TURNS = 3        # Keep last N user-assistant conversation turns for context
MAX_ITERATIONS = 5   # Max tool-calling rounds per request (safety valve)


def _trim_history(messages: list) -> list:
    """Keep only the last MAX_TURNS user turns (with all intervening messages)."""
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_indices) <= MAX_TURNS:
        return messages
    keep_from = user_indices[-(MAX_TURNS)]
    return messages[keep_from:]


def _build_payload(messages: list, stream: bool = True, rag_context: str = "") -> dict:
    """Build the request payload for DeepSeek API.

    Args:
        messages: Conversation history
        stream: Enable SSE streaming
        rag_context: Optional RAG-retrieved document context to inject into system prompt
    """
    system_content = SYSTEM_PROMPT
    # Inject real-time health data from CSV, replacing the placeholder
    health_data = get_health_context_text()
    system_content = system_content.replace('__HEALTH_DATA_INJECTED_AT_RUNTIME__', health_data)
    if rag_context:
        system_content += (
            "\n\n## 📚 参考文档（来自知识库检索，请优先参考以下内容回答）\n\n"
            + rag_context
            + "\n\n---\n**注意**: 以上内容来自系统知识库检索，请基于这些内容回答用户问题。"
            + "如果检索内容与问题无关，可以忽略并使用你的训练知识回答。"
        )
    return {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_content},
            *messages,
        ],
        "tools": TOOLS,
        "stream": stream,
        "temperature": 0.3,
        "max_tokens": 4096,
    }


async def _stream_deepseek(messages: list, url: str, headers: dict, rag_context: str = ""):
    """
    Make one streaming call to DeepSeek.  Yields SSE events directly:
      {"type": "text_delta", "text": "..."}
      {"type": "_tools", "tool_calls": [...]}   ← sentinel: stream ended, these are the tool calls
      {"type": "_error", "message": "..."}      ← sentinel: error occurred

    Text is streamed character-by-character as it arrives (no buffering).
    Tool calls are accumulated across all chunks and emitted once at the end.
    """
    payload = _build_payload(messages, stream=True, rag_context=rag_context)
    tool_call_buffers = {}  # index -> {id, name, arguments_str}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield {"type": "_error",
                           "message": f"DeepSeek API error ({response.status_code}): {error_body.decode()[:500]}"}
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

                    # Text delta — stream in real time
                    if "content" in delta and delta["content"]:
                        yield {"type": "text_delta", "text": delta["content"]}

                    # Tool call delta (OpenAI streaming format)
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": "",
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

    except httpx.TimeoutException:
        yield {"type": "_error", "message": "DeepSeek API 请求超时，请稍后重试。"}
        return
    except Exception as e:
        yield {"type": "_error", "message": f"DeepSeek API 连接异常: {str(e)}"}
        return

    # Finalize tool calls
    tool_calls = []
    for idx in sorted(tool_call_buffers.keys()):
        buf = tool_call_buffers[idx]
        if buf["name"]:
            tool_calls.append({
                "id": buf["id"],
                "name": buf["name"],
                "arguments_str": buf["arguments_str"],
            })

    yield {"type": "_tools", "tool_calls": tool_calls}


def _build_tool_call_objects(tool_calls: list) -> list:
    """Build OpenAI-format tool_call objects from raw tool_calls."""
    return [
        {
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": tc["arguments_str"],
            },
        }
        for tc in tool_calls
    ]


async def _execute_tool_round(tool_calls: list, messages: list):
    """
    Execute one round of tool calls.  Yields SSE events directly:
      tool_call, tool_result, tool_result_text, chart, report

    Mutates `messages` in-place (appends tool result messages).
    """
    # --- Yield tool_call events ---
    for tc in tool_calls:
        yield {
            "type": "tool_call",
            "name": tc["name"],
            "arguments": tc["arguments_str"],
        }

    # --- Execute and yield tool_result events ---
    for tc in tool_calls:
        try:
            args = json.loads(tc["arguments_str"])
        except json.JSONDecodeError:
            args = {}

        result_str = execute_tool(tc["name"], args)

        # Parse result for embedded chart/report data
        result_obj = {}
        try:
            result_obj = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            result_obj = {}

        # SSE: tool_result summary — RAG tools get structured summary, others truncated
        if tc["name"] in ("search_system_docs", "search_maintenance_kb", "search_fault_cases"):
            # Map tool name to collection name
            _tool_collection_map = {
                "search_system_docs": "sys_docs",
                "search_maintenance_kb": "maint_kb",
                "search_fault_cases": "fault_cases",
            }
            _collection = _tool_collection_map.get(tc["name"], "")
            rag_items = []
            for r in result_obj.get("results", [])[:3]:
                rag_items.append({
                    "source": str(r.get("source", "")),
                    "section": str(r.get("section", "")),
                    "score": float(r.get("score", 0)),
                    "collection": _collection,
                    "content": (str(r.get("content", "") or ""))[:300],
                    "full_content": (str(r.get("full_content", "") or ""))[:1200],
                })
            rag_summary = json.dumps({
                "total_found": result_obj.get("total_found", 0),
                "results": rag_items,
            }, ensure_ascii=False)
            yield {
                "type": "tool_result",
                "name": tc["name"],
                "summary": rag_summary,
            }
        else:
            result_len = len(result_str)
            yield {
                "type": "tool_result",
                "name": tc["name"],
                "summary": result_str[:400] + ("..." if result_len > 400 else ""),
            }

        # SSE: natural language text from tool result (if present)
        text_summary = result_obj.get("text_summary") or result_obj.get("summary_text", "")
        if text_summary:
            yield {"type": "tool_result_text", "text": "\n\n" + text_summary}

        # SSE: chart data (if present)
        chart_data = result_obj.get("chart_data")
        if chart_data:
            yield {"type": "chart", "name": tc["name"], "chart_data": chart_data}

        # SSE: report (if present)
        if tc["name"] == "generate_maintenance_report" and result_obj.get("success"):
            yield {
                "type": "report",
                "name": tc["name"],
                "html_url": result_obj["html_url"],
                "html_size_kb": result_obj.get("html_size_kb", 0),
                "pdf_url": result_obj.get("pdf_url"),
                "pdf_size_kb": result_obj.get("pdf_size_kb", 0),
                "report_type": result_obj.get("report_type", "weekly"),
            }

        # Append tool result to conversation history
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": result_str,
        })


async def chat_stream(messages: list, rag_context: str = "", rag_citations: list = None) -> AsyncGenerator[dict, None]:
    """
    Stream chat with DeepSeek, handling tool calls iteratively.

    The model can call tools across multiple rounds. Each round:
      1. Call DeepSeek with current messages → stream text in real time
      2. If the model called tools → execute, yield results, add to history → loop
      3. If text only → done

    This preserves real-time text streaming (no buffering) while allowing
    the model to call multiple tools sequentially before answering.

    Args:
        messages: Conversation history
        rag_context: Optional RAG document context injected into system prompt
        rag_citations: Optional list of RAG citation dicts for frontend rendering

    SSE event types yielded:
      rag_citations, text_delta, tool_call, tool_result, tool_result_text, chart, report, error, done
    """
    if not DEEPSEEK_API_KEY:
        yield {"type": "error", "message": "DEEPSEEK_API_KEY 未配置。请设置环境变量 DEEPSEEK_API_KEY。"}
        return

    # ── Yield RAG citations before streaming text ──
    if rag_citations:
        yield {"type": "rag_citations", "citations": rag_citations}

    messages = _trim_history(messages)

    url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    assistant_text_buffer = ""  # accumulates text within one round

    for iteration in range(MAX_ITERATIONS):
        tool_calls = []
        assistant_text_buffer = ""

        # ── Stream DeepSeek response in real time ──
        async for event in _stream_deepseek(messages, url, headers, rag_context):
            if event["type"] == "text_delta":
                assistant_text_buffer += event["text"]
                yield event  # stream to frontend immediately

            elif event["type"] == "_tools":
                tool_calls = event["tool_calls"]

            elif event["type"] == "_error":
                yield {"type": "error", "message": event["message"]}
                return

        # ── No tools called → model is answering, we're done ──
        if not tool_calls:
            yield {"type": "done"}
            return

        # ── Tools called → add assistant message with tool calls ──
        messages.append({
            "role": "assistant",
            "content": assistant_text_buffer if assistant_text_buffer.strip() else None,
            "tool_calls": [],  # filled below, after tool execution
        })
        assistant_idx = len(messages) - 1  # pin index before tool results shift it

        # Execute tools and yield tool-related events
        async for event in _execute_tool_round(tool_calls, messages):
            yield event

        # Attach tool_call objects to the correct assistant message
        messages[assistant_idx]["tool_calls"] = _build_tool_call_objects(tool_calls)

        # Loop continues — model gets another round with tool results in context

    # Safety valve
    yield {"type": "error",
           "message": f"已达到最大工具调用轮次（{MAX_ITERATIONS}），请简化问题后重试。"}
