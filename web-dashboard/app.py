#!/usr/bin/env python3
"""
Predictive Maintenance — AI Gateway (DeepSeek + MCP Tools)
===========================================================
Serves dashboard static files + industrial AI chatbot.

Architecture:
  Browser ── GET  /          → index.html (dashboard, unchanged)
  Browser ── GET  /chat      → chat.html  (AI assistant, NEW)
  Browser ── POST /api/chat  → DeepSeek API → MCP Tools → SSE stream

Start:
    python app.py
    http://localhost:8765          → Dashboard
    http://localhost:8765/chat     → AI Chatbot
    http://localhost:8765/docs     → API Docs

Minimal invasive: keeps index.html, server.py, and agent-mcp架构/ unchanged.
"""
import sys
import os
import io
from pathlib import Path

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Ensure gateway package is importable
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.chdir(str(BASE_DIR))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from gateway.routes import router as chat_router
from gateway.config import HOST, PORT

app = FastAPI(
    title="Predictive Maintenance — AI Gateway",
    description="Industrial predictive maintenance dashboard + DeepSeek AI assistant with MCP tool calling",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ──
app.include_router(chat_router)

# ── Static files ──
if (BASE_DIR / "data").exists():
    app.mount("/data", StaticFiles(directory=str(BASE_DIR / "data")), name="data")
if (BASE_DIR / "images").exists():
    app.mount("/images", StaticFiles(directory=str(BASE_DIR / "images")), name="images")
if (BASE_DIR / "shared").exists():
    app.mount("/shared", StaticFiles(directory=str(BASE_DIR / "shared")), name="shared")
if (BASE_DIR / "reports" / "generated").exists():
    app.mount("/reports/generated", StaticFiles(directory=str(BASE_DIR / "reports" / "generated")), name="reports_generated")
else:
    (BASE_DIR / "reports" / "generated").mkdir(parents=True, exist_ok=True)
    app.mount("/reports/generated", StaticFiles(directory=str(BASE_DIR / "reports" / "generated")), name="reports_generated")


# ── Pages ──
@app.get("/")
async def index():
    """Serve the main dashboard (unchanged)."""
    return FileResponse(BASE_DIR / "index.html")


@app.get("/chat")
async def chat_page():
    """Serve the AI chatbot page."""
    chat_html = BASE_DIR / "chat.html"
    if chat_html.exists():
        return FileResponse(chat_html)
    return HTMLResponse("<h1>chat.html not found — run the setup first</h1>", status_code=404)


@app.get("/technical-overview")
async def tech_overview():
    """Serve the technical architecture overview page."""
    html = BASE_DIR / "technical-overview.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>technical-overview.html not found</h1>", status_code=404)



# ── Reports Page ──
@app.get("/reports")
async def reports_page():
    """Serve the Reports history management page."""
    from fastapi.responses import Response
    reports_html = BASE_DIR / "reports.html"
    if reports_html.exists():
        content = reports_html.read_text(encoding='utf-8')
        return Response(
            content=content,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
        )
    return HTMLResponse("<h1>reports.html not found</h1>", status_code=404)


@app.get("/api/reports")
async def list_reports():
    """Scan reports/generated/ folder and return sorted report list."""
    import datetime
    generated_dir = BASE_DIR / "reports" / "generated"
    if not generated_dir.exists():
        return {"reports": [], "total": 0}

    reports = []
    for f in sorted(generated_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix.lower() == '.html':
            info = {
                "filename": f.name,
                "html_url": f"/reports/generated/{f.name}",
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified_time": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
            # Determine report type from filename
            name_lower = f.name.lower()
            if name_lower.startswith('weekly'):
                info["report_type"] = "weekly"
            elif name_lower.startswith('device'):
                info["report_type"] = "device"
            elif name_lower.startswith('risk'):
                info["report_type"] = "risk"
            elif 'thermal' in name_lower:
                info["report_type"] = "thermal"
            else:
                info["report_type"] = "general"

            # Check for corresponding PDF
            pdf_path = generated_dir / (f.stem + ".pdf")
            if pdf_path.exists():
                info["pdf_url"] = f"/reports/generated/{pdf_path.name}"

            reports.append(info)

    return {
        "reports": reports,
        "total": len(reports),
    }


# ── Entry Point ──
if __name__ == "__main__":
    from gateway.config import DEEPSEEK_API_KEY

    print(f"""
  ╔══════════════════════════════════════════════════════╗
  ║   Predictive Maintenance — AI Gateway v2.0           ║
  ╠══════════════════════════════════════════════════════╣
  ║  Dashboard:    http://localhost:{PORT}                 ║
  ║  AI Chatbot:   http://localhost:{PORT}/chat            ║
  ║  API Docs:     http://localhost:{PORT}/docs            ║
  ║  Health:       http://localhost:{PORT}/health          ║
  ╠══════════════════════════════════════════════════════╣
  ║  LLM:          DeepSeek (deepseek-chat)              ║
  ║  API Key:      {"configured" if DEEPSEEK_API_KEY else "NOT SET — set DEEPSEEK_API_KEY env var"}                 ║
  ╚══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host=HOST, port=PORT)
