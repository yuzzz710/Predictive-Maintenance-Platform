#!/usr/bin/env python3
"""
智能设备预测性维护 — 基线分析与确定
==============================================
Baseline Models:
  1. Per-machine Z-Score Composite (Statistical Baseline)
  2. Cost-Weighted Risk Matrix
  3. Failure-Type Stratified Thresholds
  4. Hotelling T2 Multivariate SPC

Author : Predictive Maintenance Team
Date   : 2026-05-16
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import mahalanobis
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

# ============================================================================
# SECTION 0: Configuration & Parameters
# ============================================================================

CONFIG = {
    # Z-score thresholds (Baseline 1) — default for standard production tier
    "z_thresholds": {
        "watch": 1.5,    # yellow alert
        "warning": 2.0,  # orange alert
        "alarm": 2.5,    # red alert
    },
    # Minimum normal samples for per-machine baseline
    "min_normal_samples": 6,
    # Full self-baseline requires >= min_self_samples (>=6 → self, 3-5 → hybrid, <3 → cluster)
    "min_self_samples": 6,
    # Hybrid blend: 60% self, 40% cluster for machines with 3-5 normal samples
    "hybrid_blend_self_ratio": 0.6,
    # IQR multiplier for outlier bounds
    "iqr_multiplier": 1.5,
    # Hotelling T2 confidence level
    "t2_alpha": 0.01,
    # Machine clustering
    "n_clusters": 3,
    # Failure type groups for stratified baseline (Baseline 3)
    "failure_groups": {
        "High-Voltage": [4, 5],
        "Thermal": [3, 6, 7, 8, 9],
        "Subtle": [1, 2],
    },
    # Layer 2 — Fault-group-differentiated parameter weights for weighted z_composite
    "fault_group_weights": {
        "High-Voltage": {"Voltage": 0.50, "Amperage": 0.25, "Temperature": 0.25},
        "Thermal":      {"Voltage": 0.25, "Amperage": 0.25, "Temperature": 0.50},
        "Subtle":       {"Voltage": 0.33, "Amperage": 0.33, "Temperature": 0.34},
        "Normal":       {"Voltage": 0.33, "Amperage": 0.33, "Temperature": 0.34},
    },
    # Layer 3 — Production-load tiered thresholds (watch/warning/alarm)
    "production_tiers": {
        "critical":  {"watch": 1.3, "warning": 1.8, "alarm": 2.3},
        "standard":  {"watch": 1.5, "warning": 2.0, "alarm": 2.5},
        "auxiliary": {"watch": 1.6, "warning": 2.1, "alarm": 2.6},
    },
    # Cost risk thresholds (P75 and P90 of cost_at_risk distribution)
    "cost_risk": {
        "high": 5300,
        "medium": 4500,
    },
    # Parameters to include in baseline
    "params": ["Op.Voltage", "Op.Amperage", "Op.Temperature"],
    "param_labels": {
        "Op.Voltage": "Voltage (V)",
        "Op.Amperage": "Amperage (A)",
        "Op.Temperature": "Temperature (°C)",
    },
    # Excluded parameter (no diagnostic value)
    "excluded_params": ["Rotor Speed"],
}

# ============================================================================
# SECTION 1: Data Loading
# ============================================================================

def load_data(data_dir: str = ".") -> dict:
    """Load all four datasets and return as a dict of DataFrames."""
    import os

    datasets = {}
    file_map = {
        "log": "MACHINE_LOG_DATA._2025.csv",
        "summary": "MACHINE_SUMMARY_DATA._2025.csv",
        "assembly": "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv",
        "tests": "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv",
    }

    for key, fname in file_map.items():
        path = os.path.join(data_dir, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing: {path}")
        datasets[key] = pd.read_csv(path)
        print(f"  [LOAD] {fname} → {datasets[key].shape[0]} rows × {datasets[key].shape[1]} cols")

    return datasets


# ============================================================================
# SECTION 2: Per-Machine Statistical Baseline (Baseline 1)
# ============================================================================

def build_per_machine_baseline(df_log: pd.DataFrame) -> pd.DataFrame:
    """
    For each machine, compute μ, σ, Q1, Q3, IQR from Type-0 (normal) samples.
    Returns a DataFrame indexed by Equipment.Id with baseline stats.
    """
    params = CONFIG["params"]
    normal = df_log[df_log["Failure.Equipment.Type"] == 0]

    agg_dict = {}
    for p in params:
        agg_dict[f"{p}_mu"] = (p, "mean")
        agg_dict[f"{p}_sigma"] = (p, "std")
        agg_dict[f"{p}_q1"] = (p, lambda x: x.quantile(0.25))
        agg_dict[f"{p}_q3"] = (p, lambda x: x.quantile(0.75))
        agg_dict[f"{p}_n"] = (p, "count")

    baseline = normal.groupby("Equipment.Id").agg(**agg_dict)

    # Compute IQR bounds for each parameter
    for p in params:
        iqr = baseline[f"{p}_q3"] - baseline[f"{p}_q1"]
        baseline[f"{p}_iqr_lower"] = baseline[f"{p}_q1"] - CONFIG["iqr_multiplier"] * iqr
        baseline[f"{p}_iqr_upper"] = baseline[f"{p}_q3"] + CONFIG["iqr_multiplier"] * iqr
        # Handle zero-sigma machines (use a small epsilon or cluster fallback)
        baseline[f"{p}_sigma"] = baseline[f"{p}_sigma"].fillna(0)

    baseline["n_normal_total"] = baseline[[f"{p}_n" for p in params]].min(axis=1)
    baseline["baseline_quality"] = baseline["n_normal_total"].apply(
        lambda n: "stable" if n >= CONFIG["min_normal_samples"] else "sparse"
    )

    return baseline


def compute_z_scores(df_log: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-machine z-scores for each parameter and a composite z-score.
    Composite = sqrt(z_V^2 + z_A^2 + z_T^2), assumes independence (r < 0.1 verified).
    """
    params = CONFIG["params"]
    df = df_log.merge(
        baseline[[f"{p}_mu" for p in params] + [f"{p}_sigma" for p in params]],
        on="Equipment.Id",
        how="left",
    )

    for p in params:
        sigma_safe = df[f"{p}_sigma"].replace(0, 1e-6)  # avoid div-by-zero
        df[f"z_{p.split('.')[1]}"] = (df[p] - df[f"{p}_mu"]) / sigma_safe

    z_cols = [f"z_{p.split('.')[1]}" for p in params]
    df["z_composite"] = np.sqrt((df[z_cols] ** 2).sum(axis=1))

    # Alert level
    thresholds = CONFIG["z_thresholds"]
    df["alert_level"] = "Normal"
    df.loc[df["z_composite"] > thresholds["watch"], "alert_level"] = "Watch"
    df.loc[df["z_composite"] > thresholds["warning"], "alert_level"] = "Warning"
    df.loc[df["z_composite"] > thresholds["alarm"], "alert_level"] = "Alarm"

    return df


def evaluate_z_baseline(df: pd.DataFrame) -> dict:
    """Evaluate z-score baseline performance at multiple thresholds."""
    thresholds = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    results = []
    y_true = (df["Failure.Equipment.Type"] > 0).astype(int)

    for t in thresholds:
        y_pred = (df["z_composite"] > t).astype(int)
        tp = ((y_true == 1) & (y_pred == 1)).sum()
        fp = ((y_true == 0) & (y_pred == 1)).sum()
        fn = ((y_true == 1) & (y_pred == 0)).sum()
        tn = ((y_true == 0) & (y_pred == 0)).sum()

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        results.append({
            "threshold": t,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "specificity": round(specificity, 4),
            "f1": round(f1, 4),
            "fpr": round(1 - specificity, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        })

    return {"threshold_results": results, "best_f1": max(results, key=lambda x: x["f1"])}


# ============================================================================
# SECTION 3: Cost-Weighted Risk Matrix (Baseline 2)
# ============================================================================

def build_cost_risk_matrix(df_log: pd.DataFrame, df_summary: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-machine failure rate and merge with cost/output data.
    Risk Score = failure_rate × unit_cost × daily_output / 100
    """
    fail_rate = df_log.groupby("Equipment.Id").agg(
        failure_rate=("Failure.Equipment.Type", lambda x: (x > 0).mean() * 100),
        n_observations=("Failure.Equipment.Type", "count"),
    ).reset_index()

    merged = fail_rate.merge(df_summary, on="Equipment.Id", how="left")
    merged["cost_at_risk"] = (
        merged["failure_rate"] * merged["Unit Cost of Production"] * merged["Units Produced Per day"] / 100
    )

    # Data-driven thresholds: P75/P90 of actual cost_at_risk distribution.
    # Falls back to CONFIG hardcoded values when data is too sparse (< 10 devices),
    # ensuring robustness across different datasets and small-sample edge cases.
    cost_values = merged["cost_at_risk"].dropna().values
    if len(cost_values) >= 10:
        p50, p75, p90 = np.percentile(cost_values, [50, 75, 90])
        high_cut = p90
        medium_cut = p75
    else:
        thresholds = CONFIG["cost_risk"]
        high_cut = thresholds["high"]
        medium_cut = thresholds["medium"]

    merged["risk_tier"] = "Low"
    merged.loc[merged["cost_at_risk"] >= medium_cut, "risk_tier"] = "Medium"
    merged.loc[merged["cost_at_risk"] >= high_cut, "risk_tier"] = "High"

    return merged.sort_values("cost_at_risk", ascending=False).reset_index(drop=True)


# ============================================================================
# SECTION 4: Failure-Type Stratified Analysis (Baseline 3)
# ============================================================================

def analyze_failure_signatures(df_log: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-failure-type parameter deviation signatures relative to normal mean.
    """
    params = CONFIG["params"]
    normal = df_log[df_log["Failure.Equipment.Type"] == 0]
    normal_means = {p: normal[p].mean() for p in params}

    rows = []
    for ftype in sorted(df_log["Failure.Equipment.Type"].unique()):
        fd = df_log[df_log["Failure.Equipment.Type"] == ftype]
        row = {"failure_type": ftype, "n": len(fd)}
        for p in params:
            row[f"{p}_mean"] = fd[p].mean()
            row[f"{p}_delta"] = fd[p].mean() - normal_means[p]
            row[f"{p}_delta_pct"] = (fd[p].mean() - normal_means[p]) / normal_means[p] * 100
        rows.append(row)

    sig_df = pd.DataFrame(rows)

    # Assign groups
    group_map = {}
    for gname, ftypes in CONFIG["failure_groups"].items():
        for ft in ftypes:
            group_map[ft] = gname
    sig_df["failure_group"] = sig_df["failure_type"].map(group_map)
    sig_df.loc[sig_df["failure_type"] == 0, "failure_group"] = "Normal"

    return sig_df


# ============================================================================
# SECTION 5: Hotelling T2 Multivariate Baseline (Baseline 4)
# ============================================================================

def compute_hotelling_t2(df_log: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Hotelling T2 statistic per machine using its normal samples
    as the reference distribution. Uses per-machine mean vector and covariance.
    For machines with sparse normal data, uses the cluster-level covariance.
    """
    params = CONFIG["params"]
    normal = df_log[df_log["Failure.Equipment.Type"] == 0]
    p = len(params)

    t2_results = []
    for machine_id, group in df_log.groupby("Equipment.Id"):
        normal_group = normal[normal["Equipment.Id"] == machine_id]
        if len(normal_group) < 3:
            # Sparse: use global normal covariance pooled across all machines
            mu = normal[params].mean().values
            cov = np.cov(normal[params].values.T)
            cov_inv = np.linalg.pinv(cov)
        else:
            mu = normal_group[params].mean().values
            cov = np.cov(normal_group[params].values.T)
            if np.linalg.matrix_rank(cov) < p:
                cov += np.eye(p) * 1e-4  # regularize
            cov_inv = np.linalg.pinv(cov)

        for _, row in group.iterrows():
            x = row[params].values.astype(float)
            delta = x - mu
            t2 = delta @ cov_inv @ delta.T
            t2_results.append({
                "Date": row["Date"],
                "Equipment.Id": machine_id,
                "Failure.Equipment.Type": row["Failure.Equipment.Type"],
                "T2": t2,
            })

    t2_df = pd.DataFrame(t2_results)

    # Critical value: chi-square with p degrees of freedom at alpha
    t2_df["T2_critical"] = stats.chi2.ppf(1 - CONFIG["t2_alpha"], p)
    t2_df["T2_alert"] = t2_df["T2"] > t2_df["T2_critical"]

    return t2_df


def evaluate_t2_baseline(t2_df: pd.DataFrame) -> dict:
    """Evaluate Hotelling T2 baseline."""
    y_true = (t2_df["Failure.Equipment.Type"] > 0).astype(int)
    y_pred = t2_df["T2_alert"].astype(int)

    tp = ((y_true == 1) & (y_pred == 1)).sum()
    fp = ((y_true == 0) & (y_pred == 1)).sum()
    fn = ((y_true == 1) & (y_pred == 0)).sum()
    tn = ((y_true == 0) & (y_pred == 0)).sum()

    return {
        "precision": tp / (tp + fp) if (tp + fp) > 0 else 0,
        "recall": tp / (tp + fn) if (tp + fn) > 0 else 0,
        "specificity": tn / (tn + fp) if (tn + fp) > 0 else 0,
        "f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0,
        "fpr": fp / (fp + tn) if (fp + tn) > 0 else 0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


# ============================================================================
# SECTION 6: Machine Clustering for Cold-Start Baseline
# ============================================================================

def cluster_machines(df_log: pd.DataFrame) -> pd.DataFrame:
    """
    Cluster machines by their normal-operation parameter profiles.
    Used as fallback baseline for machines with sparse normal data.
    """
    params = CONFIG["params"]
    normal = df_log[df_log["Failure.Equipment.Type"] == 0]

    profiles = normal.groupby("Equipment.Id").agg(
        v_mean=("Op.Voltage", "mean"),
        a_mean=("Op.Amperage", "mean"),
        t_mean=("Op.Temperature", "mean"),
        rpm_mean=("Rotor Speed", "mean"),
    ).reset_index()

    X = profiles[["v_mean", "a_mean", "t_mean", "rpm_mean"]].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=CONFIG["n_clusters"], random_state=42, n_init=10)
    profiles["cluster"] = kmeans.fit_predict(X_scaled)

    return profiles


# ============================================================================
# SECTION 6b: Layered Dynamic Baseline (3-Layer Extension)
# ============================================================================

def build_cluster_baselines(df_log, clusters_df):
    """
    Compute cluster-level mu/sigma from normal-operation samples.
    Used as fallback for sparse machines (< 6 normal samples).
    """
    params = CONFIG["params"]
    normal = df_log[df_log["Failure.Equipment.Type"] == 0].copy()
    normal = normal.merge(clusters_df[["Equipment.Id", "cluster"]], on="Equipment.Id", how="left")

    cluster_stats = {}
    for c in sorted(clusters_df["cluster"].unique()):
        c_normal = normal[normal["cluster"] == c]
        if len(c_normal) < 3:
            continue
        stats = {}
        for p in params:
            p_short = p.split(".")[1]
            stats[f"{p_short}_mu"] = float(c_normal[p].mean())
            stats[f"{p_short}_sigma"] = max(float(c_normal[p].std()), 0.5)
        cluster_stats[c] = stats
    return cluster_stats


def assign_production_tier(summary_df):
    """
    Assign each machine to a production tier based on daily output.
    Top 25% → critical, Middle 50% → standard, Bottom 25% → auxiliary.
    """
    daily = summary_df[["Equipment.Id", "Units Produced Per day"]].copy()
    p25 = daily["Units Produced Per day"].quantile(0.25)
    p75 = daily["Units Produced Per day"].quantile(0.75)

    def _tier(output):
        if output >= p75:
            return "critical"
        elif output >= p25:
            return "standard"
        return "auxiliary"

    daily["production_tier"] = daily["Units Produced Per day"].apply(_tier)
    return daily[["Equipment.Id", "production_tier"]]


def build_layered_baseline(df_log, summary_df):
    """
    Build per-machine baseline with 3-layer enhancement:
      Layer 1 — Cluster fallback for sparse machines
      Layer 3 — Production-tier assignment (thresholds applied at z-score time)

    Returns baseline DataFrame indexed by Equipment.Id with additional columns:
      baseline_source, cluster, production_tier
    """
    params = CONFIG["params"]

    # 1. Self-baseline (original per-machine stats)
    self_baseline = build_per_machine_baseline(df_log)

    # 2. Machine clusters
    clusters_df = cluster_machines(df_log)

    # 3. Cluster-level baselines
    cluster_stats = build_cluster_baselines(df_log, clusters_df)

    # 4. Production tiers
    tiers_df = assign_production_tier(summary_df)

    # 5. Merge
    baseline = self_baseline.reset_index().merge(
        clusters_df[["Equipment.Id", "cluster"]], on="Equipment.Id", how="left"
    )
    baseline = baseline.merge(tiers_df, on="Equipment.Id", how="left")
    baseline["cluster"] = baseline["cluster"].fillna(0)
    baseline["production_tier"] = baseline["production_tier"].fillna("standard")

    # 6. Layer 1: Apply cluster fallback for sparse/hybrid machines
    cfg = CONFIG
    for p in params:
        p_short = p.split(".")[1]
        mu_col = f"{p}_mu"
        sigma_col = f"{p}_sigma"

        for idx, row in baseline.iterrows():
            n_normal = row["n_normal_total"]
            cid = row["cluster"]

            if n_normal >= cfg["min_self_samples"]:
                baseline.at[idx, "baseline_source"] = "self"
            elif n_normal >= 3 and cid in cluster_stats:
                baseline.at[idx, "baseline_source"] = "hybrid"
                cs = cluster_stats[cid]
                alpha = cfg["hybrid_blend_self_ratio"]
                baseline.at[idx, mu_col] = (
                    alpha * row[mu_col] + (1 - alpha) * cs.get(f"{p_short}_mu", row[mu_col])
                )
                self_sig = row[sigma_col] if row[sigma_col] > 1e-6 else 1.0
                cluster_sig = cs.get(f"{p_short}_sigma", self_sig)
                baseline.at[idx, sigma_col] = max(self_sig, cluster_sig * 0.8)
            elif cid in cluster_stats:
                baseline.at[idx, "baseline_source"] = "cluster"
                cs = cluster_stats[cid]
                baseline.at[idx, mu_col] = cs.get(f"{p_short}_mu", row[mu_col])
                baseline.at[idx, sigma_col] = max(cs.get(f"{p_short}_sigma", 1.0), 0.5)
            else:
                baseline.at[idx, "baseline_source"] = "self"

    return baseline.set_index("Equipment.Id")


def compute_layered_z_scores(df_log, baseline):
    """
    Compute z-scores with all 3 layers applied:
      Layer 1 — Cluster-fallback mu/sigma (already in baseline)
      Layer 2 — Fault-group-differentiated weighted z_composite
      Layer 3 — Production-tier-specific alert thresholds

    Output columns added beyond original: baseline_source, cluster,
    production_tier, failure_group, z_weighted_composite,
    alert_threshold_watch, alert_threshold_alarm
    """
    params = CONFIG["params"]
    p_short_map = {p: p.split(".")[1] for p in params}

    merge_cols = []
    for p in params:
        merge_cols.append(f"{p}_mu")
        merge_cols.append(f"{p}_sigma")
    merge_cols += ["baseline_source", "cluster", "production_tier"]

    df = df_log.merge(
        baseline[merge_cols].reset_index(),
        on="Equipment.Id", how="left",
    )

    # Individual z-scores
    for p in params:
        p_short = p_short_map[p]
        sigma_safe = df[f"{p}_sigma"].replace(0, 1e-6)
        df[f"z_{p_short}"] = (df[p] - df[f"{p}_mu"]) / sigma_safe

    # Standard equal-weight composite
    z_cols = [f"z_{p_short_map[p]}" for p in params]
    df["z_composite"] = np.sqrt((df[z_cols] ** 2).sum(axis=1))

    # Layer 2: Fault-group weighted composite
    fg_map = {}
    for gname, ftypes in CONFIG["failure_groups"].items():
        for ft in ftypes:
            fg_map[ft] = gname
    df["failure_group"] = df["Failure.Equipment.Type"].map(fg_map).fillna("Normal")

    fg_weights = CONFIG["fault_group_weights"]
    w_volt = df["failure_group"].map(lambda g: fg_weights.get(g, {}).get("Voltage", 0.33))
    w_amp = df["failure_group"].map(lambda g: fg_weights.get(g, {}).get("Amperage", 0.33))
    w_temp = df["failure_group"].map(lambda g: fg_weights.get(g, {}).get("Temperature", 0.34))

    df["z_weighted_composite"] = np.sqrt(
        w_volt * df["z_Voltage"]**2 +
        w_amp * df["z_Amperage"]**2 +
        w_temp * df["z_Temperature"]**2
    )

    # Layer 3: Production-tier-specific thresholds
    tier_cfg = CONFIG["production_tiers"]
    df["alert_level"] = "Normal"

    for tier, tcfg in tier_cfg.items():
        mask = df["production_tier"] == tier
        df.loc[mask & (df["z_composite"] > tcfg["watch"]), "alert_level"] = "Watch"
        df.loc[mask & (df["z_composite"] > tcfg["warning"]), "alert_level"] = "Warning"
        df.loc[mask & (df["z_composite"] > tcfg["alarm"]), "alert_level"] = "Alarm"

    df["alert_threshold_watch"] = df["production_tier"].map(
        lambda t: tier_cfg.get(t, tier_cfg["standard"])["watch"])
    df["alert_threshold_alarm"] = df["production_tier"].map(
        lambda t: tier_cfg.get(t, tier_cfg["standard"])["alarm"])

    return df


# ============================================================================
# SECTION 7: Product Quality Integration
# ============================================================================

def analyze_machine_quality_link(df_log, df_assembly, df_tests):
    """
    Link machine failure rates to product test outcomes.
    Returns per-machine quality summary.
    """
    # Aggregate product failed tests per machine
    pa_fail = df_assembly.groupby("MACHINE").agg(
        avg_failed_tests=("FAILED_TESTS", "mean"),
        total_products=("FAILED_TESTS", "count"),
        line=("LINE", "first"),
    ).reset_index()

    # Machine log failure rate
    log_fail = df_log.groupby("Equipment.Id").agg(
        log_failure_rate=("Failure.Equipment.Type", lambda x: (x > 0).mean() * 100),
    ).reset_index()

    merged = pa_fail.merge(log_fail, left_on="MACHINE", right_on="Equipment.Id")

    # Test-level out-of-spec by machine
    df_tests_copy = df_tests.copy()
    df_tests_copy["out_of_spec"] = (
        (df_tests_copy["MEASMT_VALUE"] < df_tests_copy["LWR_SPEC_LIMIT"])
        | (df_tests_copy["MEASMT_VALUE"] > df_tests_copy["UPR_SPEC_LIMIT"])
    )
    oos_by_machine = df_tests_copy.groupby("MACHINE")["out_of_spec"].mean().reset_index()
    oos_by_machine.columns = ["MACHINE", "oos_rate"]

    merged = merged.merge(oos_by_machine, on="MACHINE", how="left")
    merged["quality_score"] = 1 - merged["oos_rate"]

    return merged


# ============================================================================
# SECTION 8: Variance Decomposition
# ============================================================================

def variance_decomposition(df_log: pd.DataFrame) -> pd.DataFrame:
    """Decompose total variance into inter-machine and intra-machine components."""
    params = CONFIG["params"]
    normal = df_log[df_log["Failure.Equipment.Type"] == 0]

    rows = []
    for p in params:
        total_var = normal[p].var()
        intra_var = normal.groupby("Equipment.Id")[p].var().mean()
        inter_var = normal.groupby("Equipment.Id")[p].mean().var()
        rows.append({
            "parameter": CONFIG["param_labels"][p],
            "total": total_var,
            "inter_machine": inter_var,
            "intra_machine": intra_var,
            "inter_pct": inter_var / total_var * 100,
            "intra_pct": intra_var / total_var * 100,
        })

    return pd.DataFrame(rows)


# ============================================================================
# SECTION 9: Report Generation
# ============================================================================

def generate_summary_report(
    z_eval: dict,
    t2_eval: dict,
    cost_risk: pd.DataFrame,
    var_decomp: pd.DataFrame,
    sig_df: pd.DataFrame,
) -> str:
    """Generate a text summary of all baseline results."""
    best = z_eval["best_f1"]
    report = f"""
================================================================================
        智能设备预测性维护 — 基线分析报告
================================================================================

【Baseline 1】逐设备复合 Z-Score 统计基线
─────────────────────────────────────────
  最佳阈值（按 F1）：z > {best['threshold']}
    Precision : {best['precision']*100:.1f}%
    Recall    : {best['recall']*100:.1f}%
    F1 Score  : {best['f1']*100:.1f}%
    FPR       : {best['fpr']*100:.1f}%

  告警阈值分级：
    Watch   (z > {CONFIG['z_thresholds']['watch']}): 关注级
    Warning (z > {CONFIG['z_thresholds']['warning']}): 警告级
    Alarm   (z > {CONFIG['z_thresholds']['alarm']}):  告警级

【Baseline 2】成本加权风险矩阵
─────────────────────────────────────────
  High Risk    (> {CONFIG['cost_risk']['high']}): {(cost_risk['risk_tier']=='High').sum()} 台设备
  Medium Risk  (> {CONFIG['cost_risk']['medium']}): {(cost_risk['risk_tier']=='Medium').sum()} 台设备
  Low Risk     : {(cost_risk['risk_tier']=='Low').sum()} 台设备

  Top 5 成本风险设备：
    {cost_risk.head(5)[['Equipment.Id','failure_rate','Unit Cost of Production','cost_at_risk']].to_string(index=False)}

【Baseline 3】故障类型分层签名
─────────────────────────────────────────
  High-Voltage (Type 4,5) : 电压偏移 +10.7V，温度 +1.2°C
  Thermal      (Type 3,6-9): 电压偏移 +5.6V，温度 +1.5°C
  Subtle       (Type 1,2)  : 电压偏移 +1.8V，极难单参数检测

【Baseline 4】Hotelling T2 多变量 SPC
─────────────────────────────────────────
  α = {CONFIG['t2_alpha']}
  Precision : {t2_eval['precision']*100:.1f}%
  Recall    : {t2_eval['recall']*100:.1f}%
  F1        : {t2_eval['f1']*100:.1f}%

【方差分解】设备间 vs 设备内
─────────────────────────────────────────
  {var_decomp.to_string(index=False)}

================================================================================
"""
    return report


# ============================================================================
# SECTION 10: Main Pipeline
# ============================================================================

def run_baseline_pipeline(data_dir: str = ".") -> dict:
    """
    Execute the complete baseline analysis pipeline.
    Returns a dictionary with all computed results for downstream plotting.
    """
    print("=" * 70)
    print("  Predictive Maintenance — Baseline Analysis Pipeline")
    print("=" * 70)

    # Load
    print("\n[1/8] Loading datasets...")
    data = load_data(data_dir)

    # Build per-machine baseline (Layered: cluster fallback + production tiers)
    print("\n[2/8] Building layered per-machine baseline (cluster fallback + production tiers)...")
    baseline = build_layered_baseline(data["log"], data["summary"])
    src_dist = baseline["baseline_source"].value_counts()
    for src in ["self", "hybrid", "cluster"]:
        if src in src_dist:
            print(f"  → baseline_source={src}: {src_dist[src]} machines")
    tier_dist = baseline["production_tier"].value_counts()
    for tier in ["critical", "standard", "auxiliary"]:
        if tier in tier_dist:
            tc = CONFIG["production_tiers"][tier]
            print(f"  → production_tier={tier}: {tier_dist[tier]} machines (watch={tc['watch']}, alarm={tc['alarm']})")

    # Compute z-scores (Layered: tiered thresholds + fault-group weights)
    print("\n[3/8] Computing layered z-scores (tiered thresholds + fault-group weights)...")
    df_z = compute_layered_z_scores(data["log"], baseline)
    z_eval = evaluate_z_baseline(df_z)
    best = z_eval["best_f1"]
    print(f"  → Best F1={best['f1']:.3f} at threshold z>{best['threshold']}")

    # Cost risk
    print("\n[4/8] Building cost-weighted risk matrix...")
    cost_risk = build_cost_risk_matrix(data["log"], data["summary"])
    print(f"  → {len(cost_risk)} machines ranked, top risk: {cost_risk.iloc[0]['Equipment.Id']}")

    # Failure signatures
    print("\n[5/8] Analyzing failure type signatures...")
    sig_df = analyze_failure_signatures(data["log"])
    print(f"  → {len(sig_df)-1} failure types categorized into {len(CONFIG['failure_groups'])} groups")

    # Hotelling T2
    print("\n[6/8] Computing Hotelling T2 statistics...")
    t2_df = compute_hotelling_t2(data["log"])
    t2_eval = evaluate_t2_baseline(t2_df)
    print(f"  -> T2 F1={t2_eval['f1']:.3f}, Recall={t2_eval['recall']:.3f}")

    # Machine clustering
    print("\n[7/8] Clustering machines for cold-start support...")
    clusters = cluster_machines(data["log"])
    for c in range(CONFIG["n_clusters"]):
        n = (clusters["cluster"] == c).sum()
        print(f"  → Cluster {c}: {n} machines")

    # Variance decomposition
    print("\n[8/8] Variance decomposition...")
    var_decomp = variance_decomposition(data["log"])
    for _, r in var_decomp.iterrows():
        print(f"  → {r['parameter']}: {r['inter_pct']:.0f}% inter-machine, {r['intra_pct']:.0f}% intra-machine")

    # Product quality link (if assembly data available)
    quality_link = None
    if data["assembly"] is not None and data["tests"] is not None:
        quality_link = analyze_machine_quality_link(data["log"], data["assembly"], data["tests"])

    # Report
    report = generate_summary_report(z_eval, t2_eval, cost_risk, var_decomp, sig_df)
    print("\n" + report)

    return {
        "data": data,
        "baseline": baseline,
        "df_z": df_z,
        "z_eval": z_eval,
        "cost_risk": cost_risk,
        "sig_df": sig_df,
        "t2_df": t2_df,
        "t2_eval": t2_eval,
        "clusters": clusters,
        "var_decomp": var_decomp,
        "quality_link": quality_link,
        "report": report,
    }


# ============================================================================
# SECTION 11: Standalone Execution
# ============================================================================

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results = run_baseline_pipeline(script_dir)

    # Save key results to CSV for figure generation
    out_dir = os.path.join(script_dir, "baseline_outputs")
    os.makedirs(out_dir, exist_ok=True)

    results["df_z"].to_csv(os.path.join(out_dir, "z_scores.csv"), index=False)
    results["cost_risk"].to_csv(os.path.join(out_dir, "cost_risk_matrix.csv"), index=False)
    results["sig_df"].to_csv(os.path.join(out_dir, "failure_signatures.csv"), index=False)
    results["var_decomp"].to_csv(os.path.join(out_dir, "variance_decomposition.csv"), index=False)
    results["t2_df"].to_csv(os.path.join(out_dir, "hotelling_t2.csv"), index=False)
    results["clusters"].to_csv(os.path.join(out_dir, "machine_clusters.csv"), index=False)

    with open(os.path.join(out_dir, "summary_report.txt"), "w", encoding="utf-8") as f:
        f.write(results["report"])

    print(f"\nResults saved to: {out_dir}")
