#!/usr/bin/env python3
"""
Strategy Selector — Multi-Strategy Maintenance Decision Engine
===============================================================
Provides three industrial maintenance strategies as a configurable,
parameterized layer that wraps the base MaintenanceDecisionEngine.

Strategies:
  - COST_EFFICIENCY:   minimize costs, merge downtime, fewer work orders
  - PRODUCTION_EFFICIENCY: minimize downtime, faster response, prioritize key machines
  - QUALITY_FIRST:     minimize defect risk, lowest thresholds, most aggressive

All thresholds are parameterized via StrategyConfig dataclass — no magic numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


class MaintenanceStrategy(Enum):
    COST_EFFICIENCY = "cost_efficiency"
    PRODUCTION_EFFICIENCY = "production_efficiency"
    QUALITY_FIRST = "quality_first"


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable strategy configuration — all thresholds parameterized."""
    strategy: MaintenanceStrategy
    alarm_threshold: float
    warning_threshold: float
    watch_threshold: float
    fusion_weights: Dict[str, float] = field(default_factory=dict)
    sla_p1: int = 48
    sla_p2: int = 96
    sla_p3: int = 168
    max_orders: int = 20
    max_budget: float = 0.0  # 0 = unlimited; >0 = USD cap for preventive maintenance
    window_multiplier: float = 1.0
    cost_multiplier_at_risk: float = 1.0
    quality_sensitivity: float = 0.5
    merge_downtime: bool = False

    def get_sla(self, priority: str) -> int:
        """Return SLA target in hours for a given priority."""
        mapping = {"P1": self.sla_p1, "P2": self.sla_p2, "P3": self.sla_p3}
        return mapping.get(priority, 72)

    def get_threshold_description(self) -> str:
        """Human-readable strategy trigger description."""
        return (
            f"alarm>={self.alarm_threshold}, warning>={self.warning_threshold}, "
            f"watch>={self.watch_threshold}, max_orders={self.max_orders}, "
            f"merge_downtime={self.merge_downtime}"
        )


# ── Strategy Configurations ────────────────────────────────────────────────

STRATEGY_CONFIGS: Dict[MaintenanceStrategy, StrategyConfig] = {
    MaintenanceStrategy.COST_EFFICIENCY: StrategyConfig(
        strategy=MaintenanceStrategy.COST_EFFICIENCY,
        alarm_threshold=0.80,
        warning_threshold=0.60,
        watch_threshold=0.40,
        fusion_weights={"ml_density_weight": 0.15, "stat_anomaly_weight": 0.35,
                        "cost_risk_weight": 0.40, "trend_weight": 0.10},
        sla_p1=48, sla_p2=96, sla_p3=168,
        max_orders=12,
        max_budget=80000,  # $80K budget cap — activates knapsack DP selection
        window_multiplier=1.5,
        cost_multiplier_at_risk=1.0,
        quality_sensitivity=0.3,
        merge_downtime=True,
    ),
    MaintenanceStrategy.PRODUCTION_EFFICIENCY: StrategyConfig(
        strategy=MaintenanceStrategy.PRODUCTION_EFFICIENCY,
        alarm_threshold=0.70,
        warning_threshold=0.50,
        watch_threshold=0.30,
        fusion_weights={"ml_density_weight": 0.25, "stat_anomaly_weight": 0.40,
                        "cost_risk_weight": 0.20, "trend_weight": 0.15},
        sla_p1=12, sla_p2=48, sla_p3=72,
        max_orders=20,
        max_budget=150000,  # $150K budget cap — enables cost-constrained DP optimization
        window_multiplier=0.8,
        cost_multiplier_at_risk=0.9,
        quality_sensitivity=0.5,
        merge_downtime=False,
    ),
    MaintenanceStrategy.QUALITY_FIRST: StrategyConfig(
        strategy=MaintenanceStrategy.QUALITY_FIRST,
        alarm_threshold=0.60,
        warning_threshold=0.40,
        watch_threshold=0.25,
        fusion_weights={"ml_density_weight": 0.20, "stat_anomaly_weight": 0.45,
                        "cost_risk_weight": 0.15, "trend_weight": 0.20},
        sla_p1=8, sla_p2=24, sla_p3=48,
        max_orders=30,
        max_budget=250000,  # $250K budget cap — widest coverage under DP optimization
        window_multiplier=0.5,
        cost_multiplier_at_risk=1.2,
        quality_sensitivity=1.0,
        merge_downtime=False,
    ),
}


class StrategySelector:
    """
    Strategy-aware wrapper for MaintenanceDecisionEngine.

    Does NOT modify the engine — instead filters and re-ranks decisions
    based on the selected strategy's thresholds and priorities.

    Usage:
        selector = StrategySelector(MaintenanceStrategy.PRODUCTION_EFFICIENCY)
        filtered = selector.apply_strategy_thresholds(signal_list, engine)
    """

    def __init__(self, strategy: MaintenanceStrategy):
        if strategy not in STRATEGY_CONFIGS:
            raise ValueError(
                f"Unknown strategy '{strategy}'. "
                f"Valid: {[s.value for s in MaintenanceStrategy]}"
            )
        self.strategy = strategy
        self.config: StrategyConfig = STRATEGY_CONFIGS[strategy]

    def apply_strategy_thresholds(
        self,
        signal_list: List[dict],
        engine: Any,  # MaintenanceDecisionEngine
    ) -> List[dict]:
        """
        Evaluate all machines through the engine, then filter/re-rank
        using strategy-specific thresholds.

        Args:
            signal_list: List of signal dicts (same format as engine.evaluate())
            engine: MaintenanceDecisionEngine instance

        Returns:
            List of dicts with keys: signals, risk_score, diagnosis, alert_level,
            strategy_config. Only includes machines above the strategy's
            minimum threshold (WATCH or above, or all if quality_first).
        """
        from maintenance_decision_engine import AlertLevel

        cfg = self.config
        results = []

        for signals in signal_list:
            # Use engine's existing Layer 1-2 (unchanged)
            risk_score = engine.fuse_signals(signals)
            diagnosis = engine.diagnose(signals)

            # Apply strategy-specific thresholds for alert level
            if risk_score >= cfg.alarm_threshold:
                alert_level = AlertLevel.ALARM
            elif risk_score >= cfg.warning_threshold:
                alert_level = AlertLevel.WARNING
            elif risk_score >= cfg.watch_threshold:
                alert_level = AlertLevel.WATCH
            else:
                alert_level = AlertLevel.NORMAL

            # Apply strategy cost multiplier
            cost = float(signals.get("cost_at_risk", 5000))
            adjusted_cost = cost * cfg.cost_multiplier_at_risk
            signals_adj = dict(signals)
            signals_adj["cost_at_risk"] = adjusted_cost

            # For cost_efficiency with merge_downtime: skip NORMAL machines
            if alert_level == AlertLevel.NORMAL and cfg.merge_downtime:
                continue

            # For all strategies: only skip truly NORMAL if they have no pattern
            if alert_level == AlertLevel.NORMAL and diagnosis.primary_pattern == "normal":
                # Still include for quality_first (most aggressive)
                if cfg.strategy != MaintenanceStrategy.QUALITY_FIRST:
                    continue

            results.append({
                "signals": signals_adj,
                "risk_score": risk_score,
                "diagnosis": diagnosis,
                "alert_level": alert_level,
                "strategy_config": cfg,
            })

        # Apply work order cap — with OR-optimized selection when budget-constrained
        results.sort(key=lambda r: r["risk_score"], reverse=True)
        # Check for OR budget override (set by IndustrialMaintenanceEngine)
        or_budget = getattr(self, '_or_max_budget', 0) or cfg.max_budget
        or_max_orders = getattr(self, '_or_max_orders', 0) or cfg.max_orders
        or_max_hours = getattr(self, '_or_max_hours', 0)
        if or_budget > 0:
            results = self.optimize_work_order_selection(results, or_budget, or_max_orders, max_hours=or_max_hours)
        elif len(results) > cfg.max_orders:
            results = results[:cfg.max_orders]

        return results

    def optimize_work_order_selection(
        self,
        candidates: List[dict],
        budget_limit: float = 0,
        max_orders: int = 20,
        max_hours: float = 0,
    ) -> List[dict]:
        """
        0-1 Knapsack DP: maximize total risk reduction under budget + labor-hour constraints.

        Each candidate i has:
          - r_i: risk reduction = risk_score × cost_at_risk (risk avoided if maintained)
          - c_i: execution cost = estimated labor + parts + downtime
          - t_i: estimated labor hours

        Constraints:
          - Σ c_i ≤ budget_limit (budget cap)
          - Σ t_i ≤ H (available labor hours, derived from max_orders × 4h typical)

        Returns the optimal subset of candidates (same list-of-dict format).
        """
        n = len(candidates)
        if n == 0:
            return []

        B = int(budget_limit)
        # Labor-hour cap: user override, or technician schedule, or fallback (14d × 8h × 2 techs)
        H = max_hours if max_hours > 0 else self._calculate_available_hours(14)

        # Build items array: (risk_reduction, cost, hours)
        items = []
        for r in candidates:
            signals = r.get("signals", {})
            risk_score = float(r.get("risk_score", 0))
            cost_at_risk = float(signals.get("cost_at_risk", 5000))
            # Risk reduction ≈ risk_score × cost_at_risk (how much $ risk is eliminated)
            risk_reduction = risk_score * cost_at_risk
            # Execution cost estimate
            exec_cost = float(signals.get("estimated_cost",
                              signals.get("cost_at_risk", 5000) * 0.15))
            exec_cost = max(1.0, exec_cost)
            # Labor hours estimate
            labor_hrs = float(signals.get("estimated_duration_hours",
                              signals.get("estimated_labor_hours", 4.0)))
            labor_hrs = max(0.5, labor_hrs)
            items.append({
                "risk_reduction": risk_reduction,
                "cost": int(exec_cost),
                "hours": int(labor_hrs),
                "candidate": r,
            })

        # 3D 0-1 Knapsack DP: dp[b][c] = max risk reduction with budget b, exactly c items.
        # Third dimension c (item count) guarantees each item is selected at most once,
        # fixing the 2D DP bug where both dims swept downward caused item reuse.
        SCALE = 200
        B_scaled = max(1, B // SCALE)
        H_max = int(H)
        M = min(max_orders, n, 50)

        dp_risk = [[-1.0] * (M + 1) for _ in range(B_scaled + 1)]
        dp_hrs = [[0] * (M + 1) for _ in range(B_scaled + 1)]
        trace = [[None] * (M + 1) for _ in range(B_scaled + 1)]
        dp_risk[0][0] = 0.0

        for i, item in enumerate(items):
            ci = max(1, item["cost"] // SCALE)
            hi = min(item["hours"], H_max)
            ri = item["risk_reduction"]
            old_risk = [row[:] for row in dp_risk]
            old_hrs = [row[:] for row in dp_hrs]
            for b in range(B_scaled, ci - 1, -1):
                for c in range(M, 0, -1):
                    prev_val = old_risk[b - ci][c - 1]
                    if prev_val >= 0 and old_hrs[b - ci][c - 1] + hi <= H_max:
                        nv = prev_val + ri
                        if nv > dp_risk[b][c]:
                            dp_risk[b][c] = nv
                            dp_hrs[b][c] = old_hrs[b - ci][c - 1] + hi
                            prev_trace = trace[b - ci][c - 1]
                            trace[b][c] = (prev_trace + [i]) if prev_trace else [i]

        # Find best (budget, count) combination
        best_b, best_c, best_val = 0, 0, 0.0
        for b in range(B_scaled + 1):
            for c in range(M + 1):
                if dp_risk[b][c] > best_val:
                    best_val = dp_risk[b][c]
                    best_b = b
                    best_c = c

        selected_indices = trace[best_b][best_c] or []
        budget_used = sum(items[i]["cost"] for i in selected_indices)
        risk_achieved = best_val

        # Annotate results with optimization metadata
        selected = [items[i]["candidate"] for i in selected_indices]
        greedy_n = min(len(candidates), max_orders)
        greedy_risk = sum(
            candidates[k]["risk_score"] * float(candidates[k].get("signals", {}).get("cost_at_risk", 5000))
            for k in range(greedy_n)
        )

        for s in selected:
            s["_or_selected"] = True
            s["_or_budget_used"] = budget_used
            s["_or_risk_achieved"] = round(risk_achieved, 2)
        for k in range(greedy_n):
            if candidates[k] not in selected:
                candidates[k]["_or_deferred"] = True  # would've been selected by greedy but deferred by OR

        # Attach optimization summary to first item for downstream reporting
        if selected:
            selected[0]["_or_summary"] = {
                "method": "0-1_knapsack_dp",
                "budget_limit": B,
                "labor_hour_limit": H,
                "n_greedy": greedy_n,
                "n_optimized": len(selected),
                "budget_used": budget_used,
                "budget_utilization_pct": round(budget_used / B * 100, 1) if B > 0 else 0,
                "risk_reduction_optimized": round(risk_achieved, 2),
                "risk_reduction_greedy": round(greedy_risk, 2),
                "risk_improvement_pct": round((risk_achieved - greedy_risk) / greedy_risk * 100, 1) if greedy_risk > 0 else 0,
            }

        return selected

    @staticmethod
    def _extract_fields(item) -> tuple:
        """Extract (risk_score, cost_at_risk, estimated_cost, estimated_hours) from dict or Series."""
        if isinstance(item, pd.Series):
            risk = float(item.get("anomaly_score", item.get("risk_score", 0.5)))
            cost_at_risk = float(item.get("cost_at_risk", 5000))
            est_cost = float(item.get("estimated_cost", cost_at_risk * 0.15))
            est_hrs = float(item.get("estimated_duration_hours", 4.0))
        elif isinstance(item, dict):
            sig = item.get("signals", item)
            risk = float(item.get("risk_score", sig.get("risk_score", 0.5)))
            cost_at_risk = float(sig.get("cost_at_risk", item.get("cost_at_risk", 5000)))
            est_cost = float(sig.get("estimated_cost", item.get("estimated_cost", cost_at_risk * 0.15)))
            est_hrs = float(sig.get("estimated_duration_hours", item.get("estimated_duration_hours", 4.0)))
        else:
            risk = 0.5; cost_at_risk = 5000.0; est_cost = 750.0; est_hrs = 4.0
        return risk, cost_at_risk, est_cost, est_hrs

    def generate_optimization_comparison(
        self,
        candidates,
        cfg: 'StrategyConfig',
    ) -> dict:
        """Compare greedy vs knapsack-optimized selection. Accepts list[dict] or DataFrame."""
        or_budget = getattr(self, '_or_max_budget', 0) or cfg.max_budget
        or_max_orders = getattr(self, '_or_max_orders', 0) or cfg.max_orders
        if or_budget <= 0 or len(candidates) == 0:
            return None

        n = len(candidates)
        greedy_n = min(n, or_max_orders)

        # Convert candidates to rows, sorted by risk_score descending for greedy baseline
        items_list = list(candidates.iterrows() if isinstance(candidates, pd.DataFrame)
                         else enumerate(candidates))
        scored = []
        for idx, item in items_list:
            risk, cost_at_risk, est_cost, est_hrs = self._extract_fields(item)
            scored.append({
                "idx": idx, "risk_score": risk, "cost_at_risk": cost_at_risk,
                "estimated_cost": est_cost, "estimated_duration_hours": est_hrs,
                "_orig": item,
            })
        scored.sort(key=lambda x: x["risk_score"], reverse=True)

        greedy_risk = sum(
            scored[k]["risk_score"] * scored[k]["cost_at_risk"]
            for k in range(greedy_n)
        )
        greedy_cost = sum(scored[k]["estimated_cost"] for k in range(greedy_n))

        # Convert to dict-list format for optimize_work_order_selection
        opt_candidates = [{
            "risk_score": s["risk_score"],
            "signals": {
                "cost_at_risk": s["cost_at_risk"],
                "estimated_cost": s["estimated_cost"],
                "estimated_duration_hours": s["estimated_duration_hours"],
            },
        } for s in scored]

        optimized = self.optimize_work_order_selection(opt_candidates, or_budget, or_max_orders)
        opt_risk = sum(
            o["risk_score"] * float(o.get("signals", {}).get("cost_at_risk", 5000))
            for o in optimized
        )
        opt_cost = sum(
            float(o.get("signals", {}).get("estimated_cost",
                float(o.get("signals", {}).get("cost_at_risk", 5000) * 0.15)))
            for o in optimized
        )

        summary = optimized[0].get("_or_summary", {}) if optimized else {}

        return {
            "strategy": cfg.strategy.value if hasattr(cfg.strategy, 'value') else str(cfg.strategy),
            "budget_limit": or_budget,
            "greedy_n_orders": greedy_n,
            "greedy_risk_reduction": round(greedy_risk, 2),
            "greedy_cost": round(greedy_cost, 2),
            "optimized_n_orders": len(optimized),
            "optimized_risk_reduction": round(opt_risk, 2),
            "optimized_cost": round(opt_cost, 2),
            "risk_improvement_pct": round((opt_risk - greedy_risk) / greedy_risk * 100, 1) if greedy_risk > 0 else 0,
            "budget_utilization_pct": summary.get("budget_utilization_pct", 0),
            "deferred_by_or": summary.get("n_greedy", greedy_n) - len(optimized) if len(optimized) < greedy_n else 0,
        }

    def calculate_dynamic_budget(self, plan_df: pd.DataFrame,
                                 coverage_ratio: float = 0.75) -> float:
        """
        Calculate a data-driven budget from cost_at_risk distribution.

        Budget = coverage_ratio × sum of estimated_cost for P1+P2 (high-risk) machines.
        Falls back to top-20 by urgency if priority column missing.
        """
        if plan_df.empty:
            return self.config.max_budget or 100000

        if "maintenance_priority" in plan_df.columns:
            high_risk = plan_df[plan_df["maintenance_priority"].isin(["P1", "P2"])]
        else:
            high_risk = plan_df.nlargest(min(20, len(plan_df)), "urgency_score")

        if "estimated_cost" in high_risk.columns:
            total = float(high_risk["estimated_cost"].sum())
        else:
            total = float(high_risk["cost_at_risk"].sum() * 0.15)

        return max(round(total * coverage_ratio, -3), 5000)  # round to nearest 1000, min $5K

    @staticmethod
    def _calculate_available_hours(horizon_days: int = 14) -> int:
        """Estimate available labor hours from technician schedule or fallback (cached)."""
        cache_attr = f'_cached_hours_{horizon_days}'
        cached = getattr(StrategySelector, cache_attr, None)
        if cached is not None:
            return cached
        tech_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "web-dashboard", "data", "technician_schedule.csv"
        )
        result = horizon_days * 8 * 2  # fallback
        if os.path.exists(tech_path):
            try:
                tech_df = pd.read_csv(tech_path, encoding="utf-8")
                if "available_hours" in tech_df.columns:
                    result = int(tech_df["available_hours"].head(horizon_days).sum())
            except Exception:
                pass
        setattr(StrategySelector, cache_attr, result)
        return result

    def get_sla(self, priority: str) -> int:
        """Return SLA target in hours for a given priority level."""
        return self.config.get_sla(priority)

    def get_threshold_description(self) -> str:
        """Return human-readable description of current strategy thresholds."""
        return self.config.get_threshold_description()

    def generate_strategy_comparison(
        self,
        signal_list: List[dict],
        engine: Any,
    ) -> pd.DataFrame:
        """
        Generate a 3-row comparison table showing how the same input signals
        produce different outputs under each strategy.

        Returns:
            DataFrame with one row per strategy.
        """
        from maintenance_decision_engine import AlertLevel

        rows: List[dict] = []
        for strat in MaintenanceStrategy:
            selector = StrategySelector(strat)
            filtered = selector.apply_strategy_thresholds(signal_list, engine)

            n_alarms = sum(1 for f in filtered if f["alert_level"] == AlertLevel.ALARM)
            n_warnings = sum(1 for f in filtered if f["alert_level"] == AlertLevel.WARNING)
            n_watch = sum(1 for f in filtered if f["alert_level"] == AlertLevel.WATCH)
            n_normal = sum(1 for f in filtered if f["alert_level"] == AlertLevel.NORMAL)
            n_orders = len([f for f in filtered
                            if f["alert_level"] != AlertLevel.NORMAL])

            risk_scores = [f["risk_score"] for f in filtered]
            costs = [f["signals"].get("cost_at_risk", 0) for f in filtered]

            # Average SLA for WARNING+ machines
            sla_vals = []
            for f in filtered:
                if f["alert_level"] in (AlertLevel.ALARM, AlertLevel.WARNING):
                    mp = "P1" if f["alert_level"] == AlertLevel.ALARM else "P2"
                    sla_vals.append(selector.get_sla(mp))

            rows.append({
                "strategy": strat.value,
                "n_alarms": n_alarms,
                "n_warnings": n_warnings,
                "n_watch": n_watch,
                "n_normal": n_normal,
                "n_work_orders": n_orders,
                "avg_risk_score": round(np.mean(risk_scores), 4) if risk_scores else 0.0,
                "total_estimated_cost": round(sum(costs), 2),
                "avg_sla_hours": round(np.mean(sla_vals), 1) if sla_vals else 0.0,
                "alarm_threshold": selector.config.alarm_threshold,
                "warning_threshold": selector.config.warning_threshold,
                "max_orders": selector.config.max_orders,
                "merge_downtime": selector.config.merge_downtime,
            })

        return pd.DataFrame(rows)
