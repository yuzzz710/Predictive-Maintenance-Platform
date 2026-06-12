"""
Report Orchestrator — multi-step MCP tool coordination for AI-driven reports.

Architecture:
  generate_maintenance_report() orchestrates multiple existing MCP tools
  (list_alarm_devices, query_device_status, get_sensor_trend,
   get_fault_history, get_root_cause_analysis) without reading CSV directly.

Report Types:
  - weekly:          Full weekly report — all alarm devices, trends, fault stats
  - device:           Single-device deep health report
  - risk:             High-risk devices only
  - thermal:          Thermal buildup focused analysis
  - health_critical:  Low health-score devices collective report (default < 30)
  - parts_summary:    Spare parts aggregation across all work orders
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

# Ensure gateway package is importable
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from gateway.config import DASHBOARD_DATA
from gateway.tools import (
    _list_alarm_devices,
    _query_device_status,
    _get_sensor_trend,
    _get_fault_history,
    _get_root_cause_analysis,
    _get_work_order_history,
    _explain_predictability_limit,
)

# ══════════════════════════════════════════════════════════════════════════
# Work Order Context Builder (for generative work order reports)
# ══════════════════════════════════════════════════════════════════════════

def _build_work_order_context(machine_id: str) -> dict:
    """
    Aggregate all available multi-source data for a single machine
    to serve as context for LLM-generated work order execution sheets.
    """
    ctx = {
        "machine_id": machine_id,
    }

    # ── Device status (z-scores, diagnostic pattern, alert level) ──
    try:
        status = _query_device_status(machine_id)
        wo = status.get("industrial_plan") or status.get("work_order") or {}
        ctx["alert_level"] = wo.get("alert_level", status.get("alert_level", "NORMAL"))
        ctx["action_type"] = wo.get("action_type", status.get("action_type", "routine_check"))
        ctx["priority"] = wo.get("priority", status.get("priority", 99))
        ctx["urgency_score"] = wo.get("urgency_score", status.get("urgency_score", 0))
        ctx["cost_at_risk"] = wo.get("cost_at_risk", status.get("cost_at_risk", 0))
        ctx["maintenance_suggestion"] = wo.get("suggestion", wo.get("maintenance_suggestion", ""))
        ctx["primary_pattern"] = status.get("primary_pattern", "combined_degradation")
        ctx["diagnosis_confidence"] = status.get("diagnosis_confidence", 0)
        ctx["health_score"] = status.get("health_score", 50)
        ctx["health_trend"] = status.get("health_trend", "stable")
        ctx["top_risk_factor"] = status.get("top_risk_factor", "")
        ctx["z_scores"] = {
            "z_voltage": status.get("z_voltage", 0),
            "z_amperage": status.get("z_amperage", 0),
            "z_temperature": status.get("z_temperature", 0),
            "z_composite": status.get("z_composite", 0),
        }
        # SHAP attribution
        ctx["shap_attribution"] = {
            "top_risk_factor_1": wo.get("top_risk_factor_1", ""),
            "top_risk_factor_2": wo.get("top_risk_factor_2", ""),
            "top_risk_factor_3": wo.get("top_risk_factor_3", ""),
            "shap_risk_summary": wo.get("shap_risk_summary", ""),
        }
        # Technician & parts
        ctx["technician_type"] = wo.get("technician_type", "")
        ctx["technician_count"] = wo.get("technician_count", 1)
        ctx["spare_parts"] = wo.get("spare_parts", "[]")
        ctx["suggested_window_days"] = wo.get("suggested_window_days", wo.get("window_days", 7))
        ctx["sla_target_hours"] = wo.get("sla_target_hours", 24)
        ctx["estimated_cost"] = wo.get("estimated_cost", 0)
        ctx["expected_savings"] = wo.get("expected_savings", 0)
        ctx["acceptance_standard"] = wo.get("acceptance_standard", "")
    except Exception:
        pass

    # ── Fault history ──
    try:
        history = _get_fault_history(machine_id, limit=20)
        if history.get("found"):
            ctx["fault_history"] = {
                "total_faults": history.get("total_faults", 0),
                "fault_rate_pct": history.get("fault_rate_pct", 0),
                "fault_types": history.get("fault_type_distribution", {}),
                "recent_faults": history.get("recent_faults", [])[:5],
            }
    except Exception:
        ctx["fault_history"] = {"total_faults": 0, "note": "unavailable"}

    # ── Sensor trend summary ──
    try:
        trend_v = _get_sensor_trend(machine_id, "voltage", hours=24)
        trend_t = _get_sensor_trend(machine_id, "temperature", hours=24)
        trend_a = _get_sensor_trend(machine_id, "amperage", hours=24)
        ctx["sensor_trends"] = {
            "voltage": {
                "trend_direction": trend_v.get("trend_direction", "stable"),
                "risk_level": trend_v.get("risk_level", "low"),
            },
            "temperature": {
                "trend_direction": trend_t.get("trend_direction", "stable"),
                "risk_level": trend_t.get("risk_level", "low"),
            },
            "amperage": {
                "trend_direction": trend_a.get("trend_direction", "stable"),
                "risk_level": trend_a.get("risk_level", "low"),
            },
        }
    except Exception:
        ctx["sensor_trends"] = {"note": "unavailable"}

    # ── Acceptance criteria (from rules JSON) ──
    try:
        pattern = ctx.get("primary_pattern", "")
        rules_path = (
            BASE_DIR.parent / "skills" / "predictive-maintenance-decision"
            / "scripts" / "data" / "acceptance_rules.json"
        )
        if rules_path.exists():
            with open(rules_path, "r", encoding="utf-8") as f:
                acceptance_rules = json.load(f)
            for rule in acceptance_rules.get("rules", []):
                if rule.get("fault_type") == pattern:
                    ctx["acceptance_criteria"] = rule.get("acceptance_criteria", [])
                    break
            ctx["universal_criteria"] = acceptance_rules.get("universal_criteria", [])
    except Exception:
        ctx["acceptance_criteria"] = []

    return ctx


# ══════════════════════════════════════════════════════════════════════════
# Report Orchestrator
# ══════════════════════════════════════════════════════════════════════════

def generate_maintenance_report(
    report_type: str = "weekly",
    machine_id: Optional[str] = None,
    top_n: int = 5,
    health_threshold: int = 30,
) -> dict:
    """
    Orchestrate multi-step MCP tool calls to generate structured report data.

    Args:
        report_type: "weekly" | "device" | "risk" | "thermal"
        machine_id: Required for "device" type, optional for others
        top_n: Number of high-risk devices to analyze in detail

    Returns:
        Structured report_data dict ready for PDF generation
    """
    report_data = {
        "report_type": report_type,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": {},
        "charts": [],
        "summary": "",
        "alerts_summary": {},
        "device_details": [],
        "fault_statistics": {},
        "root_cause": {},
        "cost_analysis": {},
        "recommendations": [],
        "predictability_context": {},
    }

    # ── Step 1: Get alarm overview ──
    alarms = _list_alarm_devices()
    report_data["alerts_summary"] = {
        "total": alarms.get("total_alarm_devices", 0),
        "alarm_count": alarms.get("alarm_count", 0),
        "warning_count": alarms.get("warning_count", 0),
        "thermal_drift_count": alarms.get("thermal_drift_count", 0),
        "immediate_shutdown_count": alarms.get("immediate_shutdown_count", 0),
        "thermal_drift_devices": alarms.get("thermal_drift_devices", []),
        "immediate_shutdown_devices": alarms.get("immediate_shutdown_devices", []),
    }

    # ── Step 2: Handle work_order report type (special path — uses LLM generation) ──
    if report_type == "work_order":
        if not machine_id:
            return {
                "success": False,
                "error": "machine_id is required for work_order report type",
                "report_type": "work_order",
            }
        # Delegate to the work order report generator (LLM-powered)
        from gateway.work_order_report_generator import generate_work_order_report
        ctx = _build_work_order_context(machine_id)
        result = generate_work_order_report(machine_id, ctx)
        result["report_type"] = "work_order"
        return result

    # ── Step 3: Determine target devices ──
    if report_type == "device" and machine_id:
        target_devices = [machine_id]
    elif report_type == "health_critical":
        # Read health scores from equipment_health_score.csv
        health_path = DASHBOARD_DATA / "equipment_health_score.csv"
        if health_path.exists():
            hs = pd.read_csv(health_path)
            threshold = health_threshold if health_threshold else 30
            id_col = "Equipment.Id" if "Equipment.Id" in hs.columns else "machine_id"
            low = hs[hs["health_score"] < threshold].sort_values("health_score")
            target_devices = [str(mid) for mid in low[id_col].head(top_n * 2).tolist()]
        if not target_devices:
            target_devices = [d["machine_id"] for d in alarms.get("all_devices", [])[:top_n]]
    elif report_type == "parts_summary":
        # Collect all devices with work orders (from industrial plan)
        plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
        if plan_path.exists():
            plan = pd.read_csv(plan_path)
            target_devices = [str(mid) for mid in plan["machine_id"].head(top_n * 2).tolist()]
        if not target_devices:
            target_devices = [d["machine_id"] for d in alarms.get("all_devices", [])[:top_n]]
    else:
        all_devices = alarms.get("all_devices", [])
        if report_type == "thermal":
            target_devices = alarms.get("thermal_drift_devices", [])[:top_n]
        elif report_type == "risk":
            target_devices = [d["machine_id"] for d in all_devices[:top_n]]
        else:  # weekly
            target_devices = [d["machine_id"] for d in all_devices[:top_n]]

    if not target_devices:
        target_devices = [d["machine_id"] for d in alarms.get("all_devices", [])[:top_n]]

    # ── Step 3: Query device status for each target ──
    device_details = []
    for mid in target_devices:
        detail = _query_device_status(mid)
        device_details.append(detail)

        # Collect recommendations (prefer industrial_plan, fall back to work_order)
        wo = detail.get("industrial_plan") or detail.get("work_order") or {}
        if wo:
            report_data["recommendations"].append({
                "machine_id": mid,
                "priority": wo.get("priority"),
                "action": wo.get("action_type"),
                "urgency": wo.get("urgency_score"),
                "cost_risk": wo.get("cost_at_risk"),
                "suggestion": wo.get("suggestion", "")[:300],
            })

    report_data["device_details"] = device_details

    # ── Step 4: Sensor trends for top devices ──
    sensor_charts = []
    sensors_to_query = ["temperature", "voltage", "amperage"]
    for mid in target_devices[:3]:  # Limit to top 3 for chart volume
        for sensor in sensors_to_query:
            trend = _get_sensor_trend(mid, sensor, hours=24)
            if "chart_data" in trend:
                sensor_charts.append({
                    "machine_id": mid,
                    "sensor": sensor,
                    "sensor_label": trend.get("sensor_label", sensor),
                    "trend_direction": trend.get("trend_direction", "stable"),
                    "risk_level": trend.get("risk_level", "low"),
                    "metrics": trend.get("metrics", {}),
                    "chart_data": trend["chart_data"],
                })

    report_data["sensor_charts"] = sensor_charts

    # ── Step 5: Fault history aggregation ──
    fault_stats = {
        "machines_analyzed": 0,
        "total_faults": 0,
        "fault_type_distribution": {},
        "fault_group_distribution": {},
        "highest_fault_rate": {"machine_id": "", "rate": 0},
    }
    for mid in target_devices:
        history = _get_fault_history(mid, limit=30)
        if history.get("found"):
            fault_stats["machines_analyzed"] += 1
            fault_stats["total_faults"] += history.get("total_faults", 0)

            rate = history.get("fault_rate_pct", 0)
            if rate > fault_stats["highest_fault_rate"]["rate"]:
                fault_stats["highest_fault_rate"] = {"machine_id": mid, "rate": rate}

            for ft, info in history.get("fault_type_distribution", {}).items():
                if ft not in fault_stats["fault_type_distribution"]:
                    fault_stats["fault_type_distribution"][ft] = 0
                fault_stats["fault_type_distribution"][ft] += info.get("count", 0)

                group = info.get("group", "Unknown")
                if group not in fault_stats["fault_group_distribution"]:
                    fault_stats["fault_group_distribution"][group] = 0
                fault_stats["fault_group_distribution"][group] += info.get("count", 0)

    report_data["fault_statistics"] = fault_stats

    # ── Step 6: Root cause analysis for the most critical device ──
    if target_devices:
        primary_device = target_devices[0]
        rca = _get_root_cause_analysis(primary_device)
        report_data["root_cause"] = {
            "machine_id": primary_device,
            "root_causes": rca.get("root_causes", []),
            "cascade_chains": rca.get("cascade_chains", []),
            "overall_confidence": rca.get("overall_confidence", 0),
            "diagnosis": rca.get("diagnosis", {}),
        }

    # ── Step 7: Cost risk aggregation ──
    total_cost_risk = 0
    cost_by_action = {}
    for d in device_details:
        wo = d.get("industrial_plan") or d.get("work_order") or {}
        if wo:
            cost = wo.get("cost_at_risk", 0)
            total_cost_risk += cost
            action = wo.get("action_type", "unknown")
            cost_by_action[action] = cost_by_action.get(action, 0) + cost

    report_data["cost_analysis"] = {
        "total_cost_at_risk": total_cost_risk,
        "cost_by_action": cost_by_action,
        "device_count": len(device_details),
        "average_cost_per_device": total_cost_risk / len(device_details) if device_details else 0,
    }

    # ── Step 7b: Health score aggregation ──
    health_scores = []
    health_path = DASHBOARD_DATA / "equipment_health_score.csv"
    if health_path.exists():
        hs = pd.read_csv(health_path)
        id_col = "Equipment.Id" if "Equipment.Id" in hs.columns else "machine_id"
        for d in device_details:
            mid = d.get("machine_id", "")
            match = hs[hs[id_col] == mid]
            if len(match) > 0:
                row = match.iloc[0]
                score = float(row["health_score"])
                trend = str(row.get("trend", ""))
                top_risk = str(row.get("top_risk_factor", ""))
                health_scores.append({"machine_id": mid, "health_score": score, "trend": trend, "top_risk": top_risk})
    health_scores.sort(key=lambda x: x["health_score"])
    report_data["health_analysis"] = {
        "scores": health_scores,
        "lowest": health_scores[0] if health_scores else None,
        "average": sum(h["health_score"] for h in health_scores) / len(health_scores) if health_scores else 0,
        "critical_count": sum(1 for h in health_scores if h["health_score"] < 30),
        "degrading_count": sum(1 for h in health_scores if h.get("trend") == "Degrading"),
    }

    # ── Step 7c: Spare parts aggregation ──
    parts_summary = {}
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    if plan_path.exists():
        plan = pd.read_csv(plan_path)
        for _, row in plan.iterrows():
            parts_str = str(row.get("spare_parts", "[]"))
            try:
                parts_list = json.loads(parts_str)
            except (json.JSONDecodeError, TypeError):
                parts_list = []
            for p in parts_list:
                pname = str(p).strip().replace('"', '') if p else "unknown"
                parts_summary[pname] = parts_summary.get(pname, 0) + 1
    # Sort by count descending
    parts_summary_sorted = sorted(parts_summary.items(), key=lambda x: x[1], reverse=True)
    report_data["parts_summary"] = {
        "total_part_types": len(parts_summary_sorted),
        "total_parts_needed": sum(v for _, v in parts_summary_sorted),
        "top_parts": [{"name": k, "count": v} for k, v in parts_summary_sorted[:10]],
        "all_parts": [{"name": k, "count": v} for k, v in parts_summary_sorted],
    }

    # ── Step 8: Predictability context ──
    try:
        pred = _explain_predictability_limit()
        report_data["predictability_context"] = {
            "conclusion": pred.get("conclusion", ""),
            "best_next_action": pred.get("best_next_action", ""),
        }
    except Exception:
        pass

    # ── Step 9: Build executive summary ──
    report_data["summary"] = _build_summary(report_data)

    # ── Step 10: Structure sections ──
    base_sections = {
        "executive_summary": {"title": "执行摘要", "order": 1},
        "alerts_overview": {"title": "高风险设备概览", "order": 2},
        "device_trends": {"title": "设备趋势分析", "order": 3},
        "fault_history": {"title": "故障历史分析", "order": 4},
        "root_cause": {"title": "根因分析", "order": 5},
        "maintenance_recommendations": {"title": "维护建议清单", "order": 6},
        "cost_risk_analysis": {"title": "成本风险分析", "order": 7},
        "predictive_benefits": {"title": "预测性维护效益分析", "order": 8},
    }
    if report_type == "health_critical":
        base_sections["health_analysis"] = {"title": "健康分排名 · 全场设备健康度", "order": 2.5}
    if report_type == "parts_summary":
        base_sections["parts_breakdown"] = {"title": "备件需求汇总 · 按频率排序", "order": 2.5}
    report_data["sections"] = base_sections

    return report_data


def _build_summary(report_data: dict) -> str:
    """Build an executive summary from aggregated report data."""
    alerts = report_data.get("alerts_summary", {})
    costs = report_data.get("cost_analysis", {})
    faults = report_data.get("fault_statistics", {})
    rca = report_data.get("root_cause", {})

    total_alarms = alerts.get("total", 0)
    thermal_count = alerts.get("thermal_drift_count", 0)
    shutdown_count = alerts.get("immediate_shutdown_count", 0)
    total_cost = costs.get("total_cost_at_risk", 0)

    lines = [
        f"## 执行摘要",
        f"",
        f"报告生成时间：{report_data.get('generated_at', 'N/A')}",
        f"报告类型：{report_data.get('report_type', 'N/A')}",
        f"",
        f"### 关键指标",
        f"- 当前需要关注的设备总数：{total_alarms} 台",
        f"- 热漂移设备：{thermal_count} 台",
        f"- 需要立即停机设备：{shutdown_count} 台",
        f"- 总成本风险：${total_cost:,.2f}",
        f"- 最高故障率设备：{faults.get('highest_fault_rate', {}).get('machine_id', 'N/A')} "
        f"({faults.get('highest_fault_rate', {}).get('rate', 0)}% 故障率)",
    ]

    if shutdown_count > 0:
        shutdown_devices = alerts.get("immediate_shutdown_devices", [])
        lines.append(f"")
        lines.append(f"### ⚠ 紧急关注")
        lines.append(f"以下设备需要立即停机检查：{', '.join(shutdown_devices[:5])}")

    if thermal_count > 0:
        thermal_devices = alerts.get("thermal_drift_devices", [])
        lines.append(f"")
        lines.append(f"### 🔥 热漂移风险")
        lines.append(f"以下设备存在持续热积聚趋势，预计72小时内可能进入紧急停机风险区间：")
        lines.append(f"{', '.join(thermal_devices[:10])}")

    rca_causes = rca.get("root_causes", [])
    if rca_causes:
        lines.append(f"")
        lines.append(f"### 主要故障模式")
        for c in rca_causes[:3]:
            lines.append(f"- {c.get('cause', 'Unknown')}（置信度 {c.get('confidence', 0):.0%}）")

    return "\n".join(lines)
