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
from fastapi import FastAPI, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from gateway.routes import router as chat_router
from gateway.tracking_routes import router as tracking_router, router2 as work_order_router, router3 as workflow_router, router4 as inventory_router, router5 as technician_router
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

# ── APScheduler setup ──
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


@app.on_event("startup")
async def startup_event():
    """Startup: initialize workflow engine + RAG + register scheduled jobs."""
    print("[app] Initializing workflow engine...")
    from gateway.workflow_engine import initialize
    initialize()

    # Warm up RAG engine in background (BGE model loading ~5-10s)
    import threading
    def warmup_rag():
        try:
            from gateway.rag_engine import ensure_initialized
            ensure_initialized()
            print("[app] RAG engine ready")
        except Exception as e:
            print(f"[app] RAG engine warm-up failed (non-fatal): {e}")
    threading.Thread(target=warmup_rag, daemon=True).start()
    print("[app] RAG engine warming up in background...")

    from gateway.scheduled_jobs import register_all_jobs
    register_all_jobs(scheduler)

    scheduler.start()
    print("[app] APScheduler started with 3 jobs")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown: stop APScheduler."""
    scheduler.shutdown()
    print("[app] APScheduler stopped")

# ── API routes ──
app.include_router(chat_router)
app.include_router(tracking_router)
app.include_router(work_order_router)
app.include_router(workflow_router)
app.include_router(inventory_router)
app.include_router(technician_router)
from gateway.kb_routes import router as kb_router
app.include_router(kb_router)
from gateway.fault_injection import router as fi_router
app.include_router(fi_router)

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

# PDF output directory (separate from HTML)
pdf_dir = BASE_DIR / "reports" / "pdfs"
if not pdf_dir.exists():
    pdf_dir.mkdir(parents=True, exist_ok=True)
app.mount("/reports/pdfs", StaticFiles(directory=str(pdf_dir)), name="reports_pdfs")


# ── Pages ──
@app.get("/role-gate")
async def role_gate():
    """Serve the role selection gate page."""
    gate_html = BASE_DIR / "role-gate.html"
    if gate_html.exists():
        return FileResponse(gate_html)
    return HTMLResponse("<h1>role-gate.html not found</h1>", status_code=404)


@app.get("/")
async def home():
    """Serve the device health grid — landing page."""
    home_html = BASE_DIR / "home.html"
    if home_html.exists():
        return FileResponse(home_html)
    return FileResponse(BASE_DIR / "index.html")


@app.get("/device-grid")
async def device_grid():
    """Serve the standalone 10x10 device health grid."""
    html = BASE_DIR / "device-grid.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>device-grid.html not found</h1>", status_code=404)


@app.get("/dashboard")
async def index():
    """Serve the main dashboard."""
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


@app.get("/work-order-tracking")
async def work_order_tracking():
    """Serve the work order tracking Kanban page."""
    html = BASE_DIR / "work-order-tracking.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>work-order-tracking.html not found</h1>", status_code=404)


@app.get("/workflows")
async def workflows_page():
    """Serve the workflow management page."""
    html = BASE_DIR / "workflows.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>workflows.html not found</h1>", status_code=404)


@app.get("/inventory")
async def inventory_page():
    """Serve the inventory management page."""
    html = BASE_DIR / "inventory.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>inventory.html not found</h1>", status_code=404)


@app.get("/technicians")
async def technicians_page():
    """Serve the technician management page."""
    html = BASE_DIR / "technicians.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse("<h1>technicians.html not found</h1>", status_code=404)


@app.get("/knowledge-base")
async def knowledge_base_page():
    """Serve the knowledge base management page."""
    html = BASE_DIR / "knowledge-base.html"
    if html.exists():
        return FileResponse(html)
    return HTMLResponse(
        """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
        <title>知识库管理</title><style>
        body { background: #080a0d; color: #e6ebf2; font-family: system-ui, sans-serif;
               display: flex; align-items: center; justify-content: center; height: 100vh; margin:0; }
        .placeholder { text-align: center; }
        .placeholder h1 { font-size: 24px; margin-bottom: 8px; }
        .placeholder p { color: #8e9aab; font-size: 14px; }
        .placeholder a { color: #a371f7; }
</style></head><body><div class="placeholder">
        <h1>📚 知识库管理中心</h1>
        <p>此页面将在 Phase 3 中实现。</p>
        <p style="margin-top:16px"><a href="javascript:history.back()">← 返回</a></p>
</div></body></html>""",
        status_code=200
    )

# ── Reports Page ──
@app.get("/reports")
async def reports_page():
    """Serve the Reports history management page."""
    reports_html = BASE_DIR / "reports.html"
    if reports_html.exists():
        return FileResponse(reports_html)
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
            # Determine report type from filename (support both Chinese and English names)
            name_lower = f.name.lower()
            cn_to_en = {
                "周度系统报告": "weekly",
                "单设备报告": "device",
                "高风险设备报告": "risk",
                "热漂移分析报告": "thermal",
                "低健康分报告": "health_critical",
                "备件需求汇总": "parts_summary",
                "工单执行报告": "work_order",
            }
            matched = False
            for cn, en in cn_to_en.items():
                if cn in f.name:
                    info["report_type"] = en
                    matched = True
                    break
            if not matched:
                if name_lower.startswith("weekly"): info["report_type"] = "weekly"
                elif name_lower.startswith("device"): info["report_type"] = "device"
                elif name_lower.startswith("risk"): info["report_type"] = "risk"
                elif "thermal" in name_lower: info["report_type"] = "thermal"
                elif name_lower.startswith("work_order"): info["report_type"] = "work_order"
                elif name_lower.startswith("health_critical"): info["report_type"] = "health_critical"
                elif name_lower.startswith("sensor_advisory"): info["report_type"] = "sensor_advisory"
                elif name_lower.startswith("parts_summary"): info["report_type"] = "parts_summary"
                elif "acceptance" in name_lower: info["report_type"] = "device"
                else: info["report_type"] = "general"

            # Check for corresponding PDF in pdfs/ folder first, then generated/
            pdf_path = pdf_dir / (f.stem + ".pdf")
            if pdf_path.exists():
                info["pdf_url"] = f"/reports/pdfs/{pdf_path.name}"
            else:
                pdf_path_legacy = generated_dir / (f.stem + ".pdf")
                if pdf_path_legacy.exists():
                    info["pdf_url"] = f"/reports/generated/{pdf_path_legacy.name}"

            reports.append(info)

    return {
        "reports": reports,
        "total": len(reports),
    }


@app.post("/api/reports/generate-pdf")
async def generate_pdf(data: dict = Body(...)):
    """Generate PDF from an existing HTML report using Playwright (Chromium headless).

    Request body: {"filename": "weekly_report_20260519_210326.html"}
    Response: {"success": bool, "pdf_url": str, "pdf_size_kb": float}
    """
    filename = data.get("filename", "")
    if not filename:
        return {"success": False, "error": "缺少 filename 参数"}

    html_path = BASE_DIR / "reports" / "generated" / filename
    if not html_path.exists():
        return {"success": False, "error": f"报告文件不存在: {filename}"}

    stem = html_path.stem
    pdf_path = pdf_dir / f"{stem}.pdf"

    import asyncio

    def _sync_generate():
        from playwright.sync_api import sync_playwright
        abs_url = html_path.resolve().as_uri()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(abs_url, wait_until="networkidle", timeout=15000)
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"},
            )
            browser.close()

    try:
        await asyncio.to_thread(_sync_generate)
        pdf_size_kb = round(pdf_path.stat().st_size / 1024, 1)

        return {
            "success": True,
            "pdf_url": f"/reports/pdfs/{pdf_path.name}",
            "pdf_size_kb": pdf_size_kb,
        }
    except ImportError:
        return {"success": False, "error": "Playwright 未安装，请运行: pip install playwright && playwright install chromium"}
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()[-500:]}


@app.post("/api/reports/delete")
async def delete_report(data: dict = Body(...)):
    """Delete a report file (HTML and PDF if exists)."""
    filename = data.get("filename", "")
    if not filename:
        return {"success": False, "error": "缺少 filename 参数"}
    if ".." in filename or "/" in filename or "\\" in filename:
        return {"success": False, "error": "非法文件名"}

    html_path = BASE_DIR / "reports" / "generated" / filename
    stem = html_path.stem
    pdf_path = BASE_DIR / "reports" / "pdfs" / f"{stem}.pdf"
    pdf_path_legacy = BASE_DIR / "reports" / "generated" / f"{stem}.pdf"

    deleted = []
    if html_path.exists():
        html_path.unlink()
        deleted.append("html")
    if pdf_path.exists():
        pdf_path.unlink()
        deleted.append("pdf")
    elif pdf_path_legacy.exists():
        pdf_path_legacy.unlink()
        deleted.append("pdf")

    if not deleted:
        return {"success": False, "error": f"文件不存在: {filename}"}

    return {"success": True, "deleted": deleted, "filename": filename}


@app.post("/api/reports/open-pdfs-folder")
async def open_pdfs_folder():
    """Open the PDF output folder in the system file manager."""
    import subprocess
    if sys.platform == "win32":
        os.startfile(str(pdf_dir))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(pdf_dir)])
    else:
        subprocess.Popen(["xdg-open", str(pdf_dir)])
    return {"success": True, "path": str(pdf_dir)}


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
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
