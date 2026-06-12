#!/usr/bin/env python3
"""
MCP Server: Predictive Maintenance — Agent-MCP 预测性维护系统
===============================================================
7 个 MCP Tool，Claude 自主规划调用，对应赛题全部要求:

  explain_predictability_limit()  → 可预测性限制说明（传感器瓶颈 + 升级建议）
  prepare_data()                  → 【数据整合探索】基线构建 + z-score + 成本矩阵
  run_stat_analysis()             → 【基线分析】统计推理（z-score, T², 告警）
  run_ml_analysis()               → 【告警模型】ML 推理（XGBoost v1 / MTNN v2）
  run_diagnosis()                 → 异常模式诊断（4 种模式 + 5 维度分析）
  generate_decision()             → ★【预测性维护计划】多信号融合 → 工单生成
  run_predictive_maintenance()    → 一键全流程（自动降级）

依赖关系: data → stat + ml (并行) → diagnosis → decision

启动:
    python mcp_server.py
    (stdio transport)
"""

import sys, os, subprocess, time, json
from pathlib import Path
from typing import Optional
import pandas as pd

SKILLS_BASE = Path(__file__).resolve().parent
if str(SKILLS_BASE) not in sys.path:
    sys.path.insert(0, str(SKILLS_BASE))

from mcp.server.fastmcp import FastMCP
from agent_orchestrator import PredictiveMaintenanceAgent, PipelineResult

mcp = FastMCP("predictive-maintenance")

# V3 model outputs — static explainability data
V3_OUTPUTS = SKILLS_BASE.parent / "预测性维护模型_v3" / "outputs"


# ══════════════════════════════════════════════════════════════════════
# Tool 0: Explainability（P1 — 工业 AI 审计入口）
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def explain_predictability_limit() -> dict:
    """返回 5 维度可预测性限制分析 + 根因 + 传感器升级建议。

    基于 v3 系统方案的 5 维度证据链，解释当前 4 参数系统的性能天花板、
    为什么所有 ML 模型收敛到平凡预测器、以及该装什么新传感器突破瓶颈。
    纯读数据，无须运行流水线。
    """
    import pandas as pd

    # ── Dimension 1: Single-parameter discriminability ──
    dim1 = pd.read_csv(V3_OUTPUTS / "dim1_single_param_discriminability.csv")
    youden_j = {}
    fault_overlap = {}
    for _, row in dim1.iterrows():
        param = row["parameter"]
        youden_j[param] = {
            "youden_j": float(row["youden_j"]),
            "interpretation": row["youden_interpretation"],
            "cohens_d": float(row["cohens_d"]),
        }
        overlap = row["fault_in_normal_pct"]
        if isinstance(overlap, str):
            overlap = float(overlap.replace("%", ""))
        fault_overlap[param] = {
            "fault_in_normal_pct": float(overlap),
            "normal_p99_range": row["normal_p99_range"],
        }

    max_youden = max(v["youden_j"] for v in youden_j.values())

    # ── Dimension 2: Parameter coupling stability ──
    dim2 = pd.read_csv(V3_OUTPUTS / "dim2_param_coupling_stability.csv")
    correlation_stability = {}
    for _, row in dim2.iterrows():
        pair = row["parameter_pair"]
        correlation_stability[pair] = {
            "normal_correlation": float(row["normal_correlation"]),
            "fault_correlation": float(row["fault_correlation"]),
            "correlation_change": float(row["correlation_change"]),
            "significant_change": bool(row["significant_change"]),
            "fisher_z_p_value": float(row["fisher_z_p_value"]),
        }

    # ── Dimension 3: Non-progressive failure onset ──
    dim3 = pd.read_csv(V3_OUTPUTS / "dim3_fault_non_progressive.csv")
    non_progressive = {}
    for _, row in dim3.iterrows():
        pf = row["pre_fault_in_normal_range_pct"]
        if isinstance(pf, str):
            pf = float(pf.replace("%", ""))
        non_progressive[row["parameter"]] = {
            "pre_fault_in_normal_pct": float(pf),
            "pre_post_norm_by_std": float(row["pre_post_norm_by_std"]),
            "n_transitions": int(row["n_transitions"]),
        }

    # ── Dimension 4: Model convergence to trivial predictor ──
    dim4 = pd.read_csv(V3_OUTPUTS / "dim4_model_convergence.csv")
    model_convergence = []
    for _, row in dim4.iterrows():
        model_convergence.append({
            "variant": row["variant"],
            "r2": float(row["r2"]),
            "binary_auc": float(row["binary_auc"]),
            "is_mean_predictor": bool(row["is_essentially_mean_predictor"]),
        })

    # ── Dimension 5: Sensor gap analysis ──
    dim5 = pd.read_csv(V3_OUTPUTS / "dim5_sensor_gap_analysis.csv")
    recommended_sensors = []
    for _, row in dim5.iterrows():
        recommended_sensors.append({
            "sensor": row["sensor"],
            "expected_youden_j": row["expected_youden_j"],
            "expected_auc_gain": row["expected_auc_gain"],
            "mechanism": row["mechanism"],
            "cost_per_machine": row["cost_per_machine"],
            "feasibility": row["feasibility"],
        })

    # ── Performance ceiling ──
    performance_ceiling = 0.60  # theoretical max with current params

    # ── Root cause diagnosis ──
    root_causes = [
        {
            "id": "R1",
            "cause": "insufficient_sensor_discriminability",
            "evidence": f"Max Youden's J across 4 params = {max_youden:.3f} (threshold for usable signal = 0.30)",
            "severity": "critical",
            "fix": "Add vibration and acoustic emission sensors",
        },
        {
            "id": "R2",
            "cause": "fault_embedded_in_normal_manifold",
            "evidence": "96-98% of fault samples fall within normal parameter ranges; fault states are indistinguishable from normal by any single parameter",
            "severity": "critical",
            "fix": "Need waveform-level data (FFT, cepstrum) instead of RMS aggregates",
        },
        {
            "id": "R3",
            "cause": "lack_of_coupling_structure",
            "evidence": "V-A, V-T, A-T correlations unchanged between normal and fault states (Fisher's z: all p > 0.01)",
            "severity": "high",
            "fix": "Current parameters measure independent dimensions; need cross-domain sensors",
        },
        {
            "id": "R4",
            "cause": "non_progressive_failure_onset",
            "evidence": "79-80% of pre-fault samples fall within normal range; no gradual degradation signal before fault onset",
            "severity": "critical",
            "fix": "Increase sampling frequency; monitor trend over hours/days rather than snapshots",
        },
        {
            "id": "R5",
            "cause": "model_trivial_convergence",
            "evidence": f"All 3 model variants converge to trivial mean predictor (R² ≈ 0, AUC ≈ 0.5). True mean density ≈ 0.74, predicted ≈ 0.73",
            "severity": "confirmatory",
            "fix": "With current features, no ML model can exceed baseline; confirms sensor gap",
        },
    ]

    return {
        "conclusion": "4 monitoring parameters DO NOT support effective predictive maintenance.",
        "performance_ceiling": performance_ceiling,
        "current_max_youden_j": max_youden,
        "youden_j": youden_j,
        "fault_overlap": fault_overlap,
        "correlation_stability": correlation_stability,
        "non_progressive_onset": non_progressive,
        "model_convergence": model_convergence,
        "root_causes": root_causes,
        "recommended_new_sensors": recommended_sensors,
        "what_works_today": {
            "approach": "cost-risk-driven maintenance (statistical baseline)",
            "detection_rate": "P=84%, FPR=20% (z-score with threshold 1.5)",
            "best_single_action": "Install vibration sensors — single highest-impact improvement",
        },
    }


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

# ── Resilience configuration ──
MCP_MAX_RETRIES = 3
MCP_TIMEOUT_SECONDS = 300


def _run_script(skill_dir_name: str, args: list,
                max_retries: int = None, timeout: int = None) -> dict:
    """Run a skill's scripts/run.py via subprocess with retry + timeout.

    Retries up to max_retries times on failure (exit code != 0 or timeout).
    Returns structured result with retry_count and degraded status.
    """
    if max_retries is None:
        max_retries = MCP_MAX_RETRIES
    if timeout is None:
        timeout = MCP_TIMEOUT_SECONDS

    script = SKILLS_BASE / skill_dir_name / "scripts" / "run.py"
    if not script.exists():
        return {"success": False, "error": f"Script not found: {script}",
                "retry_count": 0, "status": "SCRIPT_MISSING"}

    cmd = [sys.executable, str(script)] + args
    last_result = None

    for attempt in range(1, max_retries + 1):
        start = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout)
            duration = round(time.time() - start, 2)
            result = {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "duration_seconds": duration,
                "retry_count": attempt - 1,
                "stdout_tail": _tail(proc.stdout, 20),
                "stderr_tail": proc.stderr.strip()[-500:] if proc.stderr else "",
            }
            if proc.returncode == 0:
                result["status"] = "OK"
                return result
            last_result = result
        except subprocess.TimeoutExpired:
            duration = round(time.time() - start, 2)
            last_result = {
                "success": False,
                "error": f"Timeout after {timeout}s",
                "duration_seconds": duration,
                "retry_count": attempt - 1,
                "status": "TIMEOUT",
            }

    # All retries exhausted
    if last_result:
        last_result["retry_count"] = max_retries
        last_result["status"] = last_result.get("status", "EXHAUSTED")
        return last_result
    return {"success": False, "error": "Unknown failure", "retry_count": max_retries,
            "status": "EXHAUSTED"}


def _tail(text: str, n: int) -> str:
    lines = text.strip().split("\n")
    return "\n".join(lines[-n:])


def _read_csv_preview(path: str, max_rows: int = 10) -> list:
    """Read top N rows of a CSV as list of dicts. Returns [] if file missing."""
    if not Path(path).exists():
        return []
    import pandas as pd
    df = pd.read_csv(path)
    return df.head(max_rows).to_dict(orient="records")


def _find_output_dir(args: list) -> str:
    """Extract output-dir from subprocess argument list."""
    for i, a in enumerate(args):
        if a in ("--output-dir",) and i + 1 < len(args):
            return args[i + 1]
        if a == "--output-dir" and i + 1 < len(args):
            return args[i + 1]
    # For data-prep: positional args [data_dir, output_dir]
    if len(args) >= 2 and not args[1].startswith("-"):
        return args[1]
    return ""


# ══════════════════════════════════════════════════════════════════════
# Tool 1: Data Preparation
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def prepare_data(
    data_dir: str,
    output_dir: str = "./outputs/output_data_prep",
) -> dict:
    """【Step 1】加载 4 个原始 CSV，为每台 CNC 设备构建统计基线（μ, σ），计算 z-score 和成本风险矩阵。

    输入: 包含 4 个 CSV 的目录
    输出: z_scores.csv, cost_risk_matrix.csv, baseline_stats.csv, failure_signatures.csv 等
    这是流水线的第一步，必须最先调用。
    """
    args = [data_dir, output_dir]
    result = _run_script("predictive-maintenance-data-prep", args)

    summary = {}
    if result["success"]:
        od = output_dir
        if Path(od, "summary_report.txt").exists():
            summary["report"] = (Path(od) / "summary_report.txt").read_text(encoding="utf-8")[:2000]
        summary["z_scores_preview"] = _read_csv_preview(os.path.join(od, "z_scores.csv"), 5)
        summary["cost_risk_preview"] = _read_csv_preview(os.path.join(od, "cost_risk_matrix.csv"), 5)
        summary["output_files"] = [f.name for f in Path(od).iterdir() if f.is_file()]

    return {
        "tool": "prepare_data",
        "status": "success" if result["success"] else "failed",
        "output_dir": output_dir,
        "duration_seconds": result["duration_seconds"],
        "summary": summary,
        "stdout_tail": result["stdout_tail"],
        "error": result.get("error", "") or result.get("stderr_tail", ""),
        "next_step": "Run run_stat_analysis and run_ml_analysis in parallel, using this output_dir as prep_dir.",
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 2: Statistical Inference
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def run_stat_analysis(
    data_dir: str,
    prep_dir: str,
    output_dir: str = "./outputs/output_stat_inference",
) -> dict:
    """【Step 2a】统计推理：评估 z-score 基线性能，计算 Hotelling T² 多变量统计量，分析故障类型签名，汇总每台设备告警状态。

    可与 run_ml_analysis 并行调用。
    依赖: prepare_data 完成后调用。
    输出: alert_summary.csv, t2_results.csv, failure_signature_analysis.csv
    """
    args = [
        "--data-dir", data_dir,
        "--prep-dir", prep_dir,
        "--output-dir", output_dir,
    ]
    result = _run_script("predictive-maintenance-stat-inference", args)

    summary = {}
    if result["success"]:
        od = output_dir
        summary["alert_summary_preview"] = _read_csv_preview(os.path.join(od, "alert_summary.csv"), 5)
        summary["output_files"] = [f.name for f in Path(od).iterdir() if f.is_file()]

    return {
        "tool": "run_stat_analysis",
        "status": "success" if result["success"] else "failed",
        "output_dir": output_dir,
        "duration_seconds": result["duration_seconds"],
        "summary": summary,
        "stdout_tail": result["stdout_tail"],
        "error": result.get("error", "") or result.get("stderr_tail", ""),
        "next_step": "stat 和 ml 都完成后，调用 run_diagnosis。",
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 3: ML Inference
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def run_ml_analysis(
    data_dir: str,
    prep_dir: str,
    output_dir: str = "./outputs/output_ml_inference",
    model: str = "v1",
) -> dict:
    """【Step 2b】ML 推理：训练 XGBoost（v1）或多任务神经网络（v2），生成故障密度预测。

    可与 run_stat_analysis 并行调用。ML 信号在决策融合中权重 0.25。
    若环境无 xgboost/torch，此步可跳过。
    依赖: prepare_data 完成后调用。
    输出: prediction_report.csv
    """
    args = [
        "--data-dir", data_dir,
        "--prep-dir", prep_dir,
        "--output-dir", output_dir,
        "--model", model,
    ]
    result = _run_script("predictive-maintenance-ml-inference", args)

    summary = {}
    if result["success"]:
        od = output_dir
        summary["prediction_preview"] = _read_csv_preview(os.path.join(od, "prediction_report.csv"), 5)
        summary["output_files"] = [f.name for f in Path(od).iterdir() if f.is_file()]

    return {
        "tool": "run_ml_analysis",
        "status": "success" if result["success"] else "failed",
        "output_dir": output_dir,
        "duration_seconds": result["duration_seconds"],
        "summary": summary,
        "stdout_tail": result["stdout_tail"],
        "error": result.get("error", "") or result.get("stderr_tail", ""),
        "skip_hint": "If this step fails (no xgboost/torch), the decision engine will fall back to stat-only mode.",
        "next_step": "stat 和 ml 都完成后，调用 run_diagnosis。",
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 4: Diagnosis
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def run_diagnosis(
    data_dir: str,
    prep_dir: str,
    stat_dir: str,
    ml_dir: Optional[str] = None,
    output_dir: str = "./outputs/output_diagnosis",
    skip_predictability: bool = True,
) -> dict:
    """【Step 3】诊断：识别 4 种异常模式（voltage_drift, thermal_buildup, power_anomaly, combined_degradation），
    运行 5 维度可预测性分析（可跳过以提速）。

    依赖: stat 和 ml 推理完成后调用。
    输出: diagnosis_report.csv
    """
    args = [
        "--data-dir", data_dir,
        "--prep-dir", prep_dir,
        "--stat-dir", stat_dir,
        "--output-dir", output_dir,
    ]
    if ml_dir:
        args.extend(["--ml-dir", ml_dir])
    if skip_predictability:
        args.append("--skip-predictability")

    result = _run_script("predictive-maintenance-diagnosis", args)

    summary = {}
    if result["success"]:
        od = output_dir
        summary["diagnosis_preview"] = _read_csv_preview(os.path.join(od, "diagnosis_report.csv"), 10)
        summary["output_files"] = [f.name for f in Path(od).iterdir() if f.is_file()]

    return {
        "tool": "run_diagnosis",
        "status": "success" if result["success"] else "failed",
        "output_dir": output_dir,
        "duration_seconds": result["duration_seconds"],
        "summary": summary,
        "stdout_tail": result["stdout_tail"],
        "error": result.get("error", "") or result.get("stderr_tail", ""),
        "next_step": "最后一步，调用 generate_decision 生成工单。",
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 5: Decision Engine
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_decision(
    data_dir: str,
    prep_dir: str,
    stat_dir: str,
    ml_dir: Optional[str] = None,
    diag_dir: Optional[str] = None,
    output_dir: str = "./outputs/output_decision",
    streaming: bool = False,
    max_orders: int = 20,
    strategy: str = "production_efficiency",
) -> dict:
    """【Step 4 - 最终】决策引擎：4 层决策架构 + 5 层工业扩展 → 工单 + 工业维护计划。

    多信号融合权重: stat_anomaly=0.40, ml_density=0.25, cost_risk=0.25, trend=0.10。
    依赖: 前序步骤全部完成后调用。
    输出: maintenance_work_orders.csv, industrial_maintenance_plan.csv（22 列工业级工单）,
          spare_parts_plan.csv, technician_schedule.csv, downtime_schedule.csv,
          strategy_comparison.csv, maintenance_acceptance_rules.json
    strategy: cost_efficiency | production_efficiency | quality_first
    """
    args = [
        "--data-dir", data_dir,
        "--prep-dir", prep_dir,
        "--stat-dir", stat_dir,
        "--output-dir", output_dir,
    ]
    if ml_dir:
        args.extend(["--ml-dir", ml_dir])
    if diag_dir:
        args.extend(["--diag-dir", diag_dir])
    if streaming:
        args.append("--streaming")
    args.extend(["--max-orders", str(max_orders)])
    args.extend(["--strategy", strategy])

    result = _run_script("predictive-maintenance-decision", args)

    work_orders = []
    total_count = 0
    industrial_count = 0
    report_text = ""
    if result["success"]:
        od = output_dir
        wo_path = os.path.join(od, "maintenance_work_orders.csv")
        work_orders = _read_csv_preview(wo_path, 10)
        if Path(wo_path).exists():
            total_count = len(pd.read_csv(wo_path))
        ip_path = Path(od) / "industrial_maintenance_plan.csv"
        if ip_path.exists():
            industrial_count = len(pd.read_csv(ip_path))
        rp = Path(od) / "maintenance_report.txt"
        if rp.exists():
            report_text = rp.read_text(encoding="utf-8")[:3000]

    return {
        "tool": "generate_decision",
        "status": "success" if result["success"] else "failed",
        "output_dir": output_dir,
        "duration_seconds": result["duration_seconds"],
        "work_orders_count": total_count,
        "industrial_orders_count": industrial_count,
        "work_orders": work_orders,
        "report": report_text,
        "stdout_tail": result["stdout_tail"],
        "error": result.get("error", "") or result.get("stderr_tail", ""),
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 8: RUL Prediction — Remaining Useful Life
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_rul_prediction(
    equipment_id: Optional[str] = None,
    stat_dir: str = "./outputs/output_stat_inference",
) -> dict:
    """查询设备的剩余使用寿命(RUL)预测。

    基于健康分退化轨迹外推，返回各设备的RUL天数、置信区间、退化速率、
    健康分投影等。RUL不可用时自动标注原因（无退化信号/数据不足）。

    equipment_id: 设备ID（如 CNC_042），不传则返回全部设备的RUL概览
    stat_dir: stat-inference 输出目录，需包含 rul_degradation.csv 和 rul_summary.json
    """
    import json as _json

    rul_path = os.path.join(stat_dir, "rul_degradation.csv")
    summary_path = os.path.join(stat_dir, "rul_summary.json")

    if not os.path.exists(rul_path):
        return {
            "tool": "get_rul_prediction",
            "status": "unavailable",
            "error": f"rul_degradation.csv not found in {stat_dir}. "
                     f"Run stat-inference without --skip-rul first.",
        }

    rul_df = pd.read_csv(rul_path)
    summary = {}
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = _json.load(f)

    if equipment_id:
        # Single machine query
        match = rul_df[rul_df["Equipment.Id"] == equipment_id]
        if len(match) == 0:
            return {
                "tool": "get_rul_prediction",
                "status": "not_found",
                "equipment_id": equipment_id,
                "error": f"Equipment {equipment_id} not found in RUL data",
            }
        row = match.iloc[0]
        return {
            "tool": "get_rul_prediction",
            "status": "success",
            "equipment_id": equipment_id,
            "rul": {
                "rul_steps": None if pd.isna(row["rul_steps"]) else float(row["rul_steps"]),
                "rul_hours": None if pd.isna(row["rul_hours"]) else float(row["rul_hours"]),
                "rul_ci_lower_hours": float(row["rul_ci_lower_hours"]),
                "rul_ci_upper_hours": float(row["rul_ci_upper_hours"]),
                "health_score_current": float(row["health_score_current"]),
                "health_score_projected_7d": None if pd.isna(row["health_score_projected_7d"]) else float(row["health_score_projected_7d"]),
                "health_score_projected_14d": None if pd.isna(row["health_score_projected_14d"]) else float(row["health_score_projected_14d"]),
                "degradation_rate_per_day": float(row["degradation_rate_per_day"]),
                "model_type": str(row["model_type"]),
                "r_squared": float(row["r_squared"]),
                "trend": str(row["trend"]),
                "status": str(row["status"]),
                "status_reason": str(row["status_reason"]),
                "warnings": str(row["warnings"]) if pd.notna(row["warnings"]) else "",
            },
        }

    # All machines overview
    n_available = int((rul_df["status"] == "ok").sum())
    n_no_degradation = int((rul_df["status"] == "no_degradation").sum())
    n_insufficient = int((rul_df["status"] == "insufficient_data").sum())

    # Top 10 most urgent (shortest RUL)
    available = rul_df[rul_df["status"] == "ok"].head(10)
    urgent_list = []
    for _, row in available.iterrows():
        urgent_list.append({
            "equipment_id": str(row["Equipment.Id"]),
            "rul_hours": None if pd.isna(row["rul_hours"]) else round(float(row["rul_hours"]), 1),
            "health_score_current": float(row["health_score_current"]),
            "trend": str(row["trend"]),
            "degradation_rate_per_day": float(row["degradation_rate_per_day"]),
        })

    return {
        "tool": "get_rul_prediction",
        "status": "success",
        "summary": summary,
        "overview": {
            "total_machines": len(rul_df),
            "rul_available": n_available,
            "no_degradation_signal": n_no_degradation,
            "insufficient_data": n_insufficient,
            "coverage_rate": round(n_available / len(rul_df), 3) if len(rul_df) > 0 else 0,
        },
        "most_urgent": urgent_list,
    }


# ══════════════════════════════════════════════════════════════════════
# Tool 0: 全流程一键运行（降级路径 + 便利入口）
# ══════════════════════════════════════════════════════════════════════

@mcp.tool()
def run_predictive_maintenance(
    data_dir: str,
    output_dir: str = "./outputs",
    skip_ml: bool = False,
    skip_diagnosis: bool = False,
    model: str = "v1",
    streaming: bool = False,
    max_orders: int = 20,
    strategy: str = "production_efficiency",
) -> dict:
    """【全流程一键运行】自动按 DAG 编排: data-prep → stat+ml(并行) → diagnosis → decision。

    内置降级: ML 不可用时自动走 stat-only 路径。
    推荐快速体验时使用此 Tool；需要精细控制时使用上述 5 个独立 Tool。
    strategy: cost_efficiency | production_efficiency | quality_first
    """
    agent = PredictiveMaintenanceAgent(
        data_dir=data_dir,
        output_base=output_dir,
        skip_ml=skip_ml,
        skip_diagnosis=skip_diagnosis,
        model_version=model,
        streaming=streaming,
        max_orders=max_orders,
        strategy=strategy,
    )
    result: PipelineResult = agent.run()

    wo_preview = []
    industrial_preview = []
    wo_path = Path(result.final_output_dir) / "maintenance_work_orders.csv"
    if wo_path.exists():
        import pandas as pd
        wo_df = pd.read_csv(wo_path)
        wo_preview = wo_df.head(10).to_dict(orient="records")
    ip_path = Path(result.final_output_dir) / "industrial_maintenance_plan.csv"
    if ip_path.exists():
        import pandas as pd
        ip_df = pd.read_csv(ip_path)
        industrial_preview = ip_df.head(5).to_dict(orient="records")

    return {
        "status": result.summary,
        "work_orders_count": result.work_orders_count,
        "work_orders_preview": wo_preview,
        "industrial_plan_preview": industrial_preview,
        "output_dir": result.final_output_dir,
        "step_statuses": {r.skill_name: r.status.value for r in result.steps},
        "total_duration_seconds": result.total_duration,
    }


# ══════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
