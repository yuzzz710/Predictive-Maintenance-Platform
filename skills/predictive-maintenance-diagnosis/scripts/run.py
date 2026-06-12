#!/usr/bin/env python3
"""
Skill 4: predictive-maintenance-diagnosis — Runner Script
===========================================================
Anomaly pattern recognition + predictability limitation analysis.
Fuses stat-inference and ml-inference outputs to produce diagnostic reports.

Usage:
    python run.py --data-dir <raw_data> --prep-dir <data_prep_output> \
                  --stat-dir <stat_inference_output> --ml-dir <ml_inference_output> \
                  --output-dir <output>
"""

import sys, os, argparse, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def diagnose_machines(alert_df, pred_df, cost_df):
    """
    Run pattern diagnosis for each machine using the diagnostic rules
    from maintenance_decision_engine.
    """
    from maintenance_decision_engine import MaintenanceDecisionEngine

    engine = MaintenanceDecisionEngine(cost_risk_data=cost_df)

    results = []
    for _, row in alert_df.iterrows():
        mid = row["machine_id"]

        # Build signals dict
        signals = {
            "machine_id": mid,
            "z_v": float(row.get("z_v_last", 0)),
            "z_a": float(row.get("z_a_last", 0)),
            "z_t": float(row.get("z_t_last", 0)),
            "z_comp_mean": float(row.get("z_comp_mean", 0)),
            "z_comp_max": float(row.get("z_comp_max", 0)),
            "voltage_trend_slope": float(row.get("v_slope", 0)),
            "temp_trend_slope": float(row.get("t_slope", 0)),
            "amperage_trend_slope": float(row.get("a_slope", 0)),
            "thermal_over_p95": int(row.get("n_alarm_windows", 0)),
            "ml_fault_density": 0.7,
            "cost_at_risk": float(row.get("cost_at_risk", 5000)),
        }

        # Enrich with ML prediction if available
        if pred_df is not None:
            pred_row = pred_df[pred_df["machine_id"] == mid]
            if len(pred_row) > 0:
                signals["ml_fault_density"] = float(pred_row.iloc[0].get(
                    "fault_density_pred", 0.7
                ))

        # Enrich with cost data
        if cost_df is not None:
            cost_row = cost_df[cost_df["Equipment.Id"] == mid]
            if len(cost_row) > 0:
                signals["cost_at_risk"] = float(cost_row.iloc[0]["cost_at_risk"])

        diagnosis = engine.diagnose(signals)
        results.append({
            "machine_id": mid,
            "primary_pattern": diagnosis.primary_pattern,
            "patterns_detected": "|".join(diagnosis.patterns_detected) if diagnosis.patterns_detected else "none",
            "diagnosis_confidence": round(diagnosis.confidence, 3),
            "evidence_voltage_drift": round(diagnosis.evidence.get("voltage_drift", 0), 3),
            "evidence_thermal_buildup": round(diagnosis.evidence.get("thermal_buildup", 0), 3),
            "evidence_power_anomaly": round(diagnosis.evidence.get("power_anomaly", 0), 3),
            "evidence_combined_degradation": round(diagnosis.evidence.get("combined_degradation", 0), 3),
        })

    return pd.DataFrame(results)


def run_predictability_analysis(data_dir, output_dir):
    """
    Run the 5-dimension predictability limitation analysis.
    """
    import predictability_analysis as pa

    pa.DATA_DIR = data_dir
    pa.OUTPUT_DIR = output_dir
    pa.FIGURE_DIR = os.path.join(output_dir, "figures")
    os.makedirs(pa.OUTPUT_DIR, exist_ok=True)
    os.makedirs(pa.FIGURE_DIR, exist_ok=True)

    print("Running 5-dimension predictability analysis...")
    pa.main()
    print("  Predictability analysis complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance — Diagnosis"
    )
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing raw CSV files")
    parser.add_argument("--prep-dir", required=True,
                        help="Directory containing data-prep outputs")
    parser.add_argument("--stat-dir", default=None,
                        help="Directory containing stat-inference outputs")
    parser.add_argument("--ml-dir", default=None,
                        help="Directory containing ml-inference outputs")
    parser.add_argument("--output-dir", default="outputs_diagnosis",
                        help="Directory for output files")
    parser.add_argument("--skip-predictability", action="store_true",
                        help="Skip the long-running predictability analysis")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    prep_dir = os.path.abspath(args.prep_dir)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Data directory    : {data_dir}")
    print(f"Data-prep outputs : {prep_dir}")
    print(f"Stat-inference    : {args.stat_dir or 'not provided'}")
    print(f"ML-inference      : {args.ml_dir or 'not provided'}")
    print(f"Output directory  : {output_dir}")

    # Load inputs
    alert_path = None
    if args.stat_dir:
        alert_path = os.path.join(args.stat_dir, "alert_summary.csv")
    if not alert_path or not os.path.exists(alert_path):
        # Try prep_dir as fallback (stat-inference might output there)
        alert_path = os.path.join(prep_dir, "alert_summary.csv")
    if not os.path.exists(alert_path):
        # Build alerts directly from z_scores
        print("  No alert_summary.csv found, building from z_scores...")
        z_path = os.path.join(prep_dir, "z_scores.csv")
        if os.path.exists(z_path):
            df_z = pd.read_csv(z_path)
            alerts = []
            for mid, grp in df_z.groupby("Equipment.Id"):
                try:
                    latest = grp.sort_values("Date").iloc[-1]
                except KeyError:
                    latest = grp.iloc[-1]
                alerts.append({
                    "machine_id": mid,
                    "z_comp_max": float(grp["z_composite"].max()),
                    "z_comp_mean": float(grp["z_composite"].mean()),
                    "z_v_last": float(latest.get("z_Voltage", 0)),
                    "z_a_last": float(latest.get("z_Amperage", 0)),
                    "z_t_last": float(latest.get("z_Temperature", 0)),
                    "n_alarm_windows": 0,
                })
            alert_df = pd.DataFrame(alerts)
        else:
            raise FileNotFoundError(f"Cannot find z_scores.csv in {prep_dir}")
    else:
        alert_df = pd.read_csv(alert_path)

    print(f"  Alert data: {alert_df.shape[0]} machines")

    # Load cost data
    cost_path = os.path.join(prep_dir, "cost_risk_matrix.csv")
    cost_df = pd.read_csv(cost_path) if os.path.exists(cost_path) else None

    # Load ML predictions if available
    pred_df = None
    if args.ml_dir:
        pred_path = None
        for candidate in [
            os.path.join(args.ml_dir, "prediction_report.csv"),
            os.path.join(args.ml_dir, "model_outputs", "prediction_report.csv"),
        ]:
            if os.path.exists(candidate):
                pred_path = candidate
                break
        if os.path.exists(pred_path):
            pred_df = pd.read_csv(pred_path)
            print(f"  ML predictions loaded: {pred_df.shape[0]} machines")

    # Step 1: Pattern diagnosis
    print("\n[1/2] Running anomaly pattern diagnosis...")
    diag_df = diagnose_machines(alert_df, pred_df, cost_df)
    diag_df.to_csv(os.path.join(output_dir, "diagnosis_report.csv"), index=False)

    # Summary
    print("\n--- Anomaly Pattern Distribution ---")
    for pattern, count in diag_df["primary_pattern"].value_counts().items():
        print(f"  {pattern}: {count} machines")

    # Step 2: Predictability analysis (optional, slow)
    if not args.skip_predictability:
        print("\n[2/2] Running predictability limitation analysis...")
        try:
            run_predictability_analysis(data_dir, output_dir)
        except Exception as e:
            print(f"  Note: Predictability analysis skipped due to: {e}")
            print(f"  (This is OK — it requires additional data files from v2 model outputs)")
    else:
        print("\n[2/2] Predictability analysis skipped (--skip-predictability)")

    # Manifest
    manifest = {
        "data_dir": data_dir,
        "prep_dir": prep_dir,
        "output_dir": output_dir,
        "files": {
            "diagnosis_report": "diagnosis_report.csv",
        },
        "pattern_distribution": diag_df["primary_pattern"].value_counts().to_dict(),
    }
    with open(os.path.join(output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nOutput files written to: {output_dir}/")
    for fname in manifest["files"].values():
        fpath = os.path.join(output_dir, fname)
        if os.path.exists(fpath):
            print(f"  {fname} ({os.path.getsize(fpath)/1024:.1f} KB)")

    print("\nDiagnosis complete.")


if __name__ == "__main__":
    main()
