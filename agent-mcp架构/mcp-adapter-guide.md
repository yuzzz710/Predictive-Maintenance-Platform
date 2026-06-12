# 预测性维护系统 MCP 适配层开发指南

## 概述

MCP（Model Context Protocol）是 Anthropic 发布的标准化协议，用于连接 AI 模型与外部工具和数据源。本文档描述如何将 5 技能预测性维护推理系统封装为 MCP Server，通过 Tool / Resource / Client 三种机制暴露给 Agent。

**目标**：Agent 不再直接执行 Python 脚本，而是通过 MCP 协议调用标准化的推理能力和知识资源。

**架构概览**：

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Client (Claude / Agent)             │
│  tools/list → tools/call → resources/read → resources/list │
└──────────────────────────┬──────────────────────────────────┘
                           │ JSON-RPC over stdio / HTTP
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server                              │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  Tools (6)       │  │  Resources (5)  │  │  Prompts (3) │ │
│  │  - run_data_prep │  │  - baseline://  │  │  - analyze   │ │
│  │  - run_stat      │  │  - failure://   │  │  - diagnose  │ │
│  │  - run_ml        │  │  - cost://      │  │  - report    │ │
│  │  - run_diagnosis │  │  - knowledge:// │  │              │ │
│  │  - run_decision  │  │  - sensor://    │  │              │ │
│  │  - run_pipeline  │  │                 │  │              │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│           │                    │                   │         │
│           ▼                    ▼                   ▼         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Inference Adapter Layer                   │   │
│  │  调用 5 个技能的 scripts/run.py，管理数据流和状态       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 第 1 章：环境准备

### 1.1 安装 MCP SDK

```bash
pip install mcp
```

### 1.2 目录结构

```
skills/
├── mcp_server.py              # MCP Server 主程序
├── mcp_config.json            # MCP Server 配置（注册到 Claude）
├── agent_orchestrator.py      # Agent 编排器（复用）
├── predictive-maintenance-*/  # 5 个技能目录
└── mcp-adapter-guide.md       # 本文档
```

### 1.3 MCP Server 注册配置

`mcp_config.json`（配置在 Claude Desktop 或 Claude Code 的 mcpServers 中）：

```json
{
  "mcpServers": {
    "predictive-maintenance": {
      "command": "python",
      "args": [
        "C:/Users/yuzzz/Desktop/苗圃杯/数据探索基线确定/skills/mcp_server.py"
      ],
      "env": {
        "DATA_DIR": "/path/to/default/raw_csvs",
        "OUTPUT_BASE": "/path/to/default/outputs"
      }
    }
  }
}
```

---

## 第 2 章：将模型推理封装为 MCP Tool

MCP Tool 是 Agent 可调用的函数——输入参数、执行计算、返回结果。以下将 5 个推理步骤封装为 6 个 Tool（5 个单步 + 1 个全流程）。

### 2.1 Tool 定义

```python
#!/usr/bin/env python3
"""
MCP Server: Predictive Maintenance System
===========================================
将 5 技能推理系统封装为 MCP Tools + Resources + Prompts。

启动:
    python mcp_server.py
    (通过 stdio 与 MCP Client 通信)
"""

import sys, os, json, subprocess, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationCapabilities
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel,
)


# ==============================================================================
# Server Initialization
# ==============================================================================

server = Server("predictive-maintenance")

SKILLS_BASE = Path(__file__).resolve().parent

# 从环境变量读取默认路径
DEFAULT_DATA_DIR = os.environ.get("DATA_DIR", str(SKILLS_BASE / ".." / "原始数据集"))
DEFAULT_OUTPUT_BASE = os.environ.get("OUTPUT_BASE", str(SKILLS_BASE / "outputs"))


def _run_skill_script(skill_dir_name: str, args: List[str]) -> dict:
    """执行技能脚本并返回结果。"""
    skill_dir = SKILLS_BASE / skill_dir_name
    script = skill_dir / "scripts" / "run.py"

    if not script.exists():
        return {"success": False, "error": f"Script not found: {script}"}

    cmd = [sys.executable, str(script)] + args
    start = time.time()

    try:
        result = subprocess.run(
            cmd, cwd=str(skill_dir),
            capture_output=True, text=True, timeout=600,
        )
        duration = time.time() - start
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "duration_seconds": round(duration, 2),
            "stdout": result.stdout[-3000:],  # 截断，避免上下文溢出
            "stderr": result.stderr[-1000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout after 600 seconds",
            "duration_seconds": 600,
        }


def _read_manifest(skill_name: str, output_dir: str) -> dict:
    """读取技能输出的 manifest.json。"""
    manifest_path = Path(output_dir) / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {}


def _read_csv_summary(csv_path: str, max_rows: int = 10) -> dict:
    """安全读取 CSV 并返回摘要。"""
    import pandas as pd
    p = Path(csv_path)
    if not p.exists():
        return {"error": f"File not found: {csv_path}"}
    df = pd.read_csv(p)
    return {
        "path": csv_path,
        "rows": len(df),
        "columns": list(df.columns),
        "head": df.head(max_rows).to_dict(orient="records"),
    }


# ==============================================================================
# Tool Definitions
# ==============================================================================

@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """注册全部 6 个 Tool。"""
    return [
        Tool(
            name="run_data_prep",
            description="""
【数据准备】加载 4 个原始 CSV 文件，构建每台 CNC 设备的统计基线（μ, σ），
计算 z-score 复合指标，构建成本风险矩阵。
输入: data_dir（含 4 个 CSV 的目录路径）
输出: z_scores.csv, cost_risk_matrix.csv, baseline_stats.csv 等 10 个文件
此工具是流水线的第一步，必须最先调用。
""".strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": "包含 4 个原始 CSV 文件的目录路径",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录（默认: outputs_data_prep）",
                    },
                },
                "required": ["data_dir"],
            },
        ),
        Tool(
            name="run_stat_inference",
            description="""
【统计推理】评估 z-score 基线性能，计算 Hotelling T2 多变量统计量，
分析故障类型签名，汇总每台设备的告警状态。
输入: data_dir + prep_dir（data_prep 的输出目录）
输出: alert_summary.csv, z_threshold_sweep.csv, t2_results.csv
可与 run_ml_inference 并行调用。
""".strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string", "description": "原始 CSV 目录"},
                    "prep_dir": {"type": "string", "description": "data_prep 输出目录"},
                    "output_dir": {"type": "string", "description": "输出目录"},
                },
                "required": ["data_dir", "prep_dir"],
            },
        ),
        Tool(
            name="run_ml_inference",
            description="""
【ML 推理】训练 XGBoost（v1）或多任务神经网络（v2），生成故障密度预测。
输入: data_dir + prep_dir
输出: prediction_report.csv
注意: ML 信号在决策融合中权重仅 0.25；若环境无 xgboost/torch，请跳过此工具。
可与 run_stat_inference 并行调用。
""".strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string", "description": "原始 CSV 目录"},
                    "prep_dir": {"type": "string", "description": "data_prep 输出目录"},
                    "output_dir": {"type": "string", "description": "输出目录"},
                    "model_version": {
                        "type": "string",
                        "enum": ["v1", "v2"],
                        "description": "模型版本: v1=XGBoost(快), v2=MTNN(需PyTorch)",
                    },
                },
                "required": ["data_dir", "prep_dir"],
            },
        ),
        Tool(
            name="run_diagnosis",
            description="""
【诊断】识别 4 种异常模式（voltage_drift, thermal_buildup, power_anomaly,
combined_degradation），运行 5 维度可预测性分析。
输入: data_dir + prep_dir + stat_dir + ml_dir(可选)
输出: diagnosis_report.csv
""".strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string", "description": "原始 CSV 目录"},
                    "prep_dir": {"type": "string", "description": "data_prep 输出目录"},
                    "stat_dir": {"type": "string", "description": "stat_inference 输出目录"},
                    "ml_dir": {"type": "string", "description": "ml_inference 输出目录（可选）"},
                    "output_dir": {"type": "string", "description": "输出目录"},
                    "skip_predictability": {
                        "type": "boolean",
                        "description": "跳过耗时的 5 维度分析",
                    },
                },
                "required": ["data_dir", "prep_dir", "stat_dir"],
            },
        ),
        Tool(
            name="run_decision",
            description="""
【决策引擎】4 层决策架构：多信号融合 → 诊断 → 动作确定 → 工单生成。
输出 6 种动作类型之一的维护工单，含成本节约估算。
输入: data_dir + prep_dir + stat_dir + ml_dir(可选) + diag_dir(可选)
输出: maintenance_work_orders.csv（最终产物）
这是流水线的最后一步，必须最后调用。
""".strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string", "description": "原始 CSV 目录"},
                    "prep_dir": {"type": "string", "description": "data_prep 输出目录"},
                    "stat_dir": {"type": "string", "description": "stat_inference 输出目录"},
                    "ml_dir": {"type": "string", "description": "ml_inference 输出目录（可选）"},
                    "diag_dir": {"type": "string", "description": "diagnosis 输出目录（可选）"},
                    "output_dir": {"type": "string", "description": "输出目录"},
                    "streaming": {
                        "type": "boolean",
                        "description": "启用连续确认模式（用于实时监测）",
                    },
                    "max_orders": {
                        "type": "integer",
                        "description": "每周期最大工单数（默认 20）",
                    },
                },
                "required": ["data_dir", "prep_dir", "stat_dir"],
            },
        ),
        Tool(
            name="run_full_pipeline",
            description="""
【全流程编排】一键运行完整流水线: data-prep → stat+ml(并行) → diagnosis → decision。
自动处理降级（ML 不可用时走 stat-only 路径）和错误恢复。
输入: data_dir
输出: maintenance_work_orders.csv + 完整执行报告
推荐 Agent 使用此 Tool 替代逐个调用——更简单、更可靠。
""".strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": "包含 4 个原始 CSV 文件的目录路径",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出基础目录",
                    },
                    "skip_ml": {
                        "type": "boolean",
                        "description": "跳过 ML 推理（降级路径）",
                    },
                    "skip_diagnosis": {
                        "type": "boolean",
                        "description": "跳过诊断步骤",
                    },
                    "model_version": {
                        "type": "string",
                        "enum": ["v1", "v2"],
                        "description": "ML 模型版本",
                    },
                    "streaming": {
                        "type": "boolean",
                        "description": "启用连续确认",
                    },
                    "max_orders": {
                        "type": "integer",
                        "description": "最大工单数",
                    },
                },
                "required": ["data_dir"],
            },
        ),
    ]


# ==============================================================================
# Tool Handlers
# ==============================================================================

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Dict[str, Any]
) -> List[TextContent]:
    """处理 Tool 调用。"""

    # ─── run_full_pipeline: 委托给 agent_orchestrator ───
    if name == "run_full_pipeline":
        return await _handle_pipeline(arguments)

    # ─── 单步 Tools ───
    tool_map = {
        "run_data_prep": (
            "predictive-maintenance-data-prep",
            lambda a: [a["data_dir"], a.get("output_dir", "outputs_data_prep")],
        ),
        "run_stat_inference": (
            "predictive-maintenance-stat-inference",
            lambda a: [
                "--data-dir", a["data_dir"],
                "--prep-dir", a["prep_dir"],
                "--output-dir", a.get("output_dir", "outputs_stat"),
            ],
        ),
        "run_ml_inference": (
            "predictive-maintenance-ml-inference",
            lambda a: [
                "--data-dir", a["data_dir"],
                "--prep-dir", a["prep_dir"],
                "--output-dir", a.get("output_dir", "outputs_ml"),
                "--model", a.get("model_version", "v1"),
            ],
        ),
        "run_diagnosis": (
            "predictive-maintenance-diagnosis",
            lambda a: _build_diag_args(a),
        ),
        "run_decision": (
            "predictive-maintenance-decision",
            lambda a: _build_decision_args(a),
        ),
    }

    if name not in tool_map:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    skill_dir, arg_builder = tool_map[name]
    args = arg_builder(arguments)

    await server.request_logging(LoggingLevel.INFO, f"Running {name} with args: {args}")
    result = _run_skill_script(skill_dir, args)

    if result["success"]:
        # 读取 manifest 获取输出文件列表
        output_dir = arguments.get("output_dir", "")
        if not output_dir:
            # 推导输出目录
            for i, a in enumerate(args):
                if a == "--output-dir" and i + 1 < len(args):
                    output_dir = args[i + 1]
                    break
            if not output_dir:
                output_dir = str(SKILLS_BASE / skill_dir / "outputs_test")

        manifest = _read_manifest(skill_dir, output_dir)
        response = {
            "tool": name,
            "status": "success",
            "duration_seconds": result["duration_seconds"],
            "output_dir": output_dir,
            "output_files": manifest.get("files", {}),
            "summary": {k: v for k, v in manifest.items() if k != "files"},
        }
        return [TextContent(type="text", text=json.dumps(response, indent=2, ensure_ascii=False))]
    else:
        return [TextContent(type="text", text=json.dumps({
            "tool": name,
            "status": "failed",
            "error": result.get("error", result.get("stderr", "Unknown error")),
            "duration_seconds": result["duration_seconds"],
        }, indent=2, ensure_ascii=False))]


def _build_diag_args(a: dict) -> List[str]:
    args = [
        "--data-dir", a["data_dir"],
        "--prep-dir", a["prep_dir"],
        "--stat-dir", a["stat_dir"],
        "--output-dir", a.get("output_dir", "outputs_diag"),
    ]
    if a.get("ml_dir"):
        args.extend(["--ml-dir", a["ml_dir"]])
    if a.get("skip_predictability"):
        args.append("--skip-predictability")
    return args


def _build_decision_args(a: dict) -> List[str]:
    args = [
        "--data-dir", a["data_dir"],
        "--prep-dir", a["prep_dir"],
        "--stat-dir", a["stat_dir"],
        "--output-dir", a.get("output_dir", "outputs_decision"),
    ]
    if a.get("ml_dir"):
        args.extend(["--ml-dir", a["ml_dir"]])
    if a.get("diag_dir"):
        args.extend(["--diag-dir", a["diag_dir"]])
    if a.get("streaming"):
        args.append("--streaming")
    if a.get("max_orders"):
        args.extend(["--max-orders", str(a["max_orders"])])
    return args


async def _handle_pipeline(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理 run_full_pipeline Tool（委托给 agent_orchestrator.py）。"""
    orchestrator = SKILLS_BASE / "agent_orchestrator.py"
    if not orchestrator.exists():
        return [TextContent(type="text", text=json.dumps({
            "status": "failed",
            "error": "agent_orchestrator.py not found. Please ensure it is in the skills/ directory.",
        }))]

    cmd = [
        sys.executable, str(orchestrator),
        "--data-dir", arguments["data_dir"],
        "--output-dir", arguments.get("output_dir", "outputs"),
    ]
    if arguments.get("skip_ml"):
        cmd.append("--skip-ml")
    if arguments.get("skip_diagnosis"):
        cmd.append("--skip-diagnosis")
    if arguments.get("model_version"):
        cmd.extend(["--model", arguments["model_version"]])
    if arguments.get("streaming"):
        cmd.append("--streaming")
    if arguments.get("max_orders"):
        cmd.extend(["--max-orders", str(arguments["max_orders"])])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode == 0:
        # 读取执行报告
        output_dir = arguments.get("output_dir", "outputs")
        report_path = Path(output_dir) / "pipeline_execution_report.json"
        report = {}
        if report_path.exists():
            with open(report_path) as f:
                report = json.load(f)

        # 读取工单摘要
        wo_path = Path(output_dir) / "output_decision" / "maintenance_work_orders.csv"
        work_orders_summary = _read_csv_summary(str(wo_path), max_rows=5) if wo_path.exists() else {}

        response = {
            "status": "success",
            "output_dir": output_dir,
            "execution_report": report,
            "work_orders": work_orders_summary,
        }
        return [TextContent(type="text", text=json.dumps(response, indent=2, ensure_ascii=False))]
    else:
        return [TextContent(type="text", text=json.dumps({
            "status": "failed",
            "error": result.stderr[-1000:] or result.stdout[-1000:],
        }, indent=2, ensure_ascii=False))]


# ==============================================================================
# Resource Definitions (知识检索封装为 MCP Resource)
# ==============================================================================

@server.list_resources()
async def handle_list_resources() -> List[Any]:
    """注册知识资源。"""
    from mcp.types import Resource

    return [
        Resource(
            uri="baseline://stats",
            name="Baseline Statistics",
            description="每台 CNC 设备的统计基线（μ, σ, Q1, Q3, IQR），含 baseline_quality 标记",
            mimeType="text/csv",
        ),
        Resource(
            uri="baseline://thresholds",
            name="Alert Threshold Configuration",
            description="告警阈值配置：Watch(1.5), Warning(2.0), Alarm(2.5)；成本风险 Medium(4500), High(5300)",
            mimeType="application/json",
        ),
        Resource(
            uri="failure://signatures",
            name="Failure Type Signatures",
            description="3 组故障签名：高电压型、热型、微弱型，含参数偏移量和可检测性评估",
            mimeType="text/csv",
        ),
        Resource(
            uri="failure://patterns",
            name="Anomaly Pattern Rules",
            description="4 种异常模式的判定条件、物理含义和证据强度计算规则",
            mimeType="application/json",
        ),
        Resource(
            uri="cost://matrix",
            name="Cost Risk Matrix",
            description="100 台设备的成本风险矩阵：故障率、单位成本、日产量、cost_at_risk、risk_tier",
            mimeType="text/csv",
        ),
        Resource(
            uri="knowledge://predictability",
            name="Predictability Limitation Report",
            description="5 维度可预测性分析结论：Youden's J=0.075, 70%故障在正常范围, 传感器缺口分析",
            mimeType="text/plain",
        ),
        Resource(
            uri="knowledge://sensor-recommendations",
            name="Sensor Upgrade Recommendations",
            description="传感器升级优先级：振动(收益最大)→声发射→电流特征分析",
            mimeType="application/json",
        ),
        Resource(
            uri="knowledge://decision-logic",
            name="Decision Engine Logic",
            description="4 层决策架构说明：融合权重、6 种动作类型、时间窗口、成本乘数",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """处理资源读取请求。"""
    resource_data = {
        "baseline://thresholds": json.dumps({
            "z_thresholds": {"watch": 1.5, "warning": 2.0, "alarm": 2.5},
            "cost_risk": {"medium": 4500, "high": 5300},
            "min_normal_samples": 6,
            "iqr_multiplier": 1.5,
            "params": ["Op.Voltage", "Op.Amperage", "Op.Temperature"],
            "excluded_params": ["Rotor Speed"],
        }, indent=2, ensure_ascii=False),

        "failure://patterns": json.dumps({
            "voltage_drift": {
                "physical_meaning": "PSU 退化、母线电压不稳定",
                "rule": "|z_V| > 2.0 AND |voltage_trend_slope| > 0.02",
                "evidence": "min(1.0, |z_V| / 4.0)",
            },
            "thermal_buildup": {
                "physical_meaning": "冷却系统问题、轴承摩擦",
                "rule": "|z_T| > 2.0 AND thermal_over_p95 >= 2",
                "evidence": "min(1.0, |z_T| / 4.0)",
            },
            "power_anomaly": {
                "physical_meaning": "负载不匹配、绕组退化",
                "rule": "|z_V| > 1.5 AND |z_A| > 1.5",
                "evidence": "min(1.0, (|z_V| + |z_A|) / 8.0)",
            },
            "combined_degradation": {
                "physical_meaning": "系统性劣化",
                "rule": ">= 2 params with |z| > 2.0",
                "evidence": "min(1.0, abnormal_count / 3.0)",
            },
        }, indent=2, ensure_ascii=False),

        "knowledge://predictability": (
            "PREDICTABILITY LIMITATION — EXECUTIVE SUMMARY\n"
            "=" * 50 + "\n\n"
            "After systematic analysis across 5 evidence dimensions, we conclude:\n\n"
            "The 4 monitoring parameters (Voltage, Amperage, Temperature, Rotor Speed)\n"
            "DO NOT contain sufficient information to support effective predictive maintenance.\n\n"
            "EVIDENCE:\n"
            "  1. Single-param max Youden's J = 0.075 (threshold for 'usable' = 0.30)\n"
            "  2. 70% of fault samples fall within normal parameter ranges\n"
            "  3. Parameter correlations unchanged between normal and fault states\n"
            "  4. All ML/DL models converge to trivial mean predictor (R² ~ 0)\n"
            "  5. Missing vibration/acoustic/current-signature sensors that carry 80%+ of diagnostic info\n\n"
            "RECOMMENDATION:\n"
            "  - Deploy risk-driven maintenance (cost + statistical baseline)\n"
            "  - Add vibration sensors (single highest-impact improvement)\n"
            "  - Extend monitoring period to capture long-term degradation\n"
            "  - Until sensor suite is upgraded, use z-score baseline (P=84%, FPR=20%)\n"
        ),

        "knowledge://sensor-recommendations": json.dumps({
            "priority": [
                {
                    "rank": 1,
                    "sensor": "Vibration",
                    "expected_impact": "Increase Youden's J from 0.075 to 0.40+",
                    "detects": "Bearing degradation, imbalance, looseness",
                    "rationale": "Vibration carries ~40% of CNC diagnostic information",
                },
                {
                    "rank": 2,
                    "sensor": "Acoustic Emission",
                    "expected_impact": "Detect early-stage crack propagation, lubrication failure",
                    "detects": "Crack initiation, lubrication breakdown",
                    "rationale": "Complementary to vibration — different frequency domain",
                },
                {
                    "rank": 3,
                    "sensor": "Current Signature Analysis",
                    "expected_impact": "Detect rotor bar degradation, winding faults",
                    "detects": "Rotor bar cracks, stator winding shorts",
                    "rationale": "Need waveform-level data (high-freq sampling), not RMS",
                },
            ],
        }, indent=2, ensure_ascii=False),

        "knowledge://decision-logic": json.dumps({
            "fusion_weights": {
                "stat_anomaly": 0.40,
                "ml_density": 0.25,
                "cost_risk": 0.25,
                "trend": 0.10,
            },
            "actions": [
                {"type": "immediate_shutdown", "trigger": "z_max >= 10.0", "window_days": 0},
                {"type": "preventive_repair", "trigger": "ALARM + (z_max >= 8.0 or high-cost)", "window_days": "1-3"},
                {"type": "schedule_inspection", "trigger": "ALARM (standard) or WARNING with pattern", "window_days": "3-7"},
                {"type": "increase_monitoring", "trigger": "WARNING (no pattern) or WATCH with pattern", "window_days": "7-14"},
                {"type": "routine_check", "trigger": "WATCH (normal pattern)", "window_days": 30},
                {"type": "no_action", "trigger": "NORMAL", "window_days": 30},
            ],
            "cost_multipliers": {
                "critical": {"threshold": 10000, "multiplier": 1.4},
                "high": {"threshold": 5000, "multiplier": 1.2},
                "low": {"threshold": "below_median", "multiplier": 0.8},
            },
            "savings_formula": "expected_savings = cost_at_risk * (emergency_multiplier - preventive_ratio) = cost_at_risk * 2.70",
        }, indent=2, ensure_ascii=False),
    }

    if uri in resource_data:
        return resource_data[uri]

    # 动态资源：从输出文件中读取
    if uri == "baseline://stats":
        # 查找最新的 baseline_stats.csv
        prep_output = SKILLS_BASE / "predictive-maintenance-data-prep" / "outputs_test"
        csv_path = prep_output / "baseline_stats.csv"
        if csv_path.exists():
            import pandas as pd
            df = pd.read_csv(csv_path)
            return df.head(20).to_csv(index=False)
        return "Baseline stats not available. Run data-prep first."

    if uri == "failure://signatures":
        prep_output = SKILLS_BASE / "predictive-maintenance-data-prep" / "outputs_test"
        csv_path = prep_output / "failure_signatures.csv"
        if csv_path.exists():
            import pandas as pd
            df = pd.read_csv(csv_path)
            return df.to_csv(index=False)
        return "Failure signatures not available. Run data-prep first."

    if uri == "cost://matrix":
        prep_output = SKILLS_BASE / "predictive-maintenance-data-prep" / "outputs_test"
        csv_path = prep_output / "cost_risk_matrix.csv"
        if csv_path.exists():
            import pandas as pd
            df = pd.read_csv(csv_path)
            return df.head(20).to_csv(index=False)
        return "Cost matrix not available. Run data-prep first."

    return f"Resource not found: {uri}"


# ==============================================================================
# Prompt Definitions (可选)
# ==============================================================================

@server.list_prompts()
async def handle_list_prompts() -> List[Any]:
    """注册快捷 Prompt 模板。"""
    from mcp.types import Prompt

    return [
        Prompt(
            name="analyze",
            description="分析指定数据目录的 CNC 设备状态",
            arguments=[
                {"name": "data_dir", "description": "原始 CSV 数据目录", "required": True},
            ],
        ),
        Prompt(
            name="diagnose",
            description="诊断特定设备的异常模式",
            arguments=[
                {"name": "data_dir", "description": "原始 CSV 数据目录", "required": True},
                {"name": "machine_id", "description": "设备 ID，如 CNC_067", "required": True},
            ],
        ),
        Prompt(
            name="report",
            description="生成维护报告摘要",
            arguments=[
                {"name": "output_dir", "description": "流水线输出目录", "required": True},
            ],
        ),
    ]


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: Dict[str, Any]) -> str:
    """处理 Prompt 请求。"""
    if name == "analyze":
        data_dir = arguments.get("data_dir", ".")
        return (
            f"请分析以下目录的 CNC 设备数据: {data_dir}\n\n"
            f"步骤:\n"
            f"1. 调用 run_full_pipeline 工具，参数 data_dir='{data_dir}'\n"
            f"2. 查看输出的 maintenance_work_orders.csv\n"
            f"3. 总结前 5 个高优先级工单\n"
            f"4. 报告告警分布（ALARM/WARNING/WATCH/NORMAL）\n"
            f"5. 如果已运行 diagnosis，报告主要异常模式分布\n"
        )

    if name == "diagnose":
        data_dir = arguments.get("data_dir", ".")
        machine_id = arguments.get("machine_id", "CNC_001")
        return (
            f"诊断设备 {machine_id} 的异常状态:\n\n"
            f"1. 先调用 run_full_pipeline 工具，参数 data_dir='{data_dir}'\n"
            f"2. 从 maintenance_decision_report.csv 查找 {machine_id}\n"
            f"3. 报告: 告警级别、风险评分、主要异常模式、推荐动作\n"
            f"4. 从 diagnosis_report.csv 获取详细诊断证据\n"
            f"5. 从 baseline://stats 资源获取该设备的基线参数\n"
        )

    if name == "report":
        output_dir = arguments.get("output_dir", "outputs")
        return (
            f"生成维护报告摘要:\n\n"
            f"1. 读取 {output_dir}/output_decision/maintenance_work_orders.csv\n"
            f"2. 读取 {output_dir}/output_decision/decision_summary.json\n"
            f"3. 读取 {output_dir}/pipeline_execution_report.json\n"
            f"4. 汇总:\n"
            f"   - 总设备数、告警分布\n"
            f"   - Top 5 优先工单（设备ID、紧急度、成本风险、建议动作）\n"
            f"   - 动作类型分布\n"
            f"   - 流水线总执行时间\n"
            f"5. 引用 knowledge://predictability 资源提供传感器限制说明\n"
        )

    return f"Unknown prompt: {name}"


# ==============================================================================
# Server Entry Point
# ==============================================================================

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationCapabilities(
                sampling=None,
                experimental=None,
                roots=None,
            ),
            notification_options=NotificationOptions(
                tools_changed=True,
                resources_changed=True,
                prompts_changed=True,
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## 第 3 章：通过 MCP Client 调用

### 3.1 Claude Desktop / Claude Code 自动调用

在 `claude_desktop_config.json` 或 `~/.claude/settings.json` 中配置 MCP Server 后，Claude 会自动发现 Tools、Resources、Prompts：

```json
{
  "mcpServers": {
    "predictive-maintenance": {
      "command": "python",
      "args": ["C:/Users/yuzzz/Desktop/苗圃杯/数据探索基线确定/skills/mcp_server.py"],
      "env": {
        "DATA_DIR": "C:/Users/yuzzz/Desktop/苗圃杯/数据探索基线确定/原始数据集",
        "OUTPUT_BASE": "C:/Users/yuzzz/Desktop/苗圃杯/数据探索基线确定/skills/outputs"
      }
    }
  }
}
```

配置后，用户直接用自然语言交互：

> 用户: 分析 CNC 设备数据，生成维护工单

Claude 会自动:
1. 调用 `run_full_pipeline(data_dir="...")` Tool
2. 读取 `maintenance_work_orders.csv`
3. 用自然语言回复 Top 5 工单

> 用户: CNC_067 的电压状态怎么样？

Claude 会自动:
1. 读取 `baseline://stats` 资源获取基线
2. 读取 `failure://patterns` 资源获取判定规则
3. 如果已运行流水线，从 alert_summary 查找该设备

### 3.2 编程式 MCP Client

如果需要在自己的应用中通过 MCP 协议调用，参考以下 Python Client 代码：

```python
#!/usr/bin/env python3
"""
MCP Client Example — 编程式调用预测性维护 MCP Server
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_predictive_maintenance(data_dir: str):
    """
    通过 MCP Client 调用预测性维护流水线。

    流程:
      1. 建立与 MCP Server 的 stdio 连接
      2. 列出可用 Tools
      3. 调用 run_full_pipeline
      4. 读取知识资源（阈值、故障签名）
      5. 打印结果
    """
    server_params = StdioServerParameters(
        command="python",
        args=["path/to/skills/mcp_server.py"],
        env={
            "DATA_DIR": data_dir,
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化
            await session.initialize()

            # 1. 列出可用 Tools
            tools = await session.list_tools()
            print(f"Available tools: {len(tools.tools)}")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:80]}...")

            # 2. 列出可用 Resources
            resources = await session.list_resources()
            print(f"\nAvailable resources: {len(resources.resources)}")
            for res in resources.resources:
                print(f"  - {res.uri}: {res.name}")

            # 3. 读取知识资源（不需要运行流水线即可获取）
            print("\n--- Reading Knowledge Resources ---")
            for uri in [
                "baseline://thresholds",
                "knowledge://predictability",
                "knowledge://decision-logic",
            ]:
                content = await session.read_resource(uri)
                print(f"\n{uri}:")
                print(content[:500])

            # 4. 运行全流程
            print("\n--- Running Full Pipeline ---")
            result = await session.call_tool(
                "run_full_pipeline",
                arguments={
                    "data_dir": data_dir,
                    "output_dir": "outputs_mcp_client",
                    "skip_ml": False,
                },
            )
            print("Pipeline result:")
            print(json.dumps(json.loads(result.content[0].text), indent=2, ensure_ascii=False))

            # 5. 读取最终工单
            print("\n--- Work Orders ---")
            import pandas as pd
            wo_path = "outputs_mcp_client/output_decision/maintenance_work_orders.csv"
            try:
                df = pd.read_csv(wo_path)
                print(df.to_string())
            except FileNotFoundError:
                print(f"Work orders not found at {wo_path}")

    print("\nDone.")


async def quick_check():
    """
    快速检查：不运行推理，仅读取已有的知识和基线。
    适用于 Agent 在决策前查询系统能力边界。
    """
    server_params = StdioServerParameters(
        command="python",
        args=["path/to/skills/mcp_server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 读取关键知识
            thresholds = await session.read_resource("baseline://thresholds")
            patterns = await session.read_resource("failure://patterns")
            predictability = await session.read_resource("knowledge://predictability")
            sensors = await session.read_resource("knowledge://sensor-recommendations")

            return {
                "thresholds": json.loads(thresholds),
                "patterns": json.loads(patterns),
                "predictability_summary": predictability,
                "sensor_recommendations": json.loads(sensors),
            }


if __name__ == "__main__":
    asyncio.run(run_predictive_maintenance("/path/to/raw_csvs"))
```

### 3.3 典型调用流程对比

| 场景 | 传统方式 | MCP 方式 |
|---|---|---|
| 运行全流程 | `python agent_orchestrator.py --data-dir ...` | `session.call_tool("run_full_pipeline", {...})` |
| 查询阈值配置 | 打开 CONFIG 字典 | `session.read_resource("baseline://thresholds")` |
| 了解系统能力边界 | 阅读 predictibility 报告 | `session.read_resource("knowledge://predictability")` |
| 诊断单台设备 | 从 CSV 中 grep | 通过 Prompt `diagnose` 获取结构化分析 |
| Agent 自动决策 | 需人工编写编排逻辑 | Claude 自动发现 Tool，自主决策调用顺序 |

---

## 第 4 章：Tool、Resource、Prompt 设计原则

### 4.1 Tool 设计原则

- **粒度适中**：单步 Tool（`run_data_prep`）+ 全流程 Tool（`run_full_pipeline`）兼具灵活性和便捷性
- **幂等性**：同一个 Tool 用相同参数多次调用应产出相同结果（输出覆盖原目录）
- **超时保护**：单次 Tool 调用 600s 上限，ML 训练可能接近此限制
- **错误透传**：Tool 失败时返回结构化错误（status + error + duration），而非崩溃
- **输出截断**：stdout 限制 3000 字符，避免上下文溢出；详细结果通过文件路径引用

### 4.2 Resource 设计原则

- **静态资源**：在代码中硬编码，始终可读（阈值、规则、决策逻辑）
- **动态资源**：从最新输出文件读取，反映当前系统状态（基线、成本矩阵）
- **URI 命名**：使用 `scheme://category/name` 格式（`baseline://stats`、`knowledge://predictability`）
- **知识外置**：将传感器限制、故障签名等核心知识封装为 Resource，Agent 无需运行推理即可获取系统能力边界

### 4.3 Prompt 设计原则

- **模板化**：定义常见任务的步骤模板，Agent 填充参数后执行
- **引用 Tool**：Prompt 中明确引用需要调用的 Tool 名称
- **引用 Resource**：Prompt 中引用知识资源 URI，Agent 自动读取

---

## 第 5 章：部署与运维

### 5.1 启动 MCP Server

```bash
# 直接启动（通过 stdio 与 Client 通信）
python mcp_server.py

# 或通过 mcp CLI 工具
mcp run mcp_server.py
```

### 5.2 验证 Server 正常

```bash
# 使用 mcp CLI 验证
mcp list-tools --server python --args "mcp_server.py"
mcp list-resources --server python --args "mcp_server.py"
```

### 5.3 日志与监控

MCP Server 通过 `server.request_logging()` 向 Client 发送日志。Client 端（Claude）会记录 Tool 调用耗时、成功/失败状态。

关键监控指标：
- Tool 调用成功率（按 skill 分）
- 平均执行时长
- ML 降级频率（反映环境依赖可用性）

### 5.4 安全注意事项

- MCP Server 通过 subprocess 执行 Python 脚本——确保 `data_dir` 参数不会导致路径遍历攻击
- 生产环境建议添加输入校验：`data_dir` 必须在允许的目录白名单内
- `OUTPUT_BASE` 应限制在安全目录，避免覆盖系统文件

---

## 文件对照表

| 文件 | 作用 |
|---|---|
| `mcp_server.py` | MCP Server 主程序（Tool + Resource + Prompt） |
| `mcp_config.json` | MCP Server 注册配置 |
| `agent_orchestrator.py` | Agent 编排器（被 `run_full_pipeline` Tool 调用） |
| `predictive-maintenance-*/scripts/run.py` | 5 个技能的独立入口（被单步 Tool 调用） |
| `predictive-maintenance-*/SKILL.md` | 技能说明文档（Agent 可通过 Resource 或文件读取） |
| `mcp-adapter-guide.md` | 本文档 |
| `predictive-maintenance-skill-system-v2.md` | 系统开发与使用指南 v2 |
