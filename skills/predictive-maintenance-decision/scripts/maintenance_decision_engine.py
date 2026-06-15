#!/usr/bin/env python3
"""
Predictive Maintenance Decision Engine v3
==========================================
Upgrades the v2 AlertManager into a full 4-layer maintenance decision system.

Layer 1 — Input Fusion:     ML density + Z-Score anomaly + cost risk + trend signals
Layer 2 — Diagnostic:       Anomaly pattern recognition (voltage drift / thermal / power / combined)
Layer 3 — Decision:         Maintenance action recommendation (6 action types)
Layer 4 — Output:           Work order prioritization + cost-loss estimation

Design Principles:
  - Engineering feasibility over ML accuracy (model is weak, system compensates)
  - Cost-weighted risk as primary decision driver
  - Multiple evidence sources cross-validated
  - Actionable recommendations, not just alerts

Author : Predictive Maintenance Team
Date   : 2026-05-17
"""

import numpy as np
import pandas as pd
import os, json, sys, warnings
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

warnings.filterwarnings("ignore")

# ============================================================================
# Type Definitions
# ============================================================================

class AlertLevel(Enum):
    NORMAL = 0
    WATCH = 1
    WARNING = 2
    ALARM = 3


class ActionType(Enum):
    NO_ACTION = "no_action"
    ROUTINE_CHECK = "routine_check"
    INCREASE_MONITORING = "increase_monitoring"
    SCHEDULE_INSPECTION = "schedule_inspection"
    PREVENTIVE_REPAIR = "preventive_repair"
    IMMEDIATE_SHUTDOWN = "immediate_shutdown"


@dataclass
class DiagnosticResult:
    """Output of Layer 2: anomaly pattern diagnosis."""
    machine_id: str
    primary_pattern: str  # "voltage_drift", "thermal_buildup", "power_anomaly", "combined_degradation", "normal"
    patterns_detected: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0-1
    evidence: Dict[str, float] = field(default_factory=dict)


@dataclass
class MaintenanceDecision:
    """Output of Layer 3: actionable recommendation."""
    machine_id: str
    alert_level: AlertLevel
    action_type: ActionType
    urgency_score: float  # 0-100
    estimated_cost_at_risk: float
    recommended_window_days: int  # "do within N days"
    reasoning: List[str] = field(default_factory=list)


@dataclass
class WorkOrder:
    """Output of Layer 4: prioritized maintenance work order."""
    priority: int
    machine_id: str
    alert_level: AlertLevel
    action_type: ActionType
    cost_at_risk: float
    urgency_score: float
    recommended_window_days: int
    expected_savings: float  # cost avoided by acting
    maintenance_suggestion: str
    # SHAP explainability fields (populated by shap_postprocess after decision)
    top_risk_factor_1: str = ""
    top_risk_factor_2: str = ""
    top_risk_factor_3: str = ""
    shap_explanation: str = ""
    shap_risk_summary: str = ""


# ============================================================================
# Maintenance Decision Engine
# ============================================================================

class MaintenanceDecisionEngine:
    """
    Full predictive maintenance decision system.

    Usage:
        engine = MaintenanceDecisionEngine(cost_risk_df, baseline_stats)
        for each machine at each evaluation step:
            signals = {
                "ml_fault_density": 0.72,
                "z_comp_mean": 1.8, "z_comp_max": 3.2,
                "z_v": 2.1, "z_a": 0.5, "z_t": 1.3,
                "thermal_over_p95": 2,
                "voltage_trend_slope": 0.05,
                "temp_trend_slope": 0.03,
                "consecutive_faults": 3,
                "cost_at_risk": 5200,
                "machine_id": "CNC_085",
            }
            decision = engine.evaluate(signals)
    """

    def __init__(self, cost_risk_data: pd.DataFrame = None, config: dict = None):
        """
        Args:
            cost_risk_data: DataFrame with columns [Equipment.Id, cost_at_risk, failure_rate, ...]
            config: Override default configuration
        """
        self.config = {
            # Layer 1: Input fusion weights (4-signal, for RUL-unavailable fallback)
            "fusion": {
                "ml_density_weight": 0.25,     # reduced from 0.40 — ML is weak
                "stat_anomaly_weight": 0.40,    # increased — Z-Score is our best signal
                "cost_risk_weight": 0.25,       # cost stays important
                "trend_weight": 0.10,           # new: trend signals
                # v3.1: 5-signal fusion weights (used when RUL is available)
                "ml_density_weight_v3": 0.20,
                "stat_anomaly_weight_v3": 0.35,
                "cost_risk_weight_v3": 0.20,
                "rul_urgency_weight": 0.15,
            },

            # Layer 2: Diagnostic thresholds
            "diagnostic": {
                "voltage_drift": {"z_v_threshold": 2.0, "trend_min": 0.02},
                "thermal_buildup": {"z_t_threshold": 2.0, "over_p95_min": 2},
                "power_anomaly": {"z_v_threshold": 1.5, "z_a_threshold": 1.5},
                "combined_degradation": {"min_params_abnormal": 2, "z_threshold": 2.0},
            },

            # Layer 3: Decision thresholds
            "decision": {
                "alarm_urgency": 70,
                "warning_urgency": 45,
                "watch_urgency": 25,
                "high_cost_threshold": 5000,
                "critical_cost_threshold": 10000,
                "immediate_shutdown_z": 5.0,  # z-score at which we recommend shutdown
            },

            # Layer 4: Work order configuration
            "work_order": {
                "max_orders_per_cycle": 20,
                "max_budget": 0,               # 0 = unlimited; >0 = budget cap in USD
                "preventive_cost_ratio": 0.30,  # preventive costs 30% of corrective
                "emergency_cost_multiplier": 3.0,  # emergency repair costs 3x
            },

            # Continuous confirmation (retained from v2)
            "confirmation": {
                "upgrade_windows": {"ALARM": 3, "WARNING": 2, "WATCH": 1},
                "downgrade_windows": {"ALARM": 3, "WARNING": 2, "WATCH": 2},
            },

            # Maintenance strategy rules
            "strategy": {
                "high_cost_inspection_days": 3,
                "mid_cost_inspection_days": 7,
                "low_cost_inspection_days": 14,
                "routine_check_days": 30,
                "monitoring_frequency_normal": 30,
                "monitoring_frequency_watch": 7,
                "monitoring_frequency_warning": 3,
                "monitoring_frequency_alarm": 1,
            },
        }
        if config:
            self._deep_update(self.config, config)

        # Per-machine state
        self.machine_states: Dict[str, dict] = {}

        # Cost risk reference data
        self.cost_data: Dict[str, dict] = {}
        if cost_risk_data is not None:
            self._load_cost_data(cost_risk_data)

        # Global cost percentile thresholds
        self._compute_cost_thresholds()

        # Historical decisions log
        self.decision_history: List[MaintenanceDecision] = []

    def _deep_update(self, d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d:
                self._deep_update(d[k], v)
            else:
                d[k] = v

    def _load_cost_data(self, df: pd.DataFrame):
        for _, row in df.iterrows():
            mid = row.get("Equipment.Id", row.get("machine_id", ""))
            self.cost_data[mid] = {
                "cost_at_risk": float(row.get("cost_at_risk", 0)),
                "failure_rate": float(row.get("failure_rate", 0)),
                "unit_cost": float(row.get("Unit Cost of Production", row.get("unit_cost", 5))),
                "daily_output": float(row.get("Units Produced Per day", row.get("daily_output", 1000))),
                "risk_tier": str(row.get("risk_tier", "Medium")),
            }

    def _compute_cost_thresholds(self):
        costs = [d["cost_at_risk"] for d in self.cost_data.values()]
        if costs:
            self.cost_p50 = np.percentile(costs, 50)
            self.cost_p75 = np.percentile(costs, 75)
            self.cost_p90 = np.percentile(costs, 90)
        else:
            self.cost_p50 = 4500
            self.cost_p75 = 5000
            self.cost_p90 = 5500

    # ========================================================================
    # Layer 1: Input Fusion
    # ========================================================================

    def fuse_signals(self, signals: dict) -> float:
        """
        Combine multiple weak signals into a single anomaly risk score [0, 1].

        Each individual signal is weak (AUC ~0.5-0.6), but combined they provide
        a more reliable risk indicator than any single source.

        v3.1: Added RUL urgency as 5th signal (0.15 weight).
        When RUL is unavailable, automatically falls back to 4-signal fusion.
        """
        w = self.config["fusion"]

        # ML signal: fault density prediction
        ml_sig = np.clip(float(signals.get("ml_fault_density", 0)), 0, 1)

        # Statistical anomaly signal
        z_mean = float(signals.get("z_comp_mean", 0))
        z_max = float(signals.get("z_comp_max", 0))
        thermal = float(signals.get("thermal_over_p95", 0))

        z_signal = np.clip(z_mean / 3.0, 0, 1) * 0.7 + np.clip(z_max / 5.0, 0, 1) * 0.3
        t_signal = np.clip(thermal / 5.0, 0, 1)
        stat_sig = 0.75 * z_signal + 0.25 * t_signal

        # Cost risk signal
        cost = float(signals.get("cost_at_risk", self.cost_p50))
        if cost >= self.cost_p90:
            cost_sig = 0.95
        elif cost >= self.cost_p75:
            cost_sig = 0.70 + 0.25 * (cost - self.cost_p75) / (self.cost_p90 - self.cost_p75 + 1)
        elif cost >= self.cost_p50:
            cost_sig = 0.40 + 0.30 * (cost - self.cost_p50) / (self.cost_p75 - self.cost_p50 + 1)
        else:
            cost_sig = 0.30 * cost / (self.cost_p50 + 1)

        # Trend signal: is any parameter drifting?
        v_trend = abs(float(signals.get("voltage_trend_slope", 0)))
        t_trend = abs(float(signals.get("temp_trend_slope", 0)))
        a_trend = abs(float(signals.get("amperage_trend_slope", 0)))

        trend_sig = np.clip(
            np.clip(v_trend / 0.02, 0, 1) * 0.4 +
            np.clip(t_trend / 0.02, 0, 1) * 0.35 +
            np.clip(a_trend / 0.02, 0, 1) * 0.25,
            0, 1
        )

        # RUL urgency signal (v3.1): shorter RUL → higher urgency
        rul_days = signals.get("rul_days", None)
        rul_available = rul_days is not None and not np.isnan(float(rul_days))

        if rul_available:
            # RUL urgency: 0 = RUL > 30 days (no urgency), 1 = RUL <= 0 (critical)
            rul_days_val = float(rul_days)
            rul_urgency = max(0.0, 1.0 - min(rul_days_val, 30.0) / 30.0)

            # 5-signal fusion weights (v3.1)
            risk_score = (
                w.get("ml_density_weight_v3", 0.20) * ml_sig +
                w.get("stat_anomaly_weight_v3", 0.35) * stat_sig +
                w.get("cost_risk_weight_v3", 0.20) * cost_sig +
                w.get("trend_weight", 0.10) * trend_sig +
                w.get("rul_urgency_weight", 0.15) * rul_urgency
            )
        else:
            # Fallback: 4-signal fusion (RUL unavailable — auto-degrade)
            # Use existing weights (sum to 1.0)
            risk_score = (
                w["ml_density_weight"] * ml_sig +
                w["stat_anomaly_weight"] * stat_sig +
                w["cost_risk_weight"] * cost_sig +
                w["trend_weight"] * trend_sig
            )

        return float(np.clip(risk_score, 0, 1))

    # ========================================================================
    # Layer 2: Diagnostic — Anomaly Pattern Recognition
    # ========================================================================

    def diagnose(self, signals: dict) -> DiagnosticResult:
        """
        Identify the specific anomaly pattern from parameter signatures.

        Unlike generic "alert or no alert", this tells operators WHAT is happening:
        - voltage_drift: PSU degradation, bus voltage instability
        - thermal_buildup: cooling system issue, bearing friction
        - power_anomaly: load mismatch, winding degradation
        - combined_degradation: multiple parameters abnormal
        """
        diag_cfg = self.config["diagnostic"]
        mid = str(signals.get("machine_id", "unknown"))
        patterns = []
        evidence = {}

        z_v = float(signals.get("z_v", 0))
        z_a = float(signals.get("z_a", 0))
        z_t = float(signals.get("z_t", 0))
        v_trend = float(signals.get("voltage_trend_slope", 0))
        t_trend = float(signals.get("temp_trend_slope", 0))
        thermal_p95 = float(signals.get("thermal_over_p95", 0))

        # Pattern 1: Voltage drift
        v_cfg = diag_cfg["voltage_drift"]
        if abs(z_v) > v_cfg["z_v_threshold"] and abs(v_trend) > v_cfg["trend_min"]:
            patterns.append("voltage_drift")
            evidence["voltage_drift"] = min(1.0, abs(z_v) / 4.0)

        # Pattern 2: Thermal buildup
        t_cfg = diag_cfg["thermal_buildup"]
        if abs(z_t) > t_cfg["z_t_threshold"] and thermal_p95 >= t_cfg["over_p95_min"]:
            patterns.append("thermal_buildup")
            evidence["thermal_buildup"] = min(1.0, abs(z_t) / 4.0)

        # Pattern 3: Power anomaly
        p_cfg = diag_cfg["power_anomaly"]
        if abs(z_v) > p_cfg["z_v_threshold"] and abs(z_a) > p_cfg["z_a_threshold"]:
            patterns.append("power_anomaly")
            evidence["power_anomaly"] = min(1.0, (abs(z_v) + abs(z_a)) / 8.0)

        # Pattern 4: Combined degradation
        c_cfg = diag_cfg["combined_degradation"]
        abnormal_count = sum([
            abs(z_v) > c_cfg["z_threshold"],
            abs(z_a) > c_cfg["z_threshold"],
            abs(z_t) > c_cfg["z_threshold"],
        ])
        if abnormal_count >= c_cfg["min_params_abnormal"]:
            patterns.append("combined_degradation")
            evidence["combined_degradation"] = min(1.0, abnormal_count / 3.0)

        # Determine primary pattern
        if not patterns:
            primary = "normal"
            confidence = 0.0
        elif len(patterns) == 1:
            primary = patterns[0]
            confidence = evidence.get(primary, 0.3)
        else:
            # Multiple patterns → combined is primary if present
            if "combined_degradation" in patterns:
                primary = "combined_degradation"
            else:
                primary = max(patterns, key=lambda p: evidence.get(p, 0))
            confidence = max(evidence.get(p, 0) for p in patterns)

        return DiagnosticResult(
            machine_id=mid,
            primary_pattern=primary,
            patterns_detected=patterns,
            confidence=confidence,
            evidence=evidence,
        )

    # ========================================================================
    # Layer 3: Decision — Maintenance Action Recommendation
    # ========================================================================

    def decide(self, risk_score: float, diagnosis: DiagnosticResult,
               signals: dict) -> MaintenanceDecision:
        """
        Convert risk score + diagnosis into actionable maintenance recommendation.

        Returns specific actions, not just alert levels:
        - "Inspect voltage regulator within 3 days" vs "WARNING"
        - "Check cooling system this week" vs "WATCH"
        """
        dec_cfg = self.config["decision"]
        strat_cfg = self.config["strategy"]
        mid = diagnosis.machine_id
        cost = float(signals.get("cost_at_risk", self.cost_p50))

        # Determine alert level from risk score
        if risk_score >= 0.75:
            alert_level = AlertLevel.ALARM
            base_urgency = 85
        elif risk_score >= 0.55:
            alert_level = AlertLevel.WARNING
            base_urgency = 55
        elif risk_score >= 0.35:
            alert_level = AlertLevel.WATCH
            base_urgency = 30
        else:
            alert_level = AlertLevel.NORMAL
            base_urgency = 5

        # Adjust urgency by cost tier
        cost_multiplier = 1.0
        if cost >= self.config["decision"]["critical_cost_threshold"]:
            cost_multiplier = 1.4
        elif cost >= self.config["decision"]["high_cost_threshold"]:
            cost_multiplier = 1.2
        elif cost < self.cost_p50:
            cost_multiplier = 0.8

        urgency = min(100, base_urgency * cost_multiplier)

        # Determine action type based on alert level + diagnosis + cost
        reasoning = []
        action_type, window_days = self._determine_action(
            alert_level, diagnosis, cost, urgency, signals, reasoning
        )

        # Estimate cost at risk
        corrective_cost = cost * self.config["work_order"]["emergency_cost_multiplier"]
        preventive_cost = cost * self.config["work_order"]["preventive_cost_ratio"]
        estimated_cost_at_risk = corrective_cost if alert_level in (AlertLevel.ALARM, AlertLevel.WARNING) else preventive_cost

        decision = MaintenanceDecision(
            machine_id=mid,
            alert_level=alert_level,
            action_type=action_type,
            urgency_score=urgency,
            estimated_cost_at_risk=estimated_cost_at_risk,
            recommended_window_days=window_days,
            reasoning=reasoning,
        )
        self.decision_history.append(decision)
        return decision

    def _determine_action(self, alert_level: AlertLevel, diagnosis: DiagnosticResult,
                          cost: float, urgency: float, signals: dict,
                          reasoning: List[str]) -> Tuple[ActionType, int]:
        """Map alert level + diagnosis to specific action and time window."""
        strat = self.config["strategy"]
        z_max = float(signals.get("z_comp_max", 0))
        z_v = float(signals.get("z_v", 0))
        z_t = float(signals.get("z_t", 0))
        z_a = float(signals.get("z_a", 0))

        # Extreme outlier: z > 10 is 10 sigma from normal — genuine emergency
        if z_max >= 10.0:
            reasoning.append(f"CRITICAL: Z-score max = {z_max:.1f} — extreme deviation from baseline")
            return ActionType.IMMEDIATE_SHUTDOWN, 0

        if alert_level == AlertLevel.ALARM:
            # Determine which parameter is driving the alarm
            param_alerts = []
            if abs(z_v) > 2.5: param_alerts.append(f"Voltage (z={z_v:.1f})")
            if abs(z_t) > 2.5: param_alerts.append(f"Temperature (z={z_t:.1f})")
            if abs(z_a) > 2.5: param_alerts.append(f"Amperage (z={z_a:.1f})")

            if param_alerts:
                reasoning.append(f"Parameters out of range: {', '.join(param_alerts)}")

            if z_max >= 8.0:
                reasoning.append(f"Severe deviation (z_max={z_max:.1f}) — urgent inspection needed")
                return ActionType.PREVENTIVE_REPAIR, 1  # within 1 day

            if cost >= self.config["decision"]["high_cost_threshold"]:
                reasoning.append(f"High-cost machine (${cost:,.0f} at risk) at ALARM level")
                return ActionType.PREVENTIVE_REPAIR, strat["high_cost_inspection_days"]
            else:
                reasoning.append(f"ALARM: {diagnosis.primary_pattern} pattern")
                return ActionType.SCHEDULE_INSPECTION, strat["mid_cost_inspection_days"]

        elif alert_level == AlertLevel.WARNING:
            if diagnosis.primary_pattern in ("thermal_buildup", "voltage_drift"):
                reasoning.append(f"Specific pattern '{diagnosis.primary_pattern}' detected")
                return ActionType.SCHEDULE_INSPECTION, strat["mid_cost_inspection_days"]
            elif diagnosis.primary_pattern in ("power_anomaly", "combined_degradation"):
                reasoning.append(f"Pattern '{diagnosis.primary_pattern}' — schedule inspection")
                return ActionType.SCHEDULE_INSPECTION, strat["mid_cost_inspection_days"]
            else:
                reasoning.append("WARNING: elevated parameters, no clear degradation pattern")
                return ActionType.INCREASE_MONITORING, strat["low_cost_inspection_days"]

        elif alert_level == AlertLevel.WATCH:
            if diagnosis.primary_pattern != "normal":
                reasoning.append(f"Mild pattern '{diagnosis.primary_pattern}' — increase monitoring")
                return ActionType.INCREASE_MONITORING, strat["monitoring_frequency_watch"]
            else:
                return ActionType.ROUTINE_CHECK, strat["routine_check_days"]

        else:  # NORMAL
            return ActionType.NO_ACTION, strat["routine_check_days"]

    # ========================================================================
    # Layer 4: Output — Work Order Prioritization
    # ========================================================================

    def generate_work_orders(self) -> List[WorkOrder]:
        """
        Convert accumulated decisions into prioritized maintenance work orders.

        Priority ranking considers:
        1. Urgency score (immediate risk)
        2. Cost at risk (economic impact)
        3. Alert level severity
        """
        if not self.decision_history:
            return []

        # Only include actionable decisions (WATCH or above, non-routine actions)
        active = [d for d in self.decision_history
                  if d.alert_level != AlertLevel.NORMAL
                  and d.action_type not in (ActionType.NO_ACTION, ActionType.ROUTINE_CHECK)]
        # Deduplicate by machine_id (keep highest urgency)
        seen = {}
        for d in active:
            mid = d.machine_id
            if mid not in seen or d.urgency_score > seen[mid].urgency_score:
                seen[mid] = d
        active = list(seen.values())

        # Sort by: urgency (desc) + cost_at_risk (desc)
        active.sort(key=lambda d: (d.urgency_score, d.estimated_cost_at_risk), reverse=True)

        # Limit to max orders per cycle
        max_orders = self.config["work_order"]["max_orders_per_cycle"]
        active = active[:max_orders]

        # Budget-constrained optimization (0/1 knapsack greedy by cost-efficiency)
        max_budget = self.config["work_order"].get("max_budget", 0)
        if max_budget > 0:
            ratio = self.config["work_order"]["preventive_cost_ratio"]
            # Compute preventive cost and cost-efficiency for each candidate
            for d in active:
                d._preventive_cost = d.estimated_cost_at_risk * ratio
                d._cost_efficiency = d.urgency_score / max(d._preventive_cost, 1.0)
            # Sort by cost-efficiency (urgency per dollar) descending
            active.sort(key=lambda d: d._cost_efficiency, reverse=True)
            # Greedy selection within budget
            budgeted = []
            spent = 0.0
            for d in active:
                if spent + d._preventive_cost <= max_budget:
                    budgeted.append(d)
                    spent += d._preventive_cost
            # Re-sort budgeted by urgency for final priority ranking
            budgeted.sort(key=lambda d: (d.urgency_score, d.estimated_cost_at_risk), reverse=True)
            active = budgeted

        work_orders = []
        for rank, decision in enumerate(active, 1):
            # Expected savings = (emergency cost - preventive cost) if we act now
            emergency_cost = decision.estimated_cost_at_risk
            preventive_cost = decision.estimated_cost_at_risk * self.config["work_order"]["preventive_cost_ratio"]
            expected_savings = emergency_cost - preventive_cost

            # Generate specific maintenance suggestion
            suggestion = self._generate_suggestion(decision)

            work_orders.append(WorkOrder(
                priority=rank,
                machine_id=decision.machine_id,
                alert_level=decision.alert_level,
                action_type=decision.action_type,
                cost_at_risk=decision.estimated_cost_at_risk,
                urgency_score=decision.urgency_score,
                recommended_window_days=decision.recommended_window_days,
                expected_savings=expected_savings,
                maintenance_suggestion=suggestion,
            ))

        return work_orders

    def _generate_suggestion(self, decision: MaintenanceDecision) -> str:
        """Generate human-readable maintenance suggestion with specifics."""
        mid = decision.machine_id
        cost_info = self.cost_data.get(mid, {})
        unit_cost = cost_info.get("unit_cost", 5)
        daily_output = cost_info.get("daily_output", 1000)
        daily_value = unit_cost * daily_output
        risk_tier = cost_info.get("risk_tier", "Medium")

        risk_tier_cn = {"High": "高", "Medium": "中", "Low": "低"}.get(risk_tier, risk_tier)

        if decision.action_type == ActionType.PREVENTIVE_REPAIR:
            return (
                f"[{risk_tier_cn}风险等级] {decision.recommended_window_days}日内执行预防性维修。"
                f"日产值风险：${daily_value:,.0f}。"
                f"立即处理可避免紧急维修成本约：~${decision.estimated_cost_at_risk * 0.7:,.0f}。"
                f"重点关注：{decision.reasoning[0] if decision.reasoning else '参数异常'}"
            )

        elif decision.action_type == ActionType.SCHEDULE_INSPECTION:
            focus = decision.reasoning[0] if decision.reasoning else '参数偏移'
            return (
                f"[{risk_tier_cn}风险等级] {decision.recommended_window_days}日内安排检查。"
                f"重点项：{focus}。"
                f"日产值风险：${daily_value:,.0f}。"
                f"建议检查项：电气特征分析、热成像、物理检查。"
            )

        elif decision.action_type == ActionType.INCREASE_MONITORING:
            return (
                f"加密监控至每{decision.recommended_window_days}日一次。"
                f"跟踪指标：{decision.reasoning[0] if decision.reasoning else '全部参数'}。"
                f"如参数继续偏移，升级为安排检查。"
            )

        elif decision.action_type == ActionType.ROUTINE_CHECK:
            return (
                f"继续常规维护（{decision.recommended_window_days}日后下次检查）。"
                f"风险成本：${decision.estimated_cost_at_risk:,.0f}。基线监控即可。"
            )

        elif decision.action_type == ActionType.IMMEDIATE_SHUTDOWN:
            return (
                f"*** 立即停机 *** 参数偏离已达临界值。"
                f"日产值暴露：${daily_value:,.0f}。"
                f"启动应急预案，立即联系维护主管。"
                f"根因推测：{decision.reasoning[0] if decision.reasoning else '严重参数偏离'}。"
            )

        else:
            return "无需处理。按维护计划进行标准监控。"

    # ========================================================================
    # Main evaluation entry point
    # ========================================================================

    def evaluate(self, signals: dict, streaming: bool = False) -> dict:
        """
        Full evaluation pipeline: Input -> Diagnose -> Decide -> Output.

        Args:
            signals: dict with keys:
                ml_fault_density, z_comp_mean, z_comp_max, z_v, z_a, z_t,
                thermal_over_p95, voltage_trend_slope, temp_trend_slope,
                amperage_trend_slope, cost_at_risk, machine_id
            streaming: If True, apply continuous confirmation (for sequential data).
                       If False (default), use single-snapshot alert level directly.

        Returns:
            dict with risk_score, alert_level, action_type, diagnosis, suggestion
        """
        mid = str(signals.get("machine_id", "unknown"))

        # Initialize state if new machine
        if mid not in self.machine_states:
            self.machine_states[mid] = {
                "current_level": AlertLevel.NORMAL,
                "consecutive_up": 0,
                "consecutive_down": 0,
                "risk_history": [],
                "diagnosis_history": [],
            }

        state = self.machine_states[mid]

        # Layer 1: Signal fusion
        risk_score = self.fuse_signals(signals)
        state["risk_history"].append(risk_score)
        if len(state["risk_history"]) > 50:
            state["risk_history"] = state["risk_history"][-50:]

        # Layer 2: Diagnosis
        diagnosis = self.diagnose(signals)
        state["diagnosis_history"].append(diagnosis)
        if len(state["diagnosis_history"]) > 20:
            state["diagnosis_history"] = state["diagnosis_history"][-20:]

        # Layer 3: Decision
        decision = self.decide(risk_score, diagnosis, signals)

        # Apply continuous confirmation only in streaming mode
        if streaming:
            confirmed_level = self._apply_confirmation(state, decision.alert_level)
            decision.alert_level = confirmed_level

        # Layer 4: Generate immediate suggestion
        suggestion = self._generate_suggestion(decision)

        return {
            "machine_id": mid,
            "risk_score": round(risk_score, 4),
            "alert_level": decision.alert_level.name,
            "action_type": decision.action_type.value,
            "urgency_score": round(decision.urgency_score, 1),
            "estimated_cost_at_risk": round(decision.estimated_cost_at_risk, 0),
            "recommended_window_days": decision.recommended_window_days,
            "primary_pattern": diagnosis.primary_pattern,
            "patterns_detected": diagnosis.patterns_detected,
            "diagnosis_confidence": round(diagnosis.confidence, 3),
            "maintenance_suggestion": suggestion,
        }

    def _apply_confirmation(self, state: dict, target_level: AlertLevel) -> AlertLevel:
        """Continuous confirmation to prevent alert jitter."""
        levels = [AlertLevel.NORMAL, AlertLevel.WATCH, AlertLevel.WARNING, AlertLevel.ALARM]
        current = state["current_level"]
        current_idx = levels.index(current)
        target_idx = levels.index(target_level)
        cfg = self.config["confirmation"]

        if target_idx > current_idx:
            state["consecutive_up"] += 1
            state["consecutive_down"] = 0
            required = cfg["upgrade_windows"].get(target_level.name, 1)
            if state["consecutive_up"] >= required:
                state["current_level"] = target_level
                state["consecutive_up"] = 0
                return target_level
            return current

        elif target_idx < current_idx:
            state["consecutive_down"] += 1
            state["consecutive_up"] = 0
            required = cfg["downgrade_windows"].get(current.name, 2)
            if state["consecutive_down"] >= required:
                state["current_level"] = levels[current_idx - 1]
                state["consecutive_down"] = 0
                return levels[current_idx - 1]
            return current

        else:
            state["consecutive_up"] = 0
            state["consecutive_down"] = 0
            return target_level

    # ========================================================================
    # Batch Evaluation & Reporting
    # ========================================================================

    def evaluate_batch(self, signal_list: List[dict]) -> pd.DataFrame:
        """Evaluate a batch of signals and return a DataFrame."""
        results = [self.evaluate(s) for s in signal_list]
        df = pd.DataFrame(results)

        # Sort by urgency
        if "urgency_score" in df.columns:
            df = df.sort_values("urgency_score", ascending=False)

        return df

    def generate_batch_report(self, result_df: pd.DataFrame) -> str:
        """Generate a human-readable maintenance report from evaluation results."""
        df = result_df

        lines = []
        lines.append("=" * 70)
        lines.append("PREDICTIVE MAINTENANCE DECISION REPORT")
        lines.append("=" * 70)
        lines.append(f"Total machines evaluated: {len(df)}")
        lines.append(f"Generated at: {pd.Timestamp.now()}")
        lines.append("")

        # Summary by alert level
        lines.append("--- Alert Level Distribution ---")
        for level in ["ALARM", "WARNING", "WATCH", "NORMAL"]:
            count = (df["alert_level"] == level).sum()
            lines.append(f"  {level}: {count} machines")
        lines.append("")

        # Summary by pattern
        lines.append("--- Anomaly Pattern Distribution ---")
        for pattern in df["primary_pattern"].value_counts().index:
            count = (df["primary_pattern"] == pattern).sum()
            lines.append(f"  {pattern}: {count} machines")
        lines.append("")

        # Top risk machines
        lines.append("--- Top 10 High-Risk Machines ---")
        for rank, (_, row) in enumerate(df.head(10).iterrows(), 1):
            lines.append(
                f"  #{rank} {row['machine_id']}: "
                f"Risk={row['risk_score']:.3f}, {row['alert_level']}, "
                f"Pattern={row['primary_pattern']}, "
                f"Action={row['action_type']}, "
                f"Window={row['recommended_window_days']}d"
            )
        lines.append("")

        # Work orders
        lines.append("--- Prioritized Work Orders ---")
        orders = self.generate_work_orders()
        if orders:
            for order in orders:
                lines.append(f"  [{order.priority}] {order.machine_id}: {order.maintenance_suggestion[:120]}...")
        else:
            lines.append("  No active work orders — all machines NORMAL.")
        lines.append("")

        lines.append("=" * 70)
        lines.append("END OF REPORT")
        lines.append("=" * 70)

        return "\n".join(lines)


# ============================================================================
# Utility: Build signal dict from a machine's data row
# ============================================================================

def build_signal_from_row(row: dict, cost_data: dict = None) -> dict:
    """Construct the signals dict expected by MaintenanceDecisionEngine from a data row."""
    # RUL days: accept rul_days, rul_hours, or compute from rul_steps
    rul_days = None
    if "rul_days" in row:
        rul_days = row.get("rul_days")
    elif "rul_hours" in row:
        rul_hours = row.get("rul_hours")
        if rul_hours is not None and not (isinstance(rul_hours, float) and np.isnan(rul_hours)):
            rul_days = float(rul_hours) / 24.0
    elif "rul_steps" in row:
        rul_steps = row.get("rul_steps")
        if rul_steps is not None and not (isinstance(rul_steps, float) and np.isnan(rul_steps)):
            rul_days = float(rul_steps) * 14.0 / (60.0 * 24.0)  # steps * 14min → days

    signals = {
        "machine_id": str(row.get("machine_id", row.get("Equipment.Id", "unknown"))),
        "ml_fault_density": float(row.get("fault_density_pred", row.get("P_fault_5steps", 0.7))),
        "z_comp_mean": float(row.get("z_comp_mean", 0)),
        "z_comp_max": float(row.get("z_comp_max", 0)),
        "z_v": float(row.get("z_v_last", 0)),
        "z_a": float(row.get("z_a_last", 0)),
        "z_t": float(row.get("z_t_last", 0)),
        "thermal_over_p95": float(row.get("thermal_over_p95", 0)),
        "voltage_trend_slope": float(row.get("v_slope", 0)),
        "temp_trend_slope": float(row.get("t_slope", 0)),
        "amperage_trend_slope": float(row.get("a_slope", 0)),
        "cost_at_risk": float(row.get("cost_at_risk", 5000)),
        "rul_days": rul_days,
    }
    return signals


# ============================================================================
# Demonstration: Run on v2 prediction report
# ============================================================================

def run_demo():
    """Demonstrate the decision engine using v2 prediction report data."""
    print("=" * 60)
    print("Maintenance Decision Engine v3 — Demonstration")
    print("=" * 60)

    # Load cost risk data + z-scores
    baseline_dir = "../基线分析和确定"
    cost_risk_path = os.path.join(baseline_dir, "cost_risk_matrix.csv")
    zscores_path = os.path.join(baseline_dir, "z_scores.csv")
    v2_dir = "../预测性维护模型_v2/model_outputs"

    cost_risk_df = None
    if os.path.exists(cost_risk_path):
        cost_risk_df = pd.read_csv(cost_risk_path)

    # Load z-scores and compute per-machine latest aggregates
    z_agg = {}
    if os.path.exists(zscores_path):
        zs = pd.read_csv(zscores_path)
        zs["Date"] = pd.to_datetime(zs["Date"])
        for mid, grp in zs.groupby("Equipment.Id"):
            latest = grp.sort_values("Date").iloc[-1]
            last_n = grp.sort_values("Date").tail(5)
            z_agg[mid] = {
                "z_v_last": float(latest["z_Voltage"]),
                "z_a_last": float(latest["z_Amperage"]),
                "z_t_last": float(latest["z_Temperature"]),
                "z_comp_mean": float(last_n["z_composite"].mean()),
                "z_comp_max": float(last_n["z_composite"].max()),
                "thermal_over_p95": int(last_n["z_Temperature"].abs().gt(2.0).sum()),
                "v_slope": float(last_n["z_Voltage"].diff().mean()) if len(last_n) >= 3 else 0.0,
                "t_slope": float(last_n["z_Temperature"].diff().mean()) if len(last_n) >= 3 else 0.0,
                "a_slope": float(last_n["z_Amperage"].diff().mean()) if len(last_n) >= 3 else 0.0,
            }
        print(f"  Loaded z-score data for {len(z_agg)} machines")

    # Initialize engine
    engine = MaintenanceDecisionEngine(cost_risk_data=cost_risk_df)

    # Load v2 prediction report
    pred_path = os.path.join(v2_dir, "prediction_report.csv")
    if os.path.exists(pred_path):
        pred_df = pd.read_csv(pred_path)

        # Convert each row to signal dict, enriched with real z-score data
        signal_list = []
        for _, row in pred_df.iterrows():
            signals = build_signal_from_row(row.to_dict())
            mid = signals["machine_id"]

            # Enrich with real z-score data from baseline analysis
            if mid in z_agg:
                z = z_agg[mid]
                signals["z_v_last"] = z["z_v_last"]
                signals["z_a_last"] = z["z_a_last"]
                signals["z_t_last"] = z["z_t_last"]
                signals["z_comp_mean"] = z["z_comp_mean"]
                signals["z_comp_max"] = z["z_comp_max"]
                signals["thermal_over_p95"] = z["thermal_over_p95"]
                signals["voltage_trend_slope"] = z["v_slope"]
                signals["temp_trend_slope"] = z["t_slope"]
                signals["amperage_trend_slope"] = z["a_slope"]

            # Enrich with cost data
            if cost_risk_df is not None:
                cost_row = cost_risk_df[cost_risk_df["Equipment.Id"] == mid]
                if len(cost_row) > 0:
                    signals["cost_at_risk"] = float(cost_row.iloc[0]["cost_at_risk"])
            signal_list.append(signals)

        # Run batch evaluation
        print(f"\nEvaluating {len(signal_list)} machines...")
        batch_df = engine.evaluate_batch(signal_list)

        # Save results
        os.makedirs("outputs", exist_ok=True)
        batch_df.to_csv("outputs/maintenance_decision_report.csv", index=False, float_format="%.4f")

        # Print summary — pass DataFrame to avoid re-evaluation
        print(engine.generate_batch_report(batch_df))

        # Save work orders
        orders = engine.generate_work_orders()
        if orders:
            order_rows = [{
                "priority": o.priority,
                "machine_id": o.machine_id,
                "alert_level": o.alert_level.name,
                "action_type": o.action_type.value,
                "cost_at_risk": o.cost_at_risk,
                "urgency_score": o.urgency_score,
                "window_days": o.recommended_window_days,
                "expected_savings": o.expected_savings,
                "suggestion": o.maintenance_suggestion,
            } for o in orders]
            pd.DataFrame(order_rows).to_csv(
                "outputs/maintenance_work_orders.csv", index=False, float_format="%.2f"
            )
            print(f"\nWork orders saved to outputs/maintenance_work_orders.csv")

        return engine, batch_df

    return engine, None


# ============================================================================
# Industrial Maintenance Extension (v4 — added 2026-05-27)
# ============================================================================
# The classes below extend the existing 4-layer engine with 5 new industrial
# layers WITHOUT modifying any existing code paths.
#
# Layer 5 — StrategySelector:      multi-strategy threshold adaptation
# Layer 6 — TechnicianAssigner:    technician type/count/duration assignment
# Layer 7 — SparePartsPlanner:     fault→parts recommendation
# Layer 8 — DowntimeOptimizer:     risk-aware downtime window scheduling
# Layer 9 — AcceptanceValidator:   post-repair verification criteria
# ============================================================================


@dataclass
class IndustrialWorkOrder:
    """
    Industrial-grade maintenance work order — 22 fields for direct execution.

    Extends the original WorkOrder (9 fields) with technician assignment,
    spare parts, downtime scheduling, acceptance criteria, and SLA targets.
    All fields are derivable from existing pipeline outputs + new engines.
    """
    machine_id: str
    anomaly_score: float = 0.0
    health_score: float = 50.0
    maintenance_priority: str = "P3"          # P1 / P2 / P3
    maintenance_strategy: str = "production_efficiency"
    predicted_risk: str = "NORMAL"            # ALARM / WARNING / WATCH / NORMAL
    primary_pattern: str = "normal"
    recommended_action: str = "no_action"
    spare_parts: str = "[]"                   # JSON array string
    technician_type: str = "junior_technician"
    technician_count: int = 1
    estimated_duration_hours: float = 1.0
    recommended_downtime_window: str = "scheduled"
    downtime_start: str = ""
    production_impact: float = 0.0
    estimated_cost: float = 0.0
    acceptance_standard: str = ""
    sla_target_hours: float = 72.0
    trigger_threshold: str = ""
    execution_status: str = "pending"
    reasoning: str = ""
    maintenance_suggestion: str = ""

    priority: int = 99
    alert_level: str = "NORMAL"
    action_type: str = "no_action"
    cost_at_risk: float = 0.0
    urgency_score: float = 0.0
    recommended_window_days: int = 30
    expected_savings: float = 0.0
    # SHAP explainability fields (populated by shap_postprocess after decision)
    top_risk_factor_1: str = ""
    top_risk_factor_2: str = ""
    top_risk_factor_3: str = ""
    shap_explanation: str = ""
    shap_risk_summary: str = ""


class IndustrialMaintenanceEngine(MaintenanceDecisionEngine):
    """
    Industrial-grade maintenance engine extending the base 4-layer engine.

    Adds 5 new layers (Strategy, Technician, SpareParts, Downtime, Acceptance)
    via composable engine modules. All existing evaluate(), generate_work_orders(),
    and fuse_signals() paths remain unchanged.

    Usage:
        engine = IndustrialMaintenanceEngine(
            cost_risk_data=cost_df,
            strategy="production_efficiency",
            health_score_df=health_df,
        )
        plan_df = engine.generate_industrial_plan(signal_list)
    """

    def __init__(self, cost_risk_data: pd.DataFrame = None,
                 config: dict = None,
                 strategy: str = "production_efficiency",
                 health_score_df: pd.DataFrame = None):
        """
        Args:
            cost_risk_data: DataFrame from cost_risk_matrix.csv
            config: Override for base engine configuration
            strategy: "cost_efficiency" | "production_efficiency" | "quality_first"
            health_score_df: DataFrame from equipment_health_score.csv
        """
        super().__init__(cost_risk_data, config)

        # Lazy-import new engine modules (same directory)
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)

        from strategy_selector import (
            MaintenanceStrategy, StrategySelector, STRATEGY_CONFIGS,
        )
        from technician_assigner import TechnicianAssigner
        from spare_parts_planner import SparePartsPlanner
        from downtime_optimizer import DowntimeOptimizer
        from acceptance_validator import AcceptanceValidator
        from maintenance_scheduler import MaintenanceScheduler

        self._ms = MaintenanceStrategy
        self._strat_enum = self._ms(strategy)
        self.strategy_selector = StrategySelector(self._strat_enum)

        # OR optimization: override budget/orders from config if provided
        max_budget_override = (
            config.get("work_order", {}).get("max_budget", 0) if config else 0
        )
        max_orders_override = (
            config.get("work_order", {}).get("max_orders_per_cycle", 0) if config else 0
        )
        if max_budget_override > 0:
            self.strategy_selector._or_max_budget = max_budget_override
        if max_orders_override > 0 and max_orders_override != self.strategy_selector.config.max_orders:
            self.strategy_selector._or_max_orders = max_orders_override
        max_hours_override = (
            config.get("work_order", {}).get("max_hours", 0) if config else 0
        )
        if max_hours_override > 0:
            self.strategy_selector._or_max_hours = max_hours_override
        self.tech_assigner = TechnicianAssigner()
        self.parts_planner = SparePartsPlanner()
        self.downtime_optimizer = DowntimeOptimizer(self.strategy_selector.config)
        self.acceptance_validator = AcceptanceValidator()
        # Enable batch merging for cost_efficiency strategy (merge_downtime=True)
        _use_merge = self._strat_enum.value == 'cost_efficiency'
        self.scheduler = MaintenanceScheduler(horizon_days=14, merge_batch=_use_merge)

        # Load health scores
        self.health_scores: Dict[str, float] = {}
        if health_score_df is not None:
            id_col = ("Equipment.Id" if "Equipment.Id" in health_score_df.columns
                      else "machine_id")
            hs_col = ("health_score" if "health_score" in health_score_df.columns
                      else "Health_Score")
            for _, row in health_score_df.iterrows():
                mid = str(row[id_col])
                self.health_scores[mid] = float(row.get(hs_col, 50.0))

    # ── Public API ──────────────────────────────────────────────────────

    def generate_industrial_plan(self, signal_list: List[dict],
                                  reference_date=None) -> pd.DataFrame:
        """
        Generate the full 22-column industrial maintenance plan.

        Execution flow:
          1. Base engine Layer 1-2: fuse_signals() + diagnose() per machine
          2. StrategySelector: filter/re-rank by strategy thresholds
          3. For each prioritized machine:
             a. TechnicianAssigner: assign tech + estimate duration
             b. SparePartsPlanner: recommend parts
             c. DowntimeOptimizer: select downtime window
             d. AcceptanceValidator: get acceptance criteria
          4. Assemble IndustrialWorkOrder rows → DataFrame

        Args:
            signal_list: List of signal dicts (same format as engine.evaluate())
            reference_date: Reference timestamp for downtime scheduling

        Returns:
            DataFrame with 22 columns per industrial_maintenance_plan.csv schema
        """
        sc = self.strategy_selector

        # Step 1+2: Evaluate through base engine, filter by strategy
        filtered = sc.apply_strategy_thresholds(signal_list, self)

        # Step 3: Build industrial rows
        rows: List[dict] = []
        ref_date = reference_date or pd.Timestamp.now()

        # Sort by risk_score descending
        filtered_sorted = sorted(filtered, key=lambda e: e["risk_score"], reverse=True)

        for rank, entry in enumerate(filtered_sorted, 1):
            row = self._build_industrial_row(entry, ref_date, rank)
            rows.append(row)

        # Assemble DataFrame
        df = pd.DataFrame(rows)
        if "anomaly_score" in df.columns and len(df) > 0:
            df = df.sort_values("anomaly_score", ascending=False).reset_index(drop=True)

        # Post-process: apply MaintenanceScheduler for globally optimized schedule
        df = self._patch_with_schedule(df, ref_date)

        return df

    def _patch_with_schedule(self, plan_df: pd.DataFrame,
                             ref_date) -> pd.DataFrame:
        """
        Post-process plan_df: run MaintenanceScheduler and backfill scheduled_day,
        downtime_start, and recommended_downtime_window with optimized values.

        The original DowntimeOptimizer rule-based windows are preserved as fallback
        for any machines the scheduler cannot place (indicated by scheduled_day=-1).
        """
        if plan_df.empty:
            return plan_df

        schedule_df = self.scheduler.schedule(plan_df, ref_date)

        for _, sched_row in schedule_df.iterrows():
            mid = str(sched_row["machine_id"])
            mask = plan_df["machine_id"] == mid
            if mask.any():
                idx = plan_df[mask].index[0]
                day = int(sched_row["scheduled_day"])
                new_start = (ref_date + pd.Timedelta(days=day)).strftime("%Y-%m-%d %H:%M:%S")
                plan_df.at[idx, "scheduled_day"] = day
                plan_df.at[idx, "downtime_start"] = new_start
                # Map day offset to descriptive window (overrides rule-based)
                if day == 0:
                    plan_df.at[idx, "recommended_downtime_window"] = "immediate"
                elif day <= 2:
                    plan_df.at[idx, "recommended_downtime_window"] = "night"
                elif day <= 5:
                    plan_df.at[idx, "recommended_downtime_window"] = "weekend"
                else:
                    plan_df.at[idx, "recommended_downtime_window"] = "scheduled"

        # Explicit fallback: any row still at scheduled_day=-1 keeps DowntimeOptimizer values.
        # The original window/downtime_start are preserved from _build_industrial_row().
        unplaced = (plan_df["scheduled_day"] == -1).sum()
        if unplaced > 0:
            print(f"  [Scheduler] {unplaced} orders unplaced — keeping DowntimeOptimizer fallback")

        return plan_df

    def _build_industrial_row(self, entry: dict, reference_date,
                               rank: int) -> dict:
        """Build a single row of the industrial maintenance plan."""
        s = entry["signals"]
        risk = entry["risk_score"]
        diag = entry["diagnosis"]
        level = entry["alert_level"]

        mid = str(s.get("machine_id", "unknown"))
        sc = self.strategy_selector
        cfg = sc.config

        # ── Priority ──
        if level.value >= 3:                     # ALARM
            mp = "P1"
        elif level.value >= 2:                   # WARNING
            mp = "P2"
        else:
            mp = "P3"

        # ── Action mapping ──
        action = self._map_action_for_industrial(risk, diag, s, level)

        # ── Technician (cost-aware: low-value machines get downgraded) ──
        risk_tier = self.cost_data.get(mid, {}).get("risk_tier", "Medium")
        cost_val = float(s.get("cost_at_risk", self.cost_p50))
        tech = self.tech_assigner.assign(
            diag.primary_pattern, level.name, action, risk_tier,
            cost_at_risk=cost_val, cost_p50=self.cost_p50,
        )

        # ── Duration ──
        severity = min(2.0, 1.0 + max(
            abs(s.get("z_v", 0)), abs(s.get("z_a", 0)), abs(s.get("z_t", 0))
        ) / 5.0)
        hours = self.tech_assigner.estimate_duration(
            action, tech.get("count", 1), severity,
        )

        # ── Spare Parts ──
        parts = self.parts_planner.recommend(
            diag.primary_pattern,
            z_v=s.get("z_v", 0),
            z_a=s.get("z_a", 0),
            z_t=s.get("z_t", 0),
        )
        parts_cost = self.parts_planner.estimate_parts_cost(parts)
        parts_names = [p.get("name", "unknown") for p in parts]

        # ── Production Impact ──
        ci = self.cost_data.get(mid, {})
        daily_output = ci.get("daily_output", 1000)
        unit_cost = ci.get("unit_cost", 5)
        prod_impact = self.downtime_optimizer.get_production_impact(
            daily_output, unit_cost, hours,
        )

        # ── Downtime Window ──
        urgency = self._calc_industrial_urgency(risk, s, level)
        cost_at_risk_val = float(s.get("cost_at_risk", 5000))

        window, reasons = self.downtime_optimizer.optimize(
            urgency_score=urgency,
            cost_at_risk=cost_at_risk_val,
            production_impact=prod_impact,
            estimated_duration_hours=hours,
            risk_tier=risk_tier,
            primary_pattern=diag.primary_pattern,
        )
        dts = self.downtime_optimizer.calculate_downtime_start(window, reference_date)

        # ── Acceptance ──
        criteria = self.acceptance_validator.get_acceptance_criteria(
            diag.primary_pattern,
        )
        acc_text = self.acceptance_validator.format_acceptance_standard(criteria)

        # ── Costs ──
        labor_cost = self.tech_assigner.estimate_labor_cost(
            tech.get("type", "junior_technician"), hours,
        )
        preventive_cost = cost_at_risk_val * self.config["work_order"]["preventive_cost_ratio"]
        total_cost = preventive_cost + parts_cost + labor_cost

        # ── SLA ──
        sla = cfg.get_sla(mp)

        # ── Health Score ──
        hs = self.health_scores.get(mid, 50.0)

        # ── Trend score (degradation rate) for scheduler deadline projection ──
        trend_slopes = [
            abs(float(s.get("voltage_trend_slope", 0))),
            abs(float(s.get("temp_trend_slope", 0))),
            abs(float(s.get("amperage_trend_slope", 0))),
        ]
        trend_score = max(trend_slopes) if max(trend_slopes) > 0 else 0.01

        # ── Assemble ──
        return {
            "machine_id": mid,
            "anomaly_score": round(risk, 4),
            "health_score": hs,
            "trend_score": round(trend_score, 6),
            "maintenance_priority": mp,
            "maintenance_strategy": cfg.strategy.value,
            "predicted_risk": level.name,
            "primary_pattern": diag.primary_pattern,
            "recommended_action": action,
            "spare_parts": json.dumps(parts_names, ensure_ascii=False),
            "technician_type": tech.get("type", "junior_technician"),
            "technician_count": tech.get("count", 1),
            "tech_cost_tier": tech.get("cost_tier", "standard"),
            "tech_labor_savings": tech.get("labor_savings_per_hour", 0.0),
            "estimated_duration_hours": round(hours, 1),
            "recommended_downtime_window": window.value,
            "downtime_start": str(dts),
            "scheduled_day": -1,
            "production_impact": round(prod_impact, 2),
            "estimated_cost": round(total_cost, 2),
            "acceptance_standard": acc_text,
            "sla_target_hours": float(sla),
            "trigger_threshold": sc.get_threshold_description(),
            "execution_status": "pending",
            "reasoning": "; ".join(reasons),
            "maintenance_suggestion": self._industrial_suggestion(
                mid, level, diag, action, hours, window, parts_names, total_cost
            ),
            # Backward-compatible fields
            "priority": rank,
            "alert_level": level.name,
            "action_type": action,
            "cost_at_risk": cost_at_risk_val,
            "urgency_score": urgency,
            "recommended_window_days": max(1, int(hours / 8) + 1),
            "expected_savings": round(cost_at_risk_val * 0.7, 2),
        }

    # ── Helpers ─────────────────────────────────────────────────────────

    def _map_action_for_industrial(self, risk_score: float,
                                    diagnosis, signals: dict,
                                    alert_level) -> str:
        """Map risk + diagnosis to an action type string."""
        z_max = float(signals.get("z_comp_max", 0))
        if z_max >= 10.0:
            return "immediate_shutdown"
        if alert_level.value >= 3:  # ALARM
            if z_max >= 8.0:
                return "preventive_repair"
            return "schedule_inspection"
        if alert_level.value >= 2:  # WARNING
            if diagnosis.primary_pattern in ("thermal_buildup", "voltage_drift",
                                              "power_anomaly", "combined_degradation"):
                return "schedule_inspection"
            return "increase_monitoring"
        if alert_level.value >= 1:  # WATCH
            return "increase_monitoring" if diagnosis.primary_pattern != "normal" else "routine_check"
        return "no_action"

    def _calc_industrial_urgency(self, risk_score: float, signals: dict,
                                  alert_level) -> float:
        """Calculate urgency score (0-100) for the industrial plan."""
        base = {3: 85, 2: 55, 1: 30, 0: 5}.get(alert_level.value, 5)
        cost = float(signals.get("cost_at_risk", self.cost_p50))
        if cost >= self.config["decision"]["critical_cost_threshold"]:
            base *= 1.4
        elif cost >= self.config["decision"]["high_cost_threshold"]:
            base *= 1.2
        elif cost < self.cost_p50:
            base *= 0.8
        return round(min(100.0, base), 1)

    def _industrial_suggestion(self, machine_id: str, alert_level,
                                diagnosis, action: str, hours: float,
                                window, parts_names: List[str],
                                total_cost: float) -> str:
        """Generate industrial-grade maintenance suggestion text (Chinese)."""
        ci = self.cost_data.get(machine_id, {})
        risk_tier = ci.get("risk_tier", "Medium")
        risk_tier_cn = {"High": "高", "Medium": "中", "Low": "低"}.get(risk_tier, risk_tier)
        daily_value = ci.get("unit_cost", 5) * ci.get("daily_output", 1000)
        parts_str = ", ".join(parts_names[:3]) if parts_names else "无"

        action_cn = {
            "immediate_shutdown": "立即停机", "preventive_repair": "预防维修",
            "schedule_inspection": "安排检查", "increase_monitoring": "加密监控",
            "routine_check": "常规检查", "no_action": "无需操作",
        }.get(action, action.replace("_", " "))

        window_cn = {
            "immediate_shutdown": "立即停机", "night": "夜间", "weekend": "周末",
            "next_gap": "下次间隙", "scheduled": "计划内",
        }.get(window.value if hasattr(window, 'value') else str(window), str(window))

        pattern_cn = {
            "thermal_buildup": "热累积", "combined_degradation": "综合退化",
            "voltage_drift": "电压漂移", "power_anomaly": "功率异常",
            "normal": "正常",
        }.get(diagnosis.primary_pattern, diagnosis.primary_pattern)

        return (
            f"[{risk_tier_cn}风险等级 | {window_cn}窗口] "
            f"{action_cn}：预计{hours}h，"
            f"备件=[{parts_str}]，估算成本=${total_cost:,.0f}，"
            f"日产值风险=${daily_value:,.0f}。"
            f"故障模式：{pattern_cn}。"
            f"验收标准：参照{pattern_cn}类验收规则执行。"
        )


if __name__ == "__main__":
    run_demo()
