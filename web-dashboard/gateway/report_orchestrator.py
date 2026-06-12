"""
Report Orchestrator — multi-step MCP tool coordination for AI-driven reports.

Architecture:
  generate_maintenance_report() orchestrates multiple existing MCP tools
  (list_alarm_devices, query_device_status, get_sensor_trend,
   get_fault_history, get_root_cause_analysis) without reading CSV directly.

Report Types:
  - weekly: Full weekly report — all alarm devices, trends, fault stats
  - device:  Single-device deep health report
  - risk:    High-risk devices only
  - thermal: Thermal buildup focused analysis
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Ensure gateway package is importable
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

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
# Report Orchestrator
# ══════════════════════════════════════════════════════════════════════════

def generate_maintenance_report(
    report_type: str = "weekly",
    machine_id: Optional[str] = None,
    top_n: int = 5,
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

    # ── Step 2: Determine target devices ──
    if report_type == "device" and machine_id:
        target_devices = [machine_id]
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

        # Collect recommendations
        wo = detail.get("work_order")
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
        wo = d.get("work_order")
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
    report_data["sections"] = {
        "executive_summary": {"title": "执行摘要", "order": 1},
        "alerts_overview": {"title": "高风险设备概览", "order": 2},
        "device_trends": {"title": "设备趋势分析", "order": 3},
        "fault_history": {"title": "故障历史分析", "order": 4},
        "root_cause": {"title": "根因分析", "order": 5},
        "maintenance_recommendations": {"title": "维护建议清单", "order": 6},
        "cost_risk_analysis": {"title": "成本风险分析", "order": 7},
        "predictive_benefits": {"title": "预测性维护效益分析", "order": 8},
    }

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
