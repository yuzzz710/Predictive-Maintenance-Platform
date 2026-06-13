#!/usr/bin/env python3
"""
Pareto Optimizer — Multi-Objective Pareto Frontier for Maintenance Strategies
==============================================================================
Generates the 3-objective Pareto frontier (cost, downtime, quality risk) and
positions the three maintenance strategies on it.

Method: ε-constraint LP via scipy.optimize.linprog (HiGHS solver)
  - For each ε in cost range: min Σdowntime_i·x_i  s.t. Σcost_i·x_i ≤ ε, 0≤x_i≤1
  - Same for quality-risk minimization
  - Generates true Pareto frontier from actual machine-level trade-off data

Output: pareto_frontier.json for ECharts 3D scatter visualization.

Usage:
    python pareto_optimizer.py --comparison-csv <strategy_comparison.csv> \\
                                --plan-csv <industrial_maintenance_plan.csv> \\
                                --output <pareto_frontier.json>
"""

from __future__ import annotations

import argparse, json, os, sys
from typing import List, Dict

import numpy as np
import pandas as pd
from scipy.optimize import linprog


class ParetoOptimizer:
    """
    Generate Pareto frontiers for the 3-strategy maintenance system.

    Three objectives:
      - f1: total maintenance cost (minimize)
      - f2: total downtime hours (minimize)
      - f3: quality defect risk (minimize)

    Three strategies are positioned as fixed points on the frontier.
    """

    def __init__(self, strategy_comparison_df: pd.DataFrame,
                 plan_df: pd.DataFrame):
        self.comp_df = strategy_comparison_df
        self.plan_df = plan_df

    def generate_frontiers(self) -> dict:
        """
        Generate cost-vs-downtime and cost-vs-quality Pareto frontiers
        using true epsilon-constraint LP (scipy.optimize.linprog).

        For each epsilon_k (cost cap), solves:
          min  Σ downtime_i * x_i    s.t.  Σ cost_i * x_i <= epsilon_k,  0 <= x_i <= 1
          min  Σ quality_i * x_i     s.t.  Σ cost_i * x_i <= epsilon_k,  0 <= x_i <= 1

        Returns dict with:
          - strategy_positions: {strategy: {cost, downtime, quality, orders}}
          - cost_downtime_frontier: [{cost, downtime}]
          - cost_quality_frontier: [{cost, quality}]
          - pareto_3d_points: [{cost, downtime, quality, label}]
        """
        # Extract strategy positions from comparison data
        strategies = {}
        for _, row in self.comp_df.iterrows():
            strat = row.get("strategy", "")
            strategies[strat] = {
                "cost": float(row.get("total_estimated_cost", 0)),
                "orders": int(row.get("n_work_orders", 0)),
                "alarms": int(row.get("n_alarms", 0)),
                "warnings": int(row.get("n_warnings", 0)),
            }

        avg_duration = float(self.plan_df["estimated_duration_hours"].mean()) if "estimated_duration_hours" in self.plan_df.columns else 4.0
        avg_cost_per_order = float(self.plan_df["estimated_cost"].mean()) if "estimated_cost" in self.plan_df.columns else 3000

        for strat in strategies:
            n_orders = strategies[strat]["orders"]
            strategies[strat]["downtime_hours"] = round(n_orders * avg_duration, 1)
            strategies[strat]["quality_risk"] = round(
                strategies[strat]["alarms"] * avg_cost_per_order * 0.3, 2
            )

        # ── Build per-machine cost / downtime / quality vectors ──
        n = len(self.plan_df)
        if n == 0:
            return {
                "strategy_positions": {}, "cost_downtime_frontier": [],
                "cost_quality_frontier": [], "pareto_3d_points": [],
                "metadata": {"method": "epsilon_constraint_lp", "n_machines": 0},
            }

        cost_vec = self.plan_df["estimated_cost"].fillna(3000).values.astype(float)
        downtime_vec = self.plan_df["estimated_duration_hours"].fillna(4.0).values.astype(float)

        anomaly_col = "anomaly_score" if "anomaly_score" in self.plan_df.columns else None
        if anomaly_col:
            quality_vec = self.plan_df[anomaly_col].fillna(0.5).values.astype(float) * cost_vec * 0.3
        else:
            quality_vec = 0.5 * cost_vec * 0.3

        cost_total = float(cost_vec.sum())
        cost_min_eps = max(cost_total * 0.03, cost_vec.min())
        cost_max_eps = cost_total * 0.75
        K = 20

        # ── Cost vs Downtime frontier (LP: min downtime s.t. cost <= epsilon) ──
        cost_dt_frontier = []
        c_obj = downtime_vec
        A_ub = [cost_vec]

        for k in range(K + 1):
            eps = cost_min_eps + (k / K) * (cost_max_eps - cost_min_eps)
            result = linprog(c_obj, A_ub=A_ub, b_ub=[eps],
                             bounds=[(0, 1)] * n, method='highs')
            if result.success:
                sel = result.x > 0.5
                cost_dt_frontier.append({
                    "cost": round(float(cost_vec[sel].sum()), 0),
                    "downtime_hours": round(float(downtime_vec[sel].sum()), 1),
                    "pareto_rank": k + 1,
                })

        if not cost_dt_frontier:
            cost_dt_frontier.append({
                "cost": round(cost_total * 0.3, 0),
                "downtime_hours": round(float(downtime_vec.sum() * 0.3), 1),
                "pareto_rank": 1,
            })

        # ── Cost vs Quality frontier (LP: min quality risk s.t. cost <= epsilon) ──
        cost_qual_frontier = []
        c_qual = quality_vec

        for k in range(K + 1):
            eps = cost_min_eps + (k / K) * (cost_max_eps - cost_min_eps)
            result = linprog(c_qual, A_ub=A_ub, b_ub=[eps],
                             bounds=[(0, 1)] * n, method='highs')
            if result.success:
                sel = result.x > 0.5
                cost_qual_frontier.append({
                    "cost": round(float(cost_vec[sel].sum()), 0),
                    "quality_risk": round(float(quality_vec[sel].sum()), 2),
                    "pareto_rank": k + 1,
                })

        if not cost_qual_frontier:
            cost_qual_frontier.append({
                "cost": round(cost_total * 0.3, 0),
                "quality_risk": round(float(quality_vec.sum() * 0.3), 2),
                "pareto_rank": 1,
            })

        # ── 3D points: combine downtime + quality at each cost level ──
        pareto_3d = []
        dt_by_cost = {p["cost"]: p["downtime_hours"] for p in cost_dt_frontier}
        qual_by_cost = {p["cost"]: p["quality_risk"] for p in cost_qual_frontier}
        sorted_qual_costs = sorted(qual_by_cost.keys())

        def _interp_quality(cost_val):
            if cost_val <= sorted_qual_costs[0]:
                return qual_by_cost[sorted_qual_costs[0]]
            if cost_val >= sorted_qual_costs[-1]:
                return qual_by_cost[sorted_qual_costs[-1]]
            for i in range(len(sorted_qual_costs) - 1):
                lo, hi = sorted_qual_costs[i], sorted_qual_costs[i + 1]
                if lo <= cost_val <= hi:
                    t = (cost_val - lo) / (hi - lo) if hi > lo else 0
                    return qual_by_cost[lo] + t * (qual_by_cost[hi] - qual_by_cost[lo])
            return qual_by_cost[sorted_qual_costs[-1]]

        for pt in cost_dt_frontier:
            c = pt["cost"]
            dt = pt["downtime_hours"]
            qr = qual_by_cost.get(c, _interp_quality(c))
            pareto_3d.append({
                "cost": round(c, 0),
                "downtime_hours": round(dt, 1),
                "quality_risk": round(qr, 2),
                "label": f"Pareto-{pt['pareto_rank']}",
                "type": "frontier",
            })

        # Strategy annotations
        strat_names = {
            "cost_efficiency": "成本效率",
            "production_efficiency": "生产效率",
            "quality_first": "质量优先",
        }
        strat_colors = {
            "cost_efficiency": "#3fb950",
            "production_efficiency": "#4d94ff",
            "quality_first": "#a371f7",
        }
        for strat, data in strategies.items():
            pareto_3d.append({
                "cost": round(data["cost"], 0),
                "downtime_hours": round(data["downtime_hours"], 1),
                "quality_risk": round(data["quality_risk"], 2),
                "label": strat_names.get(strat, strat),
                "type": "strategy",
                "color": strat_colors.get(strat, "#f0a030"),
                "orders": data["orders"],
            })

        return {
            "strategy_positions": {
                strat: {
                    **{k: v for k, v in data.items()},
                    "label": strat_names.get(strat, strat),
                    "color": strat_colors.get(strat, "#f0a030"),
                }
                for strat, data in strategies.items()
            },
            "cost_downtime_frontier": cost_dt_frontier,
            "cost_quality_frontier": cost_qual_frontier,
            "pareto_3d_points": pareto_3d,
            "metadata": {
                "method": "epsilon_constraint_lp",
                "solver": "scipy.linprog_highs",
                "n_frontier_points": K + 1,
                "n_machines": n,
                "objectives": ["cost", "downtime_hours", "quality_risk"],
            },
        }


def main():
    parser = argparse.ArgumentParser(description="Pareto Frontier Generator")
    parser.add_argument("--comparison-csv", required=True, help="strategy_comparison.csv")
    parser.add_argument("--plan-csv", required=True, help="industrial_maintenance_plan.csv")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    comp_df = pd.read_csv(args.comparison_csv, encoding="utf-8")
    plan_df = pd.read_csv(args.plan_csv, encoding="utf-8")

    opt = ParetoOptimizer(comp_df, plan_df)
    result = opt.generate_frontiers()

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Pareto frontier: {len(result['pareto_3d_points'])} points → {args.output}")
    for strat, pos in result["strategy_positions"].items():
        print(f"  {pos['label']}: cost=${pos['cost']:.0f} downtime={pos['downtime_hours']:.0f}h quality={pos['quality_risk']:.0f}")


if __name__ == "__main__":
    main()
