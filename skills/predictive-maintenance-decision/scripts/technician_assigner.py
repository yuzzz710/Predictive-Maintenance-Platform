#!/usr/bin/env python3
"""
Technician Assigner — Maintenance Resource Scheduling Engine
=============================================================
Automatically assigns technician type, count, estimates labor hours
and labor cost based on fault pattern, risk level, and machine criticality.

All rules are parameterized via technician_rules.json — no hardcoded assignments.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Dict, List, Optional, Tuple


class TechnicianType(Enum):
    JUNIOR = "junior_technician"
    SENIOR = "senior_technician"
    ELECTRICAL = "electrical_specialist"
    THERMAL = "thermal_specialist"
    MECHANICAL = "mechanical_specialist"


# ── Hourly rates (USD) ──
HOURLY_RATES: Dict[str, float] = {
    "junior_technician": 35.0,
    "senior_technician": 65.0,
    "electrical_specialist": 85.0,
    "thermal_specialist": 80.0,
    "mechanical_specialist": 75.0,
}

# ── Duration lookup table (hours, min/typical/max per action_type) ──
DURATION_TABLE: Dict[str, Dict[str, float]] = {
    "immediate_shutdown":  {"min": 4.0, "typical": 8.0,  "max": 24.0},
    "preventive_repair":   {"min": 2.0, "typical": 4.0,  "max": 8.0},
    "schedule_inspection": {"min": 1.0, "typical": 2.0,  "max": 4.0},
    "increase_monitoring": {"min": 0.5, "typical": 1.0,  "max": 2.0},
    "routine_check":       {"min": 0.5, "typical": 1.0,  "max": 1.5},
    "no_action":           {"min": 0.0, "typical": 0.0,  "max": 0.0},
}


class TechnicianAssigner:
    """
    Rule-based technician assignment engine.

    Usage:
        assigner = TechnicianAssigner()
        tech = assigner.assign("voltage_drift", "ALARM", "preventive_repair", "High")
        hours = assigner.estimate_duration("preventive_repair", tech["count"])
        cost = assigner.estimate_labor_cost(tech["type"], hours)
    """

    def __init__(self, rules_path: Optional[str] = None):
        """
        Args:
            rules_path: Path to technician_rules.json. If None, uses default
                        relative path from this file's location.
        """
        if rules_path is None:
            rules_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data", "technician_rules.json",
            )
        self.rules = self._load_rules(rules_path)

    def _load_rules(self, path: str) -> dict:
        """Load technician assignment rules from JSON, with graceful fallback."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        # Graceful fallback: built-in default rules
        return {
            "rules": [
                {"condition": {"action_type": "immediate_shutdown"},
                 "assign": {"type": "senior_technician", "count": 3, "priority": 0}},
                {"condition": {"primary_pattern": "voltage_drift", "risk_level": "ALARM"},
                 "assign": {"type": "electrical_specialist", "count": 2, "priority": 1}},
                {"condition": {"primary_pattern": "thermal_buildup", "risk_level": "ALARM"},
                 "assign": {"type": "thermal_specialist", "count": 2, "priority": 1}},
                {"condition": {"primary_pattern": "combined_degradation", "risk_level": "ALARM"},
                 "assign": {"type": "senior_technician", "count": 2, "priority": 1}},
                {"condition": {"primary_pattern": "voltage_drift"},
                 "assign": {"type": "electrical_specialist", "count": 1, "priority": 2}},
                {"condition": {"primary_pattern": "thermal_buildup"},
                 "assign": {"type": "thermal_specialist", "count": 1, "priority": 2}},
                {"condition": {"primary_pattern": "power_anomaly"},
                 "assign": {"type": "electrical_specialist", "count": 1, "priority": 2}},
                {"condition": {"primary_pattern": "combined_degradation"},
                 "assign": {"type": "senior_technician", "count": 1, "priority": 2}},
                {"condition": {"risk_tier": "High"},
                 "assign": {"type": "senior_technician", "count": 1, "priority": 2}},
                {"condition": {"action_type": "preventive_repair"},
                 "assign": {"type": "senior_technician", "count": 1, "priority": 3}},
                {"condition": {"action_type": "schedule_inspection"},
                 "assign": {"type": "junior_technician", "count": 1, "priority": 4}},
            ],
            "default": {"type": "junior_technician", "count": 1},
        }

    def _match_condition(self, condition: dict, primary_pattern: str,
                         risk_level: str, action_type: str,
                         risk_tier: str) -> bool:
        """Check if a rule condition matches the current machine state."""
        if "primary_pattern" in condition:
            if condition["primary_pattern"] != primary_pattern:
                return False
        if "risk_level" in condition:
            if condition["risk_level"] != risk_level:
                return False
        if "action_type" in condition:
            if condition["action_type"] != action_type:
                return False
        if "risk_tier" in condition:
            if condition["risk_tier"] != risk_tier:
                return False
        return True

    # ── Cost-tiered technician downgrade mapping ──
    # For low-value machines, downgrade specialists to save labor cost.
    # Key = original specialist type, Value = downgraded type + hourly savings.
    _DOWNGRADE_MAP: Dict[str, tuple] = {
        "electrical_specialist": ("senior_technician", 20.0),  # $85→$65, save $20/h
        "thermal_specialist":    ("senior_technician", 15.0),  # $80→$65, save $15/h
        "mechanical_specialist": ("junior_technician", 40.0),  # $75→$35, save $40/h
        "senior_technician":     ("junior_technician", 30.0),  # $65→$35, save $30/h
    }

    def assign(self, primary_pattern: str, risk_level: str,
               action_type: str, risk_tier: str = "Medium",
               cost_at_risk: float = 5000.0,
               cost_p50: float = 4500.0) -> dict:
        """
        Assign technician type and count based on fault + risk + criticality + cost.

        Cost-aware logic:
          - cost_at_risk < cost_p50 → downgrade specialist by one tier
          - cost_at_risk >= cost_p75 → keep/upgrade to specialist
          - cost_at_risk between p50-p75 → standard assignment (unchanged)

        Args:
            primary_pattern: e.g. "voltage_drift", "thermal_buildup"
            risk_level: "ALARM", "WARNING", "WATCH", "NORMAL"
            action_type: e.g. "preventive_repair", "schedule_inspection"
            risk_tier: "High", "Medium", "Low"
            cost_at_risk: USD cost-at-risk for this machine
            cost_p50: Median cost_at_risk across all machines

        Returns:
            dict with keys: type, count, priority, cost_tier
        """
        rules = self.rules.get("rules", [])
        sorted_rules = sorted(rules, key=lambda r: r.get("assign", {}).get("priority", 99))

        result = None
        for rule in sorted_rules:
            cond = rule.get("condition", {})
            if self._match_condition(cond, primary_pattern, risk_level,
                                      action_type, risk_tier):
                result = dict(rule["assign"])
                result.setdefault("priority", 99)
                break

        if result is None:
            default = self.rules.get("default", {"type": "junior_technician", "count": 1})
            result = dict(default)

        # ── Cost-tiered adjustment ──
        tech_type = result["type"]
        if cost_at_risk < cost_p50 and tech_type in self._DOWNGRADE_MAP:
            downgraded, savings = self._DOWNGRADE_MAP[tech_type]
            result["type"] = downgraded
            result["cost_tier"] = "downgraded"
            result["labor_savings_per_hour"] = savings
        elif cost_at_risk >= cost_p50:
            result["cost_tier"] = "standard"
            result["labor_savings_per_hour"] = 0.0
        else:
            result["cost_tier"] = "standard"
            result["labor_savings_per_hour"] = 0.0

        return result

    def estimate_duration(self, action_type: str, technician_count: int = 1,
                          severity_factor: float = 1.0) -> float:
        """
        Estimate maintenance duration in hours.

        Uses the DURATION_TABLE with linear interpolation based on severity_factor
        between 'typical' and 'max'. Technician efficiency has diminishing returns.

        Args:
            action_type: One of the 6 action types
            technician_count: Number of technicians assigned
            severity_factor: 1.0 = normal, up to 2.0 = very severe

        Returns:
            Estimated hours (float)
        """
        d = DURATION_TABLE.get(action_type, {"min": 1.0, "typical": 2.0, "max": 4.0})

        base = d["typical"]
        max_val = d["max"]

        # Interpolate: severity_factor 1.0 → typical, 2.0 → max
        if severity_factor > 1.0:
            t = min(1.0, (severity_factor - 1.0))
            base = base + t * (max_val - base)

        # Technician efficiency (diminishing returns)
        efficiency = 1.0 / (1.0 + 0.3 * (technician_count - 1))

        return round(base * efficiency, 1)

    def estimate_labor_cost(self, technician_type: str, hours: float) -> float:
        """
        Estimate labor cost based on technician type and hours.

        Args:
            technician_type: e.g. "senior_technician"
            hours: Estimated duration in hours

        Returns:
            Labor cost in USD
        """
        rate = HOURLY_RATES.get(technician_type, 50.0)
        return round(rate * hours, 2)

    def get_required_skills(self, technician_type: str) -> List[str]:
        """Return required skill tags for a given technician type."""
        skill_map = {
            "junior_technician": ["basic_maintenance", "safety_training"],
            "senior_technician": ["advanced_diagnostics", "root_cause_analysis",
                                   "safety_training", "team_leadership"],
            "electrical_specialist": ["electrical_safety", "power_electronics",
                                       "motor_drive_repair", "circuit_analysis"],
            "thermal_specialist": ["thermal_analysis", "hvac_certification",
                                    "cooling_system_repair", "thermal_imaging"],
            "mechanical_specialist": ["mechanical_repair", "bearing_replacement",
                                       "rotor_balancing", "vibration_analysis"],
        }
        return skill_map.get(technician_type, ["general_maintenance"])
