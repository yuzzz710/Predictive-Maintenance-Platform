"""
MCP Tool Adapter — OpenAI-compatible tool definitions + execution engine.

Architecture:
  - Tool DEFINITIONS are in OpenAI function-calling format (for DeepSeek)
  - Tool EXECUTION either reads precomputed CSV data or calls skill scripts
  - LLM never reads CSV directly — all data access goes through tools

Two tool types:
  1. READ-ONLY (instant): query_device_status, list_alarm_devices, explain_predictability_limit
  2. PIPELINE (long-running): prepare_data, run_stat_analysis, run_ml_analysis,
     run_diagnosis, generate_decision, run_pipeline
"""
import sys
import os
import json
import time
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .config import DATA_DIR, MCP_DIR, V3_OUTPUTS, DASHBOARD_DATA, OUTPUTS_DIR, PROJECT_ROOT

# ══════════════════════════════════════════════════════════════════════════
# Tool Definitions (OpenAI / DeepSeek function-calling format)
# ══════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_device_status",
            "description": "查询单台CNC设备的完整状态：告警等级、z-score异常参数、诊断模式、维护工单、成本风险、建议动作。输入设备ID如 CNC_036。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID，格式为 CNC_后跟3位数字，例如 CNC_036, CNC_001, CNC_042"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_alarm_devices",
            "description": "列出当前所有处于ALARM或WARNING状态的设备，按优先级排序。返回设备ID、告警等级、动作类型、紧急度分数、成本风险。用于快速了解哪些设备需要立即关注。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fault_history",
            "description": "查询指定CNC设备的故障历史记录。返回最近N次故障的时间、故障类型、故障分组(Normal/Subtle/Thermal/High-Voltage)、严重程度、传感器读数。用于分析设备历史故障模式、回答'某设备最近有哪些故障'、'某设备故障趋势'等问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID，格式为 CNC_后跟3位数字，例如 CNC_001, CNC_042"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回最近N条故障记录，默认10，最大30"
                    },
                    "include_normal": {
                        "type": "boolean",
                        "description": "是否包含正常(Type 0)运行记录，默认false仅返回故障记录"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sensor_trend",
            "description": "查询指定设备的传感器时间序列趋势。返回最近N小时的温度/电压/电流/转速数据、移动平均、异常点标记、告警阈值。自动生成ECharts-ready图表数据。当用户问'温度波动'、'电压趋势'、'传感器变化'等问题时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID，例如 CNC_036, CNC_001"
                    },
                    "sensor": {
                        "type": "string",
                        "enum": ["temperature", "voltage", "amperage", "rotor_speed"],
                        "description": "传感器类型：temperature(温度), voltage(电压), amperage(电流), rotor_speed(转速)"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "查询最近多少小时的数据，默认24。实际返回可用数据范围（约7小时，30条记录）。"
                    }
                },
                "required": ["machine_id", "sensor"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_machines",
            "description": "对比两台CNC设备的运行状态。比较温度漂移、故障频率、电压异常、维护成本、告警次数、z-score偏差。返回ECharts多线对比图数据。当用户问'比较A和B'、'哪台更稳定'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_a": {
                        "type": "string",
                        "description": "第一台设备ID，例如 CNC_001"
                    },
                    "machine_b": {
                        "type": "string",
                        "description": "第二台设备ID，例如 CNC_036"
                    }
                },
                "required": ["machine_a", "machine_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_root_cause_analysis",
            "description": "对指定设备进行根因分析。综合诊断报告(diagnosis.csv)、z-score异常、故障历史、告警模式，识别可能故障原因、级联故障链、传感器关联异常。当用户问'为什么A设备异常'、'根本原因是什么'、'为什么会thermal buildup'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID，例如 CNC_036"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_order_history",
            "description": "查询指定设备的维护工单历史。返回维修记录、动作类型、维护成本、紧急度、停机时间、维修窗口。当用户问'维修记录'、'工单历史'、'维修最频繁'等问题时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID，例如 CNC_001"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回最近N条工单，默认10"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_predictability_limit",
            "description": "解释当前4参数传感器系统的可预测性限制。返回5维度证据：单参数区分力(Youden's J)、参数耦合稳定性、故障非渐进性、模型收敛分析、传感器缺口。包含根因诊断和传感器升级建议。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_maintenance_report",
            "description": "AI驱动生成工业预测性维护报告（PDF）。支持4种报告类型：weekly（周度系统报告）、device（单设备健康报告，需machine_id）、risk（高风险设备报告）、thermal（热漂移专项分析）。系统自动调用多个MCP工具（list_alarm_devices、query_device_status、get_sensor_trend、get_fault_history、get_root_cause_analysis），聚合分析结果，生成图表，输出工业级PDF报告。当用户说'生成本周维护报告'、'生成XX报告'、'维护周报'、'设备健康报告'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["weekly", "device", "risk", "thermal"],
                        "description": "报告类型：weekly(周度系统综合报告), device(单设备深度健康报告), risk(高风险设备专项报告), thermal(热漂移分析报告)"
                    },
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID（report_type=device时必填），例如 CNC_036"
                    }
                },
                "required": ["report_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_pipeline",
            "description": "一键运行完整的预测性维护分析流水线：数据准备→统计推理→诊断→决策工单。耗时约30-60秒。当用户要求'完整分析'、'重新生成工单'、'跑一遍分析'时使用。返回生成的工作订单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": f"原始数据目录路径，默认：{PROJECT_ROOT / '原始数据集'}"
                    },
                    "skip_ml": {
                        "type": "boolean",
                        "description": "是否跳过ML推理步骤（XGBoost/深度学习），默认false"
                    },
                    "max_orders": {
                        "type": "integer",
                        "description": "最大工单数量，默认20"
                    }
                },
                "required": []
            }
        }
    },
]


# ══════════════════════════════════════════════════════════════════════════
# Read-only Tool Implementations (instant, no subprocess)
# ══════════════════════════════════════════════════════════════════════════

def _query_device_status(machine_id: str) -> dict:
    """Query comprehensive status for a single machine from precomputed data."""
    result = {
        "machine_id": machine_id,
        "found": False,
        "work_order": None,
        "diagnosis": None,
        "z_scores": None,
        "summary": None,
    }

    # 1. Work order (from decision engine output)
    wo_path = DASHBOARD_DATA / "work_orders.csv"
    if wo_path.exists():
        wo = pd.read_csv(wo_path)
        match = wo[wo["machine_id"] == machine_id]
        if len(match) > 0:
            row = match.iloc[0]
            result["found"] = True
            result["work_order"] = {
                "priority": int(row["priority"]),
                "alert_level": str(row["alert_level"]),
                "action_type": str(row["action_type"]),
                "cost_at_risk": float(row["cost_at_risk"]),
                "urgency_score": float(row["urgency_score"]),
                "window_days": int(row["window_days"]),
                "expected_savings": float(row["expected_savings"]),
                "suggestion": str(row["suggestion"])[:500],
            }

    # 2. Diagnosis
    diag_path = DASHBOARD_DATA / "diagnosis.csv"
    if diag_path.exists():
        diag = pd.read_csv(diag_path)
        match = diag[diag["machine_id"] == machine_id]
        if len(match) > 0:
            result["found"] = True
            row = match.iloc[0]
            result["diagnosis"] = {
                "primary_pattern": str(row["primary_pattern"]),
                "patterns_detected": str(row["patterns_detected"]),
                "diagnosis_confidence": float(row["diagnosis_confidence"]),
                "evidence_voltage_drift": float(row["evidence_voltage_drift"]),
                "evidence_thermal_buildup": float(row["evidence_thermal_buildup"]),
                "evidence_power_anomaly": float(row["evidence_power_anomaly"]),
                "evidence_combined_degradation": float(row["evidence_combined_degradation"]),
            }

    # 3. Latest z-scores (most recent record for this machine)
    zs_path = DASHBOARD_DATA / "z_scores.csv"
    if zs_path.exists():
        zs = pd.read_csv(zs_path)
        match = zs[zs["Equipment.Id"] == machine_id]
        if len(match) > 0:
            result["found"] = True
            latest = match.iloc[-1]
            result["z_scores"] = {
                "z_Voltage": float(latest["z_Voltage"]),
                "z_Amperage": float(latest["z_Amperage"]),
                "z_Temperature": float(latest["z_Temperature"]),
                "z_composite": float(latest["z_composite"]),
                "alert_level": str(latest["alert_level"]),
                "date": str(latest["Date"]),
                "fault_type": str(latest.get("Failure.Equipment.Type", "")),
            }
            # Add alert history summary
            alert_counts = match["alert_level"].value_counts().to_dict()
            result["z_scores"]["alert_history"] = alert_counts

    # 4. Cost risk
    cost_path = DASHBOARD_DATA / "cost_risk.csv"
    if cost_path.exists():
        cost = pd.read_csv(cost_path)
        match = cost[cost["Equipment.Id"] == machine_id] if "Equipment.Id" in cost.columns else cost[cost["Equipment ID"] == machine_id] if "Equipment ID" in cost.columns else None
        if match is not None and len(match) > 0:
            result["found"] = True
            row = match.iloc[0]
            result["cost_risk"] = {
                "risk_tier": str(row.get("risk_tier", "")),
                "failure_rate": str(row.get("failure_rate", "")),
                "cost_at_risk": float(row.get("cost_at_risk", 0)) if "cost_at_risk" in row else None,
            }

    # 5. Summary info
    summary_path = DASHBOARD_DATA / "summary.csv"
    if summary_path.exists():
        sm = pd.read_csv(summary_path)
        match = sm[sm["Equipment.Id"] == machine_id] if "Equipment.Id" in sm.columns else None
        if match is not None and len(match) > 0:
            result["found"] = True
            row = match.iloc[0]
            result["summary"] = {
                "equipment_type": str(row.get("Equipment.Type", "")),
                "units_per_day": float(row.get("Units Produced Per day", 0)),
                "unit_cost": float(row.get("Unit Cost of Production", 0)),
            }

    # 6. Build human-readable text summary
    wo = result.get("work_order")
    diag = result.get("diagnosis")
    zs = result.get("z_scores")
    cost = result.get("cost_risk")
    sm = result.get("summary")

    parts = [f"设备 {machine_id} 当前状态："]

    if wo:
        parts.append(f"- 维护优先级：#{wo['priority']}")
        parts.append(f"- 告警等级：{wo['alert_level']}")
        parts.append(f"- 建议动作：{wo['action_type']}")
        parts.append(f"- 紧急度分数：{wo['urgency_score']}/100")
        parts.append(f"- 成本风险：${wo['cost_at_risk']:,.2f}")
        parts.append(f"- 维护窗口：{wo['window_days']} 天")
        parts.append(f"- 预计节约：${wo['expected_savings']:,.2f}")
        parts.append(f"- 维护建议：{wo['suggestion'][:300]}...")
    elif zs:
        parts.append(f"- Z-Score告警等级：{zs['alert_level']}")
        parts.append(f"- 记录日期：{zs['date']}")
        alert_hist = zs.get("alert_history", {})
        if alert_hist:
            hist_parts = [f"{k}: {v}次" for k, v in alert_hist.items()]
            parts.append(f"- 历史告警分布：{', '.join(hist_parts)}")

    if zs:
        parts.append(f"- 当前Z-Score：Voltage={zs['z_Voltage']:.2f}, Amperage={zs['z_Amperage']:.2f}, Temperature={zs['z_Temperature']:.2f}")
        parts.append(f"- 综合Z-Score：{zs['z_composite']:.2f}")

    if diag:
        parts.append(f"- 主要异常模式：{diag['primary_pattern']}")
        if diag['patterns_detected'] and diag['patterns_detected'] != 'none':
            patterns = diag['patterns_detected'].replace('|', ', ')
            parts.append(f"- 检测到的模式：{patterns}")
        parts.append(f"- 诊断置信度：{diag['diagnosis_confidence']:.0%}")

    if cost:
        parts.append(f"- 风险等级：{cost.get('risk_tier', 'N/A')}")
        if cost.get('cost_at_risk') is not None:
            parts.append(f"- 成本风险：${cost['cost_at_risk']:,.2f}")

    if sm:
        parts.append(f"- 日产量：{sm['units_per_day']} 件")
        parts.append(f"- 单位成本：${sm['unit_cost']}")

    if not result["found"]:
        parts.append("（该设备数据未在现有分析输出中找到）")

    result["text_summary"] = "\n".join(parts)

    return result


def _list_alarm_devices() -> dict:
    """List all devices with ALARM or WARNING status."""
    wo_path = DASHBOARD_DATA / "work_orders.csv"
    if not wo_path.exists():
        return {"error": "work_orders.csv 未找到，请先运行流水线生成工单。"}

    wo = pd.read_csv(wo_path)
    alarms = wo[wo["alert_level"].isin(["ALARM", "WARNING"])].sort_values("priority")

    # Load diagnosis data for pattern enrichment
    diag_map = {}
    diag_path = DASHBOARD_DATA / "diagnosis.csv"
    if diag_path.exists():
        diag = pd.read_csv(diag_path)
        for _, row in diag.iterrows():
            diag_map[str(row["machine_id"])] = {
                "primary_pattern": str(row["primary_pattern"]),
                "patterns_detected": str(row["patterns_detected"]),
                "diagnosis_confidence": float(row["diagnosis_confidence"]),
            }

    devices = []
    thermal_drift_devices = []
    immediate_shutdown_devices = []

    for _, row in alarms.iterrows():
        mid = str(row["machine_id"])
        d = diag_map.get(mid, {})
        device = {
            "machine_id": mid,
            "priority": int(row["priority"]),
            "alert_level": str(row["alert_level"]),
            "action_type": str(row["action_type"]),
            "urgency_score": float(row["urgency_score"]),
            "cost_at_risk": float(row["cost_at_risk"]),
            "window_days": int(row["window_days"]),
            "suggestion_short": str(row["suggestion"])[:150] + "...",
            "primary_pattern": d.get("primary_pattern", "unknown"),
            "patterns_detected": d.get("patterns_detected", ""),
            "diagnosis_confidence": d.get("diagnosis_confidence", 0),
        }
        devices.append(device)

        if "thermal" in d.get("primary_pattern", "").lower():
            thermal_drift_devices.append(device)
        if row["action_type"] == "immediate_shutdown":
            immediate_shutdown_devices.append(device)

    alarm_count = sum(1 for d in devices if d["alert_level"] == "ALARM")
    warning_count = sum(1 for d in devices if d["alert_level"] == "WARNING")

    top5 = devices[:5]

    return {
        "total_alarm_devices": len(devices),
        "alarm_count": alarm_count,
        "warning_count": warning_count,
        "thermal_drift_count": len(thermal_drift_devices),
        "thermal_drift_devices": [d["machine_id"] for d in thermal_drift_devices],
        "immediate_shutdown_count": len(immediate_shutdown_devices),
        "immediate_shutdown_devices": [d["machine_id"] for d in immediate_shutdown_devices],
        "top_5_urgent": top5,
        "all_devices": devices,
        "summary_text": (
            f"当前共有 {len(devices)} 台设备需要关注：{alarm_count} 台 ALARM（需立即处理），"
            f"{warning_count} 台 WARNING（需安排检查）。\n"
            f"其中 {len(thermal_drift_devices)} 台存在热漂移(thermal drift)问题，"
            f"{len(immediate_shutdown_devices)} 台需要立即停机。\n\n"
            f"最紧急的5台设备：\n" +
            "\n".join(
                f"  #{d['priority']} {d['machine_id']} — {d['action_type']} "
                f"(紧急度: {d['urgency_score']:.0f}, 成本风险: ${d['cost_at_risk']:,.0f}, "
                f"异常模式: {d['primary_pattern']})"
                for d in top5
            )
        )
    }


# Fault type → group mapping (from failure_signatures analysis)
FAULT_TYPE_MAP = {
    0:  {"group": "Normal",        "label": "正常运行", "severity": "none"},
    1:  {"group": "Subtle",        "label": "微弱异常 (Type 1)", "severity": "low"},
    2:  {"group": "Subtle",        "label": "微弱异常 (Type 2)", "severity": "low"},
    3:  {"group": "Thermal",       "label": "热异常 (Type 3)", "severity": "medium"},
    4:  {"group": "High-Voltage",  "label": "高电压异常 (Type 4)", "severity": "high"},
    5:  {"group": "High-Voltage",  "label": "高电压异常 (Type 5)", "severity": "high"},
    6:  {"group": "Thermal",       "label": "热异常 (Type 6)", "severity": "medium"},
    7:  {"group": "Thermal",       "label": "热异常 (Type 7)", "severity": "medium"},
    8:  {"group": "Thermal",       "label": "热异常 (Type 8)", "severity": "medium"},
    9:  {"group": "Thermal",       "label": "热异常 (Type 9)", "severity": "medium"},
}


def _get_fault_history(machine_id: str, limit: int = 10, include_normal: bool = False) -> dict:
    """Query fault history for a machine from log.csv."""
    log_path = DASHBOARD_DATA / "log.csv"
    if not log_path.exists():
        return {"error": f"日志数据文件未找到: {log_path}"}

    log = pd.read_csv(log_path)
    match = log[log["Equipment.Id"] == machine_id]

    if len(match) == 0:
        return {
            "machine_id": machine_id,
            "found": False,
            "total_records": 0,
            "text_summary": f"未找到设备 {machine_id} 的运行日志记录。",
        }

    total_records = len(match)
    all_faults = match[match["Failure.Equipment.Type"] != 0]
    total_faults = len(all_faults)

    # Select records: faults only or all (newest last in CSV, so tail gives most recent)
    records = match if include_normal else all_faults
    if len(records) == 0:
        return {
            "machine_id": machine_id,
            "found": True,
            "total_records": total_records,
            "total_faults": 0,
            "faults": [],
            "text_summary": f"设备 {machine_id} 在 {total_records} 条记录中无故障记录，全部为正常运行(Type 0)。",
        }

    recent = records.tail(min(limit, len(records)))

    faults = []
    for _, row in recent[::-1].iterrows():  # reverse to show newest first
        ft = int(row["Failure.Equipment.Type"])
        info = FAULT_TYPE_MAP.get(ft, {"group": "Unknown", "label": f"未知类型 ({ft})", "severity": "unknown"})
        faults.append({
            "date": str(row["Date"]),
            "fault_type": ft,
            "fault_group": info["group"],
            "fault_label": info["label"],
            "severity": info["severity"],
            "voltage": float(row["Op.Voltage"]),
            "amperage": float(row["Op.Amperage"]),
            "temperature": float(row["Op.Temperature"]),
            "rotor_speed": float(row["Rotor Speed"]),
        })

    # Fault type distribution for this machine
    type_dist = {}
    for ft_val, count in match["Failure.Equipment.Type"].value_counts().sort_index().items():
        ft = int(ft_val)
        info = FAULT_TYPE_MAP.get(ft, {"group": "Unknown", "label": f"Type {ft}"})
        type_dist[str(ft)] = {
            "count": int(count),
            "group": info["group"],
            "label": info["label"],
        }

    # Build text summary
    parts = [f"设备 {machine_id} 故障历史（共 {total_records} 条记录，{total_faults} 次故障）：\n"]
    parts.append(f"最近 {len(faults)} 次故障记录：")
    for i, f in enumerate(faults, 1):
        parts.append(
            f"  {i}. [{f['date']}] {f['fault_label']} | "
            f"分组: {f['fault_group']} | 严重度: {f['severity']} | "
            f"V={f['voltage']:.1f} A={f['amperage']:.1f} T={f['temperature']:.1f}°C"
        )
    parts.append(f"\n故障类型分布：")
    for ft, info in sorted(type_dist.items(), key=lambda x: int(x[0])):
        if info["count"] > 0:
            parts.append(f"  Type {ft} ({info['label']}, {info['group']}): {info['count']} 次")

    return {
        "machine_id": machine_id,
        "found": True,
        "total_records": total_records,
        "total_faults": total_faults,
        "fault_rate_pct": round(total_faults / total_records * 100, 1),
        "recent_faults": faults,
        "fault_type_distribution": type_dist,
        "text_summary": "\n".join(parts),
    }


# ══════════════════════════════════════════════════════════════════════════
# Tool: get_sensor_trend — time-series with ECharts chart_data
# ══════════════════════════════════════════════════════════════════════════

SENSOR_COLUMN_MAP = {
    "temperature": "Op.Temperature",
    "voltage": "Op.Voltage",
    "amperage": "Op.Amperage",
    "rotor_speed": "Rotor Speed",
}
SENSOR_UNIT_MAP = {
    "temperature": "°C",
    "voltage": "V",
    "amperage": "A",
    "rotor_speed": "RPM",
}
SENSOR_LABEL_MAP = {
    "temperature": "温度",
    "voltage": "电压",
    "amperage": "电流",
    "rotor_speed": "转速",
}


def _get_sensor_trend(machine_id: str, sensor: str, hours: int = 24) -> dict:
    """Get sensor time-series trend with ECharts-ready chart_data."""
    col = SENSOR_COLUMN_MAP.get(sensor)
    if not col:
        return {"error": f"Unknown sensor: {sensor}. Use: temperature, voltage, amperage, rotor_speed"}

    log_path = DASHBOARD_DATA / "log.csv"
    if not log_path.exists():
        return {"error": "log.csv not found"}

    log = pd.read_csv(log_path)
    match = log[log["Equipment.Id"] == machine_id]
    if len(match) == 0:
        return {"machine_id": machine_id, "found": False, "error": f"Device {machine_id} not found"}

    records_per_hour = 60 / 14  # ~4.3 records per hour
    max_records = int(hours * records_per_hour)
    data = match.tail(min(max_records, len(match))).copy()

    values = data[col].values
    n = len(values)

    # Metrics
    v_min, v_max = float(np.min(values)), float(np.max(values))
    v_mean, v_std = float(np.mean(values)), float(np.std(values))

    # Rolling average (window=5, edge-padded)
    window = min(5, n)
    rolling = np.convolve(values, np.ones(window)/window, mode='same')
    # Fix edges with shorter windows
    for i in range(window//2):
        rolling[i] = np.mean(values[:i+window//2+1])
        rolling[-(i+1)] = np.mean(values[-(i+window//2+1):])

    # Anomaly detection: points beyond mean ± 2*std
    anomalies = []
    for i, v in enumerate(values):
        if abs(v - v_mean) > 2 * v_std:
            anomalies.append({
                "index": i,
                "date": str(data.iloc[i]["Date"]),
                "value": float(v),
                "deviation": float((v - v_mean) / v_std),
            })

    # Thresholds
    warning_upper = v_mean + 2 * v_std
    warning_lower = v_mean - 2 * v_std
    alarm_upper = v_mean + 3 * v_std
    alarm_lower = v_mean - 3 * v_std

    # Trend direction
    if n >= 4:
        slope = float(np.polyfit(range(n), values, 1)[0])
        if slope > v_std * 0.3:
            trend = "rising"
        elif slope < -v_std * 0.3:
            trend = "falling"
        else:
            trend = "stable"
    else:
        slope = 0.0
        trend = "insufficient_data"

    # Risk level
    anomaly_count = len(anomalies)
    if anomaly_count >= n * 0.3 or v_std > v_mean * 0.15:
        risk = "high"
    elif anomaly_count >= n * 0.1:
        risk = "medium"
    else:
        risk = "low"

    # Chart data (ECharts-ready) — unified schema
    anomaly_list = [
        {"name": "异常", "coord": [a["date"], a["value"]], "value": f"{a['deviation']:.1f}σ", "date": a["date"], "value_raw": a["value"], "deviation": a["deviation"]}
        for a in anomalies
    ]
    chart_data = {
        "chart_type": "line",
        "title": f"{machine_id} {SENSOR_LABEL_MAP[sensor]}趋势",
        "x_axis": data["Date"].tolist(),
        "xAxis": data["Date"].tolist(),
        "series": [
            {
                "name": SENSOR_LABEL_MAP[sensor],
                "type": "line",
                "data": values.tolist(),
                "smooth": True,
                "lineStyle": {"color": "#00c9a0", "width": 2},
                "itemStyle": {"color": "#00c9a0"},
            },
            {
                "name": "移动平均",
                "type": "line",
                "data": rolling.tolist(),
                "smooth": True,
                "lineStyle": {"color": "#f0a030", "width": 2, "type": "dashed"},
                "itemStyle": {"color": "#f0a030"},
            },
        ],
        "markPoints": [
            {"name": "异常", "coord": [a["date"], a["value"]], "value": f"{a['deviation']:.1f}σ"}
            for a in anomalies
        ] if anomalies else [],
        "anomalies": anomaly_list,
        "thresholds": {
            "warning_upper": float(warning_upper),
            "warning_lower": float(warning_lower),
            "alarm_upper": float(alarm_upper),
            "alarm_lower": float(alarm_lower),
        },
        "tooltip": f"{SENSOR_LABEL_MAP[sensor]} ({SENSOR_UNIT_MAP[sensor]})",
    }

    # Summary text
    anomaly_pct = round(anomaly_count / n * 100, 1) if n > 0 else 0
    summary = (
        f"设备 {machine_id} 最近 {n} 条 {SENSOR_LABEL_MAP[sensor]} 记录：\n"
        f"- 范围：{v_min:.1f} ~ {v_max:.1f} {SENSOR_UNIT_MAP[sensor]}\n"
        f"- 均值：{v_mean:.1f}，标准差：{v_std:.1f}\n"
        f"- 趋势：{trend}（斜率 {slope:+.2f}/记录）\n"
        f"- 异常点：{anomaly_count} 个（{anomaly_pct}%）\n"
        f"- 风险等级：{risk}\n"
        f"- 告警上限(3σ)：{alarm_upper:.1f}，预警上限(2σ)：{warning_upper:.1f}"
    )

    return {
        "machine_id": machine_id,
        "sensor": sensor,
        "sensor_label": SENSOR_LABEL_MAP[sensor],
        "records_count": n,
        "metrics": {"min": v_min, "max": v_max, "mean": v_mean, "std": v_std, "slope": slope},
        "trend_direction": trend,
        "risk_level": risk,
        "anomaly_count": anomaly_count,
        "anomaly_pct": anomaly_pct,
        "chart_data": chart_data,
        "text_summary": summary,
    }


# ══════════════════════════════════════════════════════════════════════════
# Tool: compare_machines — side-by-side comparison with chart
# ══════════════════════════════════════════════════════════════════════════

def _compare_machines(machine_a: str, machine_b: str) -> dict:
    """Compare two machines across all dimensions."""
    log_path = DASHBOARD_DATA / "log.csv"
    zs_path = DASHBOARD_DATA / "z_scores.csv"
    wo_path = DASHBOARD_DATA / "work_orders.csv"
    cost_path = DASHBOARD_DATA / "cost_risk.csv"
    diag_path = DASHBOARD_DATA / "diagnosis.csv"

    def _stats(log_df, col):
        v = log_df[col].values
        return {"min": float(np.min(v)), "max": float(np.max(v)), "mean": float(np.mean(v)), "std": float(np.std(v))}

    result = {"machine_a": machine_a, "machine_b": machine_b, "found": {}}

    # Load data
    log = pd.read_csv(log_path) if log_path.exists() else None
    zs = pd.read_csv(zs_path) if zs_path.exists() else None
    wo = pd.read_csv(wo_path) if wo_path.exists() else None
    cost = pd.read_csv(cost_path) if cost_path.exists() else None
    diag = pd.read_csv(diag_path) if diag_path.exists() else None

    comparison = {}
    for label, mid in [("a", machine_a), ("b", machine_b)]:
        entry = {}
        if log is not None:
            mlog = log[log["Equipment.Id"] == mid]
            if len(mlog) > 0:
                result["found"][mid] = True
                entry["total_records"] = len(mlog)
                faults = mlog[mlog["Failure.Equipment.Type"] != 0]
                entry["fault_count"] = len(faults)
                entry["fault_rate"] = round(len(faults) / len(mlog) * 100, 1)
                entry["temp"] = _stats(mlog, "Op.Temperature")
                entry["voltage"] = _stats(mlog, "Op.Voltage")
                entry["amperage"] = _stats(mlog, "Op.Amperage")
                entry["rpm"] = _stats(mlog, "Rotor Speed")
            else:
                result["found"][mid] = False
                entry = {"found": False}

        if zs is not None:
            mzs = zs[zs["Equipment.Id"] == mid]
            if len(mzs) > 0:
                entry["z_composite_max"] = float(mzs["z_composite"].max())
                entry["z_composite_mean"] = float(mzs["z_composite"].mean())
                entry["alert_dist"] = mzs["alert_level"].value_counts().to_dict()

        if wo is not None and "machine_id" in wo.columns:
            mwo = wo[wo["machine_id"] == mid]
            if len(mwo) > 0:
                entry["work_order"] = {
                    "priority": int(mwo.iloc[0]["priority"]),
                    "action_type": str(mwo.iloc[0]["action_type"]),
                    "cost_at_risk": float(mwo.iloc[0]["cost_at_risk"]),
                    "urgency_score": float(mwo.iloc[0]["urgency_score"]),
                }

        if cost is not None and "Equipment.Id" in cost.columns:
            mc = cost[cost["Equipment.Id"] == mid]
            if len(mc) > 0:
                entry["risk_tier"] = str(mc.iloc[0]["risk_tier"])

        if diag is not None:
            md = diag[diag["machine_id"] == mid]
            if len(md) > 0:
                entry["primary_pattern"] = str(md.iloc[0]["primary_pattern"])
                entry["diagnosis_confidence"] = float(md.iloc[0]["diagnosis_confidence"])

        comparison[label] = entry

    # Determine winner
    a = comparison.get("a", {})
    b = comparison.get("b", {})
    winner = "tie"
    if a.get("fault_rate", 0) < b.get("fault_rate", 0) and a.get("z_composite_max", 0) < b.get("z_composite_max", 0):
        winner = machine_a
    elif b.get("fault_rate", 0) < a.get("fault_rate", 0) and b.get("z_composite_max", 0) < a.get("z_composite_max", 0):
        winner = machine_b

    # Chart data: temperature comparison (multi-line)
    chart_data = None
    if log is not None:
        la = log[log["Equipment.Id"] == machine_a]
        lb = log[log["Equipment.Id"] == machine_b]
        if len(la) > 0 and len(lb) > 0:
            # Align on index
            n = min(len(la), len(lb))
            la_t = la["Op.Temperature"].tail(n)
            lb_t = lb["Op.Temperature"].tail(n)
            chart_data = {
                "chart_type": "multi_line",
                "title": f"{machine_a} vs {machine_b} 温度对比",
                "x_axis": la["Date"].tail(n).tolist() if "Date" in la.columns else list(range(n)),
                "xAxis": la["Date"].tail(n).tolist() if "Date" in la.columns else list(range(n)),
                "series": [
                    {"name": f"{machine_a} 温度", "type": "line", "data": la_t.tolist(), "smooth": True,
                     "lineStyle": {"color": "#00c9a0"}, "itemStyle": {"color": "#00c9a0"}},
                    {"name": f"{machine_b} 温度", "type": "line", "data": lb_t.tolist(), "smooth": True,
                     "lineStyle": {"color": "#4d94ff"}, "itemStyle": {"color": "#4d94ff"}},
                ],
                "tooltip": "Temperature (°C)",
            }

    # Summary
    summary = (
        f"设备对比：{machine_a} vs {machine_b}\n"
        f"故障率：{a.get('fault_rate', 'N/A')}% vs {b.get('fault_rate', 'N/A')}%\n"
        f"最大z-score：{a.get('z_composite_max', 'N/A')} vs {b.get('z_composite_max', 'N/A')}\n"
        f"诊断模式：{a.get('primary_pattern', 'N/A')} vs {b.get('primary_pattern', 'N/A')}\n"
        f"风险等级：{a.get('risk_tier', 'N/A')} vs {b.get('risk_tier', 'N/A')}\n"
        f"更稳定设备：{winner}"
    )

    result["comparison"] = comparison
    result["winner"] = winner
    result["chart_data"] = chart_data
    result["text_summary"] = summary
    return result


# ══════════════════════════════════════════════════════════════════════════
# Tool: get_root_cause_analysis — multi-source root cause diagnosis
# ══════════════════════════════════════════════════════════════════════════

def _get_root_cause_analysis(machine_id: str) -> dict:
    """Multi-source root cause analysis combining diagnosis, z-scores, fault history."""
    result = {"machine_id": machine_id, "found": False}

    # 1. Diagnosis data
    diag_path = DASHBOARD_DATA / "diagnosis.csv"
    diag_info = None
    if diag_path.exists():
        diag = pd.read_csv(diag_path)
        match = diag[diag["machine_id"] == machine_id]
        if len(match) > 0:
            result["found"] = True
            row = match.iloc[0]
            diag_info = {
                "primary_pattern": str(row["primary_pattern"]),
                "patterns_detected": str(row["patterns_detected"]),
                "confidence": float(row["diagnosis_confidence"]),
                "voltage_drift": float(row["evidence_voltage_drift"]),
                "thermal_buildup": float(row["evidence_thermal_buildup"]),
                "power_anomaly": float(row["evidence_power_anomaly"]),
                "combined_degradation": float(row["evidence_combined_degradation"]),
            }

    # 2. Z-scores
    zs_path = DASHBOARD_DATA / "z_scores.csv"
    zs_info = None
    if zs_path.exists():
        zs = pd.read_csv(zs_path)
        match = zs[zs["Equipment.Id"] == machine_id]
        if len(match) > 0:
            result["found"] = True
            latest = match.iloc[-1]
            zs_info = {
                "z_voltage": float(latest["z_Voltage"]),
                "z_amperage": float(latest["z_Amperage"]),
                "z_temperature": float(latest["z_Temperature"]),
                "z_composite": float(latest["z_composite"]),
                "alert_level": str(latest["alert_level"]),
                "alert_history": match["alert_level"].value_counts().to_dict(),
            }

    # 3. Fault history
    log_path = DASHBOARD_DATA / "log.csv"
    fault_info = None
    if log_path.exists():
        log = pd.read_csv(log_path)
        match = log[log["Equipment.Id"] == machine_id]
        if len(match) > 0:
            faults = match[match["Failure.Equipment.Type"] != 0]
            type_dist = faults["Failure.Equipment.Type"].value_counts().sort_index().to_dict()
            fault_info = {
                "total_records": len(match),
                "total_faults": len(faults),
                "fault_rate": round(len(faults) / len(match) * 100, 1),
                "type_distribution": {int(k): int(v) for k, v in type_dist.items()},
                "dominant_fault_type": int(faults["Failure.Equipment.Type"].mode().iloc[0]) if len(faults) > 0 else None,
            }

    # Build root cause hypotheses
    causes = []
    confidence = 0.0

    if diag_info and diag_info["primary_pattern"] != "normal":
        evidence = []

        if diag_info["thermal_buildup"] > 0.5:
            causes.append({
                "cause": "热积聚 (Thermal Buildup)",
                "confidence": diag_info["thermal_buildup"],
                "evidence": [
                    f"热积聚证据强度: {diag_info['thermal_buildup']:.0%}",
                    "可能原因：冷却系统效率下降、散热通道堵塞、环境温度失控",
                    "建议检查：冷却液循环、散热风扇、热交换器",
                ],
            })

        if diag_info["power_anomaly"] > 0.5:
            causes.append({
                "cause": "电力异常 (Power Anomaly)",
                "confidence": diag_info["power_anomaly"],
                "evidence": [
                    f"电力异常证据强度: {diag_info['power_anomaly']:.0%}",
                    "可能原因：电源模块老化、电压调节器故障、线路接触不良",
                    "建议检查：电源供应模块、电气连接、电压调节器",
                ],
            })

        if diag_info["voltage_drift"] > 0.3:
            causes.append({
                "cause": "电压漂移 (Voltage Drift)",
                "confidence": diag_info["voltage_drift"],
                "evidence": [
                    f"电压漂移证据: {diag_info['voltage_drift']:.0%}",
                    "可能原因：电源不稳定、电机负载波动、逆变器异常",
                ],
            })

        if diag_info["combined_degradation"] > 0.5:
            causes.append({
                "cause": "综合退化 (Combined Degradation)",
                "confidence": diag_info["combined_degradation"],
                "evidence": [
                    f"综合退化证据: {diag_info['combined_degradation']:.0%}",
                    "⚠️ 多个子系统同时出现退化信号，需要全面检查",
                ],
            })

        confidence = diag_info["confidence"]

    elif zs_info and abs(zs_info["z_composite"]) > 1.5:
        # No clear diagnosis pattern, but z-score is elevated
        causes.append({
            "cause": "未分类异常 (Unclassified Anomaly)",
            "confidence": min(abs(zs_info["z_composite"]) / 5.0, 0.8),
            "evidence": [
                f"综合z-score: {zs_info['z_composite']:.2f}（超过正常范围）",
                f"电压z: {zs_info['z_voltage']:.1f}, 电流z: {zs_info['z_amperage']:.1f}, 温度z: {zs_info['z_temperature']:.1f}",
                "诊断系统未能匹配到已知故障模式，建议人工检查",
            ],
        })
        confidence = min(abs(zs_info["z_composite"]) / 5.0, 0.8)

    # Build cascade chain
    cascade = []
    if diag_info:
        pat = diag_info.get("patterns_detected", "")
        if "thermal_buildup" in pat and "power_anomaly" in pat:
            cascade.append("热积聚 → 绝缘老化 → 电流泄漏 → 电力异常")
        elif "voltage_drift" in pat and "power_anomaly" in pat:
            cascade.append("电压漂移 → 过载 → 电力异常")
        elif "thermal_buildup" in pat and "combined_degradation" in pat:
            cascade.append("热积聚 → 材料疲劳 → 综合退化")

    # Summary
    parts = [f"设备 {machine_id} 根因分析:"]
    if causes:
        for c in causes:
            parts.append(f"\n■ {c['cause']}（置信度 {c['confidence']:.0%}）")
            for e in c.get("evidence", []):
                parts.append(f"  - {e}")
    else:
        parts.append("\n未检测到明显异常模式。该设备可能运行正常。")

    if cascade:
        parts.append(f"\n⚠ 级联故障链分析: {'; '.join(cascade)}")

    if fault_info:
        parts.append(f"\n故障历史: {fault_info['total_faults']}/{fault_info['total_records']} 条记录有故障（{fault_info['fault_rate']}%）")

    result["diagnosis"] = diag_info
    result["z_scores"] = zs_info
    result["fault_history"] = fault_info
    result["root_causes"] = causes
    result["cascade_chains"] = cascade
    result["overall_confidence"] = confidence
    result["text_summary"] = "\n".join(parts)
    return result


# ══════════════════════════════════════════════════════════════════════════
# Tool: get_work_order_history — maintenance records
# ══════════════════════════════════════════════════════════════════════════

def _get_work_order_history(machine_id: str, limit: int = 10) -> dict:
    """Query work order history for a machine."""
    wo_path = DASHBOARD_DATA / "work_orders.csv"
    if not wo_path.exists():
        return {"error": "work_orders.csv not found. Run the pipeline first."}

    wo = pd.read_csv(wo_path)
    match = wo[wo["machine_id"] == machine_id]

    if len(match) == 0:
        return {
            "machine_id": machine_id,
            "found": False,
            "total_orders": 0,
            "text_summary": f"设备 {machine_id} 当前没有维护工单记录。该设备可能处于正常运行状态。",
        }

    orders = []
    for _, row in match.head(limit).iterrows():
        orders.append({
            "priority": int(row["priority"]),
            "alert_level": str(row["alert_level"]),
            "action_type": str(row["action_type"]),
            "cost_at_risk": float(row["cost_at_risk"]),
            "urgency_score": float(row["urgency_score"]),
            "window_days": int(row["window_days"]),
            "expected_savings": float(row["expected_savings"]),
            "suggestion": str(row["suggestion"])[:400],
        })

    parts = [f"设备 {machine_id} 维护工单历史（共 {len(orders)} 条）:"]
    for o in orders:
        parts.append(
            f"  优先级 #{o['priority']} | {o['action_type']} | "
            f"紧急度 {o['urgency_score']:.0f} | 成本风险 ${o['cost_at_risk']:,.0f} | "
            f"窗口 {o['window_days']} 天 | 预计节约 ${o['expected_savings']:,.0f}"
        )

    return {
        "machine_id": machine_id,
        "found": True,
        "total_orders": len(orders),
        "orders": orders,
        "text_summary": "\n".join(parts),
    }


# Original tools below
# ══════════════════════════════════════════════════════════════════════════

def _explain_predictability_limit() -> dict:
    """Explain why 4-parameter system has limited predictability."""
    dim1_path = V3_OUTPUTS / "dim1_single_param_discriminability.csv"
    dim5_path = V3_OUTPUTS / "dim5_sensor_gap_analysis.csv"

    params = {}
    if dim1_path.exists():
        dim1 = pd.read_csv(dim1_path)
        for _, row in dim1.iterrows():
            params[row["parameter"]] = {
                "youden_j": float(row["youden_j"]),
                "fault_in_normal_pct": str(row["fault_in_normal_pct"]),
                "cohens_d": float(row["cohens_d"]),
                "interpretation": str(row["youden_interpretation"]),
            }

    sensors = []
    if dim5_path.exists():
        dim5 = pd.read_csv(dim5_path)
        for _, row in dim5.iterrows():
            sensors.append({
                "sensor": str(row["sensor"]),
                "expected_youden_j": str(row["expected_youden_j"]),
                "expected_auc_gain": str(row["expected_auc_gain"]),
                "mechanism": str(row["mechanism"]),
                "cost_per_machine": str(row["cost_per_machine"]),
                "feasibility": str(row["feasibility"]),
            })

    return {
        "conclusion": "4个监控参数不足以支持有效的纯ML预测性维护。最大Youden's J = 0.075（可用阈值 > 0.30）。",
        "parameters": params,
        "recommended_sensors": sensors,
        "current_approach": "统计基线(z-score) + 成本风险 + ML密度 → 多信号融合决策",
        "detection_performance": "z-score阈值1.5: 检测率84%, 误报率20%",
        "best_next_action": "加装振动传感器 — 单次最高影响力改进，预计Youden's J提升至0.45+",
    }


# ══════════════════════════════════════════════════════════════════════════
# Pipeline Tool — subprocess calls to skill scripts
# ══════════════════════════════════════════════════════════════════════════

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
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "duration_seconds": duration,
            "stdout_tail": "\n".join(proc.stdout.strip().split("\n")[-20:]) if proc.stdout else "",
            "stderr_tail": proc.stderr.strip()[-500:] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout after 600s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_pipeline(data_dir: str = None, skip_ml: bool = False, max_orders: int = 20) -> dict:
    """Run the full predictive maintenance pipeline via orchestrator."""
    if data_dir is None:
        data_dir = str(PROJECT_ROOT / "原始数据集")

    output_base = str(OUTPUTS_DIR)

    # Step 1: data-prep
    prep_dir = os.path.join(output_base, "data_prep")
    r1 = _run_skill_script("predictive-maintenance-data-prep", [data_dir, prep_dir])
    if not r1["success"]:
        return {"success": False, "step": "data_prep", "error": r1.get("error", r1.get("stderr_tail", "")), "status": "data_prep_failed"}

    # Step 2: stat (required) + ml (optional, parallel in real impl, sequential here for simplicity)
    stat_dir = os.path.join(output_base, "stat")
    r2 = _run_skill_script("predictive-maintenance-stat-inference", [
        "--data-dir", data_dir, "--prep-dir", prep_dir, "--output-dir", stat_dir
    ])

    ml_dir = os.path.join(output_base, "ml")
    ml_success = False
    if not skip_ml:
        r3 = _run_skill_script("predictive-maintenance-ml-inference", [
            "--data-dir", data_dir, "--prep-dir", prep_dir, "--output-dir", ml_dir, "--model", "v1"
        ])
        ml_success = r3["success"]

    # Step 3: diagnosis
    diag_dir = os.path.join(output_base, "diagnosis")
    diag_args = ["--data-dir", data_dir, "--prep-dir", prep_dir,
                 "--stat-dir", stat_dir, "--output-dir", diag_dir, "--skip-predictability"]
    if ml_success:
        diag_args.extend(["--ml-dir", ml_dir])
    _run_skill_script("predictive-maintenance-diagnosis", diag_args)

    # Step 4: decision
    decision_dir = os.path.join(output_base, "decision")
    dec_args = ["--data-dir", data_dir, "--prep-dir", prep_dir,
                "--stat-dir", stat_dir, "--output-dir", decision_dir,
                "--max-orders", str(max_orders)]
    if ml_success:
        dec_args.extend(["--ml-dir", ml_dir])
    r5 = _run_skill_script("predictive-maintenance-decision", dec_args)

    if r5["success"]:
        wo_path = Path(decision_dir) / "maintenance_work_orders.csv"
        if wo_path.exists():
            wo_df = pd.read_csv(wo_path)
            top5 = wo_df.head(5)[["priority", "machine_id", "alert_level", "action_type", "urgency_score", "cost_at_risk"]].to_dict(orient="records")
            return {
                "success": True,
                "status": "pipeline_complete",
                "output_dir": decision_dir,
                "work_orders_count": len(wo_df),
                "top_5_orders": top5,
                "total_duration_seconds": r1["duration_seconds"] + r2["duration_seconds"] + r5["duration_seconds"],
            }

    return {"success": False, "step": "decision", "error": r5.get("error", r5.get("stderr_tail", "")), "status": "decision_failed"}


# ══════════════════════════════════════════════════════════════════════════
# Tool: generate_maintenance_report — AI-driven PDF report generation
# ══════════════════════════════════════════════════════════════════════════

def _generate_maintenance_report(report_type: str, machine_id: str = None) -> dict:
    """Generate an AI-driven predictive maintenance report (HTML + optional PDF)."""
    from gateway.report_orchestrator import generate_maintenance_report as orchestrate
    from gateway.report_generator import generate_report

    # Step 1: Orchestrate MCP tool calls to gather data
    report_data = orchestrate(
        report_type=report_type,
        machine_id=machine_id,
        top_n=5,
    )

    # Step 2: Generate HTML report (primary) + best-effort PDF
    result = generate_report(
        report_data=report_data,
        report_type=report_type,
        machine_id=machine_id,
    )

    if result["success"]:
        resp = {
            "success": True,
            "html_url": result["html_url"],
            "html_size_kb": result["html_size_kb"],
            "report_type": report_type,
            "machine_id": machine_id,
            "text_summary": result["text_summary"],
        }
        if result.get("pdf_url"):
            resp["pdf_url"] = result["pdf_url"]
            resp["pdf_size_kb"] = result["pdf_size_kb"]
        return resp
    else:
        return {
            "success": False,
            "error": result.get("error", "Unknown error"),
            "report_type": report_type,
            "text_summary": result.get("text_summary", "Report generation failed."),
        }


# ══════════════════════════════════════════════════════════════════════════
# Tool Router — dispatches tool name to implementation
# ══════════════════════════════════════════════════════════════════════════

def execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Execute a tool by name and return a JSON string result.
    This is the single entry point for all tool calls from the LLM.
    Returns a string because DeepSeek/OpenAI expects tool_result content as string.
    """
    try:
        if tool_name == "query_device_status":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            result = _query_device_status(machine_id)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "list_alarm_devices":
            result = _list_alarm_devices()
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_fault_history":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            limit = arguments.get("limit", 10)
            include_normal = arguments.get("include_normal", False)
            result = _get_fault_history(machine_id, limit=limit, include_normal=include_normal)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_sensor_trend":
            machine_id = arguments.get("machine_id", "")
            sensor = arguments.get("sensor", "")
            if not machine_id or not sensor:
                return json.dumps({"error": "machine_id and sensor are required"}, ensure_ascii=False)
            hours = arguments.get("hours", 24)
            result = _get_sensor_trend(machine_id, sensor, hours=hours)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "compare_machines":
            machine_a = arguments.get("machine_a", "")
            machine_b = arguments.get("machine_b", "")
            if not machine_a or not machine_b:
                return json.dumps({"error": "machine_a and machine_b are required"}, ensure_ascii=False)
            result = _compare_machines(machine_a, machine_b)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_root_cause_analysis":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            result = _get_root_cause_analysis(machine_id)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_work_order_history":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            limit = arguments.get("limit", 10)
            result = _get_work_order_history(machine_id, limit=limit)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "explain_predictability_limit":
            result = _explain_predictability_limit()
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "run_pipeline":
            data_dir = arguments.get("data_dir")
            skip_ml = arguments.get("skip_ml", False)
            max_orders = arguments.get("max_orders", 20)
            result = _run_pipeline(data_dir=data_dir, skip_ml=skip_ml, max_orders=max_orders)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "generate_maintenance_report":
            report_type = arguments.get("report_type", "weekly")
            machine_id = arguments.get("machine_id")
            if report_type == "device" and not machine_id:
                return json.dumps({"error": "machine_id is required for device report type"}, ensure_ascii=False)
            result = _generate_maintenance_report(report_type=report_type, machine_id=machine_id)
            return json.dumps(result, ensure_ascii=False, default=str)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"Tool execution error: {str(e)}"}, ensure_ascii=False)
