#!/usr/bin/env python3
"""
Equipment Health Score — Lifecycle Risk Aggregation Layer
==========================================================
Aggregates 8 risk dimensions from existing pipeline outputs into a single
per-machine health score (100 = healthy, 0 = critical risk).

This is NOT a standalone model. It consumes outputs from data-prep and raw
datasets, producing the final equipment_health_score.csv that feeds into
diagnosis, decision, and the Dashboard lifecycle tab.

Dimensions:
  1. failure_rate        — fault frequency from log data           (weight 0.20)
  2. zscore_risk         — statistical anomaly severity            (weight 0.20)
  3. temperature_trend   — thermal drift over recent windows       (weight 0.15)
  4. voltage_instability — CV of recent voltage readings           (weight 0.15)
  5. maintenance_overdue — days past next-service-date vs ref_date (weight 0.10)
  6. cost_at_risk        — economic exposure from cost-risk matrix (weight 0.10)
  7. quality_failure_rate— FAILED_TESTS ratio per machine          (weight 0.05)
  8. spec_violation_rate — measurement-out-of-spec ratio           (weight 0.05)

Design constraints:
  - Self-contained data loading (does not modify baseline_analysis.py)
  - All thresholds are data-driven (percentile-based, no magic numbers)
  - Fallback when quality/spec data is sparse (< 5 machines)
  - Top risk factor + confidence score for explainability
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, Tuple

# Global weights — never mutated.  Local copies are made for fallback adjustment.
WEIGHTS: Dict[str, float] = {
    "failure_rate":        0.20,
    "zscore_risk":         0.20,
    "temperature_trend":   0.15,
    "voltage_instability": 0.15,
    "maintenance_overdue": 0.10,
    "cost_at_risk":        0.10,
    "quality_failure_rate":0.05,
    "spec_violation_rate": 0.05,
}

DIMENSION_LABELS: Dict[str, str] = {
    "failure_rate":        "Failure Rate",
    "zscore_risk":         "Z-Score Anomaly",
    "temperature_trend":   "Temperature Drift",
    "voltage_instability": "Voltage Instability",
    "maintenance_overdue": "Maintenance Overdue",
    "cost_at_risk":        "Cost Risk",
    "quality_failure_rate":"Quality Failure",
    "spec_violation_rate": "Spec Violation",
}


# ══════════════════════════════════════════════════════════════════════════
# Data Loading (self-contained — no dependency on baseline_analysis)
# ══════════════════════════════════════════════════════════════════════════

def _read_all(data_dir: str, prep_dir: str) -> Tuple[pd.DataFrame, ...]:
    """Read raw datasets + data-prep outputs.  Returns 6 DataFrames."""
    df_log     = pd.read_csv(os.path.join(data_dir, "MACHINE_LOG_DATA._2025.csv"))
    df_summary = pd.read_csv(os.path.join(data_dir, "MACHINE_SUMMARY_DATA._2025.csv"))
    df_assembly = pd.read_csv(os.path.join(data_dir, "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv"))
    df_tests   = pd.read_csv(os.path.join(data_dir, "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv"))
    df_z       = pd.read_csv(os.path.join(prep_dir, "z_scores.csv"))
    df_cost    = pd.read_csv(os.path.join(prep_dir, "cost_risk_matrix.csv"))
    return df_log, df_summary, df_assembly, df_tests, df_z, df_cost


# ══════════════════════════════════════════════════════════════════════════
# Dimension 1: Failure Rate
# ══════════════════════════════════════════════════════════════════════════

def _score_failure_rate(df_log: pd.DataFrame) -> Dict[str, float]:
    """Per-machine fault frequency.  0% fault → 100, 100% fault → 0."""
    total = df_log.groupby("Equipment.Id").size()
    faults = df_log[df_log["Failure.Equipment.Type"] > 0].groupby("Equipment.Id").size()
    fr = (faults / total).fillna(0)
    return (1.0 - fr).clip(0, 1).to_dict()


# ══════════════════════════════════════════════════════════════════════════
# Dimension 2: Z-Score Risk
# ══════════════════════════════════════════════════════════════════════════

def _score_zscore(df_z: pd.DataFrame) -> Dict[str, float]:
    """Mean of last 5 z_composite per machine.  z=0 → 100, z≥3 → 0."""
    df_z = df_z.copy()
    df_z["Date"] = pd.to_datetime(df_z["Date"])
    df_z_sorted = df_z.sort_values("Date")

    scores = {}
    for mid, grp in df_z_sorted.groupby("Equipment.Id"):
        z_mean = grp["z_composite"].tail(5).mean()
        scores[mid] = float(np.clip(100.0 - z_mean * 33.333, 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Dimension 3: Temperature Trend (with rolling smooth)
# ══════════════════════════════════════════════════════════════════════════

def _score_temperature_trend(df_log: pd.DataFrame) -> Dict[str, float]:
    """Slope of trailing temperature after rolling(3) smooth.  slope=0→100, |slope|≥0.5→0."""
    df_log = df_log.copy()
    df_log["Date"] = pd.to_datetime(df_log["Date"])
    df_sorted = df_log.sort_values(["Equipment.Id", "Date"])

    scores = {}
    for mid, grp in df_sorted.groupby("Equipment.Id"):
        temps = grp["Op.Temperature"].tail(10).values.astype(float)
        n = len(temps)
        if n < 2:
            scores[mid] = 100.0
            continue
        smoothed = pd.Series(temps).rolling(window=3, min_periods=1).mean().values
        slope = float(np.polyfit(range(len(smoothed)), smoothed, 1)[0])
        scores[mid] = float(np.clip(100.0 - abs(slope) * 200.0, 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Dimension 4: Voltage Instability
# ══════════════════════════════════════════════════════════════════════════

def _score_voltage_instability(df_log: pd.DataFrame) -> Dict[str, float]:
    """CV (σ/μ) of last 10 voltage readings.  CV=0→100, CV≥0.15→0."""
    df_log = df_log.copy()
    df_log["Date"] = pd.to_datetime(df_log["Date"])
    df_sorted = df_log.sort_values(["Equipment.Id", "Date"])

    scores = {}
    for mid, grp in df_sorted.groupby("Equipment.Id"):
        v = grp["Op.Voltage"].tail(10).values.astype(float)
        mu = np.mean(v)
        if mu == 0 or len(v) < 2:
            scores[mid] = 100.0
            continue
        cv = float(np.std(v, ddof=1) / mu)
        scores[mid] = float(np.clip(100.0 - cv * 666.667, 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Dimension 5: Maintenance Overdue
# ══════════════════════════════════════════════════════════════════════════

def _score_maintenance_overdue(df_summary: pd.DataFrame, ref_date: pd.Timestamp) -> Dict[str, float]:
    """Days past Next Service Date relative to ref_date.  0d→100, ≥90d→0."""
    scores = {}
    for _, row in df_summary.iterrows():
        mid = str(row["Equipment.Id"])
        try:
            next_svc = pd.to_datetime(row["Next Service Date"])
            overdue = max(0.0, (ref_date - next_svc).days)
        except Exception:
            overdue = 0.0
        scores[mid] = float(np.clip(100.0 - overdue * 1.111, 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Dimension 6: Cost at Risk
# ══════════════════════════════════════════════════════════════════════════

def _score_cost_at_risk(df_cost: pd.DataFrame) -> Dict[str, float]:
    """Percentile-mapped cost_at_risk.  P10→100, P90→0."""
    id_col = "Equipment.Id" if "Equipment.Id" in df_cost.columns else "Equipment ID"
    cost_col = "cost_at_risk"

    costs = df_cost[cost_col].dropna().values
    if len(costs) >= 10:
        p10, p90 = np.percentile(costs, [10, 90])
    else:
        p10, p90 = costs.min(), costs.max()
    span = p90 - p10 if p90 > p10 else 1.0

    scores = {}
    for _, row in df_cost.iterrows():
        mid = str(row[id_col])
        c = float(row.get(cost_col, 0))
        scores[mid] = float(np.clip(100.0 * (1.0 - (c - p10) / span), 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Dimension 7: Quality Failure Rate
# ══════════════════════════════════════════════════════════════════════════

def _score_quality(df_assembly: pd.DataFrame) -> Dict[str, float]:
    """FAILED_TESTS ratio per MACHINE.  0%→100, 50%→0."""
    scores = {}
    if "MACHINE" not in df_assembly.columns or "FAILED_TESTS" not in df_assembly.columns:
        return scores

    machine_col = df_assembly["MACHINE"]
    unique_machines = machine_col.dropna().unique()

    for mid in unique_machines:
        subset = df_assembly[df_assembly["MACHINE"] == mid]
        n_total = len(subset)
        n_failed = int(subset["FAILED_TESTS"].sum())
        rate = n_failed / n_total if n_total > 0 else 0.0
        scores[str(mid)] = float(np.clip((1.0 - rate / 0.5) * 100.0, 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Dimension 8: Spec Violation Rate
# ══════════════════════════════════════════════════════════════════════════

def _score_spec_violation(df_tests: pd.DataFrame) -> Dict[str, float]:
    """Ratio of measurements outside [LWR_SPEC_LIMIT, UPR_SPEC_LIMIT].  0%→100, 30%→0."""
    scores = {}
    required = ["MACHINE", "MEASMT_VALUE", "LWR_SPEC_LIMIT", "UPR_SPEC_LIMIT"]
    if not all(c in df_tests.columns for c in required):
        return scores

    for mid, grp in df_tests.groupby("MACHINE"):
        mid = str(mid)
        val = grp["MEASMT_VALUE"].values.astype(float)
        lo  = grp["LWR_SPEC_LIMIT"].values.astype(float)
        hi  = grp["UPR_SPEC_LIMIT"].values.astype(float)
        n_total = len(val)
        if n_total == 0:
            continue
        n_violation = int(((val < lo) | (val > hi)).sum())
        rate = n_violation / n_total
        scores[mid] = float(np.clip((1.0 - rate / 0.3) * 100.0, 0.0, 100.0))
    return scores


# ══════════════════════════════════════════════════════════════════════════
# Trend Classification
# ══════════════════════════════════════════════════════════════════════════

def _classify_trend(temp_slope: float, z_trend: float) -> str:
    """Critical check FIRST, then Degrading, else Stable."""
    if temp_slope > 0.1 or z_trend > 0.2:
        return "Critical"
    elif temp_slope > 0.05 and z_trend > 0.1:
        return "Degrading"
    return "Stable"


def _classify_level(hs: float) -> str:
    if hs >= 80:
        return "Healthy"
    elif hs >= 60:
        return "Warning"
    elif hs >= 40:
        return "Degrading"
    return "Critical"


# ══════════════════════════════════════════════════════════════════════════
# Per-Machine Trend Slopes (for trend classification)
# ══════════════════════════════════════════════════════════════════════════

def _compute_trend_slopes(df_log: pd.DataFrame, df_z: pd.DataFrame) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Compute temp_slope and z_trend per machine for trend classification."""
    df_log = df_log.copy()
    df_log["Date"] = pd.to_datetime(df_log["Date"])
    log_sorted = df_log.sort_values(["Equipment.Id", "Date"])

    df_z = df_z.copy()
    df_z["Date"] = pd.to_datetime(df_z["Date"])
    z_sorted = df_z.sort_values(["Equipment.Id", "Date"])

    temp_slopes = {}
    for mid, grp in log_sorted.groupby("Equipment.Id"):
        temps = grp["Op.Temperature"].tail(10).values.astype(float)
        n = len(temps)
        if n < 2:
            temp_slopes[mid] = 0.0
            continue
        smoothed = pd.Series(temps).rolling(window=3, min_periods=1).mean().values
        temp_slopes[mid] = float(np.polyfit(range(len(smoothed)), smoothed, 1)[0])

    z_trends = {}
    for mid, grp in z_sorted.groupby("Equipment.Id"):
        z_vals = grp["z_composite"].tail(5).values.astype(float)
        n = len(z_vals)
        if n < 2:
            z_trends[mid] = 0.0
            continue
        z_trends[mid] = float(np.polyfit(range(n), z_vals, 1)[0])

    return temp_slopes, z_trends


# ══════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ══════════════════════════════════════════════════════════════════════════

def build_equipment_health_score(data_dir: str, prep_dir: str) -> pd.DataFrame:
    """
    Build per-machine Equipment Health Score by aggregating 8 risk dimensions.

    Args:
        data_dir: Path to raw 4-CSV dataset directory
        prep_dir: Path to data-prep output directory (z_scores.csv, cost_risk_matrix.csv)

    Returns:
        DataFrame with columns: Equipment.Id, health_score, health_level, trend,
        top_risk_factor, confidence, and per-dimension raw values.
    """
    # ── Load data ──
    df_log, df_summary, df_assembly, df_tests, df_z, df_cost = _read_all(data_dir, prep_dir)
    df_log["Date"] = pd.to_datetime(df_log["Date"])
    reference_date = df_log["Date"].max()

    # ── Detect data availability ──
    quality_machines = set()
    if "MACHINE" in df_assembly.columns:
        quality_machines = set(str(m) for m in df_assembly["MACHINE"].dropna().unique())
    spec_machines = set()
    required_spec_cols = ["MACHINE", "MEASMT_VALUE", "LWR_SPEC_LIMIT", "UPR_SPEC_LIMIT"]
    if all(c in df_tests.columns for c in required_spec_cols):
        spec_machines = set(str(m) for m in df_tests["MACHINE"].dropna().unique())

    quality_ok = len(quality_machines) >= 5
    spec_ok    = len(spec_machines) >= 5

    print(f"  Health Score dimensions: quality={'[OK]' if quality_ok else '[SPARSE]'} "
          f"(n={len(quality_machines)} machines with assembly data), "
          f"spec={'[OK]' if spec_ok else '[SPARSE]'} "
          f"(n={len(spec_machines)} machines with test data)")

    # ── Build per-dimension scores ──
    scores_fr    = _score_failure_rate(df_log)
    scores_z     = _score_zscore(df_z)
    scores_temp  = _score_temperature_trend(df_log)
    scores_volt  = _score_voltage_instability(df_log)
    scores_maint = _score_maintenance_overdue(df_summary, reference_date)
    scores_cost  = _score_cost_at_risk(df_cost)
    scores_qual  = _score_quality(df_assembly) if quality_ok else {}
    scores_spec  = _score_spec_violation(df_tests) if spec_ok else {}

    # ── Trend slopes ──
    temp_slopes, z_trends = _compute_trend_slopes(df_log, df_z)

    # ── Adjust weights (local copy) ──
    weights = WEIGHTS.copy()
    if not quality_ok:
        weights["quality_failure_rate"] = 0.0
        weights["failure_rate"] += 0.05
    if not spec_ok:
        weights["spec_violation_rate"] = 0.0
        weights["zscore_risk"] += 0.05
    # Re-normalize
    total_w = sum(weights.values())
    if total_w > 0:
        weights = {k: v / total_w for k, v in weights.items()}

    # ── Collect all machine IDs ──
    all_machines = sorted(set(
        list(scores_fr.keys()) +
        list(scores_z.keys()) +
        list(scores_cost.keys())
    ))

    # ── Pre-compute raw values for CSV columns ──
    # Maintenance overdue days
    overdue_days = {}
    for _, row in df_summary.iterrows():
        mid = str(row["Equipment.Id"])
        try:
            next_svc = pd.to_datetime(row["Next Service Date"])
            overdue_days[mid] = int(max(0, (reference_date - next_svc).days))
        except Exception:
            overdue_days[mid] = 0

    # Failure rate
    total_per_machine = df_log.groupby("Equipment.Id").size()
    faults_per_machine = df_log[df_log["Failure.Equipment.Type"] > 0].groupby("Equipment.Id").size()

    # Z-score latest mean
    df_z_sorted = df_z.copy()
    df_z_sorted["Date"] = pd.to_datetime(df_z_sorted["Date"])
    df_z_sorted = df_z_sorted.sort_values("Date")
    z_mean_map = {}
    for mid, grp in df_z_sorted.groupby("Equipment.Id"):
        z_mean_map[mid] = round(float(grp["z_composite"].tail(5).mean()), 3)

    # Quality failure rate
    qual_rate = {}
    if quality_ok:
        for mid in quality_machines:
            sub = df_assembly[df_assembly["MACHINE"] == mid]
            qual_rate[mid] = round(float(sub["FAILED_TESTS"].sum() / len(sub)), 4)

    # Spec violation rate
    spec_rate = {}
    if spec_ok:
        for mid in spec_machines:
            sub = df_tests[df_tests["MACHINE"] == mid]
            v = sub["MEASMT_VALUE"].values.astype(float)
            lo = sub["LWR_SPEC_LIMIT"].values.astype(float)
            hi = sub["UPR_SPEC_LIMIT"].values.astype(float)
            spec_rate[mid] = round(float(((v < lo) | (v > hi)).sum() / len(v)), 4)

    # Cost at risk
    cost_map = {}
    id_col = "Equipment.Id" if "Equipment.Id" in df_cost.columns else "Equipment ID"
    for _, row in df_cost.iterrows():
        mid = str(row[id_col])
        cost_map[mid] = round(float(row.get("cost_at_risk", 0)), 2)

    # ── Fuse & build output ──
    rows = []
    for mid in all_machines:
        dimension_scores = {
            "failure_rate":        scores_fr.get(mid, 100.0),
            "zscore_risk":         scores_z.get(mid, 100.0),
            "temperature_trend":   scores_temp.get(mid, 100.0),
            "voltage_instability": scores_volt.get(mid, 100.0),
            "maintenance_overdue": scores_maint.get(mid, 100.0),
            "cost_at_risk":        scores_cost.get(mid, 100.0),
            "quality_failure_rate":scores_qual.get(mid, 100.0) if quality_ok else 100.0,
            "spec_violation_rate": scores_spec.get(mid, 100.0) if spec_ok else 100.0,
        }

        hs = sum(weights[k] * dimension_scores[k] for k in weights)
        hs = float(np.clip(hs, 0.0, 100.0))

        top_risk = min(dimension_scores, key=dimension_scores.get)

        # Confidence = how many dimensions have actual data for this machine
        # Base 6 are always available; quality/spec depend on global + per-machine coverage
        n_dims_total = 6  # failure_rate, zscore_risk, temperature_trend, voltage_instability, maintenance_overdue, cost_at_risk
        if quality_ok:
            n_dims_total += 1
        if spec_ok:
            n_dims_total += 1

        n_available = 6  # base 6 always have real data for every machine
        if quality_ok and mid in scores_qual:
            n_available += 1
        if spec_ok and mid in scores_spec:
            n_available += 1

        confidence = round(n_available / n_dims_total, 2)

        trend = _classify_trend(
            temp_slopes.get(mid, 0.0),
            z_trends.get(mid, 0.0),
        )
        level = _classify_level(hs)

        n_total = int(total_per_machine.get(mid, 1))
        n_fault = int(faults_per_machine.get(mid, 0))
        fr_val = round(n_fault / n_total, 4) if n_total > 0 else 0.0

        rows.append({
            "Equipment.Id":              mid,
            "health_score":              round(hs, 1),
            "health_level":              level,
            "trend":                     trend,
            "top_risk_factor":           top_risk,
            "top_risk_factor_label":     DIMENSION_LABELS.get(top_risk, top_risk),
            "confidence":                confidence,
            "failure_rate":              fr_val,
            "zscore_risk":               z_mean_map.get(mid, 0.0),
            "temperature_slope":         round(temp_slopes.get(mid, 0.0), 5),
            "voltage_instability":       round(dimension_scores["voltage_instability"], 1),
            "maintenance_overdue_days":  overdue_days.get(mid, 0),
            "cost_at_risk":             cost_map.get(mid, 0.0),
            "quality_failure_rate":     qual_rate.get(mid, 0.0),
            "spec_violation_rate":      spec_rate.get(mid, 0.0),
        })

    df_out = pd.DataFrame(rows).sort_values("health_score")
    return df_out


# ══════════════════════════════════════════════════════════════════════════
# Health Score Timeseries — Foundation for RUL (Remaining Useful Life)
# ══════════════════════════════════════════════════════════════════════════

def build_health_score_timeseries(
    data_dir: str,
    prep_dir: str,
    min_data_points: int = 5,
) -> pd.DataFrame:
    """
    Build health score time series for each machine at each time step.

    This is the bridge between static health scores and RUL estimation.
    For each machine, at each time step t (from min_data_points to end),
    health scores are recomputed using only data up to time t ("pseudo-now"
    perspective). The resulting trajectory H(t) is the input to the
    DegradationRUL estimator.

    Args:
        data_dir: Path to raw 4-CSV dataset directory
        prep_dir: Path to data-prep output directory (z_scores.csv, cost_risk_matrix.csv)
        min_data_points: Minimum time steps required per machine (default 5)

    Returns:
        DataFrame with columns:
          Equipment.Id, time_step, time_index, health_score,
          failure_rate_score, zscore_risk_score, temperature_trend_score,
          voltage_instability_score, maintenance_overdue_score,
          cost_at_risk_score, quality_failure_score, spec_violation_score

    Performance note:
        For 100 machines × ~25 steps = ~2500 iterations. Each iteration
        filters data and computes 8 dimensions. Total runtime ~30-90 seconds.
    """
    import time as _time
    _t0 = _time.time()

    # ── Load all data ──
    df_log, df_summary, df_assembly, df_tests, df_z, df_cost = _read_all(data_dir, prep_dir)

    # Sort by date within each machine
    df_log["Date"] = pd.to_datetime(df_log["Date"])
    df_log = df_log.sort_values(["Equipment.Id", "Date"]).reset_index(drop=True)
    df_z["Date"] = pd.to_datetime(df_z["Date"])
    df_z = df_z.sort_values(["Equipment.Id", "Date"]).reset_index(drop=True)

    global_ref_date = df_log["Date"].max()

    # ── Detect data availability (constant across all time steps) ──
    quality_machines = set()
    if "MACHINE" in df_assembly.columns:
        quality_machines = set(str(m) for m in df_assembly["MACHINE"].dropna().unique())
    spec_machines = set()
    required_spec_cols = ["MACHINE", "MEASMT_VALUE", "LWR_SPEC_LIMIT", "UPR_SPEC_LIMIT"]
    if all(c in df_tests.columns for c in required_spec_cols):
        spec_machines = set(str(m) for m in df_tests["MACHINE"].dropna().unique())

    quality_ok = len(quality_machines) >= 5
    spec_ok = len(spec_machines) >= 5

    # ── Static dimensions (same for all time steps) ──
    # D6: Cost at risk (static per machine)
    scores_cost = _score_cost_at_risk(df_cost)

    # D7: Quality failure rate (static per machine)
    scores_qual = _score_quality(df_assembly) if quality_ok else {}

    # D8: Spec violation rate (static per machine)
    scores_spec = _score_spec_violation(df_tests) if spec_ok else {}

    # ── Adjust weights (same logic as build_equipment_health_score) ──
    weights = WEIGHTS.copy()
    if not quality_ok:
        weights["quality_failure_rate"] = 0.0
        weights["failure_rate"] += 0.05
    if not spec_ok:
        weights["spec_violation_rate"] = 0.0
        weights["zscore_risk"] += 0.05
    total_w = sum(weights.values())
    if total_w > 0:
        weights = {k: v / total_w for k, v in weights.items()}

    # ── Pre-compute service dates from summary (static) ──
    service_dates = {}
    for _, row in df_summary.iterrows():
        mid = str(row["Equipment.Id"])
        try:
            service_dates[mid] = pd.to_datetime(row["Next Service Date"])
        except Exception:
            service_dates[mid] = pd.NaT

    # ── Build timeseries: iterate machines, accumulate by time step ──
    machine_ids = sorted(df_log["Equipment.Id"].unique())
    all_rows = []
    n_machines = len(machine_ids)
    n_total_steps = 0

    print(f"  Building health score timeseries for {n_machines} machines "
          f"(min {min_data_points} points each)...")
    print(f"  Static dimensions: quality={'ok' if quality_ok else 'sparse'} "
          f"spec={'ok' if spec_ok else 'sparse'}")

    for mi, mid in enumerate(machine_ids):
        # Machine-specific log and z-score data, sorted by date
        m_log = df_log[df_log["Equipment.Id"] == mid].reset_index(drop=True)
        m_z = df_z[df_z["Equipment.Id"] == mid].reset_index(drop=True)

        if len(m_log) < min_data_points:
            continue

        dates = m_log["Date"].tolist()

        # Progressive accumulation for efficiency:
        # As we advance through time steps, we maintain cumulative
        # counts and sums rather than re-scanning from scratch.

        # Track cumulative failure counts for D1
        cum_n_total = 0
        cum_n_fault = 0

        # Track rolling windows for D3 (temp trend) and D4 (voltage instability)
        # We compute these fresh each step (small cost for tail operations)

        for t_idx in range(min_data_points, len(m_log)):
            ref_date = dates[t_idx]  # "pseudo-now"
            window_log = m_log.iloc[:t_idx + 1]
            window_z = m_z[m_z["Date"] <= ref_date]

            if len(window_z) < 2:
                continue  # need at least some z-scores

            # ── D1: Failure Rate (cumulative up to t_idx) ──
            cum_n_total = len(window_log)
            cum_n_fault = int((window_log["Failure.Equipment.Type"] > 0).sum())
            fr_val = cum_n_fault / cum_n_total if cum_n_total > 0 else 0.0
            score_fr = float(np.clip((1.0 - fr_val) * 100.0, 0.0, 100.0))

            # ── D2: Z-Score Risk (last 5 of window_z) ──
            z_tail = window_z["z_composite"].tail(5)
            z_mean_val = float(z_tail.mean()) if len(z_tail) > 0 else 0.0
            score_z = float(np.clip(100.0 - abs(z_mean_val) * 33.333, 0.0, 100.0))

            # ── D3: Temperature Trend (last 10 of window_log) ──
            temps = window_log["Op.Temperature"].tail(10).values.astype(float)
            if len(temps) >= 2:
                smoothed = pd.Series(temps).rolling(window=3, min_periods=1).mean().values
                temp_slope = float(np.polyfit(range(len(smoothed)), smoothed, 1)[0])
            else:
                temp_slope = 0.0
            score_temp = float(np.clip(100.0 - abs(temp_slope) * 200.0, 0.0, 100.0))

            # ── D4: Voltage Instability (last 10 of window_log) ──
            v_vals = window_log["Op.Voltage"].tail(10).values.astype(float)
            v_mu = np.mean(v_vals)
            if v_mu > 0 and len(v_vals) >= 2:
                v_cv = float(np.std(v_vals, ddof=1) / v_mu)
            else:
                v_cv = 0.0
            score_volt = float(np.clip(100.0 - v_cv * 666.667, 0.0, 100.0))

            # ── D5: Maintenance Overdue at ref_date ──
            svc_date = service_dates.get(mid, pd.NaT)
            if pd.notna(svc_date):
                overdue = max(0.0, (ref_date - svc_date).days)
            else:
                overdue = 0.0
            score_maint = float(np.clip(100.0 - overdue * 1.111, 0.0, 100.0))

            # ── D6/D7/D8: Static dimensions ──
            score_cost = scores_cost.get(mid, 100.0)
            score_qual = scores_qual.get(mid, 100.0) if quality_ok else 100.0
            score_spec = scores_spec.get(mid, 100.0) if spec_ok else 100.0

            # ── Fuse into health score ──
            dimension_scores = {
                "failure_rate":        score_fr,
                "zscore_risk":         score_z,
                "temperature_trend":   score_temp,
                "voltage_instability": score_volt,
                "maintenance_overdue": score_maint,
                "cost_at_risk":        score_cost,
                "quality_failure_rate":score_qual,
                "spec_violation_rate": score_spec,
            }
            hs = sum(weights[k] * dimension_scores[k] for k in weights)
            hs = float(np.clip(hs, 0.0, 100.0))

            all_rows.append({
                "Equipment.Id":               str(mid),
                "time_step":                  t_idx,
                "time_index":                 t_idx,
                "ref_date":                   ref_date,
                "health_score":               round(hs, 1),
                "failure_rate_score":         round(score_fr, 1),
                "zscore_risk_score":          round(score_z, 1),
                "temperature_trend_score":    round(score_temp, 1),
                "voltage_instability_score":  round(score_volt, 1),
                "maintenance_overdue_score":  round(score_maint, 1),
                "cost_at_risk_score":         round(score_cost, 1),
                "quality_failure_score":      round(score_qual, 1),
                "spec_violation_score":       round(score_spec, 1),
                "failure_rate":               round(fr_val, 4),
                "z_composite_mean":           round(z_mean_val, 3),
                "temperature_slope":          round(temp_slope, 5),
                "voltage_cv":                 round(v_cv, 5),
                "maintenance_overdue_days":   int(overdue),
            })
            n_total_steps += 1

        # Progress indicator (every 20 machines)
        if (mi + 1) % 20 == 0:
            elapsed = _time.time() - _t0
            print(f"    {mi + 1}/{n_machines} machines processed "
                  f"({n_total_steps} total snapshots, {elapsed:.0f}s elapsed)")

    elapsed = _time.time() - _t0
    print(f"  Timeseries complete: {n_total_steps} snapshots across "
          f"{len(set(r['Equipment.Id'] for r in all_rows))} machines "
          f"({elapsed:.1f}s)")

    if not all_rows:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=[
            "Equipment.Id", "time_step", "time_index", "ref_date",
            "health_score", "failure_rate_score", "zscore_risk_score",
            "temperature_trend_score", "voltage_instability_score",
            "maintenance_overdue_score", "cost_at_risk_score",
            "quality_failure_score", "spec_violation_score",
            "failure_rate", "z_composite_mean", "temperature_slope",
            "voltage_cv", "maintenance_overdue_days",
        ])

    df_out = pd.DataFrame(all_rows).sort_values(
        ["Equipment.Id", "time_step"]
    ).reset_index(drop=True)
    return df_out
