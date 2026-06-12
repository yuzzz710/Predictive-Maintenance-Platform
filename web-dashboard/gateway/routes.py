"""
FastAPI routes — chat endpoint with SSE streaming and tool-calling loop.
"""
import json
import traceback
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

from .deepseek_client import chat_stream

router = APIRouter()


@router.post("/api/chat")
async def chat_endpoint(request: Request):
    """
    Chat endpoint — SSE streaming with automatic tool calling.

    Request:  { "messages": [{ "role": "user", "content": "为什么 CNC_042 风险高？" }] }
    Response: SSE stream of events:
      - text_delta:  LLM text response chunks
      - tool_call:   LLM is calling a tool
      - tool_result: Tool execution completed
      - error:       Error occurred
      - done:        Conversation complete
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    messages = body.get("messages", [])

    if not messages:
        return JSONResponse({"error": "messages array is required"}, status_code=400)

    # Validate messages format
    for msg in messages:
        if "role" not in msg or "content" not in msg:
            return JSONResponse(
                {"error": "Each message must have 'role' and 'content' fields"},
                status_code=400
            )

    async def event_generator():
        async for event in chat_stream(messages):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.get("/api/tools")
async def list_tools():
    """List all available tools."""
    from .tools import TOOLS
    return JSONResponse({
        "tools": [
            {"name": t["function"]["name"], "description": t["function"]["description"]}
            for t in TOOLS
        ]
    })


@router.get("/health")
async def health():
    """Health check."""
    from .config import DEEPSEEK_API_KEY
    return {
        "status": "ok",
        "api_key_configured": bool(DEEPSEEK_API_KEY),
        "model": "deepseek-chat",
    }
