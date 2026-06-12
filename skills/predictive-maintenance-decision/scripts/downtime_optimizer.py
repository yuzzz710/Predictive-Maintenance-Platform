#!/usr/bin/env python3
"""
Downtime Optimizer — Maintenance Window Scheduling Engine
===========================================================
Recommends optimal downtime windows based on urgency, cost-at-risk,
production impact, maintenance duration, and strategy preferences.

All scheduling logic is parameterized — no hardcoded time windows.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Tuple

import pandas as pd


class DowntimeWindow(Enum):
    IMMEDIATE = "immediate"    # Within 1 hour
    NIGHT = "night"            # Night shift (22:00–06:00)
    WEEKEND = "weekend"        # Next weekend
    NEXT_GAP = "next_gap"      # Next production gap
    SCHEDULED = "scheduled"    # Next planned maintenance window


class DowntimeOptimizer:
    """
    Risk-aware downtime window optimizer.

    Balances production impact against maintenance urgency to recommend
    the least-disruptive safe window for maintenance work.

    Usage:
        opt = DowntimeOptimizer(strategy_config)
        window, reasons = opt.optimize(urgency=85, cost_at_risk=12000,
                                        production_impact=5000, duration=4.0,
                                        risk_tier="High", pattern="thermal_buildup")
        start_time = opt.calculate_downtime_start(window, pd.Timestamp.now())
    """

    def __init__(self, strategy_config):
        """
        Args:
            strategy_config: StrategyConfig from strategy_selector
        """
        self.strategy_config = strategy_config

    def optimize(self, urgency_score: float, cost_at_risk: float,
                 production_impact: float, estimated_duration_hours: float,
                 risk_tier: str = "Medium",
                 primary_pattern: str = "normal") -> Tuple[DowntimeWindow, List[str]]:
        """
        Determine the optimal downtime window.

        Decision hierarchy (first match wins):
          1. Critical + high cost → IMMEDIATE
          2. High urgency + short repair → NIGHT
          3. Cost-efficiency strategy → batch merge
          4. Production-efficiency → ASAP within constraints
          5. Quality-first → fastest safe window
          6. Default → SCHEDULED

        Returns:
            Tuple of (DowntimeWindow, list of reasoning strings)
        """
        reasons: List[str] = []
        strat = self.strategy_config.strategy
        # Use .value since it could be either the enum or a string
        strat_value = strat.value if hasattr(strat, 'value') else str(strat)

        # Rule 1: 紧急情况 → 立即停机
        if urgency_score >= 85 and cost_at_risk >= 10000:
            reasons.append(
                f"紧急：紧急度={urgency_score:.0f}/100，"
                f"风险成本=${cost_at_risk:,.0f} — 需要立即处理"
            )
            return DowntimeWindow.IMMEDIATE, reasons

        # Rule 2: 高紧急度 + 短维修 → 夜间窗口（最小生产影响）
        if urgency_score >= 70 and estimated_duration_hours <= 4.0:
            reasons.append(
                f"高紧急度（{urgency_score:.0f}/100）且维修工时短"
                f"（{estimated_duration_hours}h）— 夜间窗口最小化生产损失"
            )
            return DowntimeWindow.NIGHT, reasons

        # Rule 3: 成本效率策略 → 批量/合并停机
        if strat_value == "cost_efficiency" and self.strategy_config.merge_downtime:
            if urgency_score >= 45:
                reasons.append(
                    "成本效率策略：合并至周末集中维修批次"
                )
                return DowntimeWindow.WEEKEND, reasons
            else:
                reasons.append(
                    "成本效率策略：推迟至下次计划内维护窗口"
                )
                return DowntimeWindow.SCHEDULED, reasons

        # Rule 4: 生产效率策略 → 最小化停机，优先保障关键设备
        if strat_value == "production_efficiency":
            if production_impact > 5000:
                reasons.append(
                    f"高价值设备（日产值影响=${production_impact:,.0f}）— "
                    f"夜间窗口最小化生产损失"
                )
                return DowntimeWindow.NIGHT, reasons
            elif risk_tier == "High":
                reasons.append(
                    f"高风险设备 — 利用下次生产间隙快速介入"
                )
                return DowntimeWindow.NEXT_GAP, reasons
            else:
                reasons.append(
                    "生产效率策略：安排在下一个可用间隙"
                )
                return DowntimeWindow.NEXT_GAP, reasons

        # Rule 5: 质量优先策略 → 最快安全响应
        if strat_value == "quality_first":
            if estimated_duration_hours <= 6.0:
                reasons.append(
                    "质量优先策略：夜间窗口进行最快无损修复"
                )
                return DowntimeWindow.NIGHT, reasons
            else:
                reasons.append(
                    f"质量优先策略：大修（{estimated_duration_hours}h）— "
                    f"立即处理以防止质量退化"
                )
                return DowntimeWindow.IMMEDIATE, reasons

        # Rule 6: 默认降级
        reasons.append("默认策略：安排在下一个计划维护窗口")
        return DowntimeWindow.SCHEDULED, reasons

    def calculate_downtime_start(self, window: DowntimeWindow,
                                  reference_date) -> datetime:
        """
        Calculate the actual downtime start datetime.

        Args:
            window: Recommended DowntimeWindow
            reference_date: Reference timestamp (pd.Timestamp or datetime)

        Returns:
            datetime object for the downtime start
        """
        if isinstance(reference_date, pd.Timestamp):
            ref = reference_date.to_pydatetime()
        elif isinstance(reference_date, datetime):
            ref = reference_date
        else:
            ref = datetime.now()

        if window == DowntimeWindow.IMMEDIATE:
            return ref + timedelta(hours=1)

        elif window == DowntimeWindow.NIGHT:
            # Push to tonight 22:00 (or tomorrow if already past 22:00)
            night = ref.replace(hour=22, minute=0, second=0, microsecond=0)
            if night <= ref:
                night += timedelta(days=1)
            return night

        elif window == DowntimeWindow.WEEKEND:
            # Push to next Saturday 08:00
            days_until_sat = (5 - ref.weekday()) % 7
            if days_until_sat == 0:
                days_until_sat = 7
            sat = ref.replace(hour=8, minute=0, second=0, microsecond=0)
            sat += timedelta(days=days_until_sat)
            return sat

        elif window == DowntimeWindow.NEXT_GAP:
            # Assume shift change gap ~12h from now
            return ref + timedelta(hours=12)

        else:  # SCHEDULED
            # Next planned maintenance (assume 7 days out)
            return ref + timedelta(days=7)

    def get_production_impact(self, daily_output: float, unit_cost: float,
                               estimated_duration_hours: float) -> float:
        """
        Calculate production impact in USD for a given downtime.

        Args:
            daily_output: Units produced per day
            unit_cost: Cost per unit (USD)
            estimated_duration_hours: Expected downtime in hours

        Returns:
            Production impact in USD
        """
        hourly_output = daily_output / 24.0
        lost_units = hourly_output * estimated_duration_hours
        return round(lost_units * unit_cost, 2)
