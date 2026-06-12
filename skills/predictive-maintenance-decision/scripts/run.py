#!/usr/bin/env python3
"""
Skill 5: predictive-maintenance-decision — Runner Script
==========================================================
Multi-signal fusion → Action recommendation → Work order generation.
The final skill in the pipeline — produces prioritized, cost-justified
maintenance work orders AND industrial-grade executable plan.

Usage:
    python run.py --data-dir <raw_data> --prep-dir <data_prep_output> \
                  --stat-dir <stat_inference_output> \
                  [--ml-dir <ml_inference_output>] \
                  [--diag-dir <diagnosis_output>] \
                  [--strategy cost_efficiency|production_efficiency|quality_first] \
                  --output-dir <output>
"""

import sys, os, argparse, json, shutil
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maintenance_decision_engine import (
    MaintenanceDecisionEngine,
    IndustrialMaintenanceEngine,
    build_signal_from_row,
    WorkOrder,
)
from strategy_selector import StrategySelector, MaintenanceStrategy
from sensor_upgrade_roadmap import SensorUpgradeRoadmapEngine


def _load_health_scores(stat_dir, prep_dir, data_dir):
    """Load equipment health scores from stat-inference output or data-prep."""
    candidates = []
    if stat_dir:
        candidates.append(os.path.join(stat_dir, "equipment_health_score.csv"))
    if prep_dir:
        candidates.append(os.path.join(prep_dir, "equipment_health_score.csv"))
    candidates.append(os.path.join(data_dir, "equipment_health_score.csv"))

    for path in candidates:
        if os.path.exists(path):
            return pd.read_csv(path)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance — Decision Engine + Industrial Plan"
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
    parser.add_argument("--strategy", default="production_efficiency",
                        choices=["cost_efficiency", "production_efficiency", "quality_first"],
                        help="Maintenance strategy (default: production_efficiency)")
    parser.add_argument("--max-budget", type=float, default=0,
                        help="Maximum preventive maintenance budget in USD (0=unlimited)")
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
    print(f"Strategy          : {args.strategy}")

    # ── Load inputs ──────────────────────────────────────────────────
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

    # Z-scores
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

    # Health scores
    health_df = _load_health_scores(args.stat_dir, prep_dir, data_dir)
    if health_df is not None:
        print(f"Health scores: {len(health_df)} machines")

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

    # ── Initialize engines ────────────────────────────────────────────
    config_override = {
        "work_order": {
            "max_orders_per_cycle": args.max_orders,
            "max_budget": args.max_budget,
        },
    }
    engine = MaintenanceDecisionEngine(cost_risk_data=cost_df, config=config_override)
    industrial_engine = IndustrialMaintenanceEngine(
        cost_risk_data=cost_df,
        config=config_override,
        strategy=args.strategy,
        health_score_df=health_df,
    )

    # ── Build signal list ────────────────────────────────────────────
    signal_list = []
    if alert_path and os.path.exists(alert_path):
        alert_df = pd.read_csv(alert_path)
        machine_list = alert_df.to_dict("records")
    else:
        machine_list = [{"machine_id": mid} for mid in z_agg]
    print(f"Building signals for {len(machine_list)} machines...")

    for row in machine_list:
        mid = str(row.get("machine_id", row.get("Equipment.Id", "unknown")))
        if not mid or mid == "unknown":
            continue
        signals = {
            "machine_id": mid,
            "ml_fault_density": 0.7,
            "z_comp_mean": 0.0, "z_comp_max": 0.0,
            "z_v": 0.0, "z_a": 0.0, "z_t": 0.0,
            "thermal_over_p95": 0,
            "voltage_trend_slope": 0.0, "temp_trend_slope": 0.0,
            "amperage_trend_slope": 0.0,
            "cost_at_risk": 5000.0,
        }
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
        if pred_df is not None:
            pr = pred_df[pred_df["machine_id"] == mid]
            if len(pr) > 0:
                signals["ml_fault_density"] = float(pr.iloc[0].get("fault_density_pred", 0.7))
        cost_row = cost_df[cost_df["Equipment.Id"] == mid]
        if len(cost_row) > 0:
            signals["cost_at_risk"] = float(cost_row.iloc[0]["cost_at_risk"])
        signal_list.append(signals)

    # ── PHASE A: Original Pipeline (backward-compatible) ───────────────
    print(f"\n[Phase A] Running base evaluation for {len(signal_list)} machines...")
    batch_df = engine.evaluate_batch(signal_list)

    report_path = os.path.join(output_dir, "maintenance_decision_report.csv")
    batch_df.to_csv(report_path, index=False, float_format="%.4f")
    print(f"Decision report: {batch_df.shape[0]} machines → {report_path}")

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
    else:
        print("No active work orders — all machines NORMAL or ROUTINE_CHECK.")
        orders_df = pd.DataFrame()

    # Text report
    report_text = engine.generate_batch_report(batch_df)
    report_txt_path = os.path.join(output_dir, "maintenance_report.txt")
    with open(report_txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # ── PHASE B: Industrial Maintenance Plan (NEW) ─────────────────────
    print(f"\n[Phase B] Generating industrial maintenance plan (strategy={args.strategy})...")
    plan_df = industrial_engine.generate_industrial_plan(signal_list)

    plan_path = os.path.join(output_dir, "industrial_maintenance_plan.csv")
    plan_df.to_csv(plan_path, index=False, float_format="%.4f", encoding="utf-8")
    print(f"Industrial plan: {plan_df.shape[0]} machines → {plan_path}")

    # Load spare parts catalog for per-part unit cost lookup
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parts_catalog_path = os.path.join(script_dir, "data", "spare_parts_catalog.json")
    parts_cost_lookup = {}
    if os.path.exists(parts_catalog_path):
        with open(parts_catalog_path, 'r', encoding='utf-8') as f:
            catalog_data = json.load(f)
        for entry in catalog_data.get("catalog", []):
            for part in entry.get("parts", []):
                parts_cost_lookup[part["name"]] = part.get("unit_cost", 0)
        for part in catalog_data.get("common_parts", []):
            parts_cost_lookup[part["name"]] = part.get("unit_cost", 0)

    # Spare Parts Plan
    parts_rows = []
    for _, row in plan_df.iterrows():
        try:
            parts_list = json.loads(row["spare_parts"])
        except (json.JSONDecodeError, TypeError):
            parts_list = []
        for p_name in parts_list:
            unit_cost = parts_cost_lookup.get(p_name, 0)
            parts_rows.append({
                "machine_id": row["machine_id"],
                "primary_pattern": row.get("primary_pattern", ""),
                "part_name": p_name,
                "unit_cost": unit_cost,
                "estimated_cost": unit_cost,  # per-part cost from catalog
            })
    if parts_rows:
        parts_df = pd.DataFrame(parts_rows)
        parts_path = os.path.join(output_dir, "spare_parts_plan.csv")
        parts_df.to_csv(parts_path, index=False, encoding="utf-8")
        print(f"Spare parts plan: {len(parts_df)} rows → {parts_path}")

    # Technician Schedule
    tech_rows = []
    for _, row in plan_df.iterrows():
        tech_rows.append({
            "machine_id": row["machine_id"],
            "technician_type": row.get("technician_type", ""),
            "technician_count": row.get("technician_count", 1),
            "estimated_hours": row.get("estimated_duration_hours", 1.0),
            "cost_tier": row.get("tech_cost_tier", "standard"),
            "labor_savings_per_hour": row.get("tech_labor_savings", 0.0),
            "maintenance_priority": row.get("maintenance_priority", "P3"),
            "estimated_start": row.get("downtime_start", ""),
        })
    if tech_rows:
        tech_df = pd.DataFrame(tech_rows)
        tech_path = os.path.join(output_dir, "technician_schedule.csv")
        tech_df.to_csv(tech_path, index=False, encoding="utf-8")
        print(f"Technician schedule: {len(tech_df)} rows → {tech_path}")

    # Downtime Schedule
    downtime_rows = []
    for _, row in plan_df.iterrows():
        downtime_rows.append({
            "machine_id": row["machine_id"],
            "downtime_window": row.get("recommended_downtime_window", ""),
            "downtime_start": row.get("downtime_start", ""),
            "estimated_duration_hours": row.get("estimated_duration_hours", 1.0),
            "production_impact_usd": row.get("production_impact", 0.0),
            "urgency_score": row.get("urgency_score", 0.0),
            "cost_at_risk": row.get("cost_at_risk", 0.0),
        })
    if downtime_rows:
        downtime_df = pd.DataFrame(downtime_rows)
        downtime_path = os.path.join(output_dir, "downtime_schedule.csv")
        downtime_df.to_csv(downtime_path, index=False, encoding="utf-8")
        print(f"Downtime schedule: {len(downtime_df)} rows → {downtime_path}")

    # Strategy Comparison
    comp_df = industrial_engine.strategy_selector.generate_strategy_comparison(
        signal_list, engine
    )
    comp_path = os.path.join(output_dir, "strategy_comparison.csv")
    comp_df.to_csv(comp_path, index=False, encoding="utf-8")
    print(f"Strategy comparison: 3 rows → {comp_path}")

    # ── OR Optimization: Knapsack vs Greedy Comparison ──
    print(f"\n[OR] Generating knapsack optimization comparison...")
    strat_sel = industrial_engine.strategy_selector
    # Build risk-scored candidates from plan_df (has risk_score and cost data)
    or_comparison = strat_sel.generate_optimization_comparison(plan_df, strat_sel.config)
    if or_comparison:
        or_rows = []
        for key, val in or_comparison.items():
            if not isinstance(val, (list, dict)):
                or_rows.append({"metric": key, "value": val})
        or_df = pd.DataFrame(or_rows)
        or_path = os.path.join(output_dir, "optimization_comparison.csv")
        or_df.to_csv(or_path, index=False, encoding="utf-8")
        print(f"OR optimization comparison: {len(or_df)} metrics → {or_path}")
    else:
        print("OR optimization comparison: skipped (budget not set, use --max-budget > 0 to enable)")

    # ── OR Optimization: Maintenance Scheduling (14-day rolling window) ──
    print(f"\n[Scheduler] Generating optimized 14-day maintenance schedule...")
    from maintenance_scheduler import MaintenanceScheduler
    scheduler = MaintenanceScheduler(horizon_days=14)
    schedule_df = scheduler.schedule(plan_df)
    sched_path = os.path.join(output_dir, "maintenance_schedule_optimized.csv")
    schedule_df.to_csv(sched_path, index=False, encoding="utf-8")
    sched_summary = scheduler.get_summary()
    print(f"Maintenance schedule: {len(schedule_df)} orders → {sched_path}")
    print(f"  On-time: {sched_summary['n_ontime']}/{len(schedule_df)} (score={sched_summary['total_weighted_tardiness']})")

    # Rule vs optimized comparison
    sched_comp = scheduler.compare_with_rules(plan_df)
    sched_comp_path = os.path.join(output_dir, "scheduling_comparison.json")
    with open(sched_comp_path, "w", encoding="utf-8") as f:
        json.dump(sched_comp, f, indent=2, ensure_ascii=False)
    print(f"Scheduling comparison → {sched_comp_path}")

    # ── OR Optimization: (s,S) Inventory Policy ──
    print(f"\n[Inventory] Generating (s,S) inventory policy...")
    from inventory_optimizer import InventoryOptimizer
    inv_opt = InventoryOptimizer(args.strategy)
    parts_catalog = os.path.join(script_dir, "data", "spare_parts_catalog.json")
    log_csv = os.path.join(data_dir, "MACHINE_LOG_DATA._2025.csv")
    inv_df = inv_opt.optimize(parts_catalog, log_csv)
    inv_path = os.path.join(output_dir, "inventory_policy_optimized.csv")
    inv_df.to_csv(inv_path, index=False, encoding="utf-8")
    n_high = (inv_df["stockout_risk"].isin(["critical", "high"])).sum()
    print(f"Inventory policy: {len(inv_df)} parts → {inv_path}")
    print(f"  High-risk parts: {n_high}/{len(inv_df)}")

    # ── OR Optimization: Pareto Frontier ──
    print(f"\n[Pareto] Generating 3-objective Pareto frontier...")
    from pareto_optimizer import ParetoOptimizer
    pareto_opt = ParetoOptimizer(comp_df, plan_df)
    pareto_data = pareto_opt.generate_frontiers()
    pareto_path = os.path.join(output_dir, "pareto_frontier.json")
    with open(pareto_path, "w", encoding="utf-8") as f:
        json.dump(pareto_data, f, indent=2, ensure_ascii=False)
    print(f"Pareto frontier: {len(pareto_data['pareto_3d_points'])} points → {pareto_path}")

    # Acceptance Rules (copy to output)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rules_src = os.path.join(script_dir, "data", "acceptance_rules.json")
    rules_dst = os.path.join(output_dir, "maintenance_acceptance_rules.json")
    if os.path.exists(rules_src):
        shutil.copy(rules_src, rules_dst)
        print(f"Acceptance rules: → {rules_dst}")

    # ── PHASE C: Sensor Upgrade Roadmap ────────────────────────────────
    print(f"\n[Phase C] Generating sensor upgrade roadmap...")
    sensor_engine = SensorUpgradeRoadmapEngine(num_machines=100)

    upgrade_plan_df = sensor_engine.generate_upgrade_plan()
    upgrade_path = os.path.join(output_dir, "sensor_upgrade_plan.csv")
    upgrade_plan_df.to_csv(upgrade_path, index=False, encoding="utf-8")
    print(f"Sensor upgrade plan: {len(upgrade_plan_df)} deployments → {upgrade_path}")

    roi_df = sensor_engine.generate_roi_analysis()
    roi_path = os.path.join(output_dir, "sensor_roi_analysis.csv")
    roi_df.to_csv(roi_path, index=False, encoding="utf-8")
    print(f"ROI analysis: {len(roi_df)} phases → {roi_path}")

    phase_summary_df = sensor_engine.generate_phase_summary()
    summary_path = os.path.join(output_dir, "sensor_phase_summary.csv")
    phase_summary_df.to_csv(summary_path, index=False, encoding="utf-8")
    print(f"Phase summary: {len(phase_summary_df)} phases → {summary_path}")

    # ── Print industrial plan summary ─────────────────────────────────
    print("\n" + "=" * 70)
    print("INDUSTRIAL MAINTENANCE PLAN — SAMPLE WORK ORDERS")
    print("=" * 70)
    for idx, (_, row) in enumerate(plan_df.head(5).iterrows()):
        print(f"\n[{row.get('maintenance_priority','?')}] {row['machine_id']} "
              f"| {row.get('predicted_risk','?')} | {row.get('primary_pattern','?')}")
        print(f"    Tech: {row.get('technician_type','?')} x{row.get('technician_count',1)} "
              f"| Est: {row.get('estimated_duration_hours',0)}h "
              f"| Window: {row.get('recommended_downtime_window','?')}")
        print(f"    Parts: {row.get('spare_parts','[]')}")
        print(f"    SLA: {row.get('sla_target_hours',0)}h "
              f"| Cost: ${row.get('estimated_cost',0):,.0f} "
              f"| Impact: ${row.get('production_impact',0):,.0f}")
        if idx >= 4:
            break
    if len(plan_df) > 5:
        print(f"\n  ... and {len(plan_df) - 5} more work orders")

    # ── Summary JSON ─────────────────────────────────────────────────
    summary = {
        "n_machines_evaluated": len(batch_df),
        "alert_distribution": {
            level: int((batch_df["alert_level"] == level).sum())
            for level in ["ALARM", "WARNING", "WATCH", "NORMAL"]
        },
        "n_work_orders": len(work_orders),
        "n_industrial_orders": len(plan_df),
        "strategy": args.strategy,
        "n_spare_parts_rows": len(parts_rows),
        "n_technician_assignments": len(tech_rows),
        "n_downtime_slots": len(downtime_rows),
    }
    with open(os.path.join(output_dir, "decision_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ── Manifest ─────────────────────────────────────────────────────
    manifest = {
        "data_dir": data_dir,
        "prep_dir": prep_dir,
        "output_dir": output_dir,
        "strategy": args.strategy,
        "files": {
            "decision_report": "maintenance_decision_report.csv",
            "work_orders": "maintenance_work_orders.csv",
            "text_report": "maintenance_report.txt",
            "decision_summary": "decision_summary.json",
            "industrial_plan": "industrial_maintenance_plan.csv",
            "spare_parts_plan": "spare_parts_plan.csv",
            "technician_schedule": "technician_schedule.csv",
            "downtime_schedule": "downtime_schedule.csv",
            "strategy_comparison": "strategy_comparison.csv",
            "acceptance_rules": "maintenance_acceptance_rules.json",
            "sensor_upgrade_plan": "sensor_upgrade_plan.csv",
            "sensor_roi_analysis": "sensor_roi_analysis.csv",
            "sensor_phase_summary": "sensor_phase_summary.csv",
        },
        "summary": summary,
    }
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nAll outputs saved to: {output_dir}/")
    print("Decision engine + Industrial plan complete.")
    return batch_df, work_orders, plan_df


if __name__ == "__main__":
    main()
