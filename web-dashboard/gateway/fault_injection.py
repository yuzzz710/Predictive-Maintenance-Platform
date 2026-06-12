"""
Fault Injection API — 全流程故障注入演示端点
===============================================
Provides POST /api/fault-injection for the interactive demo.
Computes synthetic Z-Scores, SHAP data, and work orders
based on fault type signatures — ALL in-memory, no file writes.

Architecture:
  - Reads failure_sig.csv for fault signatures (read-only)
  - Computes synthetic Z-Scores from fault group + severity
  - Generates SHAP-like attribution data from templates
  - Calls work_order_builder internals for realistic work orders
  - Returns complete injection JSON for frontend step animation
"""

import csv
import json
import math
import random
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from gateway.config import DASHBOARD_DATA, PROJECT_ROOT

router = APIRouter(prefix="/api", tags=["fault-injection"])

# ── Constants ────────────────────────────────────────────────────────────

# Fault group → which Z-Scores are dominant/moderate/mild
FAULT_GROUP_Z_PROFILE = {
    "High-Voltage": {"dominant": "V", "moderate": "T", "mild": "A"},
    "Thermal":       {"dominant": "T", "moderate": "V", "mild": "A"},
    "Subtle":        {"dominant": "A", "moderate": "V", "mild": "T"},
}

# Severity → Z-Score multipliers for (dominant, moderate, mild)
SEVERITY_Z = {
    "mild":   {"dominant": 1.8, "moderate": 1.2, "mild": 0.5},
    "medium": {"dominant": 2.8, "moderate": 1.8, "mild": 0.8},
    "severe": {"dominant": 4.2, "moderate": 2.5, "mild": 1.2},
}

# Severity → health score penalty
SEVERITY_HEALTH_PENALTY = {"mild": -10, "medium": -25, "severe": -45}

# Fault group → Chinese label
GROUP_CN = {
    "High-Voltage": "高压异常", "Thermal": "热控异常",
    "Subtle": "微弱异常", "Normal": "正常运行",
}

# Fault group → primary risk category for SHAP
GROUP_RISK_CATEGORY = {
    "High-Voltage": "电气风险", "Thermal": "热风险", "Subtle": "综合风险",
}

# Pattern → Chinese
PATTERN_CN = {
    "voltage_drift": "电压漂移", "thermal_buildup": "热积聚",
    "power_anomaly": "功率异常", "combined_degradation": "复合退化",
    "normal": "正常运行",
}

# Action → Chinese
ACTION_CN = {
    "immediate_shutdown": "紧急停机", "preventive_repair": "预防性维修",
    "schedule_inspection": "计划检查", "increase_monitoring": "加强监控",
    "routine_check": "常规检查",
}

# Technician type → Chinese
TECH_CN = {
    "senior_technician": "高级技师", "electrical_specialist": "电气专家",
    "thermal_specialist": "热控专家", "junior_technician": "初级技师",
}

# Technician type → color
TECH_COLOR = {
    "senior_technician": "#a371f7", "electrical_specialist": "#4d94ff",
    "thermal_specialist": "#f0a030", "junior_technician": "#8e9aab",
}

# ── Request model ────────────────────────────────────────────────────────

class FaultInjectionRequest(BaseModel):
    machine_id: str = Field(..., pattern=r"^CNC_\d{3}$", description="Target machine ID, e.g. CNC_042")
    fault_type: int = Field(..., ge=1, le=9, description="Fault type 1-9")
    severity: str = Field("medium", pattern=r"^(mild|medium|severe)$",
                          description="Severity: mild / medium / severe")


# ── Helpers ──────────────────────────────────────────────────────────────

def _load_fault_sig() -> Dict[int, dict]:
    """Load failure_sig.csv into a dict keyed by fault_type."""
    sig_path = DASHBOARD_DATA / "failure_sig.csv"
    result = {}
    with open(sig_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ft = int(row["failure_type"])
            result[ft] = {
                "failure_group": row["failure_group"],
                "n": int(row["n"]),
                "v_mean": float(row["Op.Voltage_mean"]),
                "v_delta_pct": float(row["Op.Voltage_delta_pct"]),
                "a_mean": float(row["Op.Amperage_mean"]),
                "a_delta_pct": float(row["Op.Amperage_delta_pct"]),
                "t_mean": float(row["Op.Temperature_mean"]),
                "t_delta_pct": float(row["Op.Temperature_delta_pct"]),
            }
    return result


def _read_health(machine_id: str) -> dict:
    """Read current health score for a machine."""
    h_path = DASHBOARD_DATA / "equipment_health_score.csv"
    result = {"health_score": 65, "cost_at_risk": 3500, "health_level": "Healthy"}
    try:
        with open(h_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Equipment.Id", "").strip() == machine_id:
                    result["health_score"] = float(row.get("health_score", 65) or 65)
                    result["cost_at_risk"] = float(row.get("cost_at_risk", 3500) or 3500)
                    result["health_level"] = row.get("health_level", "Healthy")
                    break
    except Exception:
        pass
    return result


def _compute_z_scores(fault_group: str, severity: str) -> dict:
    """Generate synthetic Z-Scores based on fault group and severity.

    Uses per-group profiles: High-Voltage→V dominant, Thermal→T dominant, Subtle→A dominant.
    Adds small random jitter (±0.1) for realism.
    """
    profile = FAULT_GROUP_Z_PROFILE.get(fault_group, FAULT_GROUP_Z_PROFILE["Subtle"])
    sev = SEVERITY_Z[severity]

    z_vals = {"V": 0.0, "A": 0.0, "T": 0.0}
    for role, param in [("dominant", profile["dominant"]),
                         ("moderate", profile["moderate"]),
                         ("mild", profile["mild"])]:
        base = sev[role]
        jitter = random.uniform(-0.15, 0.15)
        z_vals[param] = round(base + jitter, 2)

    z_composite = round(math.sqrt(z_vals["V"]**2 + z_vals["A"]**2 + z_vals["T"]**2), 2)

    # Alert level
    if z_composite > 2.5:
        alert_level = "Alarm"
    elif z_composite > 1.5:
        alert_level = "Warning"
    else:
        alert_level = "Watch"

    return {
        "z_Voltage": z_vals["V"], "z_Amperage": z_vals["A"],
        "z_Temperature": z_vals["T"], "z_composite": z_composite,
        "alert_level": alert_level, "failure_group": fault_group,
    }


def _generate_shap(machine_id: str, z: dict, fault_group: str, severity: str) -> dict:
    """Generate synthetic SHAP attribution data matching shap_dashboard.json structure."""
    zc = z["z_composite"]

    # Risk score from z_composite
    risk_score = round(min(0.95, 0.35 + zc * 0.12), 2)
    risk_level = "High" if risk_score > 0.7 else "Medium" if risk_score > 0.4 else "Low"
    category = GROUP_RISK_CATEGORY.get(fault_group, "综合风险")

    # Build anomaly signals based on which Z-scores are elevated
    signals = []
    if z["z_Voltage"] > 1.5:
        signals.append({
            "severity": "🔴" if z["z_Voltage"] > 2.5 else "🟡",
            "feature_label": "电压异常 (Voltage Drift)",
            "value_label": f"z = {z['z_Voltage']:.1f}",
            "explanation": f"电压偏离设备基线 {z['z_Voltage']:.1f}σ，可能存在供电模块或稳压器问题",
        })
    if z["z_Temperature"] > 1.5:
        signals.append({
            "severity": "🔴" if z["z_Temperature"] > 2.5 else "🟡",
            "feature_label": "温度异常 (Thermal Buildup)",
            "value_label": f"z = {z['z_Temperature']:.1f}",
            "explanation": f"温度高于设备基线 {z['z_Temperature']:.1f}σ，可能存在散热或冷却系统问题",
        })
    if z["z_Amperage"] > 1.5:
        signals.append({
            "severity": "🔴" if z["z_Amperage"] > 2.5 else "🟡",
            "feature_label": "电流异常 (Power Anomaly)",
            "value_label": f"z = {z['z_Amperage']:.1f}",
            "explanation": f"电流偏离设备基线 {z['z_Amperage']:.1f}σ，可能存在电机驱动或绕组问题",
        })
    if not signals:
        signals.append({
            "severity": "🟢", "feature_label": "综合评估",
            "value_label": f"z_composite = {zc:.1f}",
            "explanation": "多参数联合偏离基线，建议综合诊断",
        })

    # Top contributors
    contributors = [
        {"feature": "z_composite_max", "label": "综合异常峰值", "contribution": round(0.35 * zc / 3.0 + random.uniform(-0.03, 0.03), 3), "direction": "↑"},
        {"feature": f"z_{['Voltage','Temperature','Amperage'][0]}_last",
         "label": f"{['电压','温度','电流'][0]}异常终值", "contribution": round(0.20 * zc / 3.0 + random.uniform(-0.02, 0.02), 3), "direction": "↑"},
        {"feature": "n_warning_windows", "label": "历史预警窗口数", "contribution": round(0.12 + random.uniform(-0.02, 0.02), 3), "direction": "↑"},
    ]

    # Inspection checklist
    checklists = {
        "High-Voltage": ["检查供电模块输出电压是否在规格范围内", "测量稳压器工作温度是否异常", "检查电容组有无鼓包或漏液", "验证电源线缆连接紧固程度"],
        "Thermal": ["检查散热风扇转速是否正常", "清洁散热片和风道", "测量关键位置温度分布", "检查导热硅脂是否需要更换"],
        "Subtle": ["全参数扫描对比设备基线", "检查传感器标定状态", "运行设备综合诊断测试", "检查接线端子和接插件"],
    }
    checklist = checklists.get(fault_group, checklists["Subtle"])

    # Natural summary
    summaries = {
        "High-Voltage": f"该设备电压参数出现显著偏离（z={z['z_Voltage']:.1f}），属于高压异常模式。SHAP分析显示电气风险贡献度最高，电压漂移是主要驱动因素。",
        "Thermal": f"该设备温度参数出现持续上升（z={z['z_Temperature']:.1f}），属于热控异常模式。SHAP分析显示热风险贡献度最高，温度积聚是主要驱动因素。",
        "Subtle": f"该设备多参数联合偏离基线（z_composite={zc:.1f}），异常模式较微弱但跨参数一致。SHAP分析显示综合风险，需深入诊断。",
    }

    return {
        "final_risk_score": risk_score,
        "risk_level": risk_level,
        "risk_category": category,
        "natural_summary": summaries.get(fault_group, summaries["Subtle"]),
        "key_anomaly_signals": signals,
        "top_contributors": contributors,
        "shap_risk_summary": f"{category}主导，综合风险评分{risk_score:.2f}",
        "inspection_checklist": checklist,
        "top_risk_factor_1": f"z_composite = {zc:.1f}（{risk_level}风险）",
        "top_risk_factor_2": f"{PATTERN_CN.get(_z_to_pattern(z), '异常')}模式激活",
    }


def _z_to_pattern(z: dict) -> str:
    """Map Z-Scores to fault pattern string."""
    zv, za, zt = abs(z.get("z_Voltage", 0)), abs(z.get("z_Amperage", 0)), abs(z.get("z_Temperature", 0))
    patterns = []
    if zv > 2.0: patterns.append("voltage_drift")
    if za > 2.0: patterns.append("power_anomaly")
    if zt > 2.0: patterns.append("thermal_buildup")
    if len(patterns) >= 2: return "combined_degradation"
    if len(patterns) == 1: return patterns[0]
    if z.get("alert_level", "Normal") in ("Alarm", "Warning"): return "combined_degradation"
    return "normal"


def _build_work_order(machine_id: str, z: dict, health_orig: dict, severity: str, fault_type: int) -> dict:
    """Build synthetic work order matching industrial_maintenance_plan.csv structure."""
    pattern = _z_to_pattern(z)
    hs_orig = health_orig.get("health_score", 65)
    hs_modified = max(15, hs_orig + SEVERITY_HEALTH_PENALTY[severity])
    cost_risk = health_orig.get("cost_at_risk", 3500)
    # Higher severity → higher cost risk
    cost_risk_modified = round(cost_risk * (1.0 + 0.3 * SEVERITY_Z[severity]["dominant"] / 2.8))

    # Action
    alert = z["alert_level"]
    zc = z["z_composite"]
    if alert == "Alarm" and zc > 3.0:
        action = "immediate_shutdown"
    elif alert == "Alarm":
        action = "preventive_repair"
    elif alert == "Warning":
        action = "schedule_inspection"
    else:
        action = "increase_monitoring"

    # Priority
    if hs_modified < 30 or zc > 3.0:
        priority = "P1"
    elif hs_modified < 50 or zc > 2.0:
        priority = "P2"
    else:
        priority = "P3"

    # Downtime window
    window_map = {"immediate_shutdown": "immediate", "preventive_repair": "night",
                  "schedule_inspection": "night", "increase_monitoring": "scheduled",
                  "routine_check": "scheduled"}
    window = window_map.get(action, "scheduled")

    # Technician (fallback mapping, work_order_builder's assigner is optional)
    tech_map = {
        ("voltage_drift", "Alarm"): ("electrical_specialist", 2),
        ("thermal_buildup", "Alarm"): ("thermal_specialist", 2),
        ("power_anomaly", "Alarm"): ("electrical_specialist", 2),
        ("combined_degradation", "Alarm"): ("senior_technician", 2),
        ("voltage_drift", "Warning"): ("electrical_specialist", 1),
        ("thermal_buildup", "Warning"): ("thermal_specialist", 1),
        ("power_anomaly", "Warning"): ("electrical_specialist", 1),
        ("combined_degradation", "Warning"): ("senior_technician", 1),
    }
    tech_type, tech_count = tech_map.get((pattern, alert), ("junior_technician", 1))

    # Spare parts
    parts_map = {
        "voltage_drift": ["power_supply_module", "voltage_regulator_ic", "capacitor_bank"],
        "thermal_buildup": ["cooling_fan_assembly", "thermal_paste", "temperature_sensor_pt100"],
        "power_anomaly": ["motor_driver_module", "current_sensor_hall", "power_cable_set"],
        "combined_degradation": ["rotor_assembly", "bearing_kit", "seal_kit"],
    }
    parts = parts_map.get(pattern, ["bearing_kit", "seal_kit"])

    # Urgency
    urgency = 90 if zc > 3.0 else 75 if zc > 2.0 else 55

    # SLA
    sla = "8" if priority == "P1" else "24" if priority == "P2" else "48"

    return {
        "machine_id": machine_id,
        "health_score": str(hs_modified),
        "health_score_original": str(hs_orig),
        "cost_at_risk": str(cost_risk_modified),
        "primary_pattern": pattern,
        "pattern_cn": PATTERN_CN.get(pattern, pattern),
        "recommended_action": action,
        "action_cn": ACTION_CN.get(action, action),
        "technician_type": tech_type,
        "technician_type_cn": TECH_CN.get(tech_type, tech_type),
        "technician_type_color": TECH_COLOR.get(tech_type, "#8e9aab"),
        "technician_count": str(tech_count),
        "maintenance_priority": priority,
        "recommended_downtime_window": window,
        "spare_parts": json.dumps(parts, ensure_ascii=False),
        "parts_list": parts,
        "acceptance_standard": (
            "[CD-01] Z-Score回归正常范围(z<1.5)|[CD-02] 24h无告警复现|"
            "[TH-01] 运行温度稳定在基线±2σ内"
        ),
        "reasoning": (
            f"故障注入演示（类型{int(fault_type)}，{GROUP_CN.get(z.get('failure_group',''),'')}）。"
            f"Z-Score: V={z['z_Voltage']:.1f} A={z['z_Amperage']:.1f} T={z['z_Temperature']:.1f}，"
            f"综合={zc:.1f}。健康分从{hs_orig:.0f}降至{hs_modified:.0f}。"
            f"判定为{PATTERN_CN.get(pattern, pattern)}，建议{ACTION_CN.get(action, action)}。"
        ),
        "maintenance_suggestion": (
            f"【故障注入演示工单】基于注入的{GROUP_CN.get(z.get('failure_group',''),'')}故障信号自动生成。"
            f"建议{ACTION_CN.get(action, action)}，预计{tech_count}名{TECH_CN.get(tech_type, tech_type)}执行，"
            f"所需备件：{'、'.join(parts)}。"
        ),
        "sla_target_hours": sla,
        "maintenance_strategy": "production_efficiency",
        "priority_num": "1" if priority == "P1" else "2" if priority == "P2" else "3",
        "alert_level": alert,
        "action_type": action,
        "urgency_score": str(urgency),
        "recommended_window_days": "1" if priority == "P1" else "3" if priority == "P2" else "5",
        "expected_savings": str(round(cost_risk_modified * 0.65)),
        "estimated_cost": str(round(cost_risk_modified * 0.35)),
        "estimated_duration_hours": "2" if action == "increase_monitoring" else "4" if action == "schedule_inspection" else "8",
        "production_impact": str(round(cost_risk_modified * 1.5)),
    }


def _build_steps(z: dict, shap: dict, wo: dict, fault_type: int, fault_group: str,
                  severity: str, machine_id: str, health_orig: dict) -> list:
    """Build the 6-step animation descriptors for the frontend."""
    sev_cn = {"mild": "轻微", "medium": "中等", "severe": "严重"}
    sig = _load_fault_sig().get(fault_type, {})
    v_delta = sig.get("v_delta_pct", 2.0)
    a_delta = sig.get("a_delta_pct", 2.0)
    t_delta = sig.get("t_delta_pct", 2.0)

    # Pre-compute colors for inline styles (avoid nested quotes in f-strings)
    red = "var(--accent-red)"
    amber = "var(--accent-amber)"
    green = "var(--accent-green)"
    cyan = "var(--accent-cyan)"
    muted = "var(--text-muted)"
    border = "var(--border)"

    # Build SHAP contributor lines
    contrib_lines = ""
    for c in shap["top_contributors"]:
        contrib_color = red if c["contribution"] > 0.1 else amber
        arrow = "↑" if c["contribution"] > 0 else "↓"
        contrib_lines += (
            "<span style='color:" + contrib_color + ";'>" + arrow + "</span> "
            + c["label"] + ": <b>" + str(c["contribution"]) + "</b><br>"
        )

    # Priority color
    pri_color = red if wo["maintenance_priority"] == "P1" else amber

    steps = [
        {"step": 1, "icon": "🔧",
         "title": "Step 1/6 — 故障信号注入",
         "desc": (
             "正在向 <b>" + machine_id + "</b> 注入 <b>"
             + GROUP_CN.get(fault_group, fault_group) + "</b> 故障信号"
             + "（类型" + str(fault_type) + "，严重度：" + sev_cn.get(severity, severity) + "）。<br>"
             + "传感器数据已偏移：电压 +" + str(round(v_delta, 1)) + "%，"
             + "电流 +" + str(round(a_delta, 1)) + "%，"
             + "温度 +" + str(round(t_delta, 1)) + "%。"
         ),
         "grid_class": "critical"},

        {"step": 2, "icon": "🚨",
         "title": "Step 2/6 — Z-Score 异常检测",
         "desc": (
             "<table style='margin-top:8px;font-size:12px;font-family:mono;width:100%;'>"
             + "<tr><td>z_Voltage</td><td style='color:" + red + ";'>" + str(z["z_Voltage"]) + "</td></tr>"
             + "<tr><td>z_Amperage</td><td style='color:" + amber + ";'>" + str(z["z_Amperage"]) + "</td></tr>"
             + "<tr><td>z_Temperature</td><td style='color:" + red + ";'>" + str(z["z_Temperature"]) + "</td></tr>"
             + "<tr style='border-top:1px solid " + border + ";'><td><b>综合 Z</b></td>"
             + "<td><b style='color:" + red + ";font-size:16px;'>" + str(z["z_composite"]) + "</b></td></tr>"
             + "<tr><td>告警等级</td><td><span class='badge' style='background:rgba(240,68,68,0.15);color:"
             + red + ";'>" + z["alert_level"] + "</span></td></tr></table>"
         ),
         "grid_class": "critical"},

        {"step": 3, "icon": "🔍",
         "title": "Step 3/6 — SHAP 根因分析",
         "desc": (
             "<b>" + shap["natural_summary"] + "</b><br><br>"
             + contrib_lines
             + "<br>风险等级: <b style='color:" + red + ";'>" + shap["risk_level"] + "</b>"
             + "（评分 " + str(shap["final_risk_score"]) + "）"
         ),
         "grid_class": "critical"},

        {"step": 4, "icon": "📋",
         "title": "Step 4/6 — 自动生成维护工单",
         "desc": (
             "优先级: <b style='color:" + pri_color + ";'>" + wo["maintenance_priority"] + "</b> | "
             + "动作: <b>" + wo["action_cn"] + "</b> | 模式: <b>" + wo["pattern_cn"] + "</b><br>"
             + "停机窗口: <b>" + wo["recommended_downtime_window"] + "</b> | SLA: <b>" + wo["sla_target_hours"] + "h</b><br>"
             + "备件: <b>" + "、".join(wo["parts_list"][:4]) + "</b><br>"
             + "预期节省: <b style='color:" + green + ";'>$" + str(int(wo["expected_savings"])) + "</b>"
         ),
         "grid_class": "has-wo alarm"},

        {"step": 5, "icon": "📧",
         "title": "Step 5/6 — 技师分配 & 邮件通知",
         "desc": (
             "已分配: <b style='color:" + wo["technician_type_color"] + ";'>" + wo["technician_type_cn"] + "</b> × " + wo["technician_count"] + "人<br>"
             + "工单号: <span style='font-family:mono;color:" + cyan + ";'>WO-" + machine_id + "-" + str(int(random.uniform(1000, 9999))) + "</span><br>"
             + "通知方式: <b>📧 邮件 + 系统站内信</b><br>"
             + "<span style='color:" + muted + ";font-size:11px;'>"
             + "（演示模式 — 未实际发送邮件，答辩时可配置SMTP真实发送）</span>"
         ),
         "grid_class": "has-wo alarm"},

        {"step": 6, "icon": "✅",
         "title": "Step 6/6 — 修复后验收通过",
         "desc": (
             "✅ Z-Score 已回归正常范围 (V&lt;1.5, A&lt;1.5, T&lt;1.5)<br>"
             + "✅ 24h 无告警复现<br>"
             + "✅ 设备健康分恢复至 <b style='color:" + green + ";'>" + str(int(health_orig.get("health_score", 65))) + "</b>（原始值）<br>"
             + "✅ 验收标准全部通过（[CD-01][CD-02][TH-01]）<br><br>"
             + "<b style='color:" + green + ";'>🎉 全流程演示完成</b>"
         ),
         "grid_class": "rollback"},
    ]
    return steps


# ── Route ────────────────────────────────────────────────────────────────

@router.post("/fault-injection")
async def fault_injection(req: FaultInjectionRequest):
    """
    Inject a synthetic fault for interactive demo.

    All computation is in-memory. No data files are modified.
    Returns complete injection data for frontend step animation.
    """
    try:
        # Load fault signature
        sig = _load_fault_sig().get(req.fault_type)
        if not sig:
            return {"success": False, "error": f"Unknown fault type: {req.fault_type}"}

        fault_group = sig["failure_group"]

        # Compute synthetic Z-Scores
        z = _compute_z_scores(fault_group, req.severity)

        # Read current health
        health_orig = _read_health(req.machine_id)
        hs_penalty = SEVERITY_HEALTH_PENALTY[req.severity]
        health_modified = {
            "health_score": max(15, health_orig["health_score"] + hs_penalty),
            "health_level": "Critical" if (health_orig["health_score"] + hs_penalty) < 40 else "Degrading",
            "cost_at_risk": round(health_orig["cost_at_risk"] * 1.5),
            "failure_rate": 0.18,
            "trend": "Critical",
            "maintenance_overdue_days": 3,
            "zscore_risk": z["z_composite"],
        }

        # Generate SHAP
        shap = _generate_shap(req.machine_id, z, fault_group, req.severity)

        # Build work order
        wo = _build_work_order(req.machine_id, z, health_orig, req.severity, req.fault_type)

        # Build step descriptors
        steps = _build_steps(z, shap, wo, req.fault_type, fault_group,
                            req.severity, req.machine_id, health_orig)

        # Assemble response
        return {
            "success": True,
            "machine_id": req.machine_id,
            "injection": {
                "fault_type": req.fault_type,
                "fault_group": fault_group,
                "fault_group_cn": GROUP_CN.get(fault_group, fault_group),
                "severity": req.severity,
                "severity_cn": {"mild": "轻微", "medium": "中等", "severe": "严重"}[req.severity],
                "synthetic_z": z,
                "alert_level": z["alert_level"],
                "modified_health": health_modified,
                "health_original": health_orig,
                "fault_pattern": wo["primary_pattern"],
                "action": wo["recommended_action"],
                "priority": wo["maintenance_priority"],
                "shap": shap,
                "work_order": wo,
                "steps": steps,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
