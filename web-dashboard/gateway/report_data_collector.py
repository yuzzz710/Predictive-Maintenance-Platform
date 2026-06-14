"""
Report Data Collector — Layer 1 of the report system.

Pure data gathering. Each data source has a dedicated method with its
own try/except — failure returns None, never crashes the whole report.

Usage:
    from gateway.report_data_collector import collect_all_context
    ctx = collect_all_context(report_type="weekly", config=cfg, ...)
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from gateway.config import DASHBOARD_DATA
from gateway.report_models import ReportContext

# ══════════════════════════════════════════════════════════════════════════
# MCP tool imports — these are the existing data-access functions
# ══════════════════════════════════════════════════════════════════════════
from gateway.tools import (
    _list_alarm_devices,
    _query_device_status,
    _get_sensor_trend,
    _get_fault_history,
    _get_root_cause_analysis,
    _explain_predictability_limit,
)


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def collect_all_context(
    report_type: str,
    config: dict,
    machine_id: str | None = None,
    top_n: int = 5,
    health_threshold: int = 30,
) -> ReportContext:
    """Collect all data required by the report type's data_sources list.

    Only fetches sources that appear in config['data_sources'].
    Each failure is caught, logged, and results in a None field —
    the report continues with whatever data is available.
    """
    ctx = ReportContext(report_type=report_type)
    sources = set(config.get("data_sources", []))

    # ── Alerts overview ──
    if "alerts" in sources:
        ctx.alerts_summary = _collect_alerts(ctx) or ctx.alerts_summary

    # ── Resolve target devices (needed by multiple downstream sources) ──
    target_devices = _resolve_targets(ctx, config, machine_id, top_n, health_threshold, sources)

    # ── Device details ──
    if "devices" in sources:
        ctx.device_details = _collect_device_details(ctx, target_devices)

    # ── Sensor trends ──
    if "sensors" in sources:
        ctx.sensor_charts = _collect_sensor_trends(ctx, target_devices[:3])

    # ── Fault history ──
    if "faults" in sources:
        ctx.fault_statistics = _collect_faults(ctx, target_devices)

    # ── Root cause analysis ──
    if "rca" in sources and target_devices:
        ctx.root_cause = _collect_root_cause(ctx, target_devices[0])

    # ── Cost analysis ──
    if "cost" in sources:
        ctx.cost_analysis = _collect_cost_analysis(ctx)

    # ── Health analysis ──
    if "health" in sources:
        ctx.health_analysis = _collect_health_analysis(ctx)

    # ── Parts summary ──
    if "parts" in sources:
        ctx.parts_summary = _collect_parts_summary(ctx)

    # ── Predictability context ──
    if "predictability" in sources:
        ctx.predictability_context = _collect_predictability(ctx)

    # ── Work order context (for work_order reports) ──
    if "expert_rules" in sources and machine_id:
        ctx.work_order_context = _build_work_order_context(ctx, machine_id)

    return ctx


# ══════════════════════════════════════════════════════════════════════════
# Target device resolution
# ══════════════════════════════════════════════════════════════════════════

def _resolve_targets(
    ctx: ReportContext,
    config: dict,
    machine_id: str | None,
    top_n: int,
    health_threshold: int,
    sources: set,
) -> list[str]:
    """Determine which devices to include in the report based on type & scope."""
    thresholds = config.get("thresholds", {})
    _top_n = thresholds.get("top_n", top_n)
    _health = thresholds.get("health_threshold", health_threshold)
    report_type = ctx.report_type

    if report_type == "device" and machine_id:
        return [machine_id]

    alarms = ctx.alerts_summary or {}
    all_devices = alarms.get("all_devices", [])

    if report_type == "health_critical":
        hp = DASHBOARD_DATA / "equipment_health_score.csv"
        if hp.exists():
            hs = pd.read_csv(hp)
            id_col = "Equipment.Id" if "Equipment.Id" in hs.columns else "machine_id"
            low = hs[hs["health_score"] < _health].sort_values("health_score")
            targets = [str(mid) for mid in low[id_col].head(_top_n * 2).tolist()]
            if targets:
                return targets

    if report_type == "parts_summary":
        pp = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
        if pp.exists():
            plan = pd.read_csv(pp)
            return [str(mid) for mid in plan["machine_id"].head(_top_n * 2).tolist()]

    if report_type == "thermal":
        targets = alarms.get("thermal_drift_devices", [])[:_top_n]
        if targets:
            return targets
        # fall through to default

    # weekly / risk / default
    targets = [d["machine_id"] for d in all_devices[:_top_n]]
    return targets


# ══════════════════════════════════════════════════════════════════════════
# Data source methods — each with own try/except for degradation
# ══════════════════════════════════════════════════════════════════════════

def _collect_alerts(ctx: ReportContext) -> dict | None:
    try:
        alarms = _list_alarm_devices()
        result = {
            "total": alarms.get("total_alarm_devices", 0),
            "alarm_count": alarms.get("alarm_count", 0),
            "warning_count": alarms.get("warning_count", 0),
            "thermal_drift_count": alarms.get("thermal_drift_count", 0),
            "immediate_shutdown_count": alarms.get("immediate_shutdown_count", 0),
            "thermal_drift_devices": alarms.get("thermal_drift_devices", []),
            "immediate_shutdown_devices": alarms.get("immediate_shutdown_devices", []),
            "all_devices": alarms.get("all_devices", []),
        }
        ctx.mark_source_ok("alerts")
        return result
    except Exception as e:
        ctx.mark_source_fail("alerts")
        return {"total": 0, "alarm_count": 0, "_error": str(e)}


def _collect_device_details(ctx: ReportContext, targets: list[str]) -> list[dict]:
    details = []
    for mid in targets:
        try:
            details.append(_query_device_status(mid))
        except Exception:
            details.append({"machine_id": mid, "_error": "query failed"})
    if details:
        ctx.mark_source_ok("devices")
    else:
        ctx.mark_source_fail("devices")
    return details


def _collect_sensor_trends(ctx: ReportContext, targets: list[str]) -> list[dict]:
    charts = []
    sensors = ["temperature", "voltage", "amperage"]
    for mid in targets:
        for sensor in sensors:
            try:
                trend = _get_sensor_trend(mid, sensor, hours=24)
                if "chart_data" in trend:
                    charts.append({
                        "machine_id": mid,
                        "sensor": sensor,
                        "sensor_label": trend.get("sensor_label", sensor),
                        "trend_direction": trend.get("trend_direction", "stable"),
                        "risk_level": trend.get("risk_level", "low"),
                        "metrics": trend.get("metrics", {}),
                        "chart_data": trend["chart_data"],
                    })
            except Exception:
                pass
    ctx.mark_source_ok("sensors") if charts else ctx.mark_source_fail("sensors")
    return charts


def _collect_faults(ctx: ReportContext, targets: list[str]) -> dict | None:
    try:
        stats = {
            "machines_analyzed": 0, "total_faults": 0,
            "fault_type_distribution": {}, "fault_group_distribution": {},
            "highest_fault_rate": {"machine_id": "", "rate": 0},
        }
        for mid in targets:
            try:
                history = _get_fault_history(mid, limit=30)
                if history.get("found"):
                    stats["machines_analyzed"] += 1
                    stats["total_faults"] += history.get("total_faults", 0)
                    rate = history.get("fault_rate_pct", 0)
                    if rate > stats["highest_fault_rate"]["rate"]:
                        stats["highest_fault_rate"] = {"machine_id": mid, "rate": rate}
                    for ft, info in history.get("fault_type_distribution", {}).items():
                        stats["fault_type_distribution"][ft] = (
                            stats["fault_type_distribution"].get(ft, 0) + info.get("count", 0))
                        group = info.get("group", "Unknown")
                        stats["fault_group_distribution"][group] = (
                            stats["fault_group_distribution"].get(group, 0) + info.get("count", 0))
            except Exception:
                pass
        ctx.mark_source_ok("faults")
        return stats
    except Exception as e:
        ctx.mark_source_fail("faults")
        return None


def _collect_root_cause(ctx: ReportContext, primary: str) -> dict | None:
    try:
        rca = _get_root_cause_analysis(primary)
        result = {
            "machine_id": primary,
            "root_causes": rca.get("root_causes", []),
            "cascade_chains": rca.get("cascade_chains", []),
            "overall_confidence": rca.get("overall_confidence", 0),
            "diagnosis": rca.get("diagnosis", {}),
        }
        ctx.mark_source_ok("rca")
        return result
    except Exception as e:
        ctx.mark_source_fail("rca")
        return None


def _collect_cost_analysis(ctx: ReportContext) -> dict:
    total = 0
    by_action = {}
    for d in ctx.device_details:
        try:
            wo = d.get("industrial_plan") or d.get("work_order") or {}
            if wo:
                cost = wo.get("cost_at_risk", 0)
                total += cost
                action = wo.get("action_type", "unknown")
                by_action[action] = by_action.get(action, 0) + cost
        except Exception:
            pass
    n = len(ctx.device_details) or 1
    result = {
        "total_cost_at_risk": total,
        "cost_by_action": by_action,
        "device_count": len(ctx.device_details),
        "average_cost_per_device": total / n,
    }
    ctx.mark_source_ok("cost")
    return result


def _collect_health_analysis(ctx: ReportContext) -> dict | None:
    try:
        hp = DASHBOARD_DATA / "equipment_health_score.csv"
        if not hp.exists():
            ctx.mark_source_fail("health")
            return None
        hs = pd.read_csv(hp)
        id_col = "Equipment.Id" if "Equipment.Id" in hs.columns else "machine_id"
        scores = []
        for d in ctx.device_details:
            mid = d.get("machine_id", "")
            match = hs[hs[id_col] == mid]
            if len(match) > 0:
                row = match.iloc[0]
                scores.append({
                    "machine_id": mid,
                    "health_score": float(row.get("health_score", 100) or 100),
                    "trend": str(row.get("trend", "")),
                    "top_risk": str(row.get("top_risk_factor", "")),
                })
        scores.sort(key=lambda x: x["health_score"])
        result = {
            "scores": scores,
            "lowest": scores[0] if scores else None,
            "average": sum(s["health_score"] for s in scores) / len(scores) if scores else 0,
            "critical_count": sum(1 for s in scores if s["health_score"] < 30),
            "degrading_count": sum(1 for s in scores if s.get("trend") == "Degrading"),
        }
        ctx.mark_source_ok("health")
        return result
    except Exception as e:
        ctx.mark_source_fail("health")
        return None


def _collect_parts_summary(ctx: ReportContext) -> dict | None:
    try:
        pp = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
        if not pp.exists():
            ctx.mark_source_fail("parts")
            return None
        plan = pd.read_csv(pp)
        parts = {}
        for _, row in plan.iterrows():
            try:
                parts_list = json.loads(str(row.get("spare_parts", "[]")))
            except (json.JSONDecodeError, TypeError):
                parts_list = []
            for p in parts_list:
                pname = str(p).strip().replace('"', '') if p else "unknown"
                parts[pname] = parts.get(pname, 0) + 1
        sorted_parts = sorted(parts.items(), key=lambda x: x[1], reverse=True)
        result = {
            "total_part_types": len(sorted_parts),
            "total_parts_needed": sum(v for _, v in sorted_parts),
            "top_parts": [{"name": k, "count": v} for k, v in sorted_parts[:10]],
            "all_parts": [{"name": k, "count": v} for k, v in sorted_parts],
        }
        ctx.mark_source_ok("parts")
        return result
    except Exception as e:
        ctx.mark_source_fail("parts")
        return None


def _collect_predictability(ctx: ReportContext) -> dict | None:
    try:
        pred = _explain_predictability_limit()
        result = {
            "conclusion": pred.get("conclusion", ""),
            "best_next_action": pred.get("best_next_action", ""),
        }
        ctx.mark_source_ok("predictability")
        return result
    except Exception as e:
        ctx.mark_source_fail("predictability")
        return None


# ══════════════════════════════════════════════════════════════════════════
# Work order context builder (moved from report_orchestrator.py)
# ══════════════════════════════════════════════════════════════════════════

def _build_work_order_context(ctx: ReportContext, machine_id: str) -> dict:
    """Aggregate multi-source data for a single machine as LLM prompt context."""
    wc = {"machine_id": machine_id}

    try:
        status = _query_device_status(machine_id)
        wo = status.get("industrial_plan") or status.get("work_order") or {}
        wc.update({
            "alert_level": wo.get("alert_level", status.get("alert_level", "NORMAL")),
            "action_type": wo.get("action_type", status.get("action_type", "routine_check")),
            "priority": wo.get("priority", status.get("priority", 99)),
            "urgency_score": wo.get("urgency_score", status.get("urgency_score", 0)),
            "cost_at_risk": wo.get("cost_at_risk", status.get("cost_at_risk", 0)),
            "maintenance_suggestion": wo.get("suggestion", wo.get("maintenance_suggestion", "")),
            "primary_pattern": status.get("primary_pattern", "combined_degradation"),
            "diagnosis_confidence": status.get("diagnosis_confidence", 0),
            "health_score": status.get("health_score", 50),
            "health_trend": status.get("health_trend", "stable"),
            "top_risk_factor": status.get("top_risk_factor", ""),
            "z_scores": {
                "z_voltage": status.get("z_voltage", 0),
                "z_amperage": status.get("z_amperage", 0),
                "z_temperature": status.get("z_temperature", 0),
                "z_composite": status.get("z_composite", 0),
            },
            "shap_attribution": {
                "top_risk_factor_1": wo.get("top_risk_factor_1", ""),
                "top_risk_factor_2": wo.get("top_risk_factor_2", ""),
                "top_risk_factor_3": wo.get("top_risk_factor_3", ""),
                "shap_risk_summary": wo.get("shap_risk_summary", ""),
            },
            "technician_type": wo.get("technician_type", ""),
            "technician_count": wo.get("technician_count", 1),
            "spare_parts": wo.get("spare_parts", "[]"),
            "suggested_window_days": wo.get("suggested_window_days", wo.get("window_days", 7)),
            "sla_target_hours": wo.get("sla_target_hours", 24),
            "estimated_cost": wo.get("estimated_cost", 0),
            "expected_savings": wo.get("expected_savings", 0),
            "acceptance_standard": wo.get("acceptance_standard", ""),
        })
    except Exception:
        pass

    try:
        history = _get_fault_history(machine_id, limit=20)
        if history.get("found"):
            wc["fault_history"] = {
                "total_faults": history.get("total_faults", 0),
                "fault_rate_pct": history.get("fault_rate_pct", 0),
                "fault_types": history.get("fault_type_distribution", {}),
                "recent_faults": history.get("recent_faults", [])[:5],
            }
    except Exception:
        wc["fault_history"] = {"total_faults": 0, "note": "unavailable"}

    try:
        trend_v = _get_sensor_trend(machine_id, "voltage", hours=24)
        trend_t = _get_sensor_trend(machine_id, "temperature", hours=24)
        trend_a = _get_sensor_trend(machine_id, "amperage", hours=24)
        wc["sensor_trends"] = {
            "voltage": {"trend_direction": trend_v.get("trend_direction", "stable"), "risk_level": trend_v.get("risk_level", "low")},
            "temperature": {"trend_direction": trend_t.get("trend_direction", "stable"), "risk_level": trend_t.get("risk_level", "low")},
            "amperage": {"trend_direction": trend_a.get("trend_direction", "stable"), "risk_level": trend_a.get("risk_level", "low")},
        }
    except Exception:
        wc["sensor_trends"] = {"note": "unavailable"}

    # Acceptance criteria from rules JSON
    try:
        pattern = wc.get("primary_pattern", "")
        rules_path = (
            BASE_DIR.parent / "skills" / "predictive-maintenance-decision"
            / "scripts" / "data" / "acceptance_rules.json"
        )
        if rules_path.exists():
            with open(rules_path, "r", encoding="utf-8") as f:
                acceptance_rules = json.load(f)
            for rule in acceptance_rules.get("rules", []):
                if rule.get("fault_type") == pattern:
                    wc["acceptance_criteria"] = rule.get("acceptance_criteria", [])
                    break
            wc["universal_criteria"] = acceptance_rules.get("universal_criteria", [])
    except Exception:
        wc["acceptance_criteria"] = []

    ctx.mark_source_ok("expert_rules")
    return wc
