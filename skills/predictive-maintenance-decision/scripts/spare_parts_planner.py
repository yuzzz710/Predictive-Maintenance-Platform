#!/usr/bin/env python3
"""
Spare Parts Planner — Automated Parts Recommendation Engine
=============================================================
Recommends spare parts based on fault pattern and sensor anomaly severity.
All parts data is parameterized via spare_parts_catalog.json.

Design: no hardcoded parts — everything driven by the JSON catalog.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional


class SparePartsPlanner:
    """
    Rule-based spare parts recommendation engine.

    Usage:
        planner = SparePartsPlanner()
        parts = planner.recommend("thermal_buildup", z_v=0.5, z_a=1.2, z_t=3.5)
        cost = planner.estimate_parts_cost(parts)
    """

    def __init__(self, catalog_path: Optional[str] = None):
        """
        Args:
            catalog_path: Path to spare_parts_catalog.json. If None, uses
                          default relative path from this file's location.
        """
        if catalog_path is None:
            catalog_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data", "spare_parts_catalog.json",
            )
        self.catalog = self._load_catalog(catalog_path)

    def _load_catalog(self, path: str) -> dict:
        """Load parts catalog from JSON with graceful fallback."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Graceful fallback: minimal built-in catalog
        return {
            "catalog": [
                {
                    "fault_type": "thermal_buildup",
                    "parts": [
                        {"name": "cooling_fan_assembly", "part_number": "CF-200-01",
                         "unit_cost": 180.0, "lead_time_days": 2,
                         "replacement_priority": 1, "quantity_per_machine": 1},
                        {"name": "thermal_paste", "part_number": "TP-50G",
                         "unit_cost": 25.0, "lead_time_days": 1,
                         "replacement_priority": 2, "quantity_per_machine": 1},
                        {"name": "temperature_sensor_pt100", "part_number": "TS-PT100",
                         "unit_cost": 95.0, "lead_time_days": 3,
                         "replacement_priority": 3, "quantity_per_machine": 1},
                    ],
                },
                {
                    "fault_type": "voltage_drift",
                    "parts": [
                        {"name": "power_supply_module", "part_number": "PSM-24V-500W",
                         "unit_cost": 450.0, "lead_time_days": 3,
                         "replacement_priority": 1, "quantity_per_machine": 1},
                        {"name": "voltage_regulator_ic", "part_number": "VR-LM317",
                         "unit_cost": 12.0, "lead_time_days": 1,
                         "replacement_priority": 2, "quantity_per_machine": 2},
                        {"name": "capacitor_bank", "part_number": "CAP-4700UF-63V",
                         "unit_cost": 65.0, "lead_time_days": 2,
                         "replacement_priority": 3, "quantity_per_machine": 1},
                    ],
                },
                {
                    "fault_type": "power_anomaly",
                    "parts": [
                        {"name": "motor_driver_module", "part_number": "MD-750W-V3",
                         "unit_cost": 680.0, "lead_time_days": 5,
                         "replacement_priority": 1, "quantity_per_machine": 1},
                        {"name": "current_sensor_hall", "part_number": "CS-H50A",
                         "unit_cost": 75.0, "lead_time_days": 2,
                         "replacement_priority": 2, "quantity_per_machine": 1},
                        {"name": "power_cable_set", "part_number": "PC-3P-4MM",
                         "unit_cost": 40.0, "lead_time_days": 1,
                         "replacement_priority": 3, "quantity_per_machine": 1},
                    ],
                },
                {
                    "fault_type": "combined_degradation",
                    "parts": [
                        {"name": "rotor_assembly", "part_number": "RA-CNC-100",
                         "unit_cost": 1200.0, "lead_time_days": 7,
                         "replacement_priority": 1, "quantity_per_machine": 1},
                        {"name": "bearing_kit", "part_number": "BK-6205-2RS",
                         "unit_cost": 85.0, "lead_time_days": 2,
                         "replacement_priority": 2, "quantity_per_machine": 2},
                        {"name": "seal_kit", "part_number": "SK-CNC-STD",
                         "unit_cost": 45.0, "lead_time_days": 1,
                         "replacement_priority": 3, "quantity_per_machine": 1},
                        {"name": "lubrication_kit", "part_number": "LK-SYNTH-1L",
                         "unit_cost": 30.0, "lead_time_days": 1,
                         "replacement_priority": 4, "quantity_per_machine": 1},
                    ],
                },
            ],
            "common_parts": [
                {"name": "o-ring_set", "part_number": "OR-CNC-STD",
                 "unit_cost": 8.0, "lead_time_days": 1, "quantity_per_machine": 1},
                {"name": "fastener_kit", "part_number": "FK-M6-M10",
                 "unit_cost": 15.0, "lead_time_days": 1, "quantity_per_machine": 1},
                {"name": "cleaning_kit", "part_number": "CK-IND",
                 "unit_cost": 22.0, "lead_time_days": 1, "quantity_per_machine": 1},
            ],
        }

    def _find_catalog_entry(self, primary_pattern: str) -> Optional[dict]:
        """Find the catalog entry matching the fault pattern."""
        for entry in self.catalog.get("catalog", []):
            if entry.get("fault_type") == primary_pattern:
                return entry
        return None

    def _assess_inventory_risk(self, lead_time_days: int,
                                unit_cost: float) -> str:
        """Assess inventory risk based on lead time × cost."""
        risk_score = lead_time_days * unit_cost / 100.0
        if risk_score > 50:
            return "high"
        elif risk_score > 15:
            return "medium"
        return "low"

    def recommend(self, primary_pattern: str, z_v: float = 0.0,
                  z_a: float = 0.0, z_t: float = 0.0,
                  max_parts: int = 4) -> List[dict]:
        """
        Recommend spare parts based on anomaly pattern and severity.

        Args:
            primary_pattern: e.g. "voltage_drift", "thermal_buildup"
            z_v: Voltage z-score (informs severity)
            z_a: Amperage z-score
            z_t: Temperature z-score
            max_parts: Maximum number of parts to recommend

        Returns:
            List of part dicts with keys: name, part_number, unit_cost,
            lead_time_days, replacement_priority, quantity_per_machine,
            inventory_risk
        """
        entry = self._find_catalog_entry(primary_pattern)
        parts: List[dict] = []

        if entry is not None:
            parts = list(entry.get("parts", []))

        # Adjust max_parts based on severity
        severity = max(abs(z_v), abs(z_a), abs(z_t))
        if severity > 4.0:
            max_parts = min(len(parts), max_parts + 2)
        elif severity < 1.5:
            max_parts = max(2, max_parts - 1)

        # Sort by replacement_priority
        parts.sort(key=lambda p: p.get("replacement_priority", 99))

        # Take top-N fault-specific parts
        result = []
        for p in parts[:max_parts]:
            p = dict(p)  # shallow copy
            p["inventory_risk"] = self._assess_inventory_risk(
                p.get("lead_time_days", 1),
                p.get("unit_cost", 10),
            )
            result.append(p)

        # Always append 1 common part
        common = self.catalog.get("common_parts", [])
        if common:
            c = dict(common[0])
            c["inventory_risk"] = "low"
            c["replacement_priority"] = 99
            result.append(c)

        return result

    def estimate_parts_cost(self, parts_list: List[dict]) -> float:
        """
        Calculate total parts cost from a recommended parts list.

        Args:
            parts_list: Output of recommend()

        Returns:
            Total cost in USD
        """
        total = 0.0
        for p in parts_list:
            qty = p.get("quantity_per_machine", 1)
            cost = p.get("unit_cost", 0)
            total += cost * qty
        return round(total, 2)
