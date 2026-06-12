#!/usr/bin/env python3
"""
Skill 2: predictive-maintenance-stat-inference — Runner Script
===============================================================
Evaluate z-score baselines, compute Hotelling T2, analyze failure signatures,
and aggregate per-machine alert states.

Usage:
    python run.py --data-dir <raw_data> --prep-dir <data_prep_output> --output-dir <output>
"""

import sys, os, argparse, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_analysis import (
    evaluate_z_baseline,
    compute_hotelling_t2,
    evaluate_t2_baseline,
    analyze_failure_signatures,
    load_data,
    CONFIG,
)


def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance — Statistical Inference"
    )
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing raw CSV files")
    parser.add_argument("--prep-dir", required=True,
                        help="Directory containing data-prep outputs (z_scores.csv, etc.)")
    parser.add_argument("--output-dir", default="outputs_stat",
                        help="Directory for output files")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    prep_dir = os.path.abspath(args.prep_dir)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Data directory     : {data_dir}")
    print(f"Data-prep outputs  : {prep_dir}")
    print(f"Output directory   : {output_dir}")

    # Load raw data and z-scores
    print("\n[1/4] Loading data...")
    data = load_data(data_dir)
    df_log = data["log"]

    z_path = os.path.join(prep_dir, "z_scores.csv")
    if not os.path.exists(z_path):
        raise FileNotFoundError(f"z_scores.csv not found in {prep_dir}. Run data-prep first.")
    df_z = pd.read_csv(z_path)
    print(f"  Z-scores loaded: {df_z.shape[0]} rows × {df_z.shape[1]} cols")

    # Step 1: Evaluate z-score baseline
    print("\n[2/4] Evaluating z-score baselines...")
    z_eval = evaluate_z_baseline(df_z)
    best = z_eval["best_f1"]
    print(f"  Best F1 = {best['f1']:.3f} at threshold z > {best['threshold']}")
    print(f"  Precision = {best['precision']:.3f}, Recall = {best['recall']:.3f}")
    print(f"  FPR = {best['fpr']:.3f}")

    # Save threshold sweep
    pd.DataFrame(z_eval["threshold_results"]).to_csv(
        os.path.join(output_dir, "z_threshold_sweep.csv"), index=False
    )

    # Step 2: Hotelling T2
    print("\n[3/4] Computing Hotelling T2 statistics...")
    t2_df = compute_hotelling_t2(df_log)
    t2_eval = evaluate_t2_baseline(t2_df)
    print(f"  T2 F1 = {t2_eval['f1']:.3f}, Recall = {t2_eval['recall']:.3f}")
    t2_df.to_csv(os.path.join(output_dir, "t2_results.csv"), index=False)

    # Step 3: Failure signatures
    print("\n[4/4] Analyzing failure signatures...")
    sig_df = analyze_failure_signatures(df_log)
    sig_df.to_csv(os.path.join(output_dir, "failure_signature_analysis.csv"), index=False)

    # Aggregate per-machine alerts
    alerts = []
    for mid, grp in df_z.groupby("Equipment.Id"):
        latest = grp.sort_values("Date").iloc[-1]
        last_n = grp.sort_values("Date").tail(5)
        alerts.append({
            "machine_id": mid,
            "current_alert_level": latest["alert_level"],
            "z_comp_max": float(last_n["z_composite"].max()),
            "z_comp_mean": float(last_n["z_composite"].mean()),
            "z_v_last": float(latest.get("z_Voltage", 0)),
            "z_a_last": float(latest.get("z_Amperage", 0)),
            "z_t_last": float(latest.get("z_Temperature", 0)),
            "n_alarm_windows": int((grp["alert_level"] == "Alarm").sum()),
            "n_warning_windows": int((grp["alert_level"] == "Warning").sum()),
            "n_watch_windows": int((grp["alert_level"] == "Watch").sum()),
        })

    alerts_df = pd.DataFrame(alerts).sort_values("z_comp_max", ascending=False)
    alerts_df.to_csv(os.path.join(output_dir, "alert_summary.csv"), index=False)

    # Print top 10
    print("\n--- Top 10 Machines by Max Z-Composite ---")
    for rank, (_, row) in enumerate(alerts_df.head(10).iterrows(), 1):
        print(f"  #{rank} {row['machine_id']}: "
              f"z_max={row['z_comp_max']:.1f}, "
              f"z_mean={row['z_comp_mean']:.1f}, "
              f"level={row['current_alert_level']}")

    # Save evaluation summary JSON
    summary = {
        "z_baseline": {
            "best_f1_threshold": best["threshold"],
            "best_f1": best["f1"],
            "best_precision": best["precision"],
            "best_recall": best["recall"],
            "best_fpr": best["fpr"],
        },
        "t2_baseline": {
            "f1": t2_eval["f1"],
            "recall": t2_eval["recall"],
            "precision": t2_eval["precision"],
            "fpr": t2_eval["fpr"],
        },
        "failure_groups": CONFIG["failure_groups"],
        "n_machines_alarm": int((alerts_df["current_alert_level"] == "Alarm").sum()),
        "n_machines_warning": int((alerts_df["current_alert_level"] == "Warning").sum()),
        "n_machines_watch": int((alerts_df["current_alert_level"] == "Watch").sum()),
        "n_machines_normal": int((alerts_df["current_alert_level"] == "Normal").sum()),
    }
    with open(os.path.join(output_dir, "stat_inference_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Manifest
    manifest = {
        "prep_dir": prep_dir,
        "output_dir": output_dir,
        "files": {
            "z_threshold_sweep": "z_threshold_sweep.csv",
            "t2_results": "t2_results.csv",
            "failure_signature_analysis": "failure_signature_analysis.csv",
            "alert_summary": "alert_summary.csv",
            "stat_inference_summary": "stat_inference_summary.json",
        },
    }
    with open(os.path.join(output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nOutput files written to: {output_dir}/")
    for fname in manifest["files"].values():
        fpath = os.path.join(output_dir, fname)
        if os.path.exists(fpath):
            print(f"  {fname} ({os.path.getsize(fpath)/1024:.1f} KB)")

    print("\nStatistical inference complete.")
    return alerts_df, z_eval, t2_eval


if __name__ == "__main__":
    main()
