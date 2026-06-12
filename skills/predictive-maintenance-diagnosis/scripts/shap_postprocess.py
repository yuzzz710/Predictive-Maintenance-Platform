#!/usr/bin/env python3
"""
SHAP Post-Process — Called directly by orchestrator after decision completes.
==============================================================================
NOT a standalone skill. NOT run via subprocess. This is a lightweight
post-processing layer that:

1. Reads decision + stat + prep outputs
2. Decomposes final_risk_score for every machine (RiskDecomposer)
3. Trains StatLayerSHAP for stat-layer attribution
4. Generates industrial explanations (LocalExplainer)
5. Exports shap_dashboard.json
6. Merges SHAP columns into industrial_maintenance_plan.csv

Usage (from orchestrator):
    from skills.predictive_maintenance_diagnosis.scripts.shap_postprocess import run_shap_postprocess
    run_shap_postprocess(prep_dir, stat_dir, decision_dir, strategy)
"""

import os
import sys
import json
import numpy as np
import pandas as pd

# Ensure this script's directory is on path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shap_explainer import (
    RiskDecomposer,
    StatLayerSHAP,
    build_feature_matrix,
)
from local_explainer import LocalExplainer
from shap_visualizer import export_dashboard_json, merge_shap_to_work_orders


def run_shap_postprocess(
    prep_dir: str,
    stat_dir: str,
    decision_dir: str,
    strategy: str = "production_efficiency",
    output_dir: str = None,
):
    """
    Main entry point for SHAP post-processing.

    Parameters
    ----------
    prep_dir : str
        Path to data-prep outputs (z_scores.csv, cost_risk_matrix.csv, etc.)
    stat_dir : str
        Path to stat-inference outputs (alert_summary.csv, health_score.csv, etc.)
    decision_dir : str
        Path to decision outputs (industrial_maintenance_plan.csv)
    strategy : str
        Maintenance strategy (affects fusion weights)
    output_dir : str or None
        Where to write shap_dashboard.json. If None, writes to decision_dir.
    """
    if output_dir is None:
        output_dir = decision_dir

    print("\n" + "-" * 40)
    print("SHAP Post-Process: Alert Attribution Analysis")
    print("-" * 40)

    # ── 1. Load upstream data ──
    print("  [1/5] Loading upstream data...")

    # Alert summary (required)
    alert_path = os.path.join(stat_dir, "alert_summary.csv")
    if not os.path.exists(alert_path):
        alert_path = os.path.join(prep_dir, "alert_summary.csv")
    if not os.path.exists(alert_path):
        # Build from z_scores directly
        z_path = os.path.join(prep_dir, "z_scores.csv")
        if os.path.exists(z_path):
            df_z = pd.read_csv(z_path)
            alerts = []
            for mid, grp in df_z.groupby("Equipment.Id"):
                grp_sorted = grp.sort_values("Date") if "Date" in grp.columns else grp
                latest = grp_sorted.iloc[-1]
                alerts.append({
                    "machine_id": mid,
                    "current_alert_level": str(latest.get("alert_level", "Normal")),
                    "z_comp_max": float(grp["z_composite"].max()),
                    "z_comp_mean": float(grp["z_composite"].mean()),
                    "z_v_last": float(latest.get("z_Voltage", 0)),
                    "z_a_last": float(latest.get("z_Amperage", 0)),
                    "z_t_last": float(latest.get("z_Temperature", 0)),
                    "n_alarm_windows": int((grp["alert_level"] == "Alarm").sum()),
                    "n_warning_windows": int((grp["alert_level"] == "Warning").sum()),
                })
            alert_df = pd.DataFrame(alerts)
        else:
            raise FileNotFoundError(f"Cannot find alert_summary.csv or z_scores.csv")
    else:
        alert_df = pd.read_csv(alert_path)
    print(f"    Alert data: {alert_df.shape[0]} machines")

    # Z-scores
    z_path = os.path.join(prep_dir, "z_scores.csv")
    z_df = pd.read_csv(z_path) if os.path.exists(z_path) else None

    # T²
    t2_path = os.path.join(prep_dir, "hotelling_t2.csv")
    t2_df = pd.read_csv(t2_path) if os.path.exists(t2_path) else None

    # Cost risk
    cost_path = os.path.join(prep_dir, "cost_risk_matrix.csv")
    cost_df = pd.read_csv(cost_path) if os.path.exists(cost_path) else None

    # Health score
    health_path = os.path.join(stat_dir, "equipment_health_score.csv")
    health_df = pd.read_csv(health_path) if os.path.exists(health_path) else None

    # ── 2. Build feature matrix ──
    print("  [2/5] Building feature matrix...")
    fm = build_feature_matrix(alert_df, z_df, t2_df, cost_df, health_df)
    print(f"    Feature matrix: {fm.shape[0]} machines x {fm.shape[1]} features")

    # ── 3. Compute cost percentiles for RiskDecomposer ──
    cost_values = fm["cost_at_risk"].values
    cost_p50 = float(np.percentile(cost_values, 50)) if len(cost_values) > 0 else 4500.0
    cost_p75 = float(np.percentile(cost_values, 75)) if len(cost_values) > 0 else 5000.0
    cost_p90 = float(np.percentile(cost_values, 90)) if len(cost_values) > 0 else 5500.0
    print(f"    Cost percentiles: P50=${cost_p50:.0f}, P75=${cost_p75:.0f}, P90=${cost_p90:.0f}")

    # ── 4. Decompose risk scores ──
    print("  [3/5] Decomposing risk scores...")
    decomposer = RiskDecomposer(
        cost_p50=cost_p50, cost_p75=cost_p75, cost_p90=cost_p90,
        strategy=strategy,
    )

    # Train StatLayerSHAP on stat_score
    X_stat = fm[StatLayerSHAP.FEATURE_NAMES].values.astype(float)
    # Compute stat_score for each machine (same formula as in RiskDecomposer)
    y_stat = []
    for _, row in fm.iterrows():
        signals = row.to_dict()
        dec = decomposer.decompose(signals)
        y_stat.append(dec["decomposition"]["stat_score"]["value"])
    y_stat = np.array(y_stat)

    stat_shap = StatLayerSHAP()
    try:
        stat_shap.fit(X_stat, y_stat)
        shap_values = stat_shap.explain(X_stat)
        global_imp = stat_shap.global_importance(shap_values)
        print(f"    StatLayerSHAP trained, top feature: {global_imp[0]['label']} (imp={global_imp[0]['importance']:.4f})")
    except Exception as e:
        print(f"    WARNING: StatLayerSHAP failed ({e}), using proportional attribution only")
        shap_values = None
        global_imp = [
            {"feature": name, "label": StatLayerSHAP.FEATURE_LABELS.get(name, name),
             "importance": 0.0}
            for name in StatLayerSHAP.FEATURE_NAMES
        ]

    # ── 5. Per-machine explanations ──
    print("  [4/5] Generating per-machine explanations...")
    local_explainer = LocalExplainer()

    machines = {}
    all_risk_scores = []

    for i, (_, row) in enumerate(fm.iterrows()):
        mid = row["machine_id"]
        signals = row.to_dict()

        # Decompose risk
        decomposition = decomposer.decompose(signals)
        all_risk_scores.append(decomposition["final_risk_score"])

        # Extract per-machine SHAP from stat layer
        stat_shap_dict = None
        if shap_values is not None and i < len(shap_values):
            stat_shap_dict = dict(zip(StatLayerSHAP.FEATURE_NAMES, shap_values[i]))

        # Build industrial explanation
        explanation = local_explainer.explain_machine(mid, decomposition, stat_shap_dict)
        explanation["decomposition"] = decomposition
        machines[mid] = explanation

    # Set expected_risk as population mean
    expected_risk = float(np.mean(all_risk_scores)) if all_risk_scores else 0.0
    for mid in machines:
        machines[mid]["expected_risk"] = round(expected_risk, 4)

    print(f"    {len(machines)} machines explained")
    print(f"    Population mean risk: {expected_risk:.4f}")

    # ── 6. Export ──
    print("  [5/5] Exporting results...")
    export_dashboard_json(machines, global_imp, output_dir)
    merge_shap_to_work_orders(decision_dir, machines, output_dir)

    print("  SHAP post-process complete.\n")

    return {
        "n_machines": len(machines),
        "expected_risk": expected_risk,
        "top_global_feature": global_imp[0]["label"] if global_imp else "",
        "dashboard_json": os.path.join(output_dir, "shap_dashboard.json"),
    }
