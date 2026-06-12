#!/usr/bin/env python3
"""
Maintenance Scheduler — 14-Day Rolling-Window Scheduling with Time Windows
==========================================================================
Replaces the 6-rule decision tree in downtime_optimizer.py with a
constraint-aware scheduling model that minimizes weighted tardiness.

Algorithm: Greedy construction + 2-opt local search (no external solver needed).
Solves single-machine batching with time windows for K ≤ 30 work orders × 14 days.

Usage:
    python maintenance_scheduler.py --plan-csv <industrial_maintenance_plan.csv> \\
                                     --horizon 14 --output <maintenance_schedule.csv>
"""

from __future__ import annotations

import argparse, os, sys, json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ── Work-day capacity (hours) ──
WEEKDAY_HOURS = 64.0   # 2 shifts × 8h × 4 techs
WEEKEND_HOURS = 40.0   # 1 shift × 8h × 5 techs


def _day_name(ref_date: datetime, day_offset: int) -> str:
    d = ref_date + timedelta(days=day_offset)
    return d.strftime("%m/%d") + ("(六)" if d.weekday() == 5 else "(日)" if d.weekday() == 6 else "")


def _hours_available(day_offset: int, ref_date: datetime = None) -> float:
    """Return available labor hours for a given day offset from reference."""
    if ref_date is None:
        ref_date = datetime.now()
    d = ref_date + timedelta(days=day_offset)
    return WEEKEND_HOURS if d.weekday() >= 5 else WEEKDAY_HOURS


class MaintenanceScheduler:
    """
    Constraint-aware maintenance scheduler for a rolling T-day window.

    Usage:
        sched = MaintenanceScheduler(horizon_days=14)
        result_df = sched.schedule(plan_df, ref_date=pd.Timestamp.now())
    """

    def __init__(self, horizon_days: int = 14, seed: int = 42):
        self.horizon = horizon_days
        self.rng = np.random.default_rng(seed)

    def schedule(self, plan_df: pd.DataFrame,
                 ref_date=None) -> pd.DataFrame:
        """
        Schedule work orders into the horizon window.

        Args:
            plan_df: DataFrame from industrial_maintenance_plan.csv
                     Required columns: machine_id, estimated_duration_hours,
                     urgency_score, maintenance_priority, primary_pattern,
                     technician_type, cost_at_risk
            ref_date: Reference date (default: today)

        Returns:
            DataFrame with columns: machine_id, scheduled_day, scheduled_date,
            duration_hours, priority, tardiness_hours, risk_weight, technician_type
        """
        if ref_date is None:
            ref_date = pd.Timestamp.now()

        orders = []
        for _, row in plan_df.iterrows():
            mid = str(row.get("machine_id", ""))
            hours = float(row.get("estimated_duration_hours", 4.0))
            urgency = float(row.get("urgency_score", 50.0))
            priority = str(row.get("maintenance_priority", "P3"))
            pattern = str(row.get("primary_pattern", "normal"))
            tech = str(row.get("technician_type", "junior_technician"))
            cost = float(row.get("cost_at_risk", 5000))

            # Earliest start: P1=day0, P2=day2, P3=day5
            earliest = {"P1": 0, "P2": 2, "P3": 5}.get(priority, 5)
            # Deadline: earlier for higher urgency
            deadline = max(earliest + 1, int(14 - urgency / 10))
            deadline = min(deadline, self.horizon - 1)
            if deadline <= earliest:
                deadline = earliest + 1

            # Risk weight ∝ urgency × cost_at_risk
            risk_weight = urgency * cost / 10000.0

            orders.append({
                "machine_id": mid,
                "duration_hours": hours,
                "earliest_day": earliest,
                "deadline_day": deadline,
                "risk_weight": risk_weight,
                "priority": priority,
                "pattern": pattern,
                "technician_type": tech,
            })

        # Sort by priority then risk_weight descending for greedy construction
        pri_order = {"P1": 0, "P2": 1, "P3": 2}
        orders.sort(key=lambda o: (pri_order.get(o["priority"], 3), -o["risk_weight"]))

        # ── Greedy construction ──
        day_load = [0.0] * self.horizon
        schedule = []  # (order_idx, day)

        for i, o in enumerate(orders):
            best_day = -1
            best_tardy = 1e9
            for d in range(o["earliest_day"], min(o["deadline_day"] + 3, self.horizon)):
                cap = _hours_available(d, ref_date)
                if day_load[d] + o["duration_hours"] <= cap:
                    tardy = max(0, d - o["deadline_day"])
                    if tardy < best_tardy:
                        best_tardy = tardy
                        best_day = d
            if best_day >= 0:
                day_load[best_day] += o["duration_hours"]
                schedule.append((i, best_day))
            else:
                # Force-fit: find day with most remaining capacity
                best_day = max(
                    range(o["earliest_day"], self.horizon),
                    key=lambda d: _hours_available(d, ref_date) - day_load[d]
                )
                day_load[best_day] += o["duration_hours"]
                schedule.append((i, best_day))

        # ── 2-opt local search (reduce weighted tardiness) ──
        def _total_weighted_tardiness(sched):
            total = 0.0
            used = [0.0] * self.horizon
            for oi, d in sched:
                o = orders[oi]
                used[d] += o["duration_hours"]
                tardy = max(0, d - o["deadline_day"])
                total += tardy * o["risk_weight"]
            return total, used

        improved = True
        iterations = 0
        best_score, best_load = _total_weighted_tardiness(schedule)

        while improved and iterations < 200:
            improved = False
            iterations += 1
            for a_idx in range(len(schedule)):
                for b_idx in range(a_idx + 1, len(schedule)):
                    oi_a, day_a = schedule[a_idx]
                    oi_b, day_b = schedule[b_idx]
                    # Try swap
                    swapped = list(schedule)
                    swapped[a_idx] = (oi_a, day_b)
                    swapped[b_idx] = (oi_b, day_a)

                    # Validate capacity
                    load = [0.0] * self.horizon
                    valid = True
                    for oi, d in swapped:
                        o = orders[oi]
                        if d < o["earliest_day"]:
                            valid = False
                            break
                        load[d] += o["duration_hours"]
                        if load[d] > _hours_available(d, ref_date) * 1.05:
                            valid = False
                            break
                    if not valid:
                        continue

                    # Evaluate
                    score = sum(
                        max(0, d - orders[oi]["deadline_day"]) * orders[oi]["risk_weight"]
                        for oi, d in swapped
                    )
                    if score < best_score - 0.001:
                        best_score = score
                        schedule = swapped
                        improved = True

        # ── Remove empty days, build output ──
        rows = []
        for oi, day in schedule:
            o = orders[oi]
            tardy = max(0, day - o["deadline_day"])
            sched_date = (ref_date + timedelta(days=int(day))).strftime("%Y-%m-%d")
            rows.append({
                "machine_id": o["machine_id"],
                "scheduled_day": int(day),
                "scheduled_date": sched_date,
                "duration_hours": o["duration_hours"],
                "earliest_day": o["earliest_day"],
                "deadline_day": o["deadline_day"],
                "tardiness_hours": round(tardy * 8, 1),  # convert days to working hours
                "risk_weight": round(o["risk_weight"], 2),
                "priority": o["priority"],
                "technician_type": o["technician_type"],
                "primary_pattern": o["pattern"],
            })

        result = pd.DataFrame(rows)
        result.sort_values(["scheduled_day", "priority"], inplace=True)

        # Attach metadata
        self._last_score = best_score
        self._last_load = best_load if 'best_load' in dir() else day_load
        self._n_ontime = sum(1 for r in rows if r["tardiness_hours"] <= 0)

        return result

    def get_summary(self) -> dict:
        return {
            "total_weighted_tardiness": round(getattr(self, '_last_score', 0), 2),
            "n_ontime": getattr(self, '_n_ontime', 0),
        }

    def compare_with_rules(self, plan_df: pd.DataFrame,
                           downtime_window_col: str = "recommended_downtime_window",
                           ref_date=None) -> dict:
        """
        Compare optimized scheduling against the current rule-based windows.

        Returns dict with keys for frontend comparison display.
        """
        opt_df = self.schedule(plan_df, ref_date)
        n_total = len(opt_df)

        # Count rule-based "immediate" / "night" as fast responses
        rule_fast = int(plan_df[downtime_window_col].isin(
            ["immediate", "night", "immediate_shutdown"]
        ).sum()) if downtime_window_col in plan_df.columns else n_total

        opt_ontime = int((opt_df["tardiness_hours"] <= 8).sum())
        rule_ontime = rule_fast  # rule-based: "immediate"/"night" ≈ on-time

        total_tardiness = float(opt_df["tardiness_hours"].sum())

        # Rule-based tardiness estimate: "weekend" ≈ 24h late, "scheduled" ≈ 40h late
        rule_tardiness = 0.0
        if downtime_window_col in plan_df.columns:
            for _, r in plan_df.iterrows():
                w = str(r.get(downtime_window_col, ""))
                if w in ("weekend", "next_gap"):
                    rule_tardiness += 24.0
                elif w == "scheduled":
                    rule_tardiness += 40.0

        return {
            "n_total": n_total,
            "optimized_ontime": opt_ontime,
            "rule_ontime": rule_ontime,
            "optimized_tardiness_hours": round(total_tardiness, 1),
            "rule_tardiness_hours": round(rule_tardiness, 1),
            "on_time_improvement_pct": round(
                (opt_ontime - rule_ontime) / max(rule_ontime, 1) * 100, 1
            ),
            "tardiness_reduction_pct": round(
                (rule_tardiness - total_tardiness) / max(rule_tardiness, 1) * 100, 1
            ) if rule_tardiness > 0 else 0,
        }


def main():
    parser = argparse.ArgumentParser(description="Maintenance Scheduler — 14-day rolling window")
    parser.add_argument("--plan-csv", required=True, help="Path to industrial_maintenance_plan.csv")
    parser.add_argument("--horizon", type=int, default=14, help="Scheduling horizon in days")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--compare-json", default=None, help="Output comparison JSON path")
    args = parser.parse_args()

    plan_df = pd.read_csv(args.plan_csv, encoding="utf-8")
    scheduler = MaintenanceScheduler(horizon_days=args.horizon)
    result_df = scheduler.schedule(plan_df)
    result_df.to_csv(args.output, index=False, encoding="utf-8")
    print(f"Maintenance schedule: {len(result_df)} orders → {args.output}")
    print(f"  On-time: {scheduler._n_ontime}/{len(result_df)}")

    if args.compare_json:
        comp = scheduler.compare_with_rules(plan_df)
        with open(args.compare_json, "w", encoding="utf-8") as f:
            json.dump(comp, f, indent=2, ensure_ascii=False)
        print(f"Comparison data → {args.compare_json}")


if __name__ == "__main__":
    main()
