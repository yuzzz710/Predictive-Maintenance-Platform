#!/usr/bin/env python3
"""
时序回测验证器 (Temporal Backtest Validator)
=============================================
三层时序回测体系，验证预测性维护方案在历史数据中的实际表现。

Layer 1 — 点级回测 (Point-in-Time):
  逐时间步展开混淆矩阵，生成时序热力图和滚动F1曲线。

Layer 2 — 事件级回测 (Event-Based):  ★ 核心
  以故障发作(Fault Onset)为锚点，计算预警提前量分布和漏报率。

Layer 3 — 步进回测 (Walk-Forward):
  Expanding window walk-forward validation，模拟系统上线后逐步积累数据。

输入: z_scores.csv (来自 data-prep) + MACHINE_LOG_DATA._2025.csv (原始数据)
输出: 4 个 CSV + 1 个 JSON + 2 张 PNG 图表

Author : Predictive Maintenance Team
Date   : 2026-06-01
"""

import os
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

import warnings
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════

CONFIG = {
    # Alert level numeric mapping (higher = more severe)
    "alert_levels": {
        "Normal": 0,
        "Watch": 1,
        "Warning": 2,
        "Alarm": 3,
    },
    # Fault onset: require at least this many consecutive normal steps before a fault
    "min_normal_before_onset": 2,
    # Lookback window: how many steps before fault onset to search for alerts
    "lookback_window": 5,
    # Walk-forward: minimum training steps before first test fold
    "min_train_steps": 10,
    # Walk-forward: number of steps in each test window
    "test_steps": 1,
    # RUL max for piecewise-linear labeling (steps beyond this are clipped)
    "rul_max_steps": 15,
    # Time interval per step (minutes)
    "minutes_per_step": 14,
    # Alert thresholds to evaluate
    "thresholds": ["Watch", "Warning", "Alarm"],
}

# Chart styling — matches existing project matplotlib conventions
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial"],
    "font.size": 8, "axes.titlesize": 10, "axes.labelsize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "figure.dpi": 150, "savefig.dpi": 150, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
})

COLORS = {
    "steel": "#517E9C", "brick": "#C2685A", "sage": "#5F8B6F",
    "amber": "#C8945F", "slate": "#6B7B8D", "green": "#3fb950",
    "yellow": "#f0a030", "orange": "#f0883e", "red": "#f04444",
}


# ══════════════════════════════════════════════════════════════════════════
# Data Loading
# ══════════════════════════════════════════════════════════════════════════

def load_backtest_data(data_dir: str, prep_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load z-scores and raw log data for backtesting."""
    z_path = os.path.join(prep_dir, "z_scores.csv")
    if not os.path.exists(z_path):
        raise FileNotFoundError(
            f"z_scores.csv not found in {prep_dir}. Run data-prep first."
        )
    df_z = pd.read_csv(z_path)
    df_z["Date"] = pd.to_datetime(df_z["Date"])
    df_z = df_z.sort_values(["Equipment.Id", "Date"]).reset_index(drop=True)
    # Add per-machine time_step
    df_z["time_step"] = df_z.groupby("Equipment.Id").cumcount()

    log_path = os.path.join(data_dir, "MACHINE_LOG_DATA._2025.csv")
    df_log = pd.read_csv(log_path)
    df_log["Date"] = pd.to_datetime(df_log["Date"])
    df_log = df_log.sort_values(["Equipment.Id", "Date"]).reset_index(drop=True)
    df_log["time_step"] = df_log.groupby("Equipment.Id").cumcount()

    return df_z, df_log


# ══════════════════════════════════════════════════════════════════════════
# Helper Utilities
# ══════════════════════════════════════════════════════════════════════════

def _alert_to_numeric(alert_series: pd.Series) -> pd.Series:
    """Convert alert level strings to numeric values."""
    mapping = CONFIG["alert_levels"]
    return alert_series.map(mapping).fillna(0).astype(int)


def _alert_threshold_numeric(threshold_name: str) -> int:
    """Get numeric value for an alert threshold name."""
    return CONFIG["alert_levels"].get(threshold_name, 0)


def _is_fault(series: pd.Series) -> pd.Series:
    """Check if Failure.Equipment.Type > 0."""
    return (series > 0).astype(int)


# ══════════════════════════════════════════════════════════════════════════
# Layer 1: Point-in-Time Backtest
# ══════════════════════════════════════════════════════════════════════════

def point_in_time_backtest(df_z: pd.DataFrame) -> Dict:
    """
    逐时间步计算混淆矩阵元素。

    对每个时间步 t（跨所有设备），按告警阈值判定预测正/负类，
    与实际故障标签对比，计算 Precision/Recall/F1/FPR。

    Args:
        df_z: z_scores DataFrame，必须含 time_step, alert_level,
              Failure.Equipment.Type 列

    Returns:
        dict with keys:
          - per_step: DataFrame，每步×每阈值的完整指标
          - summary: 各阈值聚合统计
    """
    df = df_z.copy()
    df["actual_fault"] = _is_fault(df["Failure.Equipment.Type"])
    max_step = int(df["time_step"].max())
    thresholds = CONFIG["thresholds"]

    all_rows = []
    for t in range(max_step + 1):
        subset = df[df["time_step"] == t]
        if len(subset) == 0:
            continue
        y_true = subset["actual_fault"].values
        n_machines = len(subset)
        fault_rate = float(y_true.mean())

        for thresh in thresholds:
            thresh_num = _alert_threshold_numeric(thresh)
            alert_num = _alert_to_numeric(subset["alert_level"]).values
            y_pred = (alert_num >= thresh_num).astype(int)

            tp = int(((y_true == 1) & (y_pred == 1)).sum())
            fp = int(((y_true == 0) & (y_pred == 1)).sum())
            tn = int(((y_true == 0) & (y_pred == 0)).sum())
            fn = int(((y_true == 1) & (y_pred == 0)).sum())

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)
                  if (precision + recall) > 0 else 0.0)
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

            all_rows.append({
                "time_step": t,
                "threshold": thresh,
                "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "fpr": round(fpr, 4),
                "n_machines": n_machines,
                "fault_rate": round(fault_rate, 4),
            })

    per_step = pd.DataFrame(all_rows)

    # Compute 5-step rolling F1 for each threshold
    rolling_rows = []
    for thresh in thresholds:
        sub = per_step[per_step["threshold"] == thresh].sort_values("time_step")
        sub = sub.copy()
        sub["rolling_f1"] = sub["f1"].rolling(window=5, min_periods=1).mean()
        rolling_rows.append(sub)
    per_step = pd.concat(rolling_rows, ignore_index=True)

    # Aggregate summary per threshold
    summary_rows = []
    for thresh in thresholds:
        sub = per_step[per_step["threshold"] == thresh]
        total_tp = sub["tp"].sum()
        total_fp = sub["fp"].sum()
        total_fn = sub["fn"].sum()
        total_tn = sub["tn"].sum()
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)
        fpr = total_fp / (total_fp + total_tn) if (total_fp + total_tn) > 0 else 0.0
        summary_rows.append({
            "threshold": thresh,
            "total_tp": int(total_tp), "total_fp": int(total_fp),
            "total_fn": int(total_fn), "total_tn": int(total_tn),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "fpr": round(fpr, 4),
            "mean_rolling_f1": round(float(sub["rolling_f1"].mean()), 4),
        })

    return {
        "per_step": per_step,
        "summary": pd.DataFrame(summary_rows),
    }


# ══════════════════════════════════════════════════════════════════════════
# Layer 2: Event-Based Backtest  ★ 核心
# ══════════════════════════════════════════════════════════════════════════

def _detect_fault_onsets(df_z: pd.DataFrame) -> List[Dict]:
    """
    检测故障发作事件。

    故障发作定义: min_normal_before 个连续正常步之后的第一个故障步。
    "正常步" = Failure.Equipment.Type == 0。

    返回事件列表，每个事件含 machine_id, onset_step, onset_date, fault_type。
    """
    min_normal = CONFIG["min_normal_before_onset"]
    events = []

    for mid, grp in df_z.groupby("Equipment.Id"):
        grp = grp.sort_values("time_step").reset_index(drop=True)
        types = grp["Failure.Equipment.Type"].values
        is_fault_arr = (types > 0).astype(int)
        n = len(types)

        # 用差分找正常→故障的转换点
        if n < 2:
            continue
        transitions = np.diff(is_fault_arr)
        onset_indices = np.where(transitions == 1)[0] + 1  # +1 因为 diff 少一个元素

        for idx in onset_indices:
            # 检查前面是否有 min_normal 个连续正常步
            if idx >= min_normal:
                pre_window = types[idx - min_normal:idx]
                if np.all(pre_window == 0):
                    events.append({
                        "machine_id": str(mid),
                        "onset_step": int(grp.iloc[idx]["time_step"]),
                        "onset_date": str(grp.iloc[idx]["Date"]),
                        "fault_type": int(grp.iloc[idx]["Failure.Equipment.Type"]),
                        "pre_normal_count": int(min_normal),
                    })

    return events


def event_based_backtest(
    df_z: pd.DataFrame,
    alert_threshold: str = "Warning",
    lookback_window: int = None,
) -> Dict:
    """
    以故障发作事件为锚点，计算预警提前量分布。

    对每个故障发作事件，回溯 lookback_window 步，寻找首次告警触发。
    若告警在故障发作前触发 → 计算 lead_time（步数）；
    若回溯窗口内无告警 → 标记为漏报(missed)。

    Args:
        df_z: z_scores DataFrame
        alert_threshold: "Watch" | "Warning" | "Alarm"
        lookback_window: 故障发作前多少步内寻找告警（默认 CONFIG）

    Returns:
        dict with:
          - lead_times_steps: 检出事件的提前量列表(步数)
          - lead_times_minutes: 检出事件的提前量列表(分钟)
          - missed_events: 漏报事件列表
          - avg_lead_time_steps: 平均提前量(步)
          - avg_lead_time_minutes: 平均提前量(分钟)
          - median_lead_time_minutes: 中位提前量(分钟)
          - miss_rate: 漏报率
          - detection_rate: 检出率
          - total_events: 总故障发作事件数
          - detected_events: 检出事件数
          - missed_events_count: 漏报事件数
          - event_details: 每个事件一行的 DataFrame
    """
    if lookback_window is None:
        lookback_window = CONFIG["lookback_window"]

    events = _detect_fault_onsets(df_z)
    thresh_num = _alert_threshold_numeric(alert_threshold)

    lead_times = []
    missed_events = []
    event_rows = []

    for event in events:
        mid = event["machine_id"]
        onset_step = event["onset_step"]

        # 取故障发作前 lookback_window 步的数据
        pre_onset = df_z[
            (df_z["Equipment.Id"] == mid) &
            (df_z["time_step"] >= onset_step - lookback_window) &
            (df_z["time_step"] < onset_step)
        ].sort_values("time_step")

        if len(pre_onset) == 0:
            event["lead_time_steps"] = None
            event["lead_time_minutes"] = None
            event["missed"] = True
            event["alert_threshold"] = alert_threshold
            missed_events.append(event)
            event_rows.append(event)
            continue

        # 找到所有触发告警的步
        alert_numeric = _alert_to_numeric(pre_onset["alert_level"]).values
        alert_steps = pre_onset["time_step"].values[alert_numeric >= thresh_num]

        if len(alert_steps) == 0:
            # 无告警 → 漏报
            event["lead_time_steps"] = None
            event["lead_time_minutes"] = None
            event["missed"] = True
            event["alert_threshold"] = alert_threshold
            missed_events.append(event)
        else:
            # 取离故障最近的告警步
            first_alert_step = int(alert_steps.max())
            lead_steps = onset_step - first_alert_step
            event["lead_time_steps"] = lead_steps
            event["lead_time_minutes"] = lead_steps * CONFIG["minutes_per_step"]
            event["missed"] = False
            event["alert_threshold"] = alert_threshold
            event["first_alert_step"] = first_alert_step
            lead_times.append(lead_steps)

        event_rows.append(event)

    total = len(events)
    detected = len(lead_times)
    missed = len(missed_events)

    return {
        "lead_times_steps": lead_times,
        "lead_times_minutes": [lt * CONFIG["minutes_per_step"] for lt in lead_times],
        "missed_events": missed_events,
        "avg_lead_time_steps": round(float(np.mean(lead_times)), 2) if lead_times else 0.0,
        "avg_lead_time_minutes": round(float(np.mean(lead_times)) * CONFIG["minutes_per_step"], 1) if lead_times else 0.0,
        "median_lead_time_minutes": round(float(np.median(lead_times)) * CONFIG["minutes_per_step"], 1) if lead_times else 0.0,
        "miss_rate": round(missed / total, 4) if total > 0 else 0.0,
        "detection_rate": round(detected / total, 4) if total > 0 else 0.0,
        "total_events": total,
        "detected_events": detected,
        "missed_events_count": missed,
        "alert_threshold": alert_threshold,
        "lookback_window": lookback_window,
        "event_details": pd.DataFrame(event_rows),
    }


def event_backtest_all_thresholds(df_z: pd.DataFrame) -> Dict:
    """对所有告警阈值运行事件级回测，返回对比结果。"""
    results = {}
    for thresh in CONFIG["thresholds"]:
        results[thresh] = event_based_backtest(df_z, alert_threshold=thresh)
    return results


# ══════════════════════════════════════════════════════════════════════════
# Layer 2b: Fault-Type Stratified Backtest
# ══════════════════════════════════════════════════════════════════════════

# Fault group definitions (aligned with baseline_analysis.py CONFIG)
FAULT_GROUPS = {
    "High-Voltage": [4, 5],
    "Thermal": [3, 6, 7, 8, 9],
    "Subtle": [1, 2],
}


def event_backtest_by_fault_group(
    df_z: pd.DataFrame,
    alert_threshold: str = "Warning",
) -> pd.DataFrame:
    """
    按故障类型分组的事件级回测。

    返回每个故障分组的预警提前量、漏报率、检出率。
    """
    rows = []
    for group_name, fault_types in FAULT_GROUPS.items():
        # 过滤只含该组故障类型的事件
        df_filtered = df_z.copy()
        # 标记：只保留目标故障类型或正常类型
        mask = df_filtered["Failure.Equipment.Type"].isin(fault_types + [0])
        df_filtered = df_filtered[mask]

        if len(df_filtered) == 0:
            continue

        result = event_based_backtest(df_filtered, alert_threshold=alert_threshold)
        rows.append({
            "fault_group": group_name,
            "fault_types": str(fault_types),
            "total_events": result["total_events"],
            "detected_events": result["detected_events"],
            "missed_events_count": result["missed_events_count"],
            "avg_lead_time_steps": result["avg_lead_time_steps"],
            "avg_lead_time_minutes": result["avg_lead_time_minutes"],
            "median_lead_time_minutes": result["median_lead_time_minutes"],
            "miss_rate": result["miss_rate"],
            "detection_rate": result["detection_rate"],
            "alert_threshold": alert_threshold,
        })

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════
# Layer 3: Walk-Forward Backtest
# ══════════════════════════════════════════════════════════════════════════

def walk_forward_backtest(
    df_z: pd.DataFrame,
    df_log: pd.DataFrame,
    alert_threshold: str = "Warning",
    min_train_steps: int = None,
    test_steps: int = None,
) -> pd.DataFrame:
    """
    Expanding-window walk-forward backtest。

    模拟系统上线后逐步积累数据的真实场景：
    对每个时间折叠 t:
      1. 用 [0, t] 的数据重新计算每台设备的 μ/σ 基线
      2. 对 [t+1, t+k] 计算 z-score 并判定告警
      3. 与实际故障标签对比，计算该折叠的 P/R/F1

    Args:
        df_z: z_scores DataFrame (用于参考列结构)
        df_log: 原始 log 数据
        alert_threshold: 告警阈值
        min_train_steps: 最小训练步数
        test_steps: 每个测试窗口的步数

    Returns:
        DataFrame: 每折叠一行，含所有指标
    """
    if min_train_steps is None:
        min_train_steps = CONFIG["min_train_steps"]
    if test_steps is None:
        test_steps = CONFIG["test_steps"]

    max_step = int(df_log.groupby("Equipment.Id").cumcount().max())
    thresh_num = _alert_threshold_numeric(alert_threshold)
    folds = []

    for train_end in range(min_train_steps, max_step - test_steps + 1):
        test_start = train_end
        test_end = train_end + test_steps

        # 训练窗口数据
        train_log = df_log[df_log["time_step"] <= train_end].copy()
        # 测试窗口数据
        test_log = df_log[
            (df_log["time_step"] > test_start) &
            (df_log["time_step"] <= test_end)
        ].copy()

        if len(test_log) == 0:
            continue

        # 重新计算每台设备的 μ/σ 基线（仅用训练窗口的正常样本）
        normal_train = train_log[train_log["Failure.Equipment.Type"] == 0]
        baseline = normal_train.groupby("Equipment.Id").agg(
            v_mu=("Op.Voltage", "mean"), v_sigma=("Op.Voltage", "std"),
            a_mu=("Op.Amperage", "mean"), a_sigma=("Op.Amperage", "std"),
            t_mu=("Op.Temperature", "mean"), t_sigma=("Op.Temperature", "std"),
            n_normal=("Op.Voltage", "count"),
        ).reset_index()
        # Fill NaN sigma with global median
        for col in ["v_sigma", "a_sigma", "t_sigma"]:
            baseline[col] = baseline[col].fillna(baseline[col].median()).clip(lower=0.01)

        # 对测试数据计算 z-score
        test_with_baseline = test_log.merge(baseline, on="Equipment.Id", how="left")
        # 如果某设备训练窗口无正常样本 → 跳过
        test_with_baseline = test_with_baseline.dropna(subset=["v_mu"])

        if len(test_with_baseline) == 0:
            continue

        # 计算 z-score
        test_with_baseline["z_v"] = (
            (test_with_baseline["Op.Voltage"] - test_with_baseline["v_mu"]) /
            test_with_baseline["v_sigma"]
        )
        test_with_baseline["z_a"] = (
            (test_with_baseline["Op.Amperage"] - test_with_baseline["a_mu"]) /
            test_with_baseline["a_sigma"]
        )
        test_with_baseline["z_t"] = (
            (test_with_baseline["Op.Temperature"] - test_with_baseline["t_mu"]) /
            test_with_baseline["t_sigma"]
        )
        z_cols = ["z_v", "z_a", "z_t"]
        test_with_baseline["z_composite"] = np.sqrt(
            (test_with_baseline[z_cols] ** 2).sum(axis=1)
        )

        # 判定告警
        z_comp = test_with_baseline["z_composite"].values
        if alert_threshold == "Alarm":
            y_pred = (z_comp > 2.5).astype(int)
        elif alert_threshold == "Warning":
            y_pred = (z_comp > 2.0).astype(int)
        else:  # Watch
            y_pred = (z_comp > 1.5).astype(int)

        y_true = _is_fault(test_with_baseline["Failure.Equipment.Type"]).values

        tp = int(((y_true == 1) & (y_pred == 1)).sum())
        fp = int(((y_true == 0) & (y_pred == 1)).sum())
        tn = int(((y_true == 0) & (y_pred == 0)).sum())
        fn = int(((y_true == 1) & (y_pred == 0)).sum())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        folds.append({
            "fold": len(folds) + 1,
            "train_end_step": train_end,
            "test_window_start": test_start + 1,  # exclusive of train_end
            "test_window_end": test_end,
            "n_train_samples": len(train_log),
            "n_test_samples": len(test_with_baseline),
            "n_machines_tested": int(test_with_baseline["Equipment.Id"].nunique()),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "fpr": round(fpr, 4),
            "test_fault_rate": round(float(y_true.mean()), 4),
        })

    return pd.DataFrame(folds)


def walk_forward_summary(wf_results: pd.DataFrame) -> Dict:
    """
    分析步进回测结果：早期(<15步) vs 稳定期(≥20步) 的性能对比。

    Returns:
        dict with early/late stats and convergence analysis.
    """
    if len(wf_results) == 0:
        return {"error": "No walk-forward folds produced"}

    early = wf_results[wf_results["train_end_step"] < 15]
    late = wf_results[wf_results["train_end_step"] >= 20]
    all_folds = wf_results

    early_f1_mean = float(early["f1"].mean()) if len(early) > 0 else 0.0
    late_f1_mean = float(late["f1"].mean()) if len(late) > 0 else 0.0
    early_f1_std = float(early["f1"].std()) if len(early) > 0 else 0.0
    late_f1_std = float(late["f1"].std()) if len(late) > 0 else 0.0

    # Find convergence step: first step where rolling F1 std < threshold
    convergence_step = None
    if len(all_folds) >= 5:
        all_folds_sorted = all_folds.sort_values("train_end_step")
        rolling_std = all_folds_sorted["f1"].rolling(window=5, min_periods=3).std()
        for i, (_, row) in enumerate(all_folds_sorted.iterrows()):
            if i >= 4 and rolling_std.iloc[i] < 0.05:
                convergence_step = int(row["train_end_step"])
                break

    return {
        "early_steps_f1_mean": round(early_f1_mean, 4),
        "early_steps_f1_std": round(early_f1_std, 4),
        "late_steps_f1_mean": round(late_f1_mean, 4),
        "late_steps_f1_std": round(late_f1_std, 4),
        "f1_stability_improvement_pct": round(
            (1 - late_f1_std / early_f1_std) * 100, 1
        ) if early_f1_std > 0 else 0.0,
        "convergence_step": convergence_step,
        "total_folds": len(wf_results),
        "min_train_steps": CONFIG["min_train_steps"],
    }


# ══════════════════════════════════════════════════════════════════════════
# Visualization
# ══════════════════════════════════════════════════════════════════════════

def plot_lead_time_distribution(
    event_results: Dict,
    output_dir: str,
    filename: str = "backtest_lead_time_distribution.png",
):
    """
    绘制预警提前量分布直方图。

    横轴: 预警提前量 (小时)
    纵轴: 故障事件数
    颜色分层: 绿(≥2h) / 黄(0.5-2h) / 橙(<0.5h) / 红(漏报)
    """
    lead_times_hours = [lt / 60.0 for lt in event_results["lead_times_minutes"]]
    missed_count = event_results["missed_events_count"]
    detected_count = event_results["detected_events"]

    if len(lead_times_hours) == 0 and missed_count == 0:
        print("  [WARN] No events to plot in lead time distribution")
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    # Define bins and color segments
    max_lt = max(lead_times_hours) if lead_times_hours else 2.0
    bins = np.linspace(0, max(max_lt + 0.5, 3.0), 25)

    # Separate lead times into quality tiers
    green = [lt for lt in lead_times_hours if lt >= 2.0]
    yellow = [lt for lt in lead_times_hours if 0.5 <= lt < 2.0]
    orange = [lt for lt in lead_times_hours if 0 < lt < 0.5]

    # Plot stacked histogram
    if green:
        ax.hist(green, bins=bins, color=COLORS["green"], alpha=0.85,
                label=f"高质量预警 (≥2h): {len(green)}")
    if yellow:
        ax.hist(yellow, bins=bins, color=COLORS["yellow"], alpha=0.85,
                label=f"中等预警 (0.5-2h): {len(yellow)}")
    if orange:
        ax.hist(orange, bins=bins, color=COLORS["orange"], alpha=0.85,
                label=f"近乎同期 (<0.5h): {len(orange)}")

    # Add missed as a text annotation bar
    if missed_count > 0:
        ax.text(0.98, 0.92, f"漏报: {missed_count} 事件\n({event_results['miss_rate']:.1%})",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=10, fontweight="bold", color=COLORS["red"],
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff0f0", alpha=0.9))

    # Stats annotation
    stats_text = (
        f"平均提前: {event_results['avg_lead_time_minutes']:.0f} 分钟\n"
        f"中位提前: {event_results['median_lead_time_minutes']:.0f} 分钟\n"
        f"检出率: {event_results['detection_rate']:.1%}\n"
        f"漏报率: {event_results['miss_rate']:.1%}"
    )
    ax.text(0.02, 0.92, stats_text, transform=ax.transAxes,
            va="top", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9))

    ax.set_xlabel("预警提前量 (小时)")
    ax.set_ylabel("故障事件数")
    ax.set_title(
        f"预警提前量分布 — {event_results['alert_threshold']} 级别 "
        f"(总事件: {event_results['total_events']}, 回溯窗口: {event_results['lookback_window']}步)"
    )
    ax.legend(loc="upper center", framealpha=0.9, fontsize=7)
    ax.set_xlim(left=0)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, filename))
    plt.close(fig)
    print(f"  Chart saved: {filename}")


def plot_walk_forward_curve(
    wf_results: pd.DataFrame,
    wf_summary: Dict,
    output_dir: str,
    filename: str = "backtest_walk_forward.png",
):
    """
    绘制步进回测性能曲线。

    横轴: 训练截止步
    纵轴: F1 Score (含滚动平均线)
    """
    if len(wf_results) == 0:
        print("  [WARN] No walk-forward folds to plot")
        return

    df = wf_results.sort_values("train_end_step")
    steps = df["train_end_step"].values
    f1_vals = df["f1"].values

    fig, ax = plt.subplots(figsize=(10, 5))

    # F1 scatter + rolling line
    ax.scatter(steps, f1_vals, c=COLORS["steel"], s=30, zorder=5, alpha=0.7,
               label="各折叠 F1")
    if len(f1_vals) >= 3:
        rolling = pd.Series(f1_vals).rolling(window=5, min_periods=1).mean()
        ax.plot(steps, rolling.values, color=COLORS["brick"], linewidth=2, zorder=4,
                label="5-折叠滚动平均")

    # Shade early vs stable regions
    ax.axvspan(steps.min(), 15, alpha=0.08, color=COLORS["orange"], label="训练不足期")
    if wf_summary.get("convergence_step"):
        ax.axvline(x=wf_summary["convergence_step"], color=COLORS["sage"],
                   linestyle="--", linewidth=1.5,
                   label=f"收敛 @ 步 {wf_summary['convergence_step']}")

    # Stats
    stats = (
        f"早期(<15步): F1={wf_summary['early_steps_f1_mean']:.3f}±{wf_summary['early_steps_f1_std']:.3f}\n"
        f"稳定期(≥20步): F1={wf_summary['late_steps_f1_mean']:.3f}±{wf_summary['late_steps_f1_std']:.3f}\n"
        f"稳定性提升: {wf_summary['f1_stability_improvement_pct']:.0f}%"
    )
    ax.text(0.02, 0.10, stats, transform=ax.transAxes, fontsize=8,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9))

    ax.set_xlabel("训练截止步 (Expanding Window)")
    ax.set_ylabel("F1 Score")
    ax.set_title(f"步进回测性能曲线 — {wf_summary['total_folds']} 折叠")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=7)
    ax.set_ylim(0, 1.05)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, filename))
    plt.close(fig)
    print(f"  Chart saved: {filename}")


# ══════════════════════════════════════════════════════════════════════════
# Master Runner
# ══════════════════════════════════════════════════════════════════════════

def build_event_based_summary(all_event_results: Dict, event_summary_rows: list) -> Dict:
    """
    构建 event_based 摘要，将三个阈值都作为顶层键。

    JS 前端需要 eb['Watch'], eb['Warning'], eb['Alarm'] 直接访问。
    """
    eb = {}
    for thresh in ["Watch", "Warning", "Alarm"]:
        if thresh in all_event_results:
            r = all_event_results[thresh]
            eb[thresh] = {
                "avg_lead_time_minutes": r["avg_lead_time_minutes"],
                "median_lead_time_minutes": r["median_lead_time_minutes"],
                "miss_rate": r["miss_rate"],
                "detection_rate": r["detection_rate"],
                "total_events": r["total_events"],
                "detected_events": r["detected_events"],
                "missed_events_count": r["missed_events_count"],
                "lookback_window": r["lookback_window"],
            }
    eb["threshold_comparison"] = event_summary_rows
    return eb


def run_backtest_pipeline(
    data_dir: str,
    prep_dir: str,
    output_dir: str,
    alert_threshold: str = "Warning",
) -> Dict:
    """
    运行完整的三层时序回测流水线。

    Args:
        data_dir: 原始 4-CSV 数据集目录
        prep_dir: data-prep 输出目录 (含 z_scores.csv)
        output_dir: 回测结果输出目录
        alert_threshold: 默认告警阈值

    Returns:
        dict: 含所有回测结果的汇总
    """
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("Temporal Backtest Pipeline")
    print("=" * 60)
    print(f"Data dir:      {data_dir}")
    print(f"Prep dir:      {prep_dir}")
    print(f"Output dir:    {output_dir}")
    print(f"Threshold:     {alert_threshold}")
    print()

    # ── Load data ──
    print("[1/5] Loading data...")
    df_z, df_log = load_backtest_data(data_dir, prep_dir)
    n_machines = df_z["Equipment.Id"].nunique()
    n_steps = df_z["time_step"].max() + 1
    print(f"  Loaded: {len(df_z)} rows, {n_machines} machines, {n_steps} steps")

    # ── Layer 1: Point-in-Time ──
    print("\n[2/5] Layer 1: Point-in-Time Backtest...")
    pt_results = point_in_time_backtest(df_z)
    pt_results["per_step"].to_csv(
        os.path.join(output_dir, "backtest_point_in_time.csv"), index=False
    )
    pt_results["summary"].to_csv(
        os.path.join(output_dir, "backtest_point_in_time_summary.csv"), index=False
    )
    best = pt_results["summary"].sort_values("f1", ascending=False).iloc[0]
    print(f"  Best threshold: {best['threshold']}, F1={best['f1']:.3f}, "
          f"P={best['precision']:.3f}, R={best['recall']:.3f}")

    # ── Layer 2: Event-Based ──
    print("\n[3/5] Layer 2: Event-Based Backtest...")
    all_event_results = event_backtest_all_thresholds(df_z)

    # Save per-threshold results
    event_summary_rows = []
    for thresh, result in all_event_results.items():
        event_summary_rows.append({
            "threshold": thresh,
            "total_events": result["total_events"],
            "detected_events": result["detected_events"],
            "missed_events_count": result["missed_events_count"],
            "avg_lead_time_minutes": result["avg_lead_time_minutes"],
            "median_lead_time_minutes": result["median_lead_time_minutes"],
            "miss_rate": result["miss_rate"],
            "detection_rate": result["detection_rate"],
        })
        # Save per-event details
        result["event_details"].to_csv(
            os.path.join(output_dir, f"backtest_events_{thresh}.csv"), index=False
        )
        print(f"  {thresh}: avg lead={result['avg_lead_time_minutes']:.0f}min, "
              f"median={result['median_lead_time_minutes']:.0f}min, "
              f"miss={result['miss_rate']:.1%}, detect={result['detection_rate']:.1%}")

    event_summary_df = pd.DataFrame(event_summary_rows)
    event_summary_df.to_csv(
        os.path.join(output_dir, "backtest_lead_time_summary.csv"), index=False
    )

    # Lead time distribution chart (using default threshold)
    default_result = all_event_results[alert_threshold]
    plot_lead_time_distribution(default_result, output_dir)

    # ── Layer 2b: Fault-Type Stratified (all thresholds) ──
    print("\n[3b/5] Layer 2b: Fault-Type Stratified Backtest (all thresholds)...")
    fault_group_by_threshold = {}
    for thresh in CONFIG["thresholds"]:
        fg_df = event_backtest_by_fault_group(df_z, alert_threshold=thresh)
        fg_df.to_csv(
            os.path.join(output_dir, f"backtest_by_fault_group_{thresh}.csv"), index=False
        )
        fault_group_by_threshold[thresh] = fg_df.to_dict(orient="records")
        for _, row in fg_df.iterrows():
            print(f"  [{thresh}] {row['fault_group']}: lead={row['avg_lead_time_minutes']:.0f}min, "
                  f"miss={row['miss_rate']:.1%}")
    # Also save the default threshold version for backward compat
    fault_group_df = event_backtest_by_fault_group(df_z, alert_threshold=alert_threshold)
    fault_group_df.to_csv(
        os.path.join(output_dir, "backtest_by_fault_group.csv"), index=False
    )

    # ── Layer 3: Walk-Forward (all thresholds) ──
    print("\n[4/5] Layer 3: Walk-Forward Backtest (all thresholds)...")
    wf_by_threshold = {}
    for thresh in CONFIG["thresholds"]:
        wf_results = walk_forward_backtest(df_z, df_log, alert_threshold=thresh)
        wf_results.to_csv(
            os.path.join(output_dir, f"backtest_walk_forward_{thresh}.csv"), index=False
        )
        wf_summary = walk_forward_summary(wf_results)
        wf_by_threshold[thresh] = wf_summary
        print(f"  [{thresh}] Folds: {wf_summary['total_folds']}, "
              f"early F1={wf_summary['early_steps_f1_mean']:.3f}, "
              f"late F1={wf_summary['late_steps_f1_mean']:.3f}")
        if wf_summary.get("convergence_step"):
            print(f"    Convergence at step {wf_summary['convergence_step']}")
    # Also save the default threshold version for backward compat
    wf_default = walk_forward_backtest(df_z, df_log, alert_threshold=alert_threshold)
    wf_default.to_csv(
        os.path.join(output_dir, "backtest_walk_forward.csv"), index=False
    )
    wf_summary = wf_by_threshold[alert_threshold]
    plot_walk_forward_curve(wf_default, wf_summary, output_dir)

    # ── Summary JSON ──
    print("\n[5/5] Writing summary...")
    summary = {
        "data_summary": {
            "n_machines": n_machines,
            "n_time_steps": int(n_steps),
            "minutes_per_step": CONFIG["minutes_per_step"],
        },
        "point_in_time": {
            "best_threshold": str(best["threshold"]),
            "best_f1": float(best["f1"]),
            "best_precision": float(best["precision"]),
            "best_recall": float(best["recall"]),
        },
        "event_based": build_event_based_summary(all_event_results, event_summary_rows),
        "fault_group_stratified": fault_group_by_threshold,
        "walk_forward": wf_by_threshold,
        "config": {
            "min_normal_before_onset": CONFIG["min_normal_before_onset"],
            "lookback_window": CONFIG["lookback_window"],
            "min_train_steps": CONFIG["min_train_steps"],
            "test_steps": CONFIG["test_steps"],
        },
    }
    with open(os.path.join(output_dir, "backtest_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "-" * 40)
    print("Backtest pipeline complete.")
    print(f"Output files written to: {output_dir}/")
    for fname in [
        "backtest_point_in_time.csv",
        "backtest_point_in_time_summary.csv",
        "backtest_lead_time_summary.csv",
        "backtest_events_Warning.csv",
        "backtest_by_fault_group.csv",
        "backtest_walk_forward.csv",
        "backtest_summary.json",
        "backtest_lead_time_distribution.png",
        "backtest_walk_forward.png",
    ]:
        fpath = os.path.join(output_dir, fname)
        if os.path.exists(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            print(f"  {fname} ({size_kb:.1f} KB)")
        else:
            print(f"  {fname} (NOT FOUND)")

    return summary


# ══════════════════════════════════════════════════════════════════════════
# Standalone CLI
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Temporal Backtest Validator — 3-layer time-dimension validation"
    )
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing raw CSV files")
    parser.add_argument("--prep-dir", required=True,
                        help="Directory containing data-prep outputs (z_scores.csv)")
    parser.add_argument("--output-dir", default="outputs_backtest",
                        help="Directory for backtest output files")
    parser.add_argument("--threshold", default="Warning",
                        choices=["Watch", "Warning", "Alarm"],
                        help="Default alert threshold for event-based backtest")
    args = parser.parse_args()

    run_backtest_pipeline(
        data_dir=os.path.abspath(args.data_dir),
        prep_dir=os.path.abspath(args.prep_dir),
        output_dir=os.path.abspath(args.output_dir),
        alert_threshold=args.threshold,
    )
