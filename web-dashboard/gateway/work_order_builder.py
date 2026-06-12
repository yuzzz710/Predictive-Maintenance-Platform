"""
Work Order Builder — dynamically compute work order details for any machine.
============================================================================
When a machine is not in industrial_maintenance_plan.csv (only top 30-100 machines),
this module dynamically computes: fault pattern, action type, technician, spare parts.

Data sources (cover all 100 machines):
  - z_scores.csv: latest Z-Scores per machine
  - equipment_health_score.csv: health score, cost risk
  - technician_assigner.py: 12 rules for matching technicians
  - spare_parts_planner.py: parts catalog for fault types
"""

import csv
import sys
import os
from pathlib import Path
from typing import Dict, Optional

from gateway.config import DASHBOARD_DATA, PROJECT_ROOT

# Add skills to path for imports
SKILLS_DIR = PROJECT_ROOT / "skills" / "predictive-maintenance-decision" / "scripts"
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))


def _read_latest_z(machine_id: str) -> Optional[Dict]:
    """Read latest Z-Score row for a machine."""
    z_path = DASHBOARD_DATA / "z_scores.csv"
    if not z_path.exists():
        return None
    latest = None
    try:
        with open(z_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Equipment.Id", "").strip() == machine_id:
                    latest = row
        if not latest:
            return None
        return {
            "z_Voltage": float(latest.get("z_Voltage", 0) or 0),
            "z_Amperage": float(latest.get("z_Amperage", 0) or 0),
            "z_Temperature": float(latest.get("z_Temperature", 0) or 0),
            "z_composite": float(latest.get("z_composite", 0) or 0),
            "alert_level": latest.get("alert_level", "Normal"),
            "failure_group": latest.get("failure_group", "Normal"),
        }
    except Exception:
        return None


def _read_health(machine_id: str) -> Dict:
    """Read health score and cost risk for a machine."""
    h_path = DASHBOARD_DATA / "equipment_health_score.csv"
    result = {"health_score": 50, "cost_at_risk": 1000}
    if not h_path.exists():
        return result
    try:
        with open(h_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Equipment.Id", "").strip() == machine_id:
                    result["health_score"] = float(row.get("health_score", 50) or 50)
                    result["cost_at_risk"] = float(row.get("cost_at_risk", 1000) or 1000)
                    break
    except Exception:
        pass
    return result


def _determine_pattern(z: Dict) -> str:
    """Determine primary fault pattern from Z-Scores."""
    if not z:
        return "normal"
    zv, za, zt = abs(z.get("z_Voltage", 0)), abs(z.get("z_Amperage", 0)), abs(z.get("z_Temperature", 0))
    patterns = []
    if zv > 2.0:
        patterns.append("voltage_drift")
    if za > 2.0:
        patterns.append("power_anomaly")
    if zt > 2.0:
        patterns.append("thermal_buildup")
    if len(patterns) >= 2:
        return "combined_degradation"
    if len(patterns) == 1:
        return patterns[0]
    # All Z low but alert level high → combined degradation
    if z.get("alert_level", "Normal") in ("Alarm", "Warning"):
        return "combined_degradation"
    return "normal"


def _determine_action(z: Dict, health: Dict) -> str:
    """Determine recommended action from alert level and health score."""
    if not z:
        return "routine_check"
    alert = z.get("alert_level", "Normal")
    zc = z.get("z_composite", 0)
    hs = health.get("health_score", 50)
    failure_group = z.get("failure_group", "Normal")

    if failure_group != "Normal":
        if alert == "Alarm" and zc > 3.0:
            return "immediate_shutdown"
        if alert == "Alarm":
            return "preventive_repair"
        if alert == "Warning":
            return "schedule_inspection"

    if alert == "Alarm":
        return "preventive_repair"
    if alert == "Warning":
        return "schedule_inspection"
    if hs < 50:
        return "increase_monitoring"
    return "routine_check"


def _determine_priority(health: Dict, z: Dict) -> str:
    """Determine maintenance priority."""
    hs = health.get("health_score", 50)
    zc = abs(z.get("z_composite", 0)) if z else 0
    if hs < 30 or zc > 3.0:
        return "P1"
    if hs < 50 or zc > 2.0:
        return "P2"
    return "P3"


def _determine_window(action: str, priority: str) -> str:
    """Determine downtime window."""
    if action == "immediate_shutdown":
        return "immediate"
    if action == "preventive_repair" and priority == "P1":
        return "night"
    if action == "schedule_inspection":
        return "night"
    return "scheduled"


def _get_technician(pattern: str, alert_level: str, action: str, cost_risk: float) -> tuple:
    """Get technician type and count using the existing assigner logic."""
    tech_type = "junior_technician"
    tech_count = 1
    try:
        from technician_assigner import TechnicianAssigner
        assigner = TechnicianAssigner()
        risk_level = "ALARM" if alert_level == "Alarm" else "WARNING" if alert_level == "Warning" else "WATCH"
        risk_tier = "High" if cost_risk > 5000 else "Medium"
        result = assigner.assign(
            primary_pattern=pattern,
            risk_level=risk_level,
            action_type=action,
            risk_tier=risk_tier,
            cost_at_risk=cost_risk,
        )
        tech_type = result.get("type", "junior_technician")
        tech_count = result.get("count", 1)
    except Exception:
        # Simple fallback based on pattern
        mapping = {
            "voltage_drift": ("electrical_specialist", 2),
            "thermal_buildup": ("thermal_specialist", 2),
            "power_anomaly": ("electrical_specialist", 2),
            "combined_degradation": ("senior_technician", 2),
            "normal": ("junior_technician", 1),
        }
        tech_type, tech_count = mapping.get(pattern, ("junior_technician", 1))
    return tech_type, tech_count


def _get_spare_parts(pattern: str, z: Dict) -> list:
    """Get spare parts list using the existing planner."""
    try:
        from spare_parts_planner import SparePartsPlanner
        planner = SparePartsPlanner()
        parts = planner.recommend(
            primary_pattern=pattern,
            z_v=z.get("z_Voltage", 0) if z else 0,
            z_a=z.get("z_Amperage", 0) if z else 0,
            z_t=z.get("z_Temperature", 0) if z else 0,
        )
        return [p.get("name", "") for p in parts if p.get("name")]
    except Exception:
        return ["o-ring_set"]


def build_work_order_context(machine_id: str) -> Dict:
    """
    Build complete work order context for any machine.
    Returns a dict compatible with plan_data format used by the frontend.
    """
    z = _read_latest_z(machine_id)
    health = _read_health(machine_id)

    pattern = _determine_pattern(z)
    action = _determine_action(z, health)
    priority = _determine_priority(health, z)
    window = _determine_window(action, priority)
    cost_risk = health.get("cost_at_risk", 1000)

    tech_type, tech_count = _get_technician(pattern, z.get("alert_level", "Normal") if z else "Normal", action, cost_risk)
    parts = _get_spare_parts(pattern, z)

    import json
    return {
        "machine_id": machine_id,
        "health_score": str(health.get("health_score", 50)),
        "cost_at_risk": str(cost_risk),
        "primary_pattern": pattern,
        "recommended_action": action,
        "technician_type": tech_type,
        "technician_count": str(tech_count),
        "maintenance_priority": priority,
        "recommended_downtime_window": window,
        "spare_parts": json.dumps(parts, ensure_ascii=False),
        "acceptance_standard": "通用验收标准: 维修后Z-Score回归正常范围，24h无告警复现",
        "reasoning": _build_reasoning(machine_id, z, health, pattern, action),
        "sla_target_hours": "24" if priority == "P1" else "48" if priority == "P2" else "72",
        "maintenance_strategy": "",
        "priority": "1" if priority == "P1" else "2" if priority == "P2" else "3",
        "alert_level": z.get("alert_level", "Normal") if z else "Normal",
        "action_type": action,
        "urgency_score": _calc_urgency(z, health),
        "recommended_window_days": "1" if priority == "P1" else "3" if priority == "P2" else "7",
        "expected_savings": str(round(cost_risk * 0.7, 2)),
        "estimated_cost": str(round(cost_risk * 0.3, 2)),
        "estimated_duration_hours": "2" if action == "routine_check" else "4" if action == "schedule_inspection" else "8",
    }


def _build_reasoning(mid: str, z: Dict, health: Dict, pattern: str, action: str) -> str:
    """Build a Chinese reasoning string."""
    hs = health.get("health_score", 50)
    pattern_cn = {
        "voltage_drift": "电压漂移", "thermal_buildup": "热积聚",
        "power_anomaly": "功率异常", "combined_degradation": "复合退化", "normal": "正常运行",
    }
    action_cn = {
        "immediate_shutdown": "紧急停机", "preventive_repair": "预防性维修",
        "schedule_inspection": "计划检查", "increase_monitoring": "加强监控", "routine_check": "常规检查",
    }
    if z:
        zc = z.get("z_composite", 0)
        return f"健康分{hs:.0f}，z_composite={zc:.2f}，判定为{pattern_cn.get(pattern, pattern)}，建议{action_cn.get(action, action)}。"
    return f"健康分{hs:.0f}，无Z-Score数据，建议常规检查。"


def _calc_urgency(z: Dict, health: Dict) -> str:
    """Calculate urgency score."""
    score = 50
    if z:
        zc = abs(z.get("z_composite", 0))
        if zc > 3:
            score = 95
        elif zc > 2:
            score = 80
        elif zc > 1:
            score = 60
    hs = health.get("health_score", 50)
    if hs < 30:
        score = max(score, 85)
    elif hs < 50:
        score = max(score, 65)
    return str(score)
