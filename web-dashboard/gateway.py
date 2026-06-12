#!/usr/bin/env python3
"""
Predictive Maintenance — FastAPI Gateway
=========================================
Serves dashboard static files + chatbot API with Claude Tool Calling.

Architecture:
  Browser ── GET  /          → index.html (dashboard)
  Browser ── GET  /chat      → chat.html  (chatbot)
  Browser ── POST /api/chat  → Claude API → MCP Tools → response (SSE stream)

Start:
    python gateway.py
    http://localhost:8765        → Dashboard
    http://localhost:8765/chat   → AI Chatbot
"""

import sys, os, json, time, subprocess, io
from pathlib import Path
from datetime import datetime
from typing import Optional

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Project root resolution ──
BASE_DIR = Path(__file__).resolve().parent
MCP_DIR = BASE_DIR.parent / "agent-mcp架构"
DATA_DIR = BASE_DIR.parent / "原始数据集"
V3_OUTPUTS = BASE_DIR.parent / "预测性维护模型_v3" / "outputs"

sys.path.insert(0, str(MCP_DIR))
os.chdir(str(BASE_DIR))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse, FileResponse, StreamingResponse, JSONResponse
)
from fastapi.staticfiles import StaticFiles
import httpx

app = FastAPI(title="Predictive Maintenance — AI Gateway")

# ═══════════════════════════════════════════════════════════
# Anthropic config
# ═══════════════════════════════════════════════════════════
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"  # fast + capable for tool calling
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# ═══════════════════════════════════════════════════════════
# MCP Tool Definitions (for Claude Tool Calling)
# ═══════════════════════════════════════════════════════════
TOOLS = [
    {
        "name": "explain_predictability_limit",
        "description": "解释当前4参数系统的可预测性限制。返回5维度证据链：单参数区分力、参数耦合稳定性、故障非渐进性、模型收敛分析、传感器缺口。包含根因诊断和传感器升级建议。无需参数。",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "prepare_data",
        "description": "【Step 1】加载4个原始CSV，为每台CNC设备构建统计基线(μ,σ)，计算z-score和成本风险矩阵。输出z_scores.csv, cost_risk_matrix.csv等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_dir": {"type": "string", "description": "包含4个原始CSV的目录路径"},
                "output_dir": {"type": "string", "description": "输出目录，默认 ./outputs/data_prep"}
            },
            "required": ["data_dir"]
        }
    },
    {
        "name": "run_stat_analysis",
        "description": "【Step 2a】统计推理：评估z-score基线性能，计算Hotelling T²多变量统计量，分析故障类型签名，汇总每台设备告警状态。输出alert_summary.csv, t2_results.csv等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_dir": {"type": "string", "description": "原始数据目录"},
                "prep_dir": {"type": "string", "description": "prepare_data的输出目录"},
                "output_dir": {"type": "string", "description": "输出目录"}
            },
            "required": ["data_dir", "prep_dir"]
        }
    },
    {
        "name": "run_ml_analysis",
        "description": "【Step 2b】ML推理：训练XGBoost(v1)或多任务神经网络(v2)，生成故障密度预测。可与run_stat_analysis并行。ML信号在决策融合中权重0.25。",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_dir": {"type": "string", "description": "原始数据目录"},
                "prep_dir": {"type": "string", "description": "prepare_data的输出目录"},
                "output_dir": {"type": "string", "description": "输出目录"},
                "model": {"type": "string", "enum": ["v1", "v2"], "description": "模型版本：v1=XGBoost, v2=Multi-Task NN"}
            },
            "required": ["data_dir", "prep_dir"]
        }
    },
    {
        "name": "run_diagnosis",
        "description": "【Step 3】诊断：识别4种异常模式(voltage_drift, thermal_buildup, power_anomaly, combined_degradation)。输出diagnosis_report.csv。",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_dir": {"type": "string", "description": "原始数据目录"},
                "prep_dir": {"type": "string", "description": "prepare_data的输出目录"},
                "stat_dir": {"type": "string", "description": "run_stat_analysis的输出目录"},
                "ml_dir": {"type": "string", "description": "run_ml_analysis的输出目录（可选）"},
                "output_dir": {"type": "string", "description": "输出目录"}
            },
            "required": ["data_dir", "prep_dir", "stat_dir"]
        }
    },
    {
        "name": "generate_decision",
        "description": "【Step 4 - 最终】决策引擎：4层决策架构→6种动作类型→优先级工单+成本节约估算。多信号融合权重: stat=0.40, ml=0.25, cost=0.25, trend=0.10。输出maintenance_work_orders.csv（最终产物）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_dir": {"type": "string", "description": "原始数据目录"},
                "prep_dir": {"type": "string", "description": "prepare_data的输出目录"},
                "stat_dir": {"type": "string", "description": "run_stat_analysis的输出目录"},
                "ml_dir": {"type": "string", "description": "run_ml_analysis的输出目录（可选）"},
                "diag_dir": {"type": "string", "description": "run_diagnosis的输出目录（可选）"},
                "output_dir": {"type": "string", "description": "输出目录"},
                "max_orders": {"type": "integer", "description": "最大工单数，默认20"}
            },
            "required": ["data_dir", "prep_dir", "stat_dir"]
        }
    },
    {
        "name": "query_device_status",
        "description": "查询指定设备的当前状态：告警等级、z-score参数、异常模式、维护建议。输入设备ID如CNC_036。",
        "input_schema": {
            "type": "object",
            "properties": {
                "machine_id": {"type": "string", "description": "设备ID，如 CNC_036, CNC_001"},
            },
            "required": ["machine_id"]
        }
    },
    {
        "name": "list_alarm_devices",
        "description": "列出当前所有告警设备（ALARM/WARNING级别），返回设备ID、告警等级、紧急度分数、建议动作。",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]

# ═══════════════════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════════════════
SYSTEM_PROMPT = """你是工业预测性维护AI助手，负责分析100台CNC设备的健康状态。

## 你的能力
你可以调用以下工具来分析设备数据和生成维护建议：
- explain_predictability_limit — 解释预测性能瓶颈（传感器限制分析）
- prepare_data — 数据准备和基线构建
- run_stat_analysis — 统计异常检测（z-score, T²）
- run_ml_analysis — ML模型推理（XGBoost/深度学习）
- run_diagnosis — 异常模式诊断
- generate_decision — 生成维护工单
- query_device_status — 查询单台设备状态
- list_alarm_devices — 列出告警设备

## 回答风格
- 用中文回答
- 先给出结论，再展开细节
- 引用具体数据和设备ID
- 如果用户问"有哪些设备需要关注"，调用 list_alarm_devices
- 如果用户问某台具体设备，调用 query_device_status
- 如果用户要求完整分析，依次调用 prepare_data → stat+ml → diagnosis → decision
- 对技术问题（如"为什么预测不准"），调用 explain_predictability_limit

## 数据背景
- 100台CNC加工设备，4个监控参数（Voltage, Amperage, Temperature, Rotor Speed）
- 原始数据位于: """ + str(DATA_DIR) + """
- 输出目录默认: """ + str(BASE_DIR / "outputs") + """
- 4参数信息量不足（Youden's J < 0.08），AI纯ML预测能力有限
- 系统采用统计基线+成本风险+ML的融合决策方式"""


# ═══════════════════════════════════════════════════════════
# Tool Execution Engine
# ═══════════════════════════════════════════════════════════

def _run_skill_script(skill_name: str, args: list) -> dict:
    """Run a skill's scripts/run.py via subprocess."""
    script = MCP_DIR / skill_name / "scripts" / "run.py"
    if not script.exists():
        return {"success": False, "error": f"Script not found: {script}"}
    cmd = [sys.executable, str(script)] + args
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        duration = round(time.time() - start, 2)
        stdout_tail = "\n".join(proc.stdout.strip().split("\n")[-20:]) if proc.stdout else ""
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "duration_seconds": duration,
            "output": stdout_tail[:2000],
            "error": proc.stderr.strip()[-500:] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout after 600s"}


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Execute an MCP tool and return structured result."""

    if tool_name == "explain_predictability_limit":
        import pandas as pd
        dim1 = pd.read_csv(V3_OUTPUTS / "dim1_single_param_discriminability.csv")
        dim5 = pd.read_csv(V3_OUTPUTS / "dim5_sensor_gap_analysis.csv")

        params = {}
        for _, row in dim1.iterrows():
            params[row["parameter"]] = {
                "youden_j": float(row["youden_j"]),
                "fault_in_normal_pct": str(row["fault_in_normal_pct"]),
                "cohens_d": float(row["cohens_d"]),
                "interpretation": row["youden_interpretation"],
            }

        sensors = []
        for _, row in dim5.iterrows():
            sensors.append({
                "sensor": row["sensor"],
                "expected_youden_j": row["expected_youden_j"],
                "expected_auc_gain": row["expected_auc_gain"],
                "cost_per_machine": row["cost_per_machine"],
                "feasibility": row["feasibility"],
            })

        return {
            "tool": tool_name,
            "success": True,
            "conclusion": "4个监控参数不支持有效预测性维护。最大Youden's J = 0.075（可用标准>0.30）。",
            "parameters": params,
            "recommended_sensors": sensors,
            "what_works_today": "统计基线(z-score>2.0): P=84%, FPR=20%。推荐加装振动传感器（单次最高影响力改进）。",
        }

    elif tool_name == "prepare_data":
        data_dir = tool_input.get("data_dir", str(DATA_DIR))
        output_dir = tool_input.get("output_dir", str(BASE_DIR / "outputs" / "data_prep"))
        r = _run_skill_script("predictive-maintenance-data-prep", [data_dir, output_dir])
        r["tool"] = tool_name
        r["output_dir"] = output_dir
        r["hint"] = "数据准备完成。接下来可并行调用 run_stat_analysis 和 run_ml_analysis。"
        return r

    elif tool_name == "run_stat_analysis":
        data_dir = tool_input.get("data_dir", str(DATA_DIR))
        prep_dir = tool_input.get("prep_dir", "")
        output_dir = tool_input.get("output_dir", str(BASE_DIR / "outputs" / "stat"))
        r = _run_skill_script("predictive-maintenance-stat-inference", [
            "--data-dir", data_dir, "--prep-dir", prep_dir, "--output-dir", output_dir
        ])
        r["tool"] = tool_name
        r["output_dir"] = output_dir
        if r["success"]:
            # 读告警摘要
            alert_path = Path(output_dir) / "alert_summary.csv"
            if alert_path.exists():
                import pandas as pd
                df = pd.read_csv(alert_path)
                r["alert_counts"] = df["alert_level"].value_counts().to_dict()
        return r

    elif tool_name == "run_ml_analysis":
        data_dir = tool_input.get("data_dir", str(DATA_DIR))
        prep_dir = tool_input.get("prep_dir", "")
        output_dir = tool_input.get("output_dir", str(BASE_DIR / "outputs" / "ml"))
        model = tool_input.get("model", "v1")
        r = _run_skill_script("predictive-maintenance-ml-inference", [
            "--data-dir", data_dir, "--prep-dir", prep_dir, "--output-dir", output_dir, "--model", model
        ])
        r["tool"] = tool_name
        r["output_dir"] = output_dir
        return r

    elif tool_name == "run_diagnosis":
        data_dir = tool_input.get("data_dir", str(DATA_DIR))
        prep_dir = tool_input.get("prep_dir", "")
        stat_dir = tool_input.get("stat_dir", "")
        ml_dir = tool_input.get("ml_dir", "")
        output_dir = tool_input.get("output_dir", str(BASE_DIR / "outputs" / "diagnosis"))
        args = ["--data-dir", data_dir, "--prep-dir", prep_dir,
                "--stat-dir", stat_dir, "--output-dir", output_dir, "--skip-predictability"]
        if ml_dir:
            args.extend(["--ml-dir", ml_dir])
        r = _run_skill_script("predictive-maintenance-diagnosis", args)
        r["tool"] = tool_name
        r["output_dir"] = output_dir
        return r

    elif tool_name == "generate_decision":
        data_dir = tool_input.get("data_dir", str(DATA_DIR))
        prep_dir = tool_input.get("prep_dir", "")
        stat_dir = tool_input.get("stat_dir", "")
        ml_dir = tool_input.get("ml_dir", "")
        diag_dir = tool_input.get("diag_dir", "")
        output_dir = tool_input.get("output_dir", str(BASE_DIR / "outputs" / "decision"))
        max_orders = tool_input.get("max_orders", 20)
        args = ["--data-dir", data_dir, "--prep-dir", prep_dir,
                "--stat-dir", stat_dir, "--output-dir", output_dir,
                "--max-orders", str(max_orders)]
        if ml_dir:
            args.extend(["--ml-dir", ml_dir])
        if diag_dir:
            args.extend(["--diag-dir", diag_dir])
        r = _run_skill_script("predictive-maintenance-decision", args)
        r["tool"] = tool_name
        r["output_dir"] = output_dir
        if r["success"]:
            wo_path = Path(output_dir) / "maintenance_work_orders.csv"
            if wo_path.exists():
                import pandas as pd
                df = pd.read_csv(wo_path)
                r["work_orders_count"] = len(df)
                r["top_orders"] = df.head(5)[["priority","machine_id","alert_level","action_type","urgency_score"]].to_dict(orient="records")
        return r

    elif tool_name == "query_device_status":
        machine_id = tool_input.get("machine_id", "")
        # 读取已有数据文件查询设备状态
        wo_path = BASE_DIR / "data" / "work_orders.csv"
        diag_path = BASE_DIR / "data" / "diagnosis.csv"
        zs_path = BASE_DIR / "data" / "z_scores.csv"

        result = {"tool": tool_name, "machine_id": machine_id, "found": False}

        if wo_path.exists():
            import pandas as pd
            wo = pd.read_csv(wo_path)
            match = wo[wo["machine_id"] == machine_id]
            if len(match) > 0:
                row = match.iloc[0]
                result["found"] = True
                result["alert_level"] = row["alert_level"]
                result["priority"] = int(row["priority"])
                result["action_type"] = row["action_type"]
                result["urgency_score"] = float(row["urgency_score"])
                result["cost_at_risk"] = float(row["cost_at_risk"])
                result["window_days"] = int(row["window_days"])
                result["suggestion"] = str(row["suggestion"])[:300]

        if diag_path.exists():
            import pandas as pd
            diag = pd.read_csv(diag_path)
            match = diag[diag["machine_id"] == machine_id] if "machine_id" in diag.columns else diag[diag["Equipment.Id"] == machine_id] if "Equipment.Id" in diag.columns else None
            if match is not None and len(match) > 0:
                row = match.iloc[0]
                result["primary_pattern"] = row.get("primary_pattern", "unknown")
                result["secondary_pattern"] = row.get("secondary_pattern", "")

        return result

    elif tool_name == "list_alarm_devices":
        wo_path = BASE_DIR / "data" / "work_orders.csv"
        if not wo_path.exists():
            return {"tool": tool_name, "error": "work_orders.csv not found"}

        import pandas as pd
        wo = pd.read_csv(wo_path)
        alarms = wo[wo["alert_level"].isin(["ALARM", "WARNING"])].sort_values("priority")

        devices = []
        for _, row in alarms.iterrows():
            devices.append({
                "machine_id": row["machine_id"],
                "priority": int(row["priority"]),
                "alert_level": row["alert_level"],
                "action_type": row["action_type"],
                "urgency_score": float(row["urgency_score"]),
                "cost_at_risk": float(row["cost_at_risk"]),
            })

        return {
            "tool": tool_name,
            "total": len(devices),
            "alarm_count": sum(1 for d in devices if d["alert_level"] == "ALARM"),
            "warning_count": sum(1 for d in devices if d["alert_level"] == "WARNING"),
            "devices": devices,
        }

    return {"success": False, "error": f"Unknown tool: {tool_name}"}


# ═══════════════════════════════════════════════════════════
# Claude API Call
# ═══════════════════════════════════════════════════════════

async def call_claude(messages: list, stream: bool = True):
    """Call Claude API with tool definitions, yield SSE events."""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "tools": TOOLS,
    }

    if stream:
        body["stream"] = True
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", ANTHROPIC_URL, headers=headers, json=body) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(ANTHROPIC_URL, headers=headers, json=body)
            return resp.json()


# ═══════════════════════════════════════════════════════════
# API Routes
# ═══════════════════════════════════════════════════════════

@app.get("/chat")
async def chat_page():
    """Serve the chatbot page."""
    chat_html = BASE_DIR / "chat.html"
    if chat_html.exists():
        return FileResponse(chat_html)
    return HTMLResponse("<h1>chat.html not found</h1>", status_code=404)


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """
    Chat endpoint — handles the full Claude conversation loop.

    Receives: { "messages": [{ "role": "user", "content": "..." }] }
    Returns:  SSE stream of events:
      - text_delta: Claude's text response chunks
      - tool_use: Claude is calling a tool
      - tool_result: Tool execution result
      - done: Conversation complete
    """
    if not ANTHROPIC_API_KEY:
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY not set. Set environment variable ANTHROPIC_API_KEY."},
            status_code=500
        )

    body = await request.json()
    messages = body.get("messages", [])

    async def event_stream():
        try:
            # Phase 1: Call Claude
            tool_use_blocks = []
            text_buffer = ""

            async for line in call_claude(messages, stream=True):
                if not line.startswith("data: "):
                    continue

                data = json.loads(line[6:])
                event_type = data.get("type")

                if event_type == "content_block_start":
                    block = data.get("content_block", {})
                    if block.get("type") == "tool_use":
                        tool_use_blocks.append({
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": {},
                            "input_json": ""
                        })

                elif event_type == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text_buffer += delta.get("text", "")
                        yield f"data: {json.dumps({'type': 'text_delta', 'text': delta.get('text', '')})}\n\n"
                    elif delta.get("type") == "input_json_delta":
                        if tool_use_blocks:
                            tool_use_blocks[-1]["input_json"] += delta.get("partial_json", "")

                elif event_type == "content_block_stop":
                    # Finalize any pending tool_use inputs
                    for tb in tool_use_blocks:
                        if tb["input_json"]:
                            try:
                                tb["input"] = json.loads(tb["input_json"])
                            except json.JSONDecodeError:
                                tb["input"] = {}

                elif event_type == "message_delta":
                    pass

                elif event_type == "message_stop":
                    pass

            # Phase 2: Execute tool calls
            if tool_use_blocks:
                # Add assistant message with tool_use
                tool_use_content = []
                for tb in tool_use_blocks:
                    yield f"data: {json.dumps({'type': 'tool_use', 'name': tb['name'], 'input': tb['input']})}\n\n"
                    tool_use_content.append({
                        "type": "tool_use",
                        "id": tb["id"],
                        "name": tb["name"],
                        "input": tb["input"]
                    })

                messages.append({
                    "role": "assistant",
                    "content": tool_use_content
                })

                # Execute each tool
                tool_results = []
                for tb in tool_use_blocks:
                    result = execute_tool(tb["name"], tb["input"])
                    tool_results.append({
                        "tool_use_id": tb["id"],
                        "content": json.dumps(result, ensure_ascii=False, default=str)
                    })
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': tb['name'], 'success': result.get('success', False), 'summary': str(result)[:300]})}\n\n"

                # Add tool results to messages
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tr["tool_use_id"],
                            "content": tr["content"]
                        }
                        for tr in tool_results
                    ]
                })

                # Phase 3: Get final response from Claude
                final_text = ""
                async for line in call_claude(messages, stream=True):
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            final_text += delta.get("text", "")
                            yield f"data: {json.dumps({'type': 'text_delta', 'text': delta.get('text', '')})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/tools")
async def list_tools():
    """List all available MCP tools."""
    return JSONResponse({
        "tools": [
            {"name": t["name"], "description": t["description"]}
            for t in TOOLS
        ]
    })


@app.get("/health")
async def health():
    return {"status": "ok", "api_key_configured": bool(ANTHROPIC_API_KEY)}


# ═══════════════════════════════════════════════════════════
# Static files — serve dashboard
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "index.html")

# Mount data directory for CSV access
if (BASE_DIR / "data").exists():
    app.mount("/data", StaticFiles(directory=str(BASE_DIR / "data")), name="data")

# Mount images
if (BASE_DIR / "images").exists():
    app.mount("/images", StaticFiles(directory=str(BASE_DIR / "images")), name="images")


# ═══════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"""
  ╔══════════════════════════════════════════════════════╗
  ║   Predictive Maintenance — AI Gateway               ║
  ╠══════════════════════════════════════════════════════╣
  ║  Dashboard:  http://localhost:8765                  ║
  ║  Chatbot:    http://localhost:8765/chat             ║
  ║  API Docs:   http://localhost:8765/docs             ║
  ║  Health:     http://localhost:8765/health           ║
  ╠══════════════════════════════════════════════════════╣
  ║  ANTHROPIC_API_KEY: {"configured" if ANTHROPIC_API_KEY else "NOT SET"}                            ║
  ╚══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8765)
