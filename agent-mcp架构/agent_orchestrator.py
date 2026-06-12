#!/usr/bin/env python3
"""
预测性维护 Agent 编排器 (Agent Orchestrator)
==============================================
完整的端到端调度脚本：按 DAG 依次调用 5 个技能，
自动处理降级、错误恢复、进度追踪。

用法:
    python agent_orchestrator.py --data-dir <原始CSV目录> --output-dir <输出目录>
    python agent_orchestrator.py --data-dir <原始CSV目录> --skip-ml --skip-diagnosis
    python agent_orchestrator.py --data-dir <原始CSV目录> --model v2 --streaming

依赖: Python 3.8+, pandas, numpy, scipy, scikit-learn
可选: xgboost (v1), pytorch (v2)
"""

import sys, os, json, argparse, subprocess, time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


# ==============================================================================
# Configuration
# ==============================================================================

SKILLS_BASE = Path(__file__).resolve().parent.parent  # project root

SKILLS = {
    "data_prep": {
        "dir": SKILLS_BASE / "skills" / "predictive-maintenance-data-prep",
        "script": "scripts/run.py",
        "required": True,
        "depends_on": [],
    },
    "stat_inference": {
        "dir": SKILLS_BASE / "skills" / "predictive-maintenance-stat-inference",
        "script": "scripts/run.py",
        "required": True,
        "depends_on": ["data_prep"],
    },
    "ml_inference": {
        "dir": SKILLS_BASE / "skills" / "predictive-maintenance-ml-inference",
        "script": "scripts/run.py",
        "required": False,
        "depends_on": ["data_prep"],
    },
    "diagnosis": {
        "dir": SKILLS_BASE / "skills" / "predictive-maintenance-diagnosis",
        "script": "scripts/run.py",
        "required": False,
        "depends_on": ["data_prep", "stat_inference", "ml_inference"],
    },
    "decision": {
        "dir": SKILLS_BASE / "skills" / "predictive-maintenance-decision",
        "script": "scripts/run.py",
        "required": True,
        "depends_on": ["data_prep", "stat_inference", "ml_inference", "diagnosis"],
    },
}

REQUIRED_FILES = [
    "MACHINE_LOG_DATA._2025.csv",
    "MACHINE_SUMMARY_DATA._2025.csv",
    "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv",
    "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv",
]


# ==============================================================================
# Data Structures
# ==============================================================================

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DegradationMode(Enum):
    """Pipeline degradation: automatic fallback on component failure."""
    FULL = "FULL"                    # ML + Stat + Rule (all components)
    STAT_ONLY = "STAT_ONLY"          # Stat + Rule (ML unavailable)
    RULE_ONLY = "RULE_ONLY"          # Threshold-based only (stat unavailable)
    EMERGENCY = "EMERGENCY"          # Bare-minimum work orders from raw data


@dataclass
class StepResult:
    skill_name: str
    status: StepStatus
    output_dir: str = ""
    duration_seconds: float = 0.0
    error_message: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass
class PipelineResult:
    steps: List[StepResult] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    total_duration: float = 0.0
    final_output_dir: str = ""
    work_orders_count: int = 0
    summary: dict = field(default_factory=dict)


# ==============================================================================
# Agent Orchestrator
# ==============================================================================

class PredictiveMaintenanceAgent:
    """
    预测性维护 Agent —— 编排 5 个技能的 DAG 执行。

    DAG:
      data_prep ──┬── stat_inference ──┬── diagnosis ── decision
                   └── ml_inference ───┘

    Features:
      - 输入校验（4 个 CSV 必须存在）
      - stat-inference 与 ml-inference 并行调度
      - ML 不可用时自动降级
      - 进度追踪与错误恢复
    """

    def __init__(self, data_dir: str, output_base: str,
                 skip_ml: bool = False, skip_diagnosis: bool = False,
                 model_version: str = "v1", streaming: bool = False,
                 max_orders: int = 20,
                 max_budget: float = 0,
                 strategy: str = "production_efficiency",
                 dashboard_data: str = ""):
        self.data_dir = Path(data_dir).resolve()
        self.output_base = Path(output_base).resolve()
        self.skip_ml = skip_ml
        self.skip_diagnosis = skip_diagnosis
        self.model_version = model_version
        self.streaming = streaming
        self.max_orders = max_orders
        self.max_budget = max_budget
        self.strategy = strategy
        self.dashboard_data = Path(dashboard_data) if dashboard_data else None
        self.enable_shap = False  # Will be set by main()
        self.degradation_mode = DegradationMode.FULL  # Start optimistic

        self.output_dirs: Dict[str, Path] = {}
        self.results: List[StepResult] = []

        self._validate_input()

    def _validate_input(self):
        """检查原始数据目录是否包含全部 4 个 CSV 文件。"""
        print("=" * 60)
        print("[VALIDATE] Checking input data directory...")
        print(f"  Path: {self.data_dir}")
        missing = []
        for fname in REQUIRED_FILES:
            fpath = self.data_dir / fname
            exists = fpath.exists()
            print(f"  {'[OK]' if exists else '[MISSING]'} {fname}")
            if not exists:
                missing.append(fname)

        if missing:
            raise FileNotFoundError(
                f"Missing {len(missing)} required file(s): {missing}\n"
                f"Please ensure all 4 CSV files are in: {self.data_dir}"
            )
        print("  All required files present.\n")

    def _run_skill(self, skill_key: str) -> StepResult:
        """执行单个技能的 run.py 脚本。"""
        skill = SKILLS[skill_key]
        skill_dir = skill["dir"]
        script_path = skill_dir / skill["script"]

        if not script_path.exists():
            return StepResult(
                skill_name=skill_key,
                status=StepStatus.FAILED,
                error_message=f"Script not found: {script_path}"
            )

        output_dir = self.output_base / f"output_{skill_key}"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dirs[skill_key] = output_dir

        # 构建命令行参数 — 适配各技能的实际 CLI 接口
        cmd = [sys.executable, str(script_path)]

        if skill_key == "data_prep":
    # 统一使用命名参数（与其它技能保持一致）
            cmd.extend(["--data-dir", str(self.data_dir), "--output-dir", str(output_dir)])
        else:
            # 其他技能使用 --data-dir / --output-dir
            cmd.extend(["--data-dir", str(self.data_dir)])
            cmd.extend(["--output-dir", str(output_dir)])

            if "data_prep" in skill["depends_on"] and "data_prep" in self.output_dirs:
                cmd.extend(["--prep-dir", str(self.output_dirs["data_prep"])])
            if "stat_inference" in skill["depends_on"] and "stat_inference" in self.output_dirs:
                cmd.extend(["--stat-dir", str(self.output_dirs["stat_inference"])])
            if "ml_inference" in skill["depends_on"] and "ml_inference" in self.output_dirs:
                cmd.extend(["--ml-dir", str(self.output_dirs["ml_inference"])])
            if "diagnosis" in skill["depends_on"] and "diagnosis" in self.output_dirs:
                cmd.extend(["--diag-dir", str(self.output_dirs["diagnosis"])])

        if skill_key == "ml_inference":
            cmd.extend(["--model", self.model_version])
        if skill_key == "decision":
            if self.streaming:
                cmd.append("--streaming")
            cmd.extend(["--max-orders", str(self.max_orders)])
            cmd.extend(["--max-budget", str(self.max_budget)])
            cmd.extend(["--strategy", self.strategy])
        if skill_key == "diagnosis":
            cmd.append("--skip-predictability")

        print(f"[RUN] {skill_key}")
        print(f"  CMD: {' '.join(cmd)}")

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(skill_dir),
                capture_output=True,
                text=True,
                timeout=600,
            )
            duration = time.time() - start

            # 提取输出尾部
            stdout_lines = result.stdout.strip().split("\n")
            stderr_lines = result.stderr.strip().split("\n")

            step = StepResult(
                skill_name=skill_key,
                status=StepStatus.SUCCESS if result.returncode == 0 else StepStatus.FAILED,
                output_dir=str(output_dir),
                duration_seconds=round(duration, 1),
                stdout_tail="\n".join(stdout_lines[-10:]),
                stderr_tail="\n".join(stderr_lines[-10:]),
                error_message="" if result.returncode == 0 else f"Exit code: {result.returncode}",
            )

            if result.returncode == 0:
                for line in stdout_lines[-6:]:
                    if line.strip():
                        print(f"  | {line}")
                print(f"  [OK] {skill_key} completed in {duration:.1f}s")
            else:
                print(f"  [FAIL] {skill_key} failed (exit {result.returncode})")
                for line in stderr_lines[-5:]:
                    if line.strip():
                        print(f"  STDERR: {line}")

            return step

        except subprocess.TimeoutExpired:
            duration = time.time() - start
            print(f"  [TIMEOUT] {skill_key} exceeded 600s limit")
            return StepResult(
                skill_name=skill_key,
                status=StepStatus.FAILED,
                output_dir=str(output_dir),
                duration_seconds=round(duration, 1),
                error_message="Timeout after 600 seconds",
            )

    def run(self) -> PipelineResult:
        """
        按 DAG 拓扑顺序执行流水线:
          data_prep → stat + ml (并行) → diagnosis → decision
        """
        pipeline_start = time.time()
        result = PipelineResult(
            start_time=datetime.now().isoformat(),
        )

        print("=" * 60)
        print("Predictive Maintenance Agent — Pipeline Orchestrator")
        print("=" * 60)
        print(f"Data dir:     {self.data_dir}")
        print(f"Output base:  {self.output_base}")
        print(f"Skip ML:      {self.skip_ml}")
        print(f"Skip Diag:    {self.skip_diagnosis}")
        print(f"Model:        {self.model_version}")
        print(f"Streaming:    {self.streaming}")
        print(f"Strategy:     {self.strategy}")
        print()

        # ── Phase 1: Data Preparation ──
        print("-" * 40)
        print("Phase 1/4: Data Preparation")
        print("-" * 40)
        step = self._run_skill("data_prep")
        self.results.append(step)
        if step.status != StepStatus.SUCCESS:
            # DEGRADE → EMERGENCY: no baselines, no stats — raw sensor flags only
            self.degradation_mode = DegradationMode.EMERGENCY
            print(f"[DEGRADE] data-prep failed → {self.degradation_mode.value}")
            self._run_emergency()
            self._write_degradation_status()
            result.steps = self.results
            result.final_output_dir = str(self.output_dirs.get("decision", ""))
            result.summary = self._build_summary(result)
            return result

        # ── Phase 2: Inference (parallel: stat + ml) ──
        print("\n" + "-" * 40)
        print("Phase 2/4: Inference (parallel)")
        print("-" * 40)

        parallel_tasks = ["stat_inference"]
        if self.skip_ml:
            self.degradation_mode = DegradationMode.STAT_ONLY
        elif not self._check_ml_deps():
            self.degradation_mode = DegradationMode.STAT_ONLY
            print(f"[FALLBACK] ML unavailable → {self.degradation_mode.value}")
            step = StepResult(
                skill_name="ml_inference",
                status=StepStatus.SKIPPED,
                error_message="ML dependencies not installed (xgboost/torch)",
            )
            self.results.append(step)
        else:
            parallel_tasks.append("ml_inference")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._run_skill, task): task
                for task in parallel_tasks
            }
            for future in as_completed(futures):
                step = future.result()
                self.results.append(step)

        stat_step = next((r for r in self.results if r.skill_name == "stat_inference"), None)
        if not stat_step or stat_step.status != StepStatus.SUCCESS:
            # DEGRADE → RULE_ONLY: stat unavailable, use raw sensor thresholds
            self.degradation_mode = DegradationMode.RULE_ONLY
            print(f"[DEGRADE] stat-inference failed → {self.degradation_mode.value}")
            self._run_rule_only()
            self._write_degradation_status()
            result.steps = self.results
            result.final_output_dir = str(self.output_dirs.get("decision", ""))
            result.summary = self._build_summary(result)
            return result

        # ── Phase 3: Diagnosis ──
        if not self.skip_diagnosis:
            print("\n" + "-" * 40)
            print("Phase 3/4: Diagnosis")
            print("-" * 40)
            step = self._run_skill("diagnosis")
            self.results.append(step)

        # ── Phase 4: Decision ──
        print("\n" + "-" * 40)
        print("Phase 4/4: Decision Engine")
        print("-" * 40)
        step = self._run_skill("decision")
        self.results.append(step)

        if step.status != StepStatus.SUCCESS:
            # DEGRADE → RULE_ONLY: decision engine failed, fallback to thresholds
            self.degradation_mode = DegradationMode.RULE_ONLY
            print(f"[DEGRADE] decision failed → {self.degradation_mode.value}")
            self._run_rule_only()
            self._write_degradation_status()
            result.steps = self.results
            result.final_output_dir = str(self.output_dirs.get("decision", ""))
            result.summary = self._build_summary(result)
            return result

        # ── Finalize ──
        result.steps = self.results
        result.end_time = datetime.now().isoformat()
        result.total_duration = round(time.time() - pipeline_start, 1)
        result.final_output_dir = str(self.output_dirs.get("decision", ""))

        wo_path = Path(result.final_output_dir) / "maintenance_work_orders.csv"
        if wo_path.exists():
            try:
                import pandas as pd
                wo_df = pd.read_csv(wo_path)
                result.work_orders_count = len(wo_df)
            except Exception:
                result.work_orders_count = -1

        # ── Phase 5: SHAP Post-Process (optional, explainability layer) ──
        if self.enable_shap:
            self._run_shap_postprocess()

        # ── Sync dashboard data ──
        self._write_degradation_status()
        if self.dashboard_data and self.dashboard_data.exists():
            self._sync_dashboard_data()

        result.summary = self._build_summary(result)
        self._print_summary(result)
        return result

    def _run_shap_postprocess(self):
        """Run SHAP post-processing directly (not via subprocess)."""
        print("\n" + "-" * 40)
        print("Phase 5/5: SHAP Alert Attribution (post-process)")
        print("-" * 40)

        # Add diagnosis scripts to path for direct import
        diag_scripts = str(SKILLS["diagnosis"]["dir"] / "scripts")
        if diag_scripts not in sys.path:
            sys.path.insert(0, diag_scripts)

        try:
            from shap_postprocess import run_shap_postprocess

            prep_dir = str(self.output_dirs.get("data_prep", self.output_base / "output_data_prep"))
            stat_dir = str(self.output_dirs.get("stat_inference", self.output_base / "output_stat_inference"))
            decision_dir = str(self.output_dirs.get("decision", self.output_base / "output_decision"))

            run_shap_postprocess(
                prep_dir=prep_dir,
                stat_dir=stat_dir,
                decision_dir=decision_dir,
                strategy=self.strategy,
                output_dir=decision_dir,
            )

            step = StepResult(
                skill_name="shap_attribution",
                status=StepStatus.SUCCESS,
                output_dir=decision_dir,
                duration_seconds=0.0,
            )
        except Exception as e:
            print(f"  [WARN] SHAP post-process failed: {e}")
            import traceback
            traceback.print_exc()
            step = StepResult(
                skill_name="shap_attribution",
                status=StepStatus.FAILED,
                error_message=str(e),
            )

        self.results.append(step)

    def _run_rule_only(self):
        """RULE_ONLY mode: generate work orders from raw sensor thresholds.
        No z-scores, no ML, no cost matrix — only voltage/current/temperature
        threshold checks against per-machine baselines from raw log data.
        """
        print("\n" + "!" * 40)
        print("[DEGRADE] RULE_ONLY — threshold-based maintenance")
        print("!" * 40)
        import pandas as pd

        log_path = self.data_dir / "MACHINE_LOG_DATA._2025.csv"
        df = pd.read_csv(log_path)
        machines = sorted(df["Equipment.Id"].unique())

        orders = []
        for mid in machines:
            mdata = df[df["Equipment.Id"] == mid]
            recent = mdata.tail(5)  # last 5 readings

            # Simple thresholds aligned with project's known ranges
            v_mean = recent["Op.Voltage"].mean()
            a_mean = recent["Op.Amperage"].mean()
            t_mean = recent["Op.Temperature"].mean()

            # Threshold checks (matching failure signature ranges from EDA)
            flags = []
            urgency = 0
            if v_mean > 210 or v_mean < 150:
                flags.append("电压超出安全范围")
                urgency += 30
            if a_mean > 35:
                flags.append("电流偏高")
                urgency += 25
            if t_mean > 95:
                flags.append("温度过高")
                urgency += 25
            if t_mean > 80 and a_mean > 30:
                flags.append("温度-电流联合偏高")
                urgency += 10

            if urgency >= 25:
                action = "preventive_repair" if urgency >= 55 else "schedule_inspection"
                orders.append({
                    "priority": 0,
                    "machine_id": mid,
                    "alert_level": "ALARM" if urgency >= 55 else "WARNING",
                    "action_type": action,
                    "cost_at_risk": 0.0,
                    "urgency_score": min(urgency, 100),
                    "recommended_window_days": 1 if urgency >= 55 else 3,
                    "expected_savings": 0.0,
                    "maintenance_suggestion": "RULE_ONLY: " + "; ".join(flags),
                })

        # Sort and cap
        orders.sort(key=lambda o: o["urgency_score"], reverse=True)
        orders = orders[:self.max_orders]
        for i, o in enumerate(orders):
            o["priority"] = i + 1

        decision_dir = self.output_base / "output_decision"
        decision_dir.mkdir(parents=True, exist_ok=True)
        self.output_dirs["decision"] = decision_dir

        wo_path = decision_dir / "maintenance_work_orders.csv"
        pd.DataFrame(orders).to_csv(wo_path, index=False, encoding="utf-8")
        print(f"  Rule-only work orders: {len(orders)} → {wo_path}")
        return decision_dir

    def _run_emergency(self):
        """EMERGENCY mode: absolute minimum — flag machines with extreme readings.
        No baselines, no thresholds — just flag top-N machines by raw sensor
        deviation from population mean.
        """
        print("\n" + "!" * 40)
        print("[DEGRADE] EMERGENCY — bare-minimum work orders")
        print("!" * 40)
        import pandas as pd

        log_path = self.data_dir / "MACHINE_LOG_DATA._2025.csv"
        df = pd.read_csv(log_path)

        orders = []
        for mid, grp in df.groupby("Equipment.Id"):
            recent = grp.tail(5)
            v_std = recent["Op.Voltage"].std()
            a_std = recent["Op.Amperage"].std()
            t_std = recent["Op.Temperature"].std()
            # Simple volatility score — higher = more unstable
            volatility = v_std / 200 + a_std / 30 + t_std / 90
            if volatility > 0.15:
                orders.append({
                    "priority": 0,
                    "machine_id": mid,
                    "alert_level": "WARNING",
                    "action_type": "increase_monitoring",
                    "cost_at_risk": 0.0,
                    "urgency_score": min(int(volatility * 100), 100),
                    "recommended_window_days": 7,
                    "expected_savings": 0.0,
                    "maintenance_suggestion": "EMERGENCY: 设备传感器波动异常，建议人工复查",
                })

        orders.sort(key=lambda o: o["urgency_score"], reverse=True)
        orders = orders[:self.max_orders]
        for i, o in enumerate(orders):
            o["priority"] = i + 1

        decision_dir = self.output_base / "output_decision"
        decision_dir.mkdir(parents=True, exist_ok=True)
        self.output_dirs["decision"] = decision_dir

        em_path = decision_dir / "emergency_work_orders.csv"
        pd.DataFrame(orders).to_csv(em_path, index=False, encoding="utf-8")
        print(f"  Emergency work orders: {len(orders)} → {em_path}")
        return decision_dir

    def _write_degradation_status(self):
        """Write degradation mode to a small JSON file for dashboard consumption."""
        status_path = self.output_base / "output_decision" / "degradation_status.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        status = {
            "mode": self.degradation_mode.value,
            "label": {
                "FULL": "全功能模式 (ML+统计+规则)",
                "STAT_ONLY": "统计降级模式 (统计+规则)",
                "RULE_ONLY": "规则降级模式 (阈值判定)",
                "EMERGENCY": "应急模式 (基础告警)",
            }.get(self.degradation_mode.value, self.degradation_mode.value),
            "components": {
                "ml_available": self.degradation_mode in (DegradationMode.FULL,),
                "stat_available": self.degradation_mode in (DegradationMode.FULL, DegradationMode.STAT_ONLY),
                "rule_available": True,
            },
        }
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        # Also sync to dashboard data if configured
        if self.dashboard_data and self.dashboard_data.exists():
            import shutil
            shutil.copy2(str(status_path),
                         str(self.dashboard_data / "degradation_status.json"))

    def _sync_dashboard_data(self):
        """Copy industrial plan CSVs from decision/stat/data-prep output to dashboard data dir."""
        import shutil

        decision_dir = self.output_dirs.get("decision")
        stat_dir = self.output_dirs.get("stat_inference")
        prep_dir = self.output_dirs.get("data_prep")

        # Files from decision output
        decision_files = [
            "industrial_maintenance_plan.csv",
            "technician_schedule.csv",
            "spare_parts_plan.csv",
            "strategy_comparison.csv",
            "downtime_schedule.csv",
            "optimization_comparison.csv",
            "maintenance_schedule_optimized.csv",
            "scheduling_comparison.json",
            "inventory_policy_optimized.csv",
            "pareto_frontier.json",
            "maintenance_decision_report.csv",
            "maintenance_acceptance_rules.json",
            "sensor_upgrade_plan.csv",
            "sensor_roi_analysis.csv",
            "sensor_phase_summary.csv",
            "shap_dashboard.json",
            "degradation_status.json",
        ]

        # Files from stat-inference output
        stat_files = [
            "quality_cost_chain.csv",
            "alert_summary.csv",
            "equipment_health_score.csv",
            "stat_inference_summary.json",
            "rul_degradation.csv",
            "rul_summary.json",
            "health_score_timeseries.csv",
        ]

        # Backtest files (in stat-inference output subdirectory)
        backtest_files = [
            "backtest/backtest_summary.json",
            "backtest/backtest_lead_time_summary.csv",
            "backtest/backtest_by_fault_group.csv",
            "backtest/backtest_walk_forward.csv",
            "backtest/backtest_point_in_time.csv",
            "backtest/backtest_point_in_time_summary.csv",
            "backtest/backtest_events_Warning.csv",
            "backtest/backtest_lead_time_distribution.png",
            "backtest/backtest_walk_forward.png",
        ]

        # Files from data-prep output (baseline CSVs for dashboard sections 1-2)
        prep_files = [
            "z_scores.csv",
            "cost_risk_matrix.csv",
            "failure_signatures.csv",
            "variance_decomposition.csv",
            "hotelling_t2.csv",
            "machine_clusters.csv",
            "baseline_stats.csv",
        ]

        # Dashboard name mappings (source → dashboard filename)
        renames = {
            "failure_signatures.csv": "failure_sig.csv",
            "cost_risk_matrix.csv": "cost_risk.csv",
            "hotelling_t2.csv": "t2_results.csv",
            "maintenance_work_orders.csv": "work_orders.csv",
            "variance_decomposition.csv": "variance_decomp.csv",
        }

        copied = 0
        for src_dir, file_list in [
            (decision_dir, decision_files),
            (stat_dir, stat_files),
            (prep_dir, prep_files),
        ]:
            if not src_dir:
                continue
            for fname in file_list:
                src = Path(src_dir) / fname
                if not src.exists():
                    continue
                dst_name = renames.get(fname, fname)
                dst = self.dashboard_data / dst_name
                shutil.copy2(src, dst)
                copied += 1

        # Sync backtest files (from stat_dir/backtest/ subdirectory)
        if stat_dir:
            bt_dir = Path(stat_dir) / "backtest"
            if bt_dir.exists():
                for fname in backtest_files:
                    # Strip "backtest/" prefix for source path
                    rel_name = fname.replace("backtest/", "")
                    src = bt_dir / rel_name
                    if not src.exists():
                        continue
                    # Keep "backtest_" prefix in dashboard data dir
                    dst = self.dashboard_data / rel_name
                    shutil.copy2(src, dst)
                    copied += 1

        if copied:
            print(f"\n[DASHBOARD] Synced {copied} files to {self.dashboard_data}")

    def _check_ml_deps(self) -> bool:
        """检查 ML 依赖是否可用。"""
        try:
            import numpy
            try:
                import xgboost
                return True
            except ImportError:
                pass
            try:
                import torch
                return True
            except ImportError:
                pass
            return False
        except ImportError:
            return False

    def _build_summary(self, result: PipelineResult) -> dict:
        statuses = {r.skill_name: r.status.value for r in result.steps}
        durations = {r.skill_name: r.duration_seconds for r in result.steps}

        decision_summary = {}
        ds_path = Path(result.final_output_dir) / "decision_summary.json"
        if ds_path.exists():
            try:
                with open(ds_path, encoding="utf-8") as f:
                    decision_summary = json.load(f)
            except Exception:
                pass

        return {
            "pipeline_status": "complete" if all(
                r.status in (StepStatus.SUCCESS, StepStatus.SKIPPED)
                for r in result.steps
            ) else "partial",
            "degradation_mode": self.degradation_mode.value,
            "step_statuses": statuses,
            "step_durations_seconds": durations,
            "total_duration_seconds": result.total_duration,
            "work_orders_count": result.work_orders_count,
            "decision_summary": decision_summary,
        }

    def _print_summary(self, result: PipelineResult):
        print("\n")
        print("=" * 60)
        print("PIPELINE EXECUTION REPORT")
        print("=" * 60)
        print(f"Start:  {result.start_time}")
        print(f"End:    {result.end_time}")
        print(f"Total:  {result.total_duration:.1f}s")
        print()

        icons = {
            StepStatus.SUCCESS: "[OK]",
            StepStatus.FAILED: "[FAIL]",
            StepStatus.SKIPPED: "[SKIP]",
            StepStatus.PENDING: "[...]",
            StepStatus.RUNNING: "[RUN]",
        }
        for r in result.steps:
            icon = icons.get(r.status, "[??]")
            print(f"  {icon} {r.skill_name:<25s} {r.duration_seconds:>6.1f}s  -> {r.output_dir}")
            if r.error_message:
                print(f"       Error: {r.error_message}")

        print()
        print(f"Work orders generated: {result.work_orders_count}")
        print(f"Final output: {result.final_output_dir}")
        print("=" * 60)


# ==============================================================================
# CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance Agent Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 完整 5 技能流水线
  python agent_orchestrator.py --data-dir ../原始数据集 --output-dir outputs_full

  # 降级路径（跳过 ML 和 diagnosis，3 步产出工单）
  python agent_orchestrator.py --data-dir ../原始数据集 --skip-ml --skip-diagnosis

  # v2 神经网络 + 流式模式
  python agent_orchestrator.py --data-dir ../原始数据集 --model v2 --streaming
        """,
    )
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing 4 raw CSV files")
    parser.add_argument("--output-dir", default="outputs",
                        help="Base directory for all outputs")
    parser.add_argument("--skip-ml", action="store_true",
                        help="Skip ML inference (use stat-only path)")
    parser.add_argument("--skip-diagnosis", action="store_true",
                        help="Skip anomaly diagnosis step")
    parser.add_argument("--model", choices=["v1", "v2"], default="v1",
                        help="ML model version (default: v1 XGBoost)")
    parser.add_argument("--streaming", action="store_true",
                        help="Enable continuous confirmation in decision engine")
    parser.add_argument("--max-orders", type=int, default=20,
                        help="Max work orders per cycle (default: 20)")
    parser.add_argument("--max-budget", type=float, default=0,
                        help="Max preventive maintenance budget in USD (0=unlimited)")
    parser.add_argument("--strategy", default="production_efficiency",
                        choices=["cost_efficiency", "production_efficiency", "quality_first"],
                        help="Maintenance strategy (default: production_efficiency)")
    parser.add_argument("--dashboard-data", default="",
                        help="Path to web-dashboard/data/ for auto-sync of industrial CSVs")
    parser.add_argument("--shap", action="store_true",
                        help="Enable SHAP-based alert attribution post-processing")
    args = parser.parse_args()

    agent = PredictiveMaintenanceAgent(
        data_dir=args.data_dir,
        output_base=args.output_dir,
        skip_ml=args.skip_ml,
        skip_diagnosis=args.skip_diagnosis,
        model_version=args.model,
        streaming=args.streaming,
        max_orders=args.max_orders,
        max_budget=args.max_budget,
        strategy=args.strategy,
        dashboard_data=args.dashboard_data,
    )
    agent.enable_shap = args.shap

    result = agent.run()

    # 保存执行报告
    report_path = Path(args.output_dir) / "pipeline_execution_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result.summary, f, indent=2, ensure_ascii=False)
    print(f"\nExecution report saved to: {report_path}")

    if result.summary.get("pipeline_status") == "complete":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
