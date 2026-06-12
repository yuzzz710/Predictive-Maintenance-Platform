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

    return signal_list


@router.post("/api/maintenance/strategy")
async def switch_strategy(data: dict = Body(...)):
    """
    Switch maintenance strategy and regenerate all industrial plan data.

    Request:  {"strategy": "quality_first"}
    Response: { "success": true, "strategy": "quality_first",
                "summary": {...}, "plan": [...], "strategy_comparison": [...],
                "technician_schedule": [...], "spare_parts_plan": [...],
                "downtime_schedule": [...] }
    """
    strategy = data.get("strategy", "production_efficiency")
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

    # Build signal list
    signal_list = _build_signal_list(PROJECT_ROOT)

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

    # Create engines
    base_engine = MaintenanceDecisionEngine(cost_risk_data=cost_df)
    industrial_engine = IndustrialMaintenanceEngine(
        cost_risk_data=cost_df,
        strategy=strategy,
        health_score_df=health_df,
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

    # Strategy comparison (all 3)
    comp_df = industrial_engine.strategy_selector.generate_strategy_comparison(
        signal_list, base_engine
    )
    # Add computed fields for frontend chart compatibility
    comp_df["avg_cost_per_order"] = comp_df.apply(
        lambda r: round(r["total_estimated_cost"] / max(r["n_work_orders"], 1), 2), axis=1
    )
    comp_df.to_csv(os.path.join(output_dir, "strategy_comparison.csv"), index=False, encoding="utf-8")

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
