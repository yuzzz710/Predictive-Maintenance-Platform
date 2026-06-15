"""
FastAPI routes — chat endpoint with SSE streaming and tool-calling loop,
plus strategy-switching endpoint for the industrial maintenance dashboard.
"""
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from fastapi import APIRouter, Request, Body
from fastapi.responses import StreamingResponse, JSONResponse

from .deepseek_client import chat_stream
from .question_classifier import classify_question
from .rag_engine import search_all_as_context, search_all, ensure_initialized as ensure_rag_initialized
from .health_summary import get_health_json, get_health_context_text

router = APIRouter()

# ── Strategy switching ────────────────────────────────────────────────────

_VALID_STRATEGIES = {"cost_efficiency", "production_efficiency", "quality_first"}

# Cache the decision engine import — heavy, only do once
_decision_module = None


def _get_decision_engine():
    """Lazy-import the decision engine modules (same pattern as run.py)."""
    global _decision_module
    if _decision_module is not None:
        return _decision_module

    from .config import PROJECT_ROOT

    skills_dir = str(PROJECT_ROOT / "skills" / "predictive-maintenance-decision" / "scripts")
    if skills_dir not in sys.path:
        sys.path.insert(0, skills_dir)

    # These imports trigger sys.path resolution inside the skills dir
    import maintenance_decision_engine as _mde
    import strategy_selector as _ss

    _decision_module = (_mde, _ss)
    return _decision_module


def _build_signal_list(project_root: Path) -> List[Dict[str, Any]]:
    """Build signal list from prep data — replicates run.py logic."""
    prep_dir = str(project_root / "agent-mcp架构" / "outputs_test" / "output_data_prep")
    stat_dir = str(project_root / "agent-mcp架构" / "outputs_test" / "output_stat_inference")

    cost_path = os.path.join(prep_dir, "cost_risk_matrix.csv")
    cost_df = pd.read_csv(cost_path)

    z_path = os.path.join(prep_dir, "z_scores.csv")
    df_z = pd.read_csv(z_path)

    # Build z-score aggregates per machine
    z_agg = {}
    if "Date" in df_z.columns:
        df_z["Date"] = pd.to_datetime(df_z["Date"])
    for mid, grp in df_z.groupby("Equipment.Id"):
        try:
            grp_sorted = grp.sort_values("Date") if "Date" in grp.columns else grp
            latest = grp_sorted.iloc[-1]
            last_n = grp_sorted.tail(5)
        except (KeyError, TypeError):
            latest = grp.iloc[-1]
            last_n = grp.tail(5)
        z_agg[mid] = {
            "z_v_last": float(latest.get("z_Voltage", 0)),
            "z_a_last": float(latest.get("z_Amperage", 0)),
            "z_t_last": float(latest.get("z_Temperature", 0)),
            "z_comp_mean": float(last_n["z_composite"].mean()),
            "z_comp_max": float(last_n["z_composite"].max()),
            "thermal_over_p95": int(last_n["z_Temperature"].abs().gt(2.0).sum()),
            "v_slope": float(last_n["z_Voltage"].diff().mean()) if len(last_n) >= 3 else 0.0,
            "t_slope": float(last_n["z_Temperature"].diff().mean()) if len(last_n) >= 3 else 0.0,
            "a_slope": float(last_n["z_Amperage"].diff().mean()) if len(last_n) >= 3 else 0.0,
        }

    alert_path = os.path.join(stat_dir, "alert_summary.csv")
    alert_df = pd.read_csv(alert_path)
    machine_list = alert_df.to_dict("records")

    signal_list = []
    for row in machine_list:
        mid = str(row.get("machine_id", row.get("Equipment.Id", "unknown")))
        if not mid or mid == "unknown":
            continue
        signals = {
            "machine_id": mid,
            "ml_fault_density": 0.7,
            "z_comp_mean": 0.0, "z_comp_max": 0.0,
            "z_v": 0.0, "z_a": 0.0, "z_t": 0.0,
            "thermal_over_p95": 0,
            "voltage_trend_slope": 0.0, "temp_trend_slope": 0.0,
            "amperage_trend_slope": 0.0,
            "cost_at_risk": 5000.0,
        }
        if mid in z_agg:
            z = z_agg[mid]
            signals.update({
                "z_v": z["z_v_last"], "z_a": z["z_a_last"], "z_t": z["z_t_last"],
                "z_comp_mean": z["z_comp_mean"], "z_comp_max": z["z_comp_max"],
                "voltage_trend_slope": z["v_slope"],
                "temp_trend_slope": z["t_slope"],
                "amperage_trend_slope": z["a_slope"],
                "thermal_over_p95": z["thermal_over_p95"],
            })
        cost_row = cost_df[cost_df["Equipment.Id"] == mid]
        if len(cost_row) > 0:
            signals["cost_at_risk"] = float(cost_row.iloc[0]["cost_at_risk"])
        signal_list.append(signals)

    return signal_list, z_agg


def _build_all_machines_summary(PROJECT_ROOT, cost_df, z_agg=None):
    """
    Build per-machine z-score aggregates + diagnosis summary for all 100 machines.
    Returns dict {machine_id: {z_comp_max, pattern, technician, risk_level, cost_at_risk, ...}}
    Used by strategy switch API to avoid frontend re-loading z_scores.csv.
    Mirrors the frontend's backendDiagnose() + backendAssignTech() + zAggMap logic exactly.
    """
    import numpy as np

    # If z_agg is provided (from _build_signal_list), skip CSV I/O and use it directly
    if z_agg is None:
        prep_dir = str(PROJECT_ROOT / "agent-mcp架构" / "outputs_test" / "output_data_prep")
        z_path = os.path.join(prep_dir, "z_scores.csv")
        if not os.path.exists(z_path):
            return {}
        df_z = pd.read_csv(z_path)
        if "Date" in df_z.columns:
            df_z["Date"] = pd.to_datetime(df_z["Date"])
        # Build z_agg from DataFrame (same logic as _build_signal_list)
        z_agg = {}
        for mid, grp in df_z.groupby("Equipment.Id"):
            mid = str(mid)
            try:
                grp_sorted = grp.sort_values("Date")
                last_n = grp_sorted.tail(5)
                latest = grp_sorted.iloc[-1]
            except (KeyError, TypeError):
                last_n = grp.tail(5)
                latest = grp.iloc[-1]
            z_agg[mid] = {
                "z_v_last": float(latest.get("z_Voltage", 0)),
                "z_a_last": float(latest.get("z_Amperage", 0)),
                "z_t_last": float(latest.get("z_Temperature", 0)),
                "z_comp_mean": float(last_n["z_composite"].mean()),
                "z_comp_max": float(last_n["z_composite"].max()),
                "thermal_over_p95": int(last_n["z_Temperature"].abs().gt(2.0).sum()),
                "v_slope": float(last_n["z_Voltage"].diff().mean()) if len(last_n) >= 3 else 0.0,
                "t_slope": float(last_n["z_Temperature"].diff().mean()) if len(last_n) >= 3 else 0.0,
                "a_slope": float(last_n["z_Amperage"].diff().mean()) if len(last_n) >= 3 else 0.0,
            }

    # Diagnostic thresholds (mirror maintenance_decision_engine.py config["diagnostic"])
    Z_V_THRESHOLD = 2.0
    Z_T_THRESHOLD = 2.0
    Z_A_THRESHOLD = 1.5
    Z_COMPOSITE_THRESHOLD = 2.0
    TREND_MIN = 0.02
    THERMAL_OVER_P95_MIN = 2

    all_machines = {}
    for mid, z in z_agg.items():
        mid = str(mid)
        zv = float(z["z_v_last"])
        za = float(z["z_a_last"])
        zt = float(z["z_t_last"])
        z_comp_mean = float(z["z_comp_mean"])
        z_comp_max = float(z["z_comp_max"])
        thermal_p95 = int(z["thermal_over_p95"])
        v_slope = float(z["v_slope"])
        t_slope = float(z["t_slope"])

        # Diagnose pattern (mirror backendDiagnose in frontend)
        pattern = "normal"
        if abs(zv) > Z_V_THRESHOLD and abs(v_slope) > TREND_MIN:
            pattern = "voltage_drift"
        elif abs(zt) > Z_T_THRESHOLD and thermal_p95 >= THERMAL_OVER_P95_MIN:
            pattern = "thermal_buildup"
        elif abs(zv) > Z_V_THRESHOLD and abs(za) > Z_A_THRESHOLD:
            pattern = "power_anomaly"
        else:
            ab = sum([abs(zv) > Z_COMPOSITE_THRESHOLD, abs(za) > Z_COMPOSITE_THRESHOLD, abs(zt) > Z_COMPOSITE_THRESHOLD])
            if ab >= 2:
                pattern = "combined_degradation"

        # Risk level
        z_comp = max(z_comp_max, z_comp_mean)
        if z_comp > 2.5: risk_level = "ALARM"
        elif z_comp > 2.0: risk_level = "WARNING"
        elif z_comp > 1.5: risk_level = "WATCH"
        else: risk_level = "NORMAL"

        # Technician assignment (mirror technician_assigner.py priority rules)
        tech = "junior_technician"
        if risk_level == "ALARM" and pattern == "voltage_drift": tech = "electrical_specialist"
        elif risk_level == "ALARM" and pattern == "thermal_buildup": tech = "thermal_specialist"
        elif risk_level == "ALARM" and pattern == "combined_degradation": tech = "senior_technician"
        elif pattern == "voltage_drift": tech = "electrical_specialist"
        elif pattern == "thermal_buildup": tech = "thermal_specialist"
        elif pattern == "power_anomaly": tech = "electrical_specialist"
        elif pattern == "combined_degradation": tech = "senior_technician"

        # Cost data
        cost_row = cost_df[cost_df["Equipment.Id"] == mid] if "Equipment.Id" in cost_df.columns else pd.DataFrame()
        cost_at_risk = float(cost_row.iloc[0]["cost_at_risk"]) if len(cost_row) > 0 else 5000.0
        risk_tier = str(cost_row.iloc[0]["risk_tier"]) if len(cost_row) > 0 and "risk_tier" in cost_row.columns else "Medium"

        all_machines[mid] = {
            "z_comp_max": float(z_comp_max),
            "z_comp_mean": float(z_comp_mean),
            "zv": float(zv), "za": float(za), "zt": float(zt),
            "thermal_over_p95": thermal_p95,
            "v_slope": float(v_slope), "t_slope": float(t_slope),
            "cost_at_risk": cost_at_risk,
            "risk_tier": risk_tier,
            "pattern": pattern,
            "technician": tech,
            "risk_level": risk_level,
        }

    return all_machines


@router.get("/api/maintenance/machines-summary")
async def machines_summary():
    """
    Return per-machine z-score aggregates + diagnosis for all 100 machines.
    Lightweight endpoint (~15KB JSON) — reads fresh z_scores.csv each call.
    Used by frontend to skip 900KB CSV load + in-browser diagnosis on initial render.
    """
    from .config import PROJECT_ROOT
    prep_dir = str(PROJECT_ROOT / "agent-mcp架构" / "outputs_test" / "output_data_prep")
    cost_path = os.path.join(prep_dir, "cost_risk_matrix.csv")
    cost_df = pd.read_csv(cost_path) if os.path.exists(cost_path) else pd.DataFrame()
    return _build_all_machines_summary(PROJECT_ROOT, cost_df)


@router.post("/api/maintenance/strategy")
async def switch_strategy(data: dict = Body(...)):
    """
    Switch maintenance strategy and regenerate all industrial plan data.

    Request:  {"strategy": "quality_first", "or_budget": 80000, "or_max_hours": 120, "or_max_orders": 15}
    All OR params optional — omit to use strategy defaults.
    Response: { "success": true, "strategy": "quality_first",
                "summary": {...}, "plan": [...], "strategy_comparison": [...],
                "technician_schedule": [...], "spare_parts_plan": [...],
                "downtime_schedule": [...] }
    """
    strategy = data.get("strategy", "production_efficiency")
    force = data.get("force", False)
    or_budget = data.get("or_budget", 0)
    or_max_hours = data.get("or_max_hours", 0)
    or_max_orders = data.get("or_max_orders", 0)
    if strategy not in _VALID_STRATEGIES:
        return JSONResponse(
            {"success": False, "error": f"Invalid strategy '{strategy}'. Valid: {sorted(_VALID_STRATEGIES)}"},
            status_code=400,
        )

    from .config import PROJECT_ROOT, DASHBOARD_DATA

    try:
        mde, ss = _get_decision_engine()
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Failed to import decision engine: {e}"},
            status_code=500,
        )

    MaintenanceDecisionEngine = mde.MaintenanceDecisionEngine
    IndustrialMaintenanceEngine = mde.IndustrialMaintenanceEngine
    MaintenanceStrategy = ss.MaintenanceStrategy

    # Build paths
    prep_dir = str(PROJECT_ROOT / "agent-mcp架构" / "outputs_test" / "output_data_prep")
    cost_path = os.path.join(prep_dir, "cost_risk_matrix.csv")
    cost_df = pd.read_csv(cost_path)

    # Build signal list (also returns z_agg to avoid re-reading z_scores.csv)
    signal_list, z_agg = _build_signal_list(PROJECT_ROOT)

    # Load health scores
    health_score_paths = [
        os.path.join(str(DASHBOARD_DATA), "equipment_health_score.csv"),
        os.path.join(str(PROJECT_ROOT / "agent-mcp架构" / "outputs_test" / "output_stat_inference"), "equipment_health_score.csv"),
    ]
    health_df = None
    for hp in health_score_paths:
        if os.path.exists(hp):
            health_df = pd.read_csv(hp)
            break

    # Load spare parts catalog for unit cost lookup
    parts_catalog_path = str(PROJECT_ROOT / "skills" / "predictive-maintenance-decision" / "scripts" / "data" / "spare_parts_catalog.json")
    parts_cost_lookup = {}
    if os.path.exists(parts_catalog_path):
        with open(parts_catalog_path, 'r', encoding='utf-8') as f:
            catalog_data = json.load(f)
        for entry in catalog_data.get("catalog", []):
            for part in entry.get("parts", []):
                parts_cost_lookup[part["name"]] = part.get("unit_cost", 0)
        for part in catalog_data.get("common_parts", []):
            parts_cost_lookup[part["name"]] = part.get("unit_cost", 0)

    # Build OR config override if user specified knapsack parameters
    or_config = None
    if or_budget > 0 or or_max_hours > 0 or or_max_orders > 0:
        or_config = {
            "work_order": {
                "max_budget": or_budget if or_budget > 0 else 150000,
                "max_orders_per_cycle": or_max_orders if or_max_orders > 0 else 20,
            }
        }
        if or_max_hours > 0:
            or_config["work_order"]["max_hours"] = or_max_hours

    # Create engines
    base_engine = MaintenanceDecisionEngine(cost_risk_data=cost_df)
    industrial_engine = IndustrialMaintenanceEngine(
        cost_risk_data=cost_df,
        strategy=strategy,
        health_score_df=health_df,
        config=or_config,
    )

    # Generate industrial plan
    plan_df = industrial_engine.generate_industrial_plan(signal_list)
    output_dir = str(DASHBOARD_DATA)
    os.makedirs(output_dir, exist_ok=True)

    # Save industrial maintenance plan
    plan_path = os.path.join(output_dir, "industrial_maintenance_plan.csv")
    plan_df.to_csv(plan_path, index=False, float_format="%.4f", encoding="utf-8")

    # Spare parts plan
    parts_rows = []
    for _, row in plan_df.iterrows():
        try:
            parts_list = json.loads(row["spare_parts"])
        except (json.JSONDecodeError, TypeError):
            parts_list = []
        for p_name in parts_list:
            unit_cost = parts_cost_lookup.get(p_name, 0)
            parts_rows.append({
                "machine_id": row["machine_id"],
                "primary_pattern": row.get("primary_pattern", ""),
                "part_name": p_name,
                "unit_cost": unit_cost,
                "estimated_cost": unit_cost,  # per-part cost, not total order cost
            })
    parts_df = pd.DataFrame(parts_rows) if parts_rows else pd.DataFrame()
    if len(parts_df) > 0:
        parts_df.to_csv(os.path.join(output_dir, "spare_parts_plan.csv"), index=False, encoding="utf-8")

    # Technician schedule
    tech_rows = []
    for _, row in plan_df.iterrows():
        tech_rows.append({
            "machine_id": row["machine_id"],
            "technician_type": row.get("technician_type", ""),
            "technician_count": row.get("technician_count", 1),
            "estimated_hours": row.get("estimated_duration_hours", 1.0),
            "maintenance_priority": row.get("maintenance_priority", "P3"),
            "estimated_start": row.get("downtime_start", ""),
        })
    tech_df = pd.DataFrame(tech_rows)
    tech_df.to_csv(os.path.join(output_dir, "technician_schedule.csv"), index=False, encoding="utf-8")

    # Downtime schedule
    downtime_rows = []
    for _, row in plan_df.iterrows():
        downtime_rows.append({
            "machine_id": row["machine_id"],
            "downtime_window": row.get("recommended_downtime_window", ""),
            "downtime_start": row.get("downtime_start", ""),
            "estimated_duration_hours": row.get("estimated_duration_hours", 1.0),
            "production_impact_usd": row.get("production_impact", 0.0),
            "urgency_score": row.get("urgency_score", 0.0),
            "cost_at_risk": row.get("cost_at_risk", 0.0),
        })
    downtime_df = pd.DataFrame(downtime_rows)
    downtime_df.to_csv(os.path.join(output_dir, "downtime_schedule.csv"), index=False, encoding="utf-8")

    # Strategy comparison (all 3) — cached unless force refresh
    comp_path = os.path.join(output_dir, "strategy_comparison.csv")
    if force or not os.path.exists(comp_path):
        comp_df = industrial_engine.strategy_selector.generate_strategy_comparison(
            signal_list, base_engine
        )
        comp_df["avg_cost_per_order"] = comp_df.apply(
            lambda r: round(r["total_estimated_cost"] / max(r["n_work_orders"], 1), 2), axis=1
        )
        comp_df.to_csv(comp_path, index=False, encoding="utf-8")
    else:
        comp_df = pd.read_csv(comp_path)

    # ── Build all_machines summary (z-score aggregates + diagnosis for 100 machines) ──
    # This avoids frontend re-loading z_scores.csv and re-running diagnosis on strategy switch
    all_machines = _build_all_machines_summary(PROJECT_ROOT, cost_df, z_agg)

    # Build inline response data for immediate frontend re-render
    def df_to_records(df, max_rows=None):
        """Convert DataFrame to JSON-safe list of dicts, handling NaN."""
        result = df.fillna(0).to_dict(orient="records")
        if max_rows:
            result = result[:max_rows]
        return result

    return {
        "success": True,
        "strategy": strategy,
        "summary": {
            "n_work_orders": int(len(plan_df)),
            "n_p1": int((plan_df["maintenance_priority"] == "P1").sum()),
            "n_p2": int((plan_df["maintenance_priority"] == "P2").sum()),
            "n_p3": int((plan_df["maintenance_priority"] == "P3").sum()),
            "avg_cost": round(float(plan_df["estimated_cost"].mean()), 2) if len(plan_df) > 0 else 0,
            "total_parts": int(len(parts_df)),
            "total_tech_hours": round(float(tech_df["estimated_hours"].sum()), 1),
            "total_production_impact": round(float(downtime_df["production_impact_usd"].sum()), 2),
        },
        "plan": df_to_records(plan_df),
        "strategy_comparison": df_to_records(comp_df),
        "technician_schedule": df_to_records(tech_df),
        "spare_parts_plan": df_to_records(parts_df),
        "downtime_schedule": df_to_records(downtime_df),
        "all_machines": all_machines,
    }


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

    # ── RAG Pre-retrieval ──────────────────────────────────────────
    rag_context = ""
    rag_citations = []
    if messages:
        # Extract the last user message
        last_user_content = ""
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                last_user_content = m["content"]
                break

        if last_user_content:
            # Classify the question type
            classification = classify_question(last_user_content)
            print(f"[routes] Question classified: type={classification['type']}, "
                  f"should_rag={classification['should_rag']}, "
                  f"collections={classification['rag_collections']}")

            if classification["should_rag"]:
                try:
                    ensure_rag_initialized()
                    # Get both context string (for LLM) and structured results (for citations)
                    rag_context = search_all_as_context(last_user_content, k=5)
                    rag_result = search_all(last_user_content, k=5)

                    # Build citation list for frontend
                    for item in rag_result.get("results", []):
                        rag_citations.append({
                            "source": str(item.get("source", "")),
                            "section": str(item.get("section", "")),
                            "score": float(item.get("score", 0)),
                            "collection": str(item.get("collection", "")),
                            "content_snippet": (str(item.get("content", "") or ""))[:300],
                            "full_content": (str(item.get("full_content", "") or ""))[:2000],
                        })

                    if rag_context:
                        print(f"[routes] RAG context injected ({len(rag_context)} chars, {len(rag_citations)} citations)")
                    else:
                        print(f"[routes] RAG returned no relevant results")
                except Exception as e:
                    print(f"[routes] RAG pre-retrieval failed (non-fatal): {e}")
                    rag_context = ""
                    rag_citations = []

    async def event_generator():
        async for event in chat_stream(messages, rag_context=rag_context, rag_citations=rag_citations):
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


@router.get("/api/health-summary")
async def health_summary():
    """Return real-time aggregated health score statistics from CSV."""
    from .health_summary import get_health_summary
    return JSONResponse(get_health_summary())


@router.post("/api/work-order/generate")
async def generate_work_order_detail(data: dict = Body(...)):
    """
    Generate a natural-language work order execution sheet for a machine.
    Uses LLM (DeepSeek) to create a detailed maintenance guide with
    step-by-step inspection checklist, parts/tools, safety notes, and
    verification methods.

    Request: {"machine_id": "CNC_036"}
    Response: {"success": bool, "html_url": str, "pdf_url": str|null, ...}
    """
    from .report_orchestrator import generate_maintenance_report

    machine_id = data.get("machine_id", "")
    if not machine_id:
        return JSONResponse(
            {"success": False, "error": "machine_id is required"}, status_code=400
        )

    result = generate_maintenance_report(
        report_type="work_order",
        machine_id=machine_id,
    )
    return JSONResponse(result)


JUDGE_EXPLAIN_PROMPT = """你是工业智能运维项目的"评委讲解助手"。你的任务是用通俗易懂、适合答辩的语言，向评委解释项目中的模块、技术和设计决策。

## 你的听众
- 评委可能是工业专家、AI专家、投资人、或跨领域评审
- 他们关心：这个模块做什么？为什么重要？解决了什么问题？效果如何？和项目整体什么关系？
- 他们不一定熟悉具体技术栈，但能听懂逻辑清晰的解释

## 你的回答风格
- **口语化但专业**：像在现场向评委介绍，不说"数据表明"而说"我们看到"、"这意味着"
- **先结论后细节**：第一句话就要让评委听懂这个模块的核心价值
- **用数字说话**：提到具体数据时，必须基于下方注入的"当前系统真实健康数据"，禁止编造任何数字
- **关联整体**：每个模块都关联到"从数据到决策的完整闭环"这个项目主线
- **自信但不夸大**：诚实说明数据限制（如30步观测窗口），不制造虚假精度
- **长度适中**：每个回答3-6句核心信息，不要长篇大论

## 项目背景速查
- 监控：100台CNC数控机床，4传感器参数（电压/电流/温度/转速）
- 方法：统计基线(z-score) + ML密度估计 + 成本风险矩阵 → 多信号融合决策
- 决策权重：stat_anomaly=0.40, ml_density=0.25, cost_risk=0.25, trend=0.10
- 核心创新：逐设备基线（非全局阈值）、SHAP可解释性、四级降级保障、三种维护策略
- 数据天花板：4参数Youden's J≤0.075，纯ML上限≈0.537，融合后→0.90
- 降级：FULL→STAT_ONLY→RULE_ONLY→EMERGENCY，任何条件都能产出可执行方案
"""


@router.post("/api/assistant/explain")
async def assistant_explain(request: Request):
    """
    Judge explanation assistant — SSE streaming endpoint.

    Request: {context: {page, section, title}, question: str, mode: str, previous_text?: str}
    Response: SSE stream with text_delta, error, done events.
    Modes: explain, simplify, expand
    """
    from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    context = body.get("context", {})
    question = body.get("question", "")
    mode = body.get("mode", "explain")
    previous_text = body.get("previous_text", "")

    if not DEEPSEEK_API_KEY:
        return JSONResponse({"error": "DEEPSEEK_API_KEY not configured"}, status_code=503)

    # Build system prompt with context
    page_name = context.get("page", "")
    section_name = context.get("section", "")
    title_name = context.get("title", "")

    system_content = JUDGE_EXPLAIN_PROMPT
    if page_name:
        system_content += f"\n\n用户当前所在页面：{page_name}"
    if section_name or title_name:
        system_content += f"\n用户关注的模块：{title_name or section_name}"

    # Inject real-time health data from CSV
    system_content += "\n\n" + get_health_context_text()

    # Mode-specific instructions
    if mode == "simplify":
        system_content += "\n\n用户要求“简化一点”——请把之前的讲解浓缩为3-4句核心信息，去掉技术细节，只说最重要的价值主张。"
    elif mode == "expand":
        system_content += "\n\n用户要求“展开讲细”——请增加更多技术细节和量化数据，让评委深入了解设计思路。"
    else:
        system_content += "\n\n请用“做什么 -> 为什么重要 -> 效果如何 -> 和整体关系”的结构来组织回答。"

    user_content = question
    if previous_text:
        user_content = f"之前的讲解：\n{previous_text[:1500]}\n\n用户新要求：{question}"

    async def event_generator():
        try:
            import httpx
            url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                "stream": True,
                "temperature": 0.5,
                "max_tokens": 2048,
            }

            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        yield f"data: {json.dumps({'type': 'error', 'message': f'API error ({response.status_code}): {error_body.decode()[:300]}'}, ensure_ascii=False)}\n\n"
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
                        content = delta.get("content", "")
                        if content:
                            yield f"data: {json.dumps({'type': 'text_delta', 'text': content}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except httpx.TimeoutException:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI服务请求超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI服务异常: {str(e)}'}, ensure_ascii=False)}\n\n"

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


@router.get("/health")
async def health():
    """Health check."""
    from .config import DEEPSEEK_API_KEY
    return {
        "status": "ok",
        "api_key_configured": bool(DEEPSEEK_API_KEY),
        "model": "deepseek-chat",
    }


# ── RAG Knowledge Base endpoints now in gateway/kb_routes.py ──
