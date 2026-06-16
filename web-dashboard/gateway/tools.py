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
            "description": "AI驱动生成工业预测性维护报告（HTML）。支持6种报告类型：weekly（周度系统报告）、device（单设备健康报告）、risk（高风险设备报告）、thermal（热漂移专项分析）、health_critical（低健康分设备集体报告，默认健康分<30）、parts_summary（备件需求汇总报告）。系统自动调用MCP工具聚合数据，生成图表，输出HTML报告。",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["weekly", "device", "risk", "thermal", "health_critical", "parts_summary"],
                        "description": "报告类型：weekly(周度系统报告), device(单设备健康报告), risk(高风险设备报告), thermal(热漂移分析), health_critical(低健康分集体报告), parts_summary(备件需求汇总)"
                    },
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID（report_type=device时必填），例如 CNC_036"
                    },
                    "health_threshold": {
                        "type": "integer",
                        "description": "健康分阈值（report_type=health_critical时生效），筛选低于此分数的设备，默认30。用户说'健康分低于50'则传50。"
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
            "description": "一键运行完整的预测性维护分析流水线：数据准备→统计推理→诊断→决策工单。耗时约15-30秒。当用户要求'完整分析'、'重新生成工单'、'跑一遍分析'时使用。支持三种维护策略。完成后自动同步到仪表盘数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": f"原始数据目录路径，默认：{PROJECT_ROOT / '原始数据集'}"
                    },
                    "skip_ml": {
                        "type": "boolean",
                        "description": "是否跳过ML推理步骤（XGBoost/深度学习），默认true（因4参数信息瓶颈ML效果有限）"
                    },
                    "max_orders": {
                        "type": "integer",
                        "description": "最大工单数量，默认20"
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["cost_efficiency", "production_efficiency", "quality_first"],
                        "description": "维护策略：cost_efficiency(成本效率，15工单，最低成本)、production_efficiency(生产效率，20工单，平衡)、quality_first(质量优先，30工单，最高覆盖)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_backtest_results",
            "description": "获取时序回测验证结果：预警提前量分布、漏报率、步进回测性能曲线。回答'提前多久发现故障'、'漏报多少'、'方案真的有效吗'等问题。可指定告警阈值和故障分组过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_threshold": {
                        "type": "string",
                        "enum": ["Watch", "Warning", "Alarm"],
                        "description": "告警阈值：Watch(最敏感)、Warning(平衡)、Alarm(最保守)。默认Warning。"
                    },
                    "fault_group": {
                        "type": "string",
                        "enum": ["all", "High-Voltage", "Thermal", "Subtle"],
                        "description": "故障分组过滤：all(全部)、High-Voltage(高压型,类型4/5)、Thermal(热故障型,类型3/6/7/8/9)、Subtle(细微型,类型1/2)。默认all。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_rul_prediction",
            "description": "查询设备的剩余使用寿命(RUL)预测。基于健康分退化轨迹外推，返回RUL小时数、95%置信区间、退化速率、健康分投影等。RUL不可用时自动标注原因（无退化信号/数据不足）。传入设备ID查询单台，不传则返回全量概览和最紧急设备列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "equipment_id": {
                        "type": "string",
                        "description": "设备ID（如 CNC_042）。不填则返回全部设备的RUL概览和最紧急的10台设备。"
                    }
                },
                "required": []
            }
        }
    },
    # ── Work Order Tracking (Phase A: Process Automation) ──
    {
        "type": "function",
        "function": {
            "name": "list_work_order_status",
            "description": "查询工单跟踪状态列表。支持按状态、技师类型、设备ID筛选。返回所有工单的当前状态机状态、分配信息、超时情况。用于工单跟踪看板的数据加载。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "按状态筛选，多个状态用逗号分隔。可选值: pending(待分配), assigned(已分配), escalated(已升级), in_progress(执行中), pending_acceptance(待验收), rejected(验收不通过), completed(已完成), archived(已归档)。不填返回全部。"
                    },
                    "technician": {
                        "type": "string",
                        "description": "按技师类型筛选，如 senior_technician, electrical_specialist。不填返回全部。"
                    },
                    "search": {
                        "type": "string",
                        "description": "按设备ID模糊搜索，如 CNC_042。不填返回全部。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_and_notify_work_order",
            "description": "为待分配工单自动匹配技师并发送邮件通知。根据故障模式（primary_pattern）和风险等级自动选择最合适的技师类型，然后发送包含设备详情、故障根因、备件清单、停机窗口的HTML邮件通知。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID（如 CNC_025）"
                    },
                    "technician_email": {
                        "type": "string",
                        "description": "接收通知的技师邮箱地址。不填则使用默认配置的邮箱。"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_order_status",
            "description": "更新工单状态，触发状态机转换并发送邮件通知。状态转换必须遵循合法路径：pending→assigned→in_progress→pending_acceptance→completed→archived。验收不通过时可从pending_acceptance→rejected→in_progress。超时的工单会自动escalated。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID（如 CNC_025）"
                    },
                    "new_status": {
                        "type": "string",
                        "description": "新状态。可选值: assigned(已分配), in_progress(执行中), pending_acceptance(待验收), completed(已完成), archived(已归档), rejected(验收不通过)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "状态变更备注，如维修过程记录、验收结果等"
                    },
                    "triggered_by": {
                        "type": "string",
                        "description": "操作人标识，如 technician(技师) / supervisor(主管) / system(系统自动)"
                    }
                },
                "required": ["machine_id", "new_status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_order_tracking_detail",
            "description": "获取单个工单的完整跟踪详情。包含：当前状态机状态、完整状态变更历史（审计轨迹）、关联的工业维护计划数据（故障根因、备件清单、验收标准等）。用于工单详情弹窗。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID（如 CNC_025）"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    # ── Phase D: Technician Management ──
    {
        "type": "function",
        "function": {
            "name": "list_technicians",
            "description": "查询员工/技师列表。返回所有技师的姓名、类型、联系方式、当前工单负载、在岗状态。支持按类型和状态筛选。用于员工管理和工单分配时的选人参考。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_type": {
                        "type": "string",
                        "description": "技师类型筛选：electrical_specialist/thermal_specialist/senior_technician/junior_technician/mechanical_specialist。不填返回全部。"
                    },
                    "status": {
                        "type": "string",
                        "description": "状态筛选：available(在岗)/busy(忙碌)/off_duty(休假)。不填返回全部。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_technician_to_work_order",
            "description": "将指定技师分配到工单。传入工单的machine_id和技师ID列表，将技师与工单关联，更新技师负载状态，发送邮件通知。用于工单分配时的具体人员选择。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "工单对应的设备ID（如 CNC_025）"
                    },
                    "technician_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要分配的技师ID列表（如 [1, 3]）"
                    }
                },
                "required": ["machine_id", "technician_ids"]
            }
        }
    },
    # ── Phase C: Inventory + Procurement ──
    {
        "type": "function",
        "function": {
            "name": "check_spare_parts_inventory",
            "description": "检查备件库存状态。对比当前库存与维护工单的备件需求，返回每种零件的库存量、需求量、缺口、状态（充足/不足/缺货）和建议采购数量。用于备件采购决策。",
            "parameters": {
                "type": "object",
                "properties": {
                    "part_name": {
                        "type": "string",
                        "description": "零件名称（如 rotor_assembly）。不填则返回全部零件的库存状态。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_procurement_order",
            "description": "自动生成采购申请单。对比所有备件库存与需求，对库存不足的零件自动生成采购订单（含供应商、数量、金额、预计到货日期）。已存在进行中采购单的零件不会重复生成。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # ── Phase B: Post-Repair Validation + Health Check ──
    {
        "type": "function",
        "function": {
            "name": "get_post_repair_validation",
            "description": "获取设备维修后的自动验收结果。对比修前/修后 Z-Score 数据，判定修复是否成功。包含：修前Z-Score快照、修后最新Z-Score、验收判定(PASS/FAIL/INCONCLUSIVE)、置信度、判定依据。用于维修完成后的自动验收。",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {
                        "type": "string",
                        "description": "设备ID（如 CNC_025）"
                    }
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_health_check",
            "description": "手动触发每日健康巡检。运行完整DAG流水线（跳过ML），更新所有设备健康状态，筛选高风险设备（健康分<40），发送邮件通知运维负责人。返回高危设备列表和流水线执行摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy": {
                        "type": "string",
                        "description": "维护策略：cost_efficiency(成本效率)/production_efficiency(生产效率)/quality_first(质量优先)。不填则使用当前策略。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_system_docs",
            "description": "检索系统使用文档和项目技术文档，回答操作方法、功能说明、算法原理等问题。"
                           "适用场景：健康分怎么计算、如何切换维护策略、基线溯源有哪些类型、三种策略有什么区别、"
                           "角色权限怎么切换、什么是Z-Score基线、仪表盘有哪些功能等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或自然语言问题，如'健康分计算公式'、'维护策略切换方法'"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认5"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_maintenance_kb",
            "description": "检索运维知识库，回答设备维护、故障排查、安全操作规程等问题。"
                           "适用场景：CNC轴承更换步骤、更换转子总成需要什么工具、设备紧急停机流程、"
                           "主轴过热怎么排查、日常点检项目有哪些、维修作业安全规范等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或自然语言问题，如'轴承更换步骤'、'紧急停机流程'"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认5"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_fault_cases",
            "description": "检索历史故障案例库，查找相似故障的处理经验和解决方案。"
                           "适用场景：Type 4故障怎么处理、有没有类似的热异常案例、"
                           "CNC_042历史故障记录、高压型故障通常怎么修复等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或自然语言问题，如'Type 4故障处理'、'热异常案例'"
                    },
                    "fault_type": {
                        "type": "string",
                        "description": "可选：按故障类型过滤，如 Type 4, Type 7, High-Voltage, Thermal, Subtle"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认5"
                    }
                },
                "required": ["query"]
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
        "industrial_plan": None,
    }

    # 1. Work order + Industrial Plan (prefer industrial plan, fall back to work_orders)
    wo_path = DASHBOARD_DATA / "work_orders.csv"
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"

    # 1a. Industrial plan (richer data: 22+ columns)
    if plan_path.exists():
        plan = pd.read_csv(plan_path)
        match = plan[plan["machine_id"] == machine_id]
        if len(match) > 0:
            row = match.iloc[0]
            result["found"] = True
            result["industrial_plan"] = {
                "priority": int(row["priority"]),
                "alert_level": str(row["alert_level"]),
                "action_type": str(row["action_type"]),
                "cost_at_risk": float(row["cost_at_risk"]),
                "urgency_score": float(row["urgency_score"]),
                "window_days": int(row.get("recommended_window_days", row.get("window_days", 0))),
                "expected_savings": float(row["expected_savings"]),
                "suggestion": str(row.get("maintenance_suggestion", ""))[:500],
                "estimated_cost": float(row.get("estimated_cost", 0)),
                "anomaly_score": float(row.get("anomaly_score", 0)),
                "health_score": float(row.get("health_score", 0)),
                "technician_type": str(row.get("technician_type", "")),
                "spare_parts": str(row.get("spare_parts", "")),
                "downtime_window": str(row.get("recommended_downtime_window", "")),
                "sla_target_hours": float(row.get("sla_target_hours", 0)),
                "acceptance_standard": str(row.get("acceptance_standard", ""))[:300],
                "production_impact": float(row.get("production_impact", 0)),
            }

    # 1b. Work order (base fallback)
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

    # 6. Health score confidence (from equipment_health_score.csv)
    health_conf = None
    health_path = DASHBOARD_DATA / "equipment_health_score.csv"
    if health_path.exists():
        hs = pd.read_csv(health_path)
        match = hs[hs["Equipment.Id"] == machine_id]
        if len(match) > 0:
            result["found"] = True
            health_conf = float(match.iloc[0]["confidence"])
            result["health_confidence"] = health_conf

    # 7. Build human-readable text summary
    wo = result.get("work_order")
    plan = result.get("industrial_plan")
    diag = result.get("diagnosis")
    zs = result.get("z_scores")
    cost = result.get("cost_risk")
    sm = result.get("summary")
    hc = result.get("health_confidence")

    parts = [f"设备 {machine_id} 当前状态："]

    # Prefer industrial plan data (richer), fall back to work_order
    if plan:
        parts.append(f"- 维护优先级：#{plan['priority']} ({plan['alert_level']})")
        parts.append(f"- 建议动作：{plan['action_type']}")
        parts.append(f"- 异常分数：{plan['anomaly_score']:.2f} | 健康分数：{plan['health_score']:.0f}/100")
        parts.append(f"- 紧急度：{plan['urgency_score']:.0f}/100 | 成本风险：${plan['cost_at_risk']:,.2f}")
        parts.append(f"- 维护窗口：{plan['window_days']} 天 | SLA {plan['sla_target_hours']:.0f}h")
        parts.append(f"- 预估总成本：${plan['estimated_cost']:,.2f} | 预计节约：${plan['expected_savings']:,.2f}")
        if plan.get("technician_type"):
            parts.append(f"- 指派技术员：{plan['technician_type']}")
        if plan.get("spare_parts"):
            parts.append(f"- 备件清单：{plan['spare_parts']}")
        if plan.get("downtime_window"):
            parts.append(f"- 停机窗口：{plan['downtime_window']}")
        if plan.get("production_impact"):
            parts.append(f"- 生产影响：${plan['production_impact']:,.2f}")
        parts.append(f"- 维护建议：{plan['suggestion'][:400]}")
    elif wo:
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
        if diag['diagnosis_confidence'] == 0:
            parts.append(f"  （设备当前无异常故障模式，诊断引擎未检测到已知故障特征，故模式检测置信度为0%）")
        if hc is not None:
            parts.append(f"- 健康评估置信度：{hc:.0%}（来自健康评分模型，基于多信号融合的评估可信度）")

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
    """List all devices with ALARM or WARNING status. Prefers industrial plan data."""
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    wo_path = DASHBOARD_DATA / "work_orders.csv"

    # Prefer industrial plan (richer), fall back to work_orders
    src_path = plan_path if plan_path.exists() else wo_path
    if not src_path.exists():
        return {"error": "未找到工单数据，请先运行流水线生成工单。"}

    src = pd.read_csv(src_path)
    # Filter by alert level field (exists in both CSVs)
    if "predicted_risk" in src.columns:
        alarms = src[src["predicted_risk"].isin(["ALARM", "WARNING"])].sort_values("priority")
    else:
        alarms = src[src["alert_level"].isin(["ALARM", "WARNING"])].sort_values("priority")

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

        # Get primary pattern — prefer diagnosis, then industrial plan's primary_pattern
        pattern = d.get("primary_pattern", "")
        if not pattern or pattern == "unknown":
            pattern = str(row.get("primary_pattern", "unknown"))

        action = str(row.get("recommended_action", row.get("action_type", "")))
        alert = str(row.get("predicted_risk", row.get("alert_level", "")))

        device = {
            "machine_id": mid,
            "priority": int(row["priority"]),
            "alert_level": alert,
            "action_type": action,
            "urgency_score": float(row.get("urgency_score", 0)),
            "cost_at_risk": float(row.get("cost_at_risk", 0)),
            "window_days": int(row.get("recommended_window_days", row.get("window_days", 0))),
            "suggestion_short": str(row.get("maintenance_suggestion", row.get("suggestion", "")))[:200] + "...",
            "primary_pattern": pattern,
            "patterns_detected": d.get("patterns_detected", ""),
            "diagnosis_confidence": d.get("diagnosis_confidence", 0),
            # Industrial plan enrichment fields
            "estimated_cost": float(row.get("estimated_cost", 0)),
            "expected_savings": float(row.get("expected_savings", 0)),
            "technician_type": str(row.get("technician_type", "")),
            "spare_parts": str(row.get("spare_parts", "")),
            "health_score": float(row.get("health_score", 0)),
        }
        devices.append(device)

        if "thermal" in pattern.lower():
            thermal_drift_devices.append(device)
        if "shutdown" in action.lower():
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
                f"  #{d['priority']} {d['machine_id']} — {d['action_type']}"
                + (f" | 预估成本 ${d['estimated_cost']:,.0f}" if d.get('estimated_cost') else "")
                + (f" | 技术员 {d['technician_type']}" if d.get('technician_type') else "")
                + (f"\n    紧急度: {d['urgency_score']:.0f}, 成本风险: ${d['cost_at_risk']:,.0f}, 异常模式: {d['primary_pattern']}")
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

    # 4. Industrial plan pattern (fallback when diagnosis.csv missing)
    if not diag_info:
        plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
        if plan_path.exists():
            plan = pd.read_csv(plan_path)
            pmatch = plan[plan["machine_id"] == machine_id]
            if len(pmatch) > 0:
                prow = pmatch.iloc[0]
                pattern = str(prow.get("primary_pattern", ""))
                if pattern and pattern != "normal":
                    diag_info = {
                        "primary_pattern": pattern,
                        "patterns_detected": pattern,
                        "confidence": float(prow.get("anomaly_score", 0.5)),
                        "voltage_drift": 0.7 if "voltage" in pattern.lower() else 0.2,
                        "thermal_buildup": 0.7 if "thermal" in pattern.lower() else 0.2,
                        "power_anomaly": 0.7 if "power" in pattern.lower() else 0.2,
                        "combined_degradation": 0.7 if "combined" in pattern.lower() or "degradation" in pattern.lower() else 0.2,
                    }
                    result["found"] = True

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
    """Query work order history for a machine. Uses industrial plan for rich data."""
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    wo_path = DASHBOARD_DATA / "work_orders.csv"

    # Prefer industrial plan (richer), fall back to work_orders
    src_path = plan_path if plan_path.exists() else wo_path
    if not src_path.exists():
        return {"error": "未找到工单数据。Run the pipeline first."}

    src = pd.read_csv(src_path)
    match = src[src["machine_id"] == machine_id]

    if len(match) == 0:
        return {
            "machine_id": machine_id,
            "found": False,
            "total_orders": 0,
            "text_summary": f"设备 {machine_id} 当前没有维护工单记录。该设备可能处于正常运行状态。",
        }

    orders = []
    for _, row in match.head(limit).iterrows():
        order = {
            "priority": int(row["priority"]),
            "alert_level": str(row.get("predicted_risk", row.get("alert_level", ""))),
            "action_type": str(row.get("recommended_action", row.get("action_type", ""))),
            "cost_at_risk": float(row.get("cost_at_risk", 0)),
            "urgency_score": float(row.get("urgency_score", 0)),
            "window_days": int(row.get("recommended_window_days", row.get("window_days", 0))),
            "expected_savings": float(row.get("expected_savings", 0)),
            "suggestion": str(row.get("maintenance_suggestion", row.get("suggestion", "")))[:400],
            # Industrial plan enrichment
            "estimated_cost": float(row.get("estimated_cost", 0)),
            "technician_type": str(row.get("technician_type", "")),
            "spare_parts": str(row.get("spare_parts", "")),
            "sla_target_hours": float(row.get("sla_target_hours", 0)),
            "health_score": float(row.get("health_score", 0)),
        }
        orders.append(order)

    parts = [f"设备 {machine_id} 维护工单（共 {len(orders)} 条）:"]
    for o in orders:
        parts.append(
            f"  优先级 #{o['priority']} | {o['action_type']} | "
            f"预估成本 ${o['estimated_cost']:,.0f} | 预计节约 ${o['expected_savings']:,.0f}"
            + (f" | 技术员 {o['technician_type']}" if o.get('technician_type') else "")
            + (f" | 备件 {o['spare_parts']}" if o.get('spare_parts') else "")
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
    """Explain why 4-parameter system has limited predictability.
    Reads from DASHBOARD_DATA first (synced pipeline output), falls back to V3_OUTPUTS."""
    # Priority: DASHBOARD_DATA (current pipeline) → V3_OUTPUTS (legacy)
    dim1_path = DASHBOARD_DATA / "dim1.csv"
    dim5_path = DASHBOARD_DATA / "dim5.csv"
    if not dim1_path.exists():
        dim1_path = V3_OUTPUTS / "dim1_single_param_discriminability.csv"
    if not dim5_path.exists():
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
        "data_sources": {
            "dim1": str(dim1_path),
            "dim5": str(dim5_path),
            "synced_to_dashboard": str(DASHBOARD_DATA),
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# Pipeline Tool — subprocess calls to skill scripts
# ══════════════════════════════════════════════════════════════════════════

def _run_skill_script(skill_name: str, args: list) -> dict:
    """Run a skill's scripts/run.py via subprocess."""
    script = PROJECT_ROOT / "skills" / skill_name / "scripts" / "run.py"
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


# ── File lists for dashboard sync (mirrors orchestrator _sync_to_dashboard) ──
_DECISION_FILES = [
    "industrial_maintenance_plan.csv", "maintenance_work_orders.csv",
    "strategy_comparison.csv", "technician_schedule.csv",
    "spare_parts_plan.csv", "downtime_schedule.csv",
    "maintenance_decision_report.csv",
    "sensor_upgrade_plan.csv", "sensor_roi_analysis.csv", "sensor_phase_summary.csv",
]
_STAT_FILES = [
    "quality_cost_chain.csv", "alert_summary.csv", "equipment_health_score.csv",
]
_PREP_FILES = [
    "z_scores.csv", "cost_risk_matrix.csv", "failure_signatures.csv",
    "variance_decomposition.csv", "hotelling_t2.csv",
    "machine_clusters.csv", "baseline_stats.csv",
]
_RENAMES = {
    "failure_signatures.csv": "failure_sig.csv",
    "cost_risk_matrix.csv": "cost_risk.csv",
    "hotelling_t2.csv": "t2_results.csv",
    "maintenance_work_orders.csv": "work_orders.csv",
    "variance_decomposition.csv": "variance_decomp.csv",
}


def _sync_to_dashboard(prep_dir: str, stat_dir: str, decision_dir: str) -> int:
    """Sync pipeline output files to DASHBOARD_DATA with renaming."""
    copied = 0
    for src_dir, file_list in [
        (decision_dir, _DECISION_FILES),
        (stat_dir, _STAT_FILES),
        (prep_dir, _PREP_FILES),
    ]:
        if not src_dir:
            continue
        for fname in file_list:
            src = Path(src_dir) / fname
            if not src.exists():
                continue
            dst_name = _RENAMES.get(fname, fname)
            dst = DASHBOARD_DATA / dst_name
            import shutil as _shutil
            _shutil.copy2(src, dst)
            copied += 1
    return copied


def _run_pipeline(data_dir: str = None, skip_ml: bool = False, max_orders: int = 20,
                  strategy: str = "production_efficiency") -> dict:
    """Run the full predictive maintenance pipeline via orchestrator. Syncs results to dashboard data."""
    if data_dir is None:
        data_dir = str(PROJECT_ROOT / "原始数据集")

    # Output to the canonical pipeline output directory (same as orchestrator CLI)
    output_base = MCP_DIR / "outputs"

    # Step 1: data-prep
    prep_dir = output_base / "output_data_prep"
    r1 = _run_skill_script("predictive-maintenance-data-prep", [data_dir, str(prep_dir)])
    if not r1["success"]:
        return {"success": False, "step": "data_prep", "error": r1.get("error", r1.get("stderr_tail", "")), "status": "data_prep_failed"}

    # Step 2: stat inference (required)
    stat_dir = output_base / "output_stat_inference"
    r2 = _run_skill_script("predictive-maintenance-stat-inference", [
        "--data-dir", data_dir, "--prep-dir", str(prep_dir), "--output-dir", str(stat_dir)
    ])

    # Step 3: ml (optional)
    ml_dir = output_base / "output_ml_inference"
    ml_success = False
    if not skip_ml:
        r3 = _run_skill_script("predictive-maintenance-ml-inference", [
            "--data-dir", data_dir, "--prep-dir", str(prep_dir), "--output-dir", str(ml_dir), "--model", "v1"
        ])
        ml_success = r3["success"]

    # Step 4: diagnosis (optional, requires ml for best results)
    diag_dir = output_base / "output_diagnosis"
    diag_args = ["--data-dir", data_dir, "--prep-dir", str(prep_dir),
                 "--stat-dir", str(stat_dir), "--output-dir", str(diag_dir), "--skip-predictability"]
    if ml_success:
        diag_args.extend(["--ml-dir", str(ml_dir)])
    _run_skill_script("predictive-maintenance-diagnosis", diag_args)

    # Step 5: decision (with strategy)
    decision_dir = output_base / "output_decision"
    dec_args = ["--data-dir", data_dir, "--prep-dir", str(prep_dir),
                "--stat-dir", str(stat_dir), "--output-dir", str(decision_dir),
                "--max-orders", str(max_orders),
                "--strategy", strategy]
    if ml_success:
        dec_args.extend(["--ml-dir", str(ml_dir)])
    if diag_dir.exists():
        dec_args.extend(["--diag-dir", str(diag_dir)])
    r5 = _run_skill_script("predictive-maintenance-decision", dec_args)

    # Sync to dashboard data directory
    synced = _sync_to_dashboard(str(prep_dir), str(stat_dir), str(decision_dir))

    if r5["success"]:
        wo_path = decision_dir / "maintenance_work_orders.csv"
        if wo_path.exists():
            wo_df = pd.read_csv(wo_path)
            top5 = wo_df.head(5)[["priority", "machine_id", "alert_level", "action_type", "urgency_score", "cost_at_risk"]].to_dict(orient="records")
            return {
                "success": True,
                "status": "pipeline_complete",
                "output_dir": str(decision_dir),
                "work_orders_count": len(wo_df),
                "top_5_orders": top5,
                "files_synced_to_dashboard": synced,
                "total_duration_seconds": r1["duration_seconds"] + r2["duration_seconds"] + r5["duration_seconds"],
            }

    return {"success": False, "step": "decision", "error": r5.get("error", r5.get("stderr_tail", "")), "status": "decision_failed"}


# ══════════════════════════════════════════════════════════════════════════
# Tool: generate_maintenance_report — AI-driven PDF report generation
# ══════════════════════════════════════════════════════════════════════════

def _generate_maintenance_report(report_type: str, machine_id: str = None,
                                 health_threshold: int = 30) -> dict:
    """Generate an AI-driven predictive maintenance report (HTML + optional PDF).

    Thin wrapper over the 4-layer report pipeline:
      report_orchestrator → collector → renderer → delivery
    """
    from gateway.report_orchestrator import generate_maintenance_report as orchestrate

    result = orchestrate(
        report_type=report_type,
        machine_id=machine_id,
        top_n=5,
        health_threshold=health_threshold,
    )

    if result.get("success"):
        resp = {
            "success": True,
            "html_url": result.get("html_url"),
            "html_size_kb": result.get("html_size_kb", 0),
            "report_type": report_type,
            "machine_id": machine_id,
            "text_summary": result.get("text_summary", ""),
        }
        if result.get("pdf_url"):
            resp["pdf_url"] = result["pdf_url"]
            resp["pdf_size_kb"] = result.get("pdf_size_kb", 0)
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

def _get_backtest_results(alert_threshold: str = "Warning", fault_group: str = "all") -> dict:
    """
    从预计算的回测CSV中读取结果，返回结构化数据供前端展示和AI回复。

    数据源：DASHBOARD_DATA/backtest_summary.json + backtest_lead_time_summary.csv
    """
    import json as _json

    result = {
        "alert_threshold": alert_threshold,
        "fault_group": fault_group,
        "available": False,
        "summary": {},
        "lead_time_by_threshold": [],
        "by_fault_group": [],
        "walk_forward": {},
        "charts": {},
    }

    # Load main summary
    summary_path = DASHBOARD_DATA / "backtest_summary.json"
    if not summary_path.exists():
        result["error"] = "回测数据不存在，请先运行流水线（含stat-inference步骤）。"
        return result

    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            bt = _json.load(f)
        result["available"] = True
        ds = bt.get("data_summary", {})
        result["summary"] = {
            "n_machines": ds.get("n_machines", 0),
            "n_time_steps": ds.get("n_time_steps", 0),
            "minutes_per_step": ds.get("minutes_per_step", 14),
        }

        # Threshold comparison — skip threshold_comparison list
        event_data = bt.get("event_based", {})
        for thresh, info in event_data.items():
            if isinstance(info, dict) and thresh != "threshold_comparison":
                result["lead_time_by_threshold"].append({
                    "threshold": thresh,
                    "avg_lead_time_minutes": info.get("avg_lead_time_minutes", 0),
                    "median_lead_time_minutes": info.get("median_lead_time_minutes", 0),
                    "miss_rate": info.get("miss_rate", 0),
                    "detection_rate": info.get("detection_rate", 0),
                    "total_events": info.get("total_events", 0),
                })

        # Fault group stratified — per-threshold dict
        fg_all = bt.get("fault_group_stratified", {})
        if isinstance(fg_all, dict):
            result["by_fault_group"] = fg_all.get(alert_threshold, [])
        else:
            result["by_fault_group"] = fg_all

        # Walk-forward — per-threshold dict
        wf_all = bt.get("walk_forward", {})
        if isinstance(wf_all, dict) and "total_folds" not in wf_all:
            result["walk_forward"] = wf_all.get(alert_threshold, {})
        else:
            result["walk_forward"] = wf_all

    except Exception as e:
        result["error"] = f"读取回测数据失败: {e}"
        return result

    # Filter by fault_group if specified
    if fault_group != "all" and result["by_fault_group"]:
        result["by_fault_group"] = [
            fg for fg in result["by_fault_group"]
            if fg.get("fault_group") == fault_group
        ]

    # Generate concise narrative for AI consumption
    if result["available"]:
        event_info = event_data.get(alert_threshold, {})
        wf_info = result.get("walk_forward", {})
        fg_list = result.get("by_fault_group", [])
        if isinstance(event_info, dict):
            result["narrative"] = (
                f"时序回测结果（{alert_threshold}级别，{ds['n_time_steps']}步窗口，{ds['n_machines']}台设备）：\n"
                f"• 平均预警提前时间：{event_info.get('avg_lead_time_minutes', 0):.0f}分钟\n"
                f"• 中位预警提前时间：{event_info.get('median_lead_time_minutes', 0):.0f}分钟\n"
                f"• 漏报率：{event_info.get('miss_rate', 0):.1%}（{event_info.get('total_events', 0)}个故障事件中"
                f"有{event_info.get('missed_events_count', 0)}个未被预警）\n"
                f"• 检出率：{event_info.get('detection_rate', 0):.1%}（{event_info.get('detected_events', 0)}个被成功预警）\n"
                f"• 步进回测：{wf_info.get('total_folds', 0)}个折叠expanding window，"
                f"基线在步{wf_info.get('convergence_step', '?')}收敛，"
                f"早期F1={wf_info.get('early_steps_f1_mean', 0):.3f}，稳定期F1={wf_info.get('late_steps_f1_mean', 0):.3f}\n"
                f"• 按故障类型（漏报率）："
                + "；".join(
                    f"{fg['fault_group']}(类型{fg.get('fault_types','?')})={fg['miss_rate']:.0%}"
                    for fg in fg_list
                    if isinstance(fg, dict)
                )
                + "\n"
                f"• 三层回测体系：①点级回测逐步展开混淆矩阵→滚动F1曲线 ②事件级回测以故障发作(N→F转换)为锚点回溯5步告警→预警提前量 ③步进回测expanding window→基线收敛性与最少训练数据需求"
            )

    return result


def _get_rul_prediction(equipment_id: str = "") -> dict:
    """查询RUL预测数据（基于健康分退化轨迹外推）。"""
    import csv as _csv
    rul_path = os.path.join(DASHBOARD_DATA, "rul_degradation.csv")
    summary_path = os.path.join(DASHBOARD_DATA, "rul_summary.json")

    if not os.path.exists(rul_path):
        return {
            "status": "unavailable",
            "error": "RUL data not yet generated. Run stat-inference pipeline without --skip-rul first.",
        }

    # Load summary
    summary = {}
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

    if equipment_id:
        # Single machine
        with open(rul_path, "r", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                if row.get("Equipment.Id") == equipment_id:
                    return {
                        "status": "success",
                        "equipment_id": equipment_id,
                        "rul": {
                            "rul_hours": round(float(row["rul_hours"]), 1) if row.get("rul_hours") and row["rul_hours"] != "" else None,
                            "rul_steps": round(float(row["rul_steps"]), 1) if row.get("rul_steps") and row["rul_steps"] != "" else None,
                            "rul_ci_lower_hours": round(float(row["rul_ci_lower_hours"]), 1),
                            "rul_ci_upper_hours": round(float(row["rul_ci_upper_hours"]), 1),
                            "health_score_current": float(row["health_score_current"]),
                            "health_score_projected_7d": round(float(row["health_score_projected_7d"]), 1) if row.get("health_score_projected_7d") and row["health_score_projected_7d"] != "" else None,
                            "health_score_projected_14d": round(float(row["health_score_projected_14d"]), 1) if row.get("health_score_projected_14d") and row["health_score_projected_14d"] != "" else None,
                            "degradation_rate_per_day": round(float(row["degradation_rate_per_day"]), 4),
                            "model_type": row.get("model_type", ""),
                            "r_squared": float(row.get("r_squared", 0)),
                            "trend": row.get("trend", ""),
                            "status": row.get("status", ""),
                            "status_reason": row.get("status_reason", ""),
                            "warnings": row.get("warnings", ""),
                        },
                    }
        return {"status": "not_found", "equipment_id": equipment_id, "error": f"Equipment {equipment_id} not found"}

    # All machines overview
    rul_data = []
    with open(rul_path, "r", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            rul_data.append(row)

    n_ok = sum(1 for r in rul_data if r.get("status") == "ok")
    n_no_deg = sum(1 for r in rul_data if r.get("status") == "no_degradation")
    n_insuff = sum(1 for r in rul_data if r.get("status") == "insufficient_data")

    # Most urgent (shortest RUL, available only)
    ok_sorted = sorted(
        [r for r in rul_data if r.get("status") == "ok" and r.get("rul_hours") and r["rul_hours"] != ""],
        key=lambda r: float(r["rul_hours"])
    )
    urgent = []
    for r in ok_sorted[:10]:
        urgent.append({
            "equipment_id": r["Equipment.Id"],
            "rul_hours": round(float(r["rul_hours"]), 1),
            "health_score_current": float(r["health_score_current"]),
            "trend": r.get("trend", ""),
            "degradation_rate_per_day": round(float(r.get("degradation_rate_per_day", 0)), 4),
        })

    return {
        "status": "success",
        "summary": summary,
        "overview": {
            "total_machines": len(rul_data),
            "rul_available": n_ok,
            "no_degradation_signal": n_no_deg,
            "insufficient_data": n_insuff,
            "coverage_rate": round(n_ok / len(rul_data), 3) if rul_data else 0,
        },
        "most_urgent": urgent,
    }


# ══════════════════════════════════════════════════════════════════════════
# Work Order Tracking Tool Implementations (Phase A: Process Automation)
# ══════════════════════════════════════════════════════════════════════════

def _list_work_order_status(status: str = "", technician: str = "", search: str = "") -> dict:
    """List work orders with state machine tracking data."""
    from gateway.workflow_engine import (
        get_work_orders, get_statistics, get_available_technicians, sync_from_plan_csv,
    )

    # Ensure DB is synced with latest CSV
    sync_from_plan_csv()

    wos = get_work_orders(
        status_filter=status or None,
        technician_filter=technician or None,
        search=search or None,
    )

    stats = get_statistics()
    techs = get_available_technicians()

    # Enrich with priority/summary from plan CSV
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    plan_map = {}
    if plan_path.exists():
        df = pd.read_csv(plan_path)
        for _, row in df.iterrows():
            mid = str(row.get("machine_id", ""))
            if mid:
                plan_map[mid] = {
                    "maintenance_priority": str(row.get("maintenance_priority", "")),
                    "primary_pattern": str(row.get("primary_pattern", "")),
                    "recommended_action": str(row.get("recommended_action", "")),
                    "downtime_window": str(row.get("recommended_downtime_window", "")),
                    "health_score": row.get("health_score", ""),
                    "cost_at_risk": row.get("cost_at_risk", ""),
                    "reasoning": str(row.get("reasoning", ""))[:200],
                }

    result_list = []
    for wo in wos:
        enriched = dict(wo)
        mid = wo["machine_id"]
        summary = plan_map.get(mid, {})
        if not summary:
            try:
                from gateway.work_order_builder import build_work_order_context
                built = build_work_order_context(mid)
                summary = {
                    "maintenance_priority": built.get("maintenance_priority", ""),
                    "primary_pattern": built.get("primary_pattern", ""),
                    "recommended_action": built.get("recommended_action", ""),
                    "downtime_window": built.get("recommended_downtime_window", ""),
                    "health_score": built.get("health_score", ""),
                    "cost_at_risk": built.get("cost_at_risk", ""),
                    "reasoning": str(built.get("reasoning", ""))[:200],
                }
            except Exception:
                pass
        enriched["plan_summary"] = summary
        result_list.append(enriched)

    from gateway.workflow_engine import STATUS_LABELS
    text_lines = [f"共 {len(result_list)} 个工单"]
    for status_key, count in stats.get("by_status", {}).items():
        label = STATUS_LABELS.get(status_key, status_key)
        text_lines.append(f"  {label}: {count}")

    return {
        "work_orders": result_list,
        "total": len(result_list),
        "statistics": stats,
        "available_technicians": [t["technician_type"] for t in techs],
        "text_summary": "\n".join(text_lines),
    }


def _assign_and_notify_work_order(machine_id: str, technician_email: str = "") -> dict:
    """Auto-assign technician to a pending work order and send email notification."""
    from gateway.workflow_engine import transition, get_work_order_detail
    from gateway.notification_service import send_work_order_assignment

    # Check current state
    detail = get_work_order_detail(machine_id)
    if not detail:
        return {"success": False, "error": f"工单不存在: {machine_id}"}

    current_status = detail.get("status", "")
    if current_status != "pending":
        return {
            "success": False,
            "error": f"工单 {machine_id} 当前状态为 {current_status}，只有待分配(pending)的工单才能自动分配",
        }

    # Transition to assigned
    ok, msg = transition(
        machine_id, "assigned",
        triggered_by="system",
        notes="自动分配技师",
        technician_email=technician_email,
    )
    if not ok:
        return {"success": False, "error": msg}

    # Refresh detail
    detail = get_work_order_detail(machine_id)

    # Send notification
    email_sent = send_work_order_assignment(
        machine_id, detail or {},
        to_email=technician_email if technician_email else None,
    )

    plan = detail.get("plan_data", {}) if detail else {}
    return {
        "success": True,
        "machine_id": machine_id,
        "status": "assigned",
        "technician_type": plan.get("technician_type", ""),
        "technician_count": plan.get("technician_count", 1),
        "email_sent": email_sent,
        "message": msg,
        "text_summary": f"工单 {machine_id} 已分配技师 {plan.get('technician_type', '')}，"
                       f"邮件通知{'已发送' if email_sent else '未发送（SMTP未配置）'}。"
                       f"下一步：技师确认后更新为执行中状态。",
    }


def _update_work_order_status(machine_id: str, new_status: str,
                              notes: str = "", triggered_by: str = "user") -> dict:
    """Update work order status with state machine transition and notification."""
    from gateway.workflow_engine import transition, get_work_order_detail, STATUS_LABELS
    from gateway.notification_service import send_status_change

    # Validate status name
    if new_status not in STATUS_LABELS:
        valid = list(STATUS_LABELS.keys())
        return {"success": False, "error": f"无效状态: {new_status}，有效值: {valid}"}

    # Get old status for notification
    detail_before = get_work_order_detail(machine_id)
    old_status = detail_before.get("status", "unknown") if detail_before else "unknown"

    # Execute transition
    ok, msg = transition(
        machine_id, new_status,
        triggered_by=triggered_by,
        notes=notes,
    )
    if not ok:
        return {"success": False, "error": msg}

    # Get updated detail
    detail_after = get_work_order_detail(machine_id)

    # Send notification for significant transitions
    email_sent = False
    if new_status in ("assigned", "in_progress", "pending_acceptance", "completed", "rejected"):
        email_sent = send_status_change(
            machine_id, old_status, new_status,
            detail=detail_after or {},
            notes=notes,
        )

    return {
        "success": True,
        "machine_id": machine_id,
        "old_status": old_status,
        "new_status": new_status,
        "message": msg,
        "email_sent": email_sent,
        "text_summary": f"工单 {machine_id}: {msg}。"
                       f"{'邮件通知已发送。' if email_sent else ''}"
                       f"备注: {notes}" if notes else "",
    }


def _get_work_order_tracking_detail(machine_id: str) -> dict:
    """Get full tracking detail for a single work order."""
    from gateway.workflow_engine import get_work_order_detail

    detail = get_work_order_detail(machine_id)
    if not detail:
        return {"success": False, "error": f"工单不存在: {machine_id}"}

    # Build text summary
    plan = detail.get("plan_data", {}) or {}
    from gateway.workflow_engine import STATUS_LABELS
    status_label = STATUS_LABELS.get(detail.get("status", ""), detail.get("status", ""))

    lines = [
        f"工单 {machine_id} — 当前状态: {status_label}",
        f"故障模式: {plan.get('primary_pattern', '?')}",
        f"维护动作: {plan.get('recommended_action', '?')}",
        f"技师: {plan.get('technician_type', '?')} × {plan.get('technician_count', '?')}人",
        f"停机窗口: {plan.get('recommended_downtime_window', '?')}",
        f"成本风险: ${plan.get('cost_at_risk', '?')}",
        f"验收标准: {plan.get('acceptance_standard', '?')[:150]}",
    ]

    history = detail.get("state_history", [])
    if history:
        lines.append(f"\n状态历史 ({len(history)} 条):")
        for h in history[-5:]:
            from_s = STATUS_LABELS.get(h.get("from_status", ""), h.get("from_status", "—"))
            to_s = STATUS_LABELS.get(h.get("to_status", ""), h.get("to_status", ""))
            lines.append(f"  {h.get('created_at', '?')[:19]}: {from_s} → {to_s}")

    return {
        "success": True,
        "machine_id": machine_id,
        "status": detail.get("status", ""),
        "status_label": status_label,
        "state_history": history,
        "plan_data": plan,
        "technician_type": detail.get("technician_type", ""),
        "technician_count": detail.get("technician_count", 1),
        "escalated": bool(detail.get("escalated", 0)),
        "escalation_count": detail.get("escalation_count", 0),
        "notes": detail.get("notes", ""),
        "assigned_at": detail.get("assigned_at", ""),
        "started_at": detail.get("started_at", ""),
        "completed_at": detail.get("completed_at", ""),
        "accepted_at": detail.get("accepted_at", ""),
        "archived_at": detail.get("archived_at", ""),
        "text_summary": "\n".join(lines),
    }


# ══════════════════════════════════════════════════════════════════════════
# Phase D Tool Implementations: Technician Management
# ══════════════════════════════════════════════════════════════════════════

def _list_technicians(tech_type: str = "", status: str = "") -> dict:
    """List technicians with workload."""
    from gateway.workflow_engine import get_technicians
    techs = get_technicians(tech_type=tech_type, status=status)
    type_labels = {
        "electrical_specialist": "电气专家", "thermal_specialist": "热控专家",
        "senior_technician": "高级技师", "junior_technician": "初级技师",
        "mechanical_specialist": "机械专家",
    }
    lines = [f"共 {len(techs)} 名技师"]
    for t in techs:
        tl = type_labels.get(t["technician_type"], t["technician_type"])
        lines.append(f"  [{t['id']}] {t['name']} ({tl}) - {t['current_workload']}/{t['max_concurrent']}工单 - {t['status']}")
    return {"technicians": techs, "total": len(techs), "text_summary": "\n".join(lines)}


def _assign_technician_to_work_order(machine_id: str, technician_ids: list) -> dict:
    """Assign technicians to a work order."""
    from gateway.workflow_engine import assign_technicians_to_work_order, get_technicians, transition, get_work_order_detail
    from gateway.notification_service import send_work_order_assignment

    result = assign_technicians_to_work_order(machine_id, technician_ids)
    if not result["success"]:
        return result

    # Update WO status
    techs = get_technicians()
    names = [next((t["name"] for t in techs if t["id"] == tid), str(tid)) for tid in technician_ids]
    transition(machine_id, "assigned", triggered_by="user", notes=f"分配技师: {', '.join(names)}")

    # Notify
    detail = get_work_order_detail(machine_id)
    emails_sent = 0
    if detail:
        from gateway.notification_service import _is_configured
        for tid in technician_ids:
            t_info = next((t for t in techs if t["id"] == tid), None)
            if t_info and t_info.get("email") and _is_configured():
                send_work_order_assignment(machine_id, detail, to_email=t_info["email"])
                emails_sent += 1

    return {
        "success": True, "machine_id": machine_id,
        "assigned_technicians": names, "emails_sent": emails_sent,
        "text_summary": f"工单 {machine_id} 已分配技师: {', '.join(names)}",
    }


# ══════════════════════════════════════════════════════════════════════════
# Phase C Tool Implementations: Inventory + Procurement
# ══════════════════════════════════════════════════════════════════════════

def _check_spare_parts_inventory(part_name: str = "") -> dict:
    """Check spare parts inventory status."""
    from gateway.inventory_connector import check_stock
    return check_stock(part_name=part_name)


def _generate_procurement_order() -> dict:
    """Auto-generate procurement orders for shortages."""
    from gateway.inventory_connector import generate_procurement_orders
    new_orders = generate_procurement_orders()

    if not new_orders:
        return {
            "success": True,
            "generated": 0,
            "message": "All parts have sufficient stock. No procurement needed.",
            "text_summary": "所有零件库存充足，无需生成采购单。",
        }

    total_cost = sum(o["total_cost"] for o in new_orders)
    lines = [f"生成 {len(new_orders)} 张采购申请单，总金额 ${total_cost:.0f}"]
    for o in new_orders:
        lines.append(f"  {o['order_id']}: {o['part_name']} ×{o['quantity_ordered']} (${o['total_cost']:.0f}) — {o['supplier']}")

    return {
        "success": True,
        "generated": len(new_orders),
        "total_cost": total_cost,
        "orders": new_orders,
        "text_summary": "\n".join(lines),
    }


# ══════════════════════════════════════════════════════════════════════════
# Phase B Tool Implementations: Post-Repair + Health Check
# ══════════════════════════════════════════════════════════════════════════

def _get_post_repair_validation(machine_id: str) -> dict:
    """Get post-repair Z-Score validation result."""
    from gateway.post_repair_checker import validate_repair, capture_pre_repair_snapshot

    # Ensure snapshot exists (try to capture if not)
    from gateway.workflow_engine import get_repair_snapshot
    snap = get_repair_snapshot(machine_id)
    if not snap:
        captured = capture_pre_repair_snapshot(machine_id)
        if not captured:
            return {
                "success": False,
                "error": f"Cannot find Z-Score data for {machine_id}. Device may not have been monitored yet.",
                "text_summary": f"设备 {machine_id} 无 Z-Score 数据，无法进行自动验收。请确认设备已运行至少一个采样周期。",
            }

    result = validate_repair(machine_id)
    return result


def _run_health_check(strategy: str = "") -> dict:
    """Run daily health check manually."""
    from gateway.scheduled_jobs import daily_health_check
    import threading

    # Run in background to avoid blocking the tool call
    def run():
        daily_health_check()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return {
        "success": True,
        "status": "started",
        "message": "Daily health check started in background. Pipeline will run, then email notification will be sent.",
        "text_summary": "每日健康巡检已在后台启动。将依次执行：DAG流水线 → 健康分筛选 → 高危设备邮件通知。预计耗时约30-60秒。",
    }


# ══════════════════════════════════════════════════════════════════════════
# RAG Tool Implementations
# ══════════════════════════════════════════════════════════════════════════

def _search_system_docs(query: str, top_k: int = 5) -> dict:
    """Search system documentation for usage/feature questions."""
    try:
        from .rag_engine import search, ensure_initialized
        ensure_initialized()
        result = search(query, "sys_docs", k=top_k)

        # Build natural language summary
        n_results = result.get("total_found", 0)
        if n_results == 0:
            text_summary = "未在系统文档库中找到相关内容。建议查阅 CLAUDE.md 或项目说明文档获取详细信息。"
        else:
            sources = list(set(r.get("source", "") for r in result["results"]))
            text_summary = f"在系统文档库中找到 {n_results} 条相关结果，来自 {len(sources)} 个文档。"

        return {
            **result,
            "text_summary": text_summary,
        }
    except Exception as e:
        return {"error": f"search_system_docs failed: {str(e)}", "results": [], "total_found": 0}


def _search_maintenance_kb(query: str, top_k: int = 5) -> dict:
    """Search maintenance knowledge base for repair/safety questions."""
    try:
        from .rag_engine import search, ensure_initialized
        ensure_initialized()
        result = search(query, "maint_kb", k=top_k)

        n_results = result.get("total_found", 0)
        if n_results == 0:
            text_summary = "运维知识库中暂未找到相关内容。运维知识库支持上传企业运维手册、安全操作规程等文档，可在知识库管理页面补充。"
        else:
            sources = list(set(r.get("source", "") for r in result["results"]))
            text_summary = f"在运维知识库中找到 {n_results} 条相关结果，来自 {len(sources)} 个文档。"

        return {
            **result,
            "text_summary": text_summary,
        }
    except Exception as e:
        return {"error": f"search_maintenance_kb failed: {str(e)}", "results": [], "total_found": 0}


def _search_fault_cases(query: str, fault_type: str = "", top_k: int = 5) -> dict:
    """Search historical fault cases for similar incident patterns."""
    try:
        from .rag_engine import search, ensure_initialized
        ensure_initialized()
        result = search(query, "fault_cases", k=top_k)

        n_results = result.get("total_found", 0)
        if n_results == 0:
            text_summary = "故障案例库中暂未找到相关案例。案例库基于历史log.csv自动生成，如需更多案例可补充上传。"
        else:
            sources = list(set(r.get("source", "") for r in result["results"]))
            text_summary = f"在故障案例库中找到 {n_results} 条相关案例"

            # If fault_type filter specified, note it
            if fault_type:
                text_summary += f"（筛选条件: {fault_type}）"
            text_summary += "。"

        return {
            **result,
            "text_summary": text_summary,
        }
    except Exception as e:
        return {"error": f"search_fault_cases failed: {str(e)}", "results": [], "total_found": 0}


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
            skip_ml = arguments.get("skip_ml", True)
            max_orders = arguments.get("max_orders", 20)
            strategy = arguments.get("strategy", "production_efficiency")
            result = _run_pipeline(data_dir=data_dir, skip_ml=skip_ml, max_orders=max_orders, strategy=strategy)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "generate_maintenance_report":
            report_type = arguments.get("report_type", "weekly")
            machine_id = arguments.get("machine_id")
            if report_type == "device" and not machine_id:
                return json.dumps({"error": "machine_id is required for device report type"}, ensure_ascii=False)
            result = _generate_maintenance_report(
                report_type=report_type, machine_id=machine_id,
                health_threshold=arguments.get("health_threshold", 30),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_backtest_results":
            alert_threshold = arguments.get("alert_threshold", "Warning")
            fault_group = arguments.get("fault_group", "all")
            result = _get_backtest_results(alert_threshold=alert_threshold, fault_group=fault_group)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_rul_prediction":
            equipment_id = arguments.get("equipment_id", "")
            result = _get_rul_prediction(equipment_id=equipment_id)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "list_work_order_status":
            result = _list_work_order_status(
                status=arguments.get("status", ""),
                technician=arguments.get("technician", ""),
                search=arguments.get("search", ""),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "assign_and_notify_work_order":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            result = _assign_and_notify_work_order(
                machine_id=machine_id,
                technician_email=arguments.get("technician_email", ""),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "update_work_order_status":
            machine_id = arguments.get("machine_id", "")
            new_status = arguments.get("new_status", "")
            if not machine_id or not new_status:
                return json.dumps({"error": "machine_id and new_status are required"}, ensure_ascii=False)
            result = _update_work_order_status(
                machine_id=machine_id,
                new_status=new_status,
                notes=arguments.get("notes", ""),
                triggered_by=arguments.get("triggered_by", "user"),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_work_order_tracking_detail":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            result = _get_work_order_tracking_detail(machine_id=machine_id)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "get_post_repair_validation":
            machine_id = arguments.get("machine_id", "")
            if not machine_id:
                return json.dumps({"error": "machine_id is required"}, ensure_ascii=False)
            result = _get_post_repair_validation(machine_id=machine_id)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "run_health_check":
            strategy = arguments.get("strategy", "")
            result = _run_health_check(strategy=strategy)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "check_spare_parts_inventory":
            part_name = arguments.get("part_name", "")
            result = _check_spare_parts_inventory(part_name=part_name)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "generate_procurement_order":
            result = _generate_procurement_order()
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "list_technicians":
            result = _list_technicians(
                tech_type=arguments.get("tech_type", ""),
                status=arguments.get("status", ""),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "assign_technician_to_work_order":
            machine_id = arguments.get("machine_id", "")
            tech_ids = arguments.get("technician_ids", [])
            if not machine_id or not tech_ids:
                return json.dumps({"error": "machine_id and technician_ids required"}, ensure_ascii=False)
            result = _assign_technician_to_work_order(machine_id=machine_id, technician_ids=tech_ids)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "search_system_docs":
            query = arguments.get("query", "")
            if not query:
                return json.dumps({"error": "query is required"}, ensure_ascii=False)
            top_k = arguments.get("top_k", 5)
            result = _search_system_docs(query=query, top_k=top_k)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "search_maintenance_kb":
            query = arguments.get("query", "")
            if not query:
                return json.dumps({"error": "query is required"}, ensure_ascii=False)
            top_k = arguments.get("top_k", 5)
            result = _search_maintenance_kb(query=query, top_k=top_k)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "search_fault_cases":
            query = arguments.get("query", "")
            if not query:
                return json.dumps({"error": "query is required"}, ensure_ascii=False)
            fault_type = arguments.get("fault_type", "")
            top_k = arguments.get("top_k", 5)
            result = _search_fault_cases(query=query, fault_type=fault_type, top_k=top_k)
            return json.dumps(result, ensure_ascii=False, default=str)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"Tool execution error: {str(e)}"}, ensure_ascii=False)
