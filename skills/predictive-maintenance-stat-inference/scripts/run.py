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
# Also add ml-inference scripts path for RUL estimator
_ml_scripts = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..',
    'predictive-maintenance-ml-inference', 'scripts'
)
if os.path.exists(_ml_scripts):
    sys.path.insert(0, os.path.abspath(_ml_scripts))
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
    parser.add_argument("--skip-health-score", action="store_true",
                        help="Skip Equipment Health Score computation")
    parser.add_argument("--skip-backtest", action="store_true",
                        help="Skip Temporal Backtest validation")
    parser.add_argument("--backtest-threshold", default="Warning",
                        choices=["Watch", "Warning", "Alarm"],
                        help="Alert threshold for event-based backtest")
    parser.add_argument("--skip-rul", action="store_true",
                        help="Skip RUL (Remaining Useful Life) estimation")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    prep_dir = os.path.abspath(args.prep_dir)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Data directory     : {data_dir}")
    print(f"Data-prep outputs  : {prep_dir}")
    print(f"Output directory   : {output_dir}")

    # Load raw data and z-scores
    print("\n[1/6] Loading data...")
    data = load_data(data_dir)
    df_log = data["log"]

    z_path = os.path.join(prep_dir, "z_scores.csv")
    if not os.path.exists(z_path):
        raise FileNotFoundError(f"z_scores.csv not found in {prep_dir}. Run data-prep first.")
    df_z = pd.read_csv(z_path)
    print(f"  Z-scores loaded: {df_z.shape[0]} rows × {df_z.shape[1]} cols")

    # Step 1: Evaluate z-score baseline
    print("\n[2/6] Evaluating z-score baselines...")
    z_eval = evaluate_z_baseline(df_z)
    best = z_eval["best_f1"]
    print(f"  Best F1 = {best['f1']:.3f} at threshold z > {best['threshold']}")
    print(f"  Precision = {best['precision']:.3f}, Recall = {best['recall']:.3f}")
    print(f"  FPR = {best['fpr']:.3f}")

    # Evaluate weighted composite if layered baseline is available
    if "z_weighted_composite" in df_z.columns:
        from baseline_analysis import evaluate_z_baseline as eval_z
        df_w = df_z.copy()
        df_w["z_composite"] = df_w["z_weighted_composite"]
        w_eval = eval_z(df_w)
        w_best = w_eval["best_f1"]
        print(f"  Weighted z F1 = {w_best['f1']:.3f} (fault-group differentiated weights)")
        z_eval["weighted_best_f1"] = w_best["f1"]

    # Save threshold sweep
    pd.DataFrame(z_eval["threshold_results"]).to_csv(
        os.path.join(output_dir, "z_threshold_sweep.csv"), index=False
    )

    # Step 2: Hotelling T2
    print("\n[3/6] Computing Hotelling T2 statistics...")
    t2_df = compute_hotelling_t2(df_log)
    t2_eval = evaluate_t2_baseline(t2_df)
    print(f"  T2 F1 = {t2_eval['f1']:.3f}, Recall = {t2_eval['recall']:.3f}")
    t2_df.to_csv(os.path.join(output_dir, "t2_results.csv"), index=False)

    # Step 3: Failure signatures
    print("\n[4/6] Analyzing failure signatures...")
    sig_df = analyze_failure_signatures(df_log)
    sig_df.to_csv(os.path.join(output_dir, "failure_signature_analysis.csv"), index=False)

    # Aggregate per-machine alerts
    # Layered baseline columns (may not exist if old data-prep was used)
    has_layered = "baseline_source" in df_z.columns

    alerts = []
    for mid, grp in df_z.groupby("Equipment.Id"):
        latest = grp.sort_values("Date").iloc[-1]
        last_n = grp.sort_values("Date").tail(5)
        entry = {
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
        }
        if has_layered:
            entry["baseline_source"] = str(latest.get("baseline_source", "self"))
            entry["production_tier"] = str(latest.get("production_tier", "standard"))
            entry["z_weighted_max"] = float(last_n["z_weighted_composite"].max()) if "z_weighted_composite" in last_n.columns else float(last_n["z_composite"].max())
            entry["z_weighted_mean"] = float(last_n["z_weighted_composite"].mean()) if "z_weighted_composite" in last_n.columns else float(last_n["z_composite"].mean())
            entry["alert_threshold_watch"] = float(latest.get("alert_threshold_watch", 1.5))
            entry["alert_threshold_alarm"] = float(latest.get("alert_threshold_alarm", 2.5))
        alerts.append(entry)

    alerts_df = pd.DataFrame(alerts).sort_values("z_comp_max", ascending=False)
    alerts_df.to_csv(os.path.join(output_dir, "alert_summary.csv"), index=False)

    # Print top 10
    print("\n--- Top 10 Machines by Max Z-Composite ---")
    for rank, (_, row) in enumerate(alerts_df.head(10).iterrows(), 1):
        print(f"  #{rank} {row['machine_id']}: "
              f"z_max={row['z_comp_max']:.1f}, "
              f"z_mean={row['z_comp_mean']:.1f}, "
              f"level={row['current_alert_level']}")

    # Step 4: Equipment Health Score
    if not args.skip_health_score:
        print("\n[5/7] Building Equipment Health Score...")
        from health_score import build_equipment_health_score
        try:
            hscore_df = build_equipment_health_score(data_dir, prep_dir)
            hscore_path = os.path.join(output_dir, "equipment_health_score.csv")
            hscore_df.to_csv(hscore_path, index=False)
            n_healthy = int((hscore_df["health_level"] == "Healthy").sum())
            n_warn = int((hscore_df["health_level"] == "Warning").sum())
            n_degrad = int((hscore_df["health_level"] == "Degrading").sum())
            n_crit = int((hscore_df["health_level"] == "Critical").sum())
            print(f"  Health Score written: {len(hscore_df)} machines")
            print(f"  Healthy: {n_healthy}, Warning: {n_warn}, Degrading: {n_degrad}, Critical: {n_crit}")
            print(f"  Lowest health: {hscore_df.iloc[0]['Equipment.Id']} ({hscore_df.iloc[0]['health_score']:.0f})")
        except Exception as e:
            print(f"  [WARN] Health Score computation failed: {e}")
    else:
        print("\n[5/7] Equipment Health Score — SKIPPED")

    # Step 5: RUL Estimation (Remaining Useful Life)
    if not args.skip_rul and not args.skip_health_score:
        print("\n[6/7] Estimating RUL (Remaining Useful Life)...")
        try:
            from health_score import build_health_score_timeseries
            from rul_estimator import run_rul_pipeline

            ts_df = build_health_score_timeseries(data_dir, prep_dir, min_data_points=5)
            rul_df, rul_summary = run_rul_pipeline(ts_df)

            rul_path = os.path.join(output_dir, "rul_degradation.csv")
            rul_df.to_csv(rul_path, index=False)
            rul_summary_path = os.path.join(output_dir, "rul_summary.json")
            with open(rul_summary_path, "w") as f:
                json.dump(rul_summary, f, ensure_ascii=False, indent=2)

            # Also save timeseries for dashboard use
            ts_path = os.path.join(output_dir, "health_score_timeseries.csv")
            ts_df.to_csv(ts_path, index=False)

            print(f"  RUL written: {len(rul_df)} machines ({rul_summary['rul_available']} with RUL)")
            print(f"  Avg RUL: {rul_summary['avg_rul_hours']:.1f}h ({rul_summary['avg_rul_days']:.1f}d)")
            print(f"  Coverage: {rul_summary['coverage_rate']:.1%}")
            print(f"  Avg R2: {rul_summary['avg_r_squared']:.3f}")
        except Exception as e:
            print(f"  [WARN] RUL estimation failed: {e}")
            import traceback
            traceback.print_exc()
    elif args.skip_health_score:
        print("\n[6/7] RUL Estimation — SKIPPED (requires health score)")
    else:
        print("\n[6/7] RUL Estimation — SKIPPED")

    # Step 6: Quality-Cost Chain Analysis
    print("\n[7/7] Building Quality-Cost Chain Analysis...")
    try:
        from quality_cost_chain import build_quality_cost_chain
        chain_df, chain_summary = build_quality_cost_chain(data_dir, prep_dir)
        chain_df.to_csv(os.path.join(output_dir, "quality_cost_chain.csv"), index=False)
        with open(os.path.join(output_dir, "quality_cost_chain_summary.json"), "w") as f:
            json.dump(chain_summary, f, ensure_ascii=False, indent=2)
        n_measured = chain_summary["n_with_quality_data"]
        total_risk = chain_summary["total_annual_quality_cost_risk"]
        strongest = chain_summary["strongest_param_quality_link"]
        print(f"  Quality-Cost Chain: {len(chain_df)} machines ({n_measured} with quality data)")
        print(f"  Total annual quality cost risk: ${total_risk:,.0f}")
        print(f"  Strongest param→quality link: {strongest['parameter']} (ρ={strongest['spearman_r']:.2f})")
    except Exception as e:
        print(f"  [WARN] Quality-Cost Chain failed: {e}")

    # Step 7: Temporal Backtest
    if not args.skip_backtest:
        print("\n[7/7] Running Temporal Backtest Validation...")
        try:
            from backtest_validator import run_backtest_pipeline
            backtest_output_dir = os.path.join(output_dir, "backtest")
            bt_summary = run_backtest_pipeline(
                data_dir=data_dir,
                prep_dir=prep_dir,
                output_dir=backtest_output_dir,
                alert_threshold=args.backtest_threshold,
            )
            print(f"  Backtest complete: {bt_summary['event_based'][args.backtest_threshold]['total_events']} events analyzed")
        except Exception as e:
            print(f"  [WARN] Temporal Backtest failed: {e}")
    else:
        print("\n[7/7] Temporal Backtest — SKIPPED")

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
    if has_layered:
        summary["layered_baseline"] = {
            "baseline_sources": {
                "self": int((alerts_df["baseline_source"] == "self").sum()) if "baseline_source" in alerts_df.columns else 0,
                "hybrid": int((alerts_df["baseline_source"] == "hybrid").sum()) if "baseline_source" in alerts_df.columns else 0,
                "cluster": int((alerts_df["baseline_source"] == "cluster").sum()) if "baseline_source" in alerts_df.columns else 0,
            },
            "production_tiers": {
                "critical": int((alerts_df["production_tier"] == "critical").sum()) if "production_tier" in alerts_df.columns else 0,
                "standard": int((alerts_df["production_tier"] == "standard").sum()) if "production_tier" in alerts_df.columns else 0,
                "auxiliary": int((alerts_df["production_tier"] == "auxiliary").sum()) if "production_tier" in alerts_df.columns else 0,
            },
            "tier_thresholds": CONFIG["production_tiers"],
            "fault_group_weights": CONFIG["fault_group_weights"],
        }
    with open(os.path.join(output_dir, "stat_inference_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Manifest
    manifest_files = {
        "z_threshold_sweep": "z_threshold_sweep.csv",
        "t2_results": "t2_results.csv",
        "failure_signature_analysis": "failure_signature_analysis.csv",
        "alert_summary": "alert_summary.csv",
        "stat_inference_summary": "stat_inference_summary.json",
    }
    if not args.skip_health_score and os.path.exists(os.path.join(output_dir, "equipment_health_score.csv")):
        manifest_files["equipment_health_score"] = "equipment_health_score.csv"
    if not args.skip_rul and os.path.exists(os.path.join(output_dir, "rul_degradation.csv")):
        manifest_files["rul_degradation"] = "rul_degradation.csv"
        manifest_files["rul_summary"] = "rul_summary.json"
        manifest_files["health_score_timeseries"] = "health_score_timeseries.csv"
    if os.path.exists(os.path.join(output_dir, "quality_cost_chain.csv")):
        manifest_files["quality_cost_chain"] = "quality_cost_chain.csv"
    if not args.skip_backtest:
        bt_dir = os.path.join(output_dir, "backtest")
        if os.path.exists(os.path.join(bt_dir, "backtest_summary.json")):
            manifest_files["backtest_summary"] = "backtest/backtest_summary.json"
            manifest_files["backtest_lead_time_summary"] = "backtest/backtest_lead_time_summary.csv"
            manifest_files["backtest_by_fault_group"] = "backtest/backtest_by_fault_group.csv"
            manifest_files["backtest_walk_forward"] = "backtest/backtest_walk_forward.csv"
            manifest_files["backtest_point_in_time"] = "backtest/backtest_point_in_time.csv"

    manifest = {
        "prep_dir": prep_dir,
        "output_dir": output_dir,
        "files": manifest_files,
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
