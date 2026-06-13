#!/usr/bin/env python3
"""
Inventory Optimizer — (s, S) Stochastic Inventory Policy
=========================================================
Implements the classical (s, S) inventory model for spare parts management.

- s (reorder point) = μ × L + z_α × √(μ × L)
- S (target stock) = s + EOQ = s + √(2Kμ/h)

Where:
  μ = demand rate (faults/day from log.csv)
  L = lead time (days)
  K = fixed ordering cost
  h = holding cost per unit per day
  z_α = service level factor (α=0.85→1.04, α=0.92→1.41, α=0.98→2.05)

Usage:
    python inventory_optimizer.py --catalog <spare_parts_catalog.json> \\
                                   --log <log.csv> --strategy production_efficiency \\
                                   --output <inventory_policy.csv>
"""

from __future__ import annotations

import argparse, json, os, sys, math
from typing import Dict

import numpy as np
import pandas as pd
from scipy.stats import norm


# Service level z-values linked to strategy
STRATEGY_Z = {
    "cost_efficiency": 1.04,        # α ≈ 0.85
    "production_efficiency": 1.41,  # α ≈ 0.92
    "quality_first": 2.05,          # α ≈ 0.98
}

FIXED_ORDERING_COST = 200.0       # $ per order (admin + shipping)
HOLDING_COST_RATE = 0.02           # daily holding cost rate (2% of unit cost)
PREMIUM_RATE = 2.5                  # emergency procurement premium (2.5x unit cost)
SHORTAGE_DOWNTIME_COST = 200.0     # $/day extra downtime waiting cost during stockout


class InventoryOptimizer:
    """
    (s, S) inventory policy optimizer for spare parts.

    Usage:
        opt = InventoryOptimizer("production_efficiency")
        policy_df = opt.optimize(catalog_path, log_path)
    """

    def __init__(self, strategy: str = "production_efficiency",
                 premium_rate: float = None, downtime_cost: float = None):
        self.strategy = strategy
        self.z = STRATEGY_Z.get(strategy, 1.41)
        self.premium_rate = premium_rate if premium_rate is not None else PREMIUM_RATE
        self.downtime_cost = downtime_cost if downtime_cost is not None else SHORTAGE_DOWNTIME_COST

    def optimize(self, catalog_path: str, log_path: str) -> pd.DataFrame:
        """
        Compute (s, S) policy for each spare part.

        Args:
            catalog_path: Path to spare_parts_catalog.json
            log_path: Path to log.csv (with Failure.Type column)

        Returns:
            DataFrame with columns: part_name, part_number, unit_cost, lead_time_days,
            demand_rate_daily, reorder_point_s, target_stock_S, safety_stock, eoq, holding_cost_daily
        """
        # Load catalog
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        # Estimate demand rate from log.csv
        mu_daily = self._estimate_demand_rates(log_path)

        rows = []
        for entry in catalog.get("catalog", []):
            fault_type = entry.get("fault_type", "unknown")
            fault_rate = mu_daily.get(fault_type, 0.05)  # default 0.05/day

            for part in entry.get("parts", []):
                name = part.get("name", "")
                pn = part.get("part_number", "")
                unit_cost = float(part.get("unit_cost", 50))
                lead_time = float(part.get("lead_time_days", 3))
                qty_per_machine = int(part.get("quantity_per_machine", 1))

                # Demand per part = fault rate × quantity needed per repair
                demand = fault_rate * qty_per_machine

                h = HOLDING_COST_RATE * unit_cost  # daily holding cost
                K = FIXED_ORDERING_COST
                # Shortage cost: emergency premium + downtime waiting cost
                p = self.premium_rate * unit_cost + self.downtime_cost * lead_time

                # Optimal service level (critical ratio from newsvendor)
                critical_ratio = p / max(p + h, 0.001)
                adjusted_z = max(self.z, norm.ppf(critical_ratio) if hasattr(norm, 'ppf') else self.z)

                # Reorder point with shortage-cost-adjusted z
                s = demand * lead_time + adjusted_z * math.sqrt(max(demand * lead_time, 0.01))
                # EOQ with shortage: EOQ_s = √(2Kμ/h · (h+p)/p)
                eoq = math.sqrt(max(2 * K * demand / max(h, 0.001) * (h + p) / max(p, 0.001), 1))
                # Target stock
                S = s + eoq

                safety_stock = adjusted_z * math.sqrt(max(demand * lead_time, 0.01))

                # Current stock estimate: assume 60% of S as baseline
                current_stock = round(S * 0.6, 0)
                order_qty = max(0, round(S - current_stock, 0))

                risk_info = self._stockout_risk(demand * lead_time, current_stock)
                annual_stockout_cost = round(p * 365 * risk_info["prob"], 2)

                rows.append({
                    "part_name": name,
                    "part_number": pn,
                    "fault_type": fault_type,
                    "unit_cost": round(unit_cost, 2),
                    "lead_time_days": int(lead_time),
                    "demand_rate_daily": round(demand, 4),
                    "reorder_point_s": round(s, 2),
                    "target_stock_S": round(S, 2),
                    "safety_stock": round(safety_stock, 2),
                    "eoq": round(eoq, 2),
                    "holding_cost_daily": round(h, 4),
                    "shortage_cost_per_unit": round(p, 2),
                    "critical_ratio": round(critical_ratio, 3),
                    "current_stock_est": int(current_stock),
                    "suggested_order_qty": int(order_qty),
                    "stockout_risk": risk_info["level"],
                    "stockout_probability": risk_info["prob"],
                    "annual_stockout_cost_est": annual_stockout_cost,
                })

        # Common parts
        for part in catalog.get("common_parts", []):
            name = part.get("name", "")
            pn = part.get("part_number", "")
            unit_cost = float(part.get("unit_cost", 10))
            lead_time = float(part.get("lead_time_days", 1))
            qty_per_machine = int(part.get("quantity_per_machine", 1))
            demand = 0.1 * qty_per_machine  # common parts used across all fault types
            h = HOLDING_COST_RATE * unit_cost
            K = FIXED_ORDERING_COST
            p = self.premium_rate * unit_cost + self.downtime_cost * lead_time
            critical_ratio = p / max(p + h, 0.001)
            adjusted_z = max(self.z, norm.ppf(critical_ratio) if hasattr(norm, 'ppf') else self.z)
            s = demand * lead_time + adjusted_z * math.sqrt(max(demand * lead_time, 0.01))
            eoq = math.sqrt(max(2 * K * demand / max(h, 0.001) * (h + p) / max(p, 0.001), 1))
            S = s + eoq
            safety_stock = adjusted_z * math.sqrt(max(demand * lead_time, 0.01))
            current_stock = round(S * 0.6, 0)
            order_qty = max(0, round(S - current_stock, 0))
            risk_info = self._stockout_risk(demand * lead_time, current_stock)
            annual_stockout_cost = round(p * 365 * risk_info["prob"], 2)

            rows.append({
                "part_name": name,
                "part_number": pn,
                "fault_type": "common",
                "unit_cost": round(unit_cost, 2),
                "lead_time_days": int(lead_time),
                "demand_rate_daily": round(demand, 4),
                "reorder_point_s": round(s, 2),
                "target_stock_S": round(S, 2),
                "safety_stock": round(safety_stock, 2),
                "eoq": round(eoq, 2),
                "holding_cost_daily": round(h, 4),
                "shortage_cost_per_unit": round(p, 2),
                "critical_ratio": round(critical_ratio, 3),
                "current_stock_est": int(current_stock),
                "suggested_order_qty": int(order_qty),
                "stockout_risk": risk_info["level"],
                "stockout_probability": risk_info["prob"],
                "annual_stockout_cost_est": annual_stockout_cost,
            })

        return pd.DataFrame(rows)

    def _estimate_demand_rates(self, log_path: str) -> Dict[str, float]:
        """Estimate daily fault rate per fault type from log.csv."""
        rates = {}
        if not os.path.exists(log_path):
            return rates

        df = pd.read_csv(log_path, encoding="utf-8")
        if "Failure.Type" not in df.columns:
            return rates

        # Map Failure.Type to pattern names
        type_pattern = {
            1: "thermal_buildup", 2: "voltage_drift", 3: "power_anomaly",
            4: "combined_degradation", 5: "thermal_buildup",
            6: "voltage_drift", 7: "power_anomaly",
            8: "combined_degradation", 9: "thermal_buildup",
        }

        n_days = max(1, (pd.to_datetime(df["Date"]).max() - pd.to_datetime(df["Date"]).min()).days)

        for ft, grp in df[df["Failure.Type"] > 0].groupby("Failure.Type"):
            pattern = type_pattern.get(int(ft), "combined_degradation")
            count = len(grp)
            rate = count / max(n_days, 1)
            # Merge into pattern categories (take max rate per pattern)
            if pattern not in rates or rate > rates[pattern]:
                rates[pattern] = rate

        # Fallback: ensure all patterns have nonzero rates
        for p in ["thermal_buildup", "voltage_drift", "power_anomaly", "combined_degradation"]:
            if p not in rates:
                rates[p] = 0.05  # default

        return rates

    @staticmethod
    def _stockout_risk(lead_time_demand: float, stock: float) -> dict:
        """Return stockout classification with numeric probability estimate."""
        if stock <= 0:
            return {"level": "critical", "prob": 0.95}
        ratio = stock / max(lead_time_demand, 0.001)
        if ratio < 1.0:
            return {"level": "high", "prob": 0.75}
        elif ratio < 2.0:
            return {"level": "medium", "prob": 0.30}
        return {"level": "low", "prob": 0.05}


def main():
    parser = argparse.ArgumentParser(description="(s,S) Inventory Policy Optimizer")
    parser.add_argument("--catalog", required=True, help="Path to spare_parts_catalog.json")
    parser.add_argument("--log", required=True, help="Path to log.csv")
    parser.add_argument("--strategy", default="production_efficiency",
                        choices=["cost_efficiency", "production_efficiency", "quality_first"])
    parser.add_argument("--output", required=True, help="Output CSV path")
    args = parser.parse_args()

    opt = InventoryOptimizer(args.strategy)
    df = opt.optimize(args.catalog, args.log)
    df.to_csv(args.output, index=False, encoding="utf-8")
    print(f"Inventory policy: {len(df)} parts → {args.output}")
    n_high_risk = (df["stockout_risk"].isin(["critical", "high"])).sum()
    print(f"  High-risk parts: {n_high_risk}/{len(df)}")
    total_order = df["suggested_order_qty"].sum()
    print(f"  Suggested total order: {int(total_order)} units")


if __name__ == "__main__":
    main()
