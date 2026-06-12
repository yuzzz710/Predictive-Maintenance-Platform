#!/usr/bin/env python3
"""
Skill 5: predictive-maintenance-decision — Runner Script
==========================================================
Multi-signal fusion → Action recommendation → Work order generation.
The final skill in the pipeline — produces prioritized, cost-justified
maintenance work orders.

Usage:
    python run.py --data-dir <raw_data> --prep-dir <data_prep_output> \
                  --stat-dir <stat_inference_output> \
                  [--ml-dir <ml_inference_output>] \
                  [--diag-dir <diagnosis_output>] \
                  --output-dir <output>
"""

import sys, os, argparse, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maintenance_decision_engine import (
    MaintenanceDecisionEngine,
    build_signal_from_row,
    WorkOrder,
)


def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance — Decision Engine"
    )
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing raw CSV files")
    parser.add_argument("--prep-dir", required=True,
                        help="Directory containing data-prep outputs")
    parser.add_argument("--stat-dir", default=None,
                        help="Directory containing stat-inference outputs")
    parser.add_argument("--ml-dir", default=None,
                        help="Directory containing ml-inference outputs")
    parser.add_argument("--diag-dir", default=None,
                        help="Directory containing diagnosis outputs")
    parser.add_argument("--output-dir", default="outputs_decision",
                        help="Directory for output files")
    parser.add_argument("--streaming", action="store_true",
                        help="Enable continuous confirmation mode")
    parser.add_argument("--max-orders", type=int, default=20,
                        help="Maximum work orders per cycle (default: 20)")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    prep_dir = os.path.abspath(args.prep_dir)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Data directory    : {data_dir}")
    print(f"Data-prep outputs : {prep_dir}")
    print(f"Stat-inference    : {args.stat_dir or 'not provided'}")
    print(f"ML-inference      : {args.ml_dir or 'not provided'}")
    print(f"Diagnosis         : {args.diag_dir or 'not provided'}")
    print(f"Output directory  : {output_dir}")
    print(f"Streaming mode    : {args.streaming}")
    print(f"Max orders/cycle  : {args.max_orders}")

    # ── Load inputs ──────────────────────────────────────────────────

    # Cost risk data (required)
    cost_path = os.path.join(prep_dir, "cost_risk_matrix.csv")
    if not os.path.exists(cost_path):
        raise FileNotFoundError(f"cost_risk_matrix.csv not found in {prep_dir}")
    cost_df = pd.read_csv(cost_path)
    print(f"\nCost data: {len(cost_df)} machines")

    # Alert summary (from stat-inference)
    alert_path = None
    for candidate in [
        os.path.join(args.stat_dir, "alert_summary.csv") if args.stat_dir else None,
        os.path.join(prep_dir, "alert_summary.csv"),
    ]:
        if candidate and os.path.exists(candidate):
            alert_path = candidate
            break

    # Z-scores (for enrichment)
    z_path = os.path.join(prep_dir, "z_scores.csv")
    df_z = pd.read_csv(z_path) if os.path.exists(z_path) else None

    # ML predictions (optional)
    pred_df = None
    if args.ml_dir:
        for candidate in [
            os.path.join(args.ml_dir, "prediction_report.csv"),
            os.path.join(args.ml_dir, "model_outputs", "prediction_report.csv"),
            os.path.join(args.ml_dir, "prediction_report_all_machines.csv"),
        ]:
            if os.path.exists(candidate):
                pred_df = pd.read_csv(candidate)
                print(f"ML predictions: {len(pred_df)} machines")
                break

    # Diagnosis (optional)
    diag_df = None
    if args.diag_dir:
        diag_path = os.path.join(args.diag_dir, "diagnosis_report.csv")
        if os.path.exists(diag_path):
            diag_df = pd.read_csv(diag_path)

    # ── Build z-score aggregates per machine ─────────────────────────
    z_agg = {}
    if df_z is not None:
        if "Date" in df_z.columns:
            df_z["Date"] = pd.to_datetime(df_z["Date"])
        for mid, grp in df_z.groupby("Equipment.Id"):
            try:
                grp_sorted = grp.sort_values("Date") if "Date" in grp.columns else grp
                latest = grp_sorted.iloc[-1]
                last_n = grp_sorted.tail(5)
            except (KeyError, TypeError):
                latest = grp.iloc[-1]
                last_n = grp.tail(5)

            z_agg[mid] = {
                "z_v_last": float(latest.get("z_Voltage", 0)),
                "z_a_last": float(latest.get("z_Amperage", 0)),
                "z_t_last": float(latest.get("z_Temperature", 0)),
                "z_comp_mean": float(last_n["z_composite"].mean()),
                "z_comp_max": float(last_n["z_composite"].max()),
                "thermal_over_p95": int(last_n["z_Temperature"].abs().gt(2.0).sum()),
                "v_slope": float(last_n["z_Voltage"].diff().mean()) if len(last_n) >= 3 else 0.0,
                "t_slope": float(last_n["z_Temperature"].diff().mean()) if len(last_n) >= 3 else 0.0,
                "a_slope": float(last_n["z_Amperage"].diff().mean()) if len(last_n) >= 3 else 0.0,
            }

    # ── Initialize engine ────────────────────────────────────────────
    config_override = {
        "work_order": {"max_orders_per_cycle": args.max_orders},
    }
    engine = MaintenanceDecisionEngine(cost_risk_data=cost_df, config=config_override)

    # ── Build signal list ────────────────────────────────────────────
    signal_list = []

    # Use alert_summary as primary machine list
    if alert_path and os.path.exists(alert_path):
        alert_df = pd.read_csv(alert_path)
        machine_list = alert_df.to_dict("records")
    else:
        # Build from z_scores
        machine_list = []
        for mid in z_agg:
            machine_list.append({"machine_id": mid})
    print(f"Building signals for {len(machine_list)} machines...")

    for row in machine_list:
        mid = str(row.get("machine_id", row.get("Equipment.Id", "unknown")))
        if not mid or mid == "unknown":
            continue

        signals = {
            "machine_id": mid,
            "ml_fault_density": 0.7,  # default
            "z_comp_mean": 0.0,
            "z_comp_max": 0.0,
            "z_v": 0.0, "z_a": 0.0, "z_t": 0.0,
            "thermal_over_p95": 0,
            "voltage_trend_slope": 0.0,
            "temp_trend_slope": 0.0,
            "amperage_trend_slope": 0.0,
            "cost_at_risk": 5000.0,
        }

        # Enrich with z-score aggregates
        if mid in z_agg:
            z = z_agg[mid]
            signals.update({
                "z_v": z["z_v_last"], "z_a": z["z_a_last"], "z_t": z["z_t_last"],
                "z_comp_mean": z["z_comp_mean"], "z_comp_max": z["z_comp_max"],
                "voltage_trend_slope": z["v_slope"],
                "temp_trend_slope": z["t_slope"],
                "amperage_trend_slope": z["a_slope"],
                "thermal_over_p95": z["thermal_over_p95"],
            })

        # Enrich with ML predictions
        if pred_df is not None:
            pr = pred_df[pred_df["machine_id"] == mid]
            if len(pr) > 0:
                signals["ml_fault_density"] = float(pr.iloc[0].get("fault_density_pred", 0.7))

        # Enrich with cost data
        cost_row = cost_df[cost_df["Equipment.Id"] == mid]
        if len(cost_row) > 0:
            signals["cost_at_risk"] = float(cost_row.iloc[0]["cost_at_risk"])

        signal_list.append(signals)

    # ── Run evaluation ───────────────────────────────────────────────
    print(f"\nEvaluating {len(signal_list)} machines...")
    batch_df = engine.evaluate_batch(signal_list)

    # Save full evaluation report
    report_path = os.path.join(output_dir, "maintenance_decision_report.csv")
    batch_df.to_csv(report_path, index=False, float_format="%.4f")
    print(f"Decision report: {batch_df.shape[0]} machines → {report_path}")

    # ── Generate work orders ─────────────────────────────────────────
    work_orders = engine.generate_work_orders()

    if work_orders:
        order_rows = [{
            "priority": o.priority,
            "machine_id": o.machine_id,
            "alert_level": o.alert_level.name,
            "action_type": o.action_type.value,
            "cost_at_risk": round(o.cost_at_risk, 2),
            "urgency_score": round(o.urgency_score, 1),
            "window_days": o.recommended_window_days,
            "expected_savings": round(o.expected_savings, 2),
            "suggestion": o.maintenance_suggestion,
        } for o in work_orders]

        orders_df = pd.DataFrame(order_rows)
        orders_path = os.path.join(output_dir, "maintenance_work_orders.csv")
        orders_df.to_csv(orders_path, index=False, float_format="%.2f")
        print(f"Work orders: {len(orders_df)} active → {orders_path}")

        # Print work orders
        print("\n" + "=" * 70)
        print("PRIORITIZED MAINTENANCE WORK ORDERS")
        print("=" * 70)
        for o in work_orders:
            print(f"\n[{o.priority}] {o.machine_id} | {o.alert_level.name} | {o.action_type.value}")
            print(f"    Urgency: {o.urgency_score:.0f}/100 | Cost at risk: ${o.cost_at_risk:,.0f}")
            print(f"    Window: {o.recommended_window_days} day(s) | Savings: ${o.expected_savings:,.0f}")
            print(f"    {o.maintenance_suggestion[:150]}")
    else:
        print("\nNo active work orders — all machines NORMAL or ROUTINE_CHECK.")

    # ── Generate text report ─────────────────────────────────────────
    report_text = engine.generate_batch_report(batch_df)
    report_txt_path = os.path.join(output_dir, "maintenance_report.txt")
    with open(report_txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nText report: {report_txt_path}")

    # ── Summary JSON ─────────────────────────────────────────────────
    summary = {
        "n_machines_evaluated": len(batch_df),
        "alert_distribution": {
            level: int((batch_df["alert_level"] == level).sum())
            for level in ["ALARM", "WARNING", "WATCH", "NORMAL"]
        },
        "action_distribution": {
            action: int((batch_df["action_type"] == action).sum())
            for action in batch_df["action_type"].unique()
        },
        "n_work_orders": len(work_orders),
        "top_5_urgent": [
            {"machine_id": o.machine_id, "urgency": o.urgency_score,
             "action": o.action_type.value, "cost": o.cost_at_risk}
            for o in work_orders[:5]
        ] if work_orders else [],
    }
    with open(os.path.join(output_dir, "decision_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # ── Manifest ─────────────────────────────────────────────────────
    manifest = {
        "data_dir": data_dir,
        "prep_dir": prep_dir,
        "output_dir": output_dir,
        "files": {
            "decision_report": "maintenance_decision_report.csv",
            "work_orders": "maintenance_work_orders.csv",
            "text_report": "maintenance_report.txt",
            "decision_summary": "decision_summary.json",
        },
        "summary": summary,
    }
    with open(os.path.join(output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nAll outputs saved to: {output_dir}/")
    print("\nDecision engine complete.")
    return batch_df, work_orders


if __name__ == "__main__":
    main()
