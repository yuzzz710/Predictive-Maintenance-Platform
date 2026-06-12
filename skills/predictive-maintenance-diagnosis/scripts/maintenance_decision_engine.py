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
import os, json, warnings
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
            # Layer 1: Input fusion weights
            "fusion": {
                "ml_density_weight": 0.25,     # reduced from 0.40 — ML is weak
                "stat_anomaly_weight": 0.40,    # increased — Z-Score is our best signal
                "cost_risk_weight": 0.25,       # cost stays important
                "trend_weight": 0.10,           # new: trend signals
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

        if decision.action_type == ActionType.PREVENTIVE_REPAIR:
            return (
                f"[{risk_tier} Risk Tier] Preventive repair within {decision.recommended_window_days} day(s). "
                f"Daily production value at risk: ${daily_value:,.0f}. "
                f"Cost avoidance by acting now vs. emergency repair: ~${decision.estimated_cost_at_risk * 0.7:,.0f}. "
                f"Key concern: {decision.reasoning[0] if decision.reasoning else 'elevated parameters'}. "
                f"Recommend: deploy vibration analysis + thermal scan during intervention."
            )

        elif decision.action_type == ActionType.SCHEDULE_INSPECTION:
            focus = decision.reasoning[0] if decision.reasoning else 'parameter deviation'
            return (
                f"[{risk_tier} Risk Tier] Schedule inspection within {decision.recommended_window_days} day(s). "
                f"Focus: {focus}. "
                f"Daily value at stake: ${daily_value:,.0f}. "
                f"Recommended checks: electrical signature analysis, thermal imaging, physical inspection."
            )

        elif decision.action_type == ActionType.INCREASE_MONITORING:
            return (
                f"Increase monitoring to every {decision.recommended_window_days} day(s). "
                f"Track: {decision.reasoning[0] if decision.reasoning else 'all parameters'}. "
                f"Escalate to inspection if parameters continue to drift."
            )

        elif decision.action_type == ActionType.ROUTINE_CHECK:
            return (
                f"Continue routine maintenance (next check in {decision.recommended_window_days} days). "
                f"Cost at risk: ${decision.estimated_cost_at_risk:,.0f}. Baseline monitoring sufficient."
            )

        elif decision.action_type == ActionType.IMMEDIATE_SHUTDOWN:
            return (
                f"*** IMMEDIATE SHUTDOWN *** Parameter deviation is critical. "
                f"Daily production exposure: ${daily_value:,.0f}. "
                f"Initiate emergency protocol. Contact maintenance supervisor immediately. "
                f"Root cause suspects: {decision.reasoning[0] if decision.reasoning else 'severe parameter deviation'}."
            )

        else:
            return "No action required. Standard monitoring per maintenance schedule."

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


if __name__ == "__main__":
    run_demo()
