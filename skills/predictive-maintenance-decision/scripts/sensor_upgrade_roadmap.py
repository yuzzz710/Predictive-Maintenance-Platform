#!/usr/bin/env python3
"""
Sensor Upgrade Roadmap Engine — Probabilistic Industrial ROI Model v2.0
========================================================================
Converts the system's core finding ("4 sensors have limited predictability,
max Youden's J = 0.075") into an actionable, phased sensor upgrade plan
with risk-adjusted, three-scenario ROI estimation.

Key upgrade from v1.0:
  - Deterministic ROI → Probabilistic 3-scenario ROI (conservative/expected/optimistic)
  - Theoretical reduction → Effective reduction via deployment/adoption/maintenance factors
  - Single-point estimates → Indicative ROI ranges
  - All factors driven by external JSON config (data/sensor_roi_factors.json)

Design Principle:
  - All ROI figures are ENGINEERING ESTIMATION RANGES, not financial-grade precision.
  - "Reduction" → "Coverage" language to avoid over-promising.
  - The engine is read-only — it does not modify any existing pipeline data.

Usage:
    engine = SensorUpgradeRoadmapEngine(num_machines=100)
    plan_df = engine.generate_upgrade_plan()
    roi_df = engine.generate_roi_analysis()
    summary_df = engine.generate_phase_summary()
"""

import json
import os
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


# ============================================================================
# Data Structures
# ============================================================================

class UpgradePhase(Enum):
    PHASE_1 = "phase_1_vibration"
    PHASE_2 = "phase_2_current_spectrum"
    PHASE_3 = "phase_3_thermal_imaging"


class Scenario(Enum):
    CONSERVATIVE = "conservative"
    EXPECTED = "expected"
    OPTIMISTIC = "optimistic"


@dataclass
class SensorUpgrade:
    """A single sensor upgrade within a phase."""
    sensor_name: str
    phase: UpgradePhase
    target_problems: List[str]
    unit_cost: float
    installation_cost: float
    annual_maintenance_cost: float
    deployment_complexity: str
    deployment_months: int
    expected_accuracy_gain: float
    theoretical_failure_coverage_pct: float   # renamed: "reduction" → "coverage"
    theoretical_downtime_coverage_pct: float  # renamed: "reduction" → "coverage"
    priority: int


@dataclass
class ScenarioROI:
    """ROI for a single scenario (conservative/expected/optimistic)."""
    scenario: Scenario
    annual_saving: float
    payback_months: int
    roi_5yr_percent: float
    effective_multiplier: float


@dataclass
class ROIModel:
    """Probabilistic industrial ROI estimation model — three-scenario."""
    phase: UpgradePhase
    total_investment: float
    annual_opex: float
    # Three scenarios
    conservative: ScenarioROI
    expected: ScenarioROI
    optimistic: ScenarioROI
    # Legacy accessors (for convenience)
    annual_saving_low: float = 0.0
    annual_saving_high: float = 0.0
    annual_saving_expected: float = 0.0
    payback_months_low: int = 0
    payback_months_high: int = 0
    payback_months_expected: int = 0
    roi_5yr_percent: float = 0.0
    risk_reduction_pct: float = 0.0
    # Factors applied
    deployment_factor: float = 0.0
    adoption_factor: float = 0.0
    maintenance_quality_factor: float = 0.0
    key_assumptions: List[str] = field(default_factory=list)


# ============================================================================
# Sensor Upgrade Roadmap Engine
# ============================================================================

class SensorUpgradeRoadmapEngine:
    """
    Generates a phased sensor upgrade roadmap with probabilistic industrial ROI.

    The roadmap is built on the system's core finding: 4 monitoring parameters
    (Voltage, Amperage, Temperature, Rotor Speed) have max Youden's J = 0.075,
    making effective predictive maintenance impossible with current sensors.

    Three phases, in priority order:
      1. Vibration Monitoring — lowest cost, fastest ROI, targets mechanical faults
      2. Current Spectrum Analysis — medium cost, targets motor/electrical faults
      3. Thermal Imaging — highest cost, highest long-term value

    ROI Model (Probabilistic, v2.0):
      effective_coverage = theoretical_coverage
                         × deployment_factor
                         × adoption_factor
                         × maintenance_quality_factor
      → computed independently for 3 scenarios (conservative/expected/optimistic)
      → output as indicative ROI range, not single-point estimate

    All cost figures are order-of-magnitude industrial estimates.
    All factors are loaded from data/sensor_roi_factors.json.
    """

    def __init__(self, num_machines: int = 100,
                 avg_downtime_cost_per_hour: float = 5000,
                 avg_failure_cost_per_incident: float = 15000,
                 current_annual_failures: int = 85,
                 current_annual_downtime_hours: int = 420,
                 config_path: str = ""):
        """
        Args:
            num_machines: Number of CNC machines in the workshop
            avg_downtime_cost_per_hour: Average production loss per hour of downtime (USD)
            avg_failure_cost_per_incident: Average cost per failure incident (repair + scrap + labor)
            current_annual_failures: Current annual failure incidents across all machines
            current_annual_downtime_hours: Current annual unplanned downtime hours
            config_path: Path to sensor_roi_factors.json (auto-detected if empty)
        """
        self.num_machines = num_machines
        self.avg_downtime_cost_per_hour = avg_downtime_cost_per_hour
        self.avg_failure_cost_per_incident = avg_failure_cost_per_incident
        self.current_annual_failures = current_annual_failures
        self.current_annual_downtime_hours = current_annual_downtime_hours

        # Load ROI factors from JSON config
        self._config = self._load_config(config_path)

        # Define the three upgrade phases
        self._phases: Dict[UpgradePhase, List[SensorUpgrade]] = self._define_phases()

    def _load_config(self, config_path: str = "") -> dict:
        """Load ROI factors from JSON config file. Auto-detect path if not provided."""
        if config_path and os.path.exists(config_path):
            path = config_path
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(script_dir, "data", "sensor_roi_factors.json")

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Fallback: hardcoded defaults (matches JSON spec)
        print(f"[WARN] ROI factor config not found at {path}, using built-in defaults.")
        return {
            "reduction_factors": {
                "deployment_factor": {
                    "conservative": 0.70, "expected": 0.85, "optimistic": 0.95
                },
                "adoption_factor": {
                    "conservative": 0.60, "expected": 0.80, "optimistic": 0.90
                },
                "maintenance_quality_factor": {
                    "conservative": 0.70, "expected": 0.85, "optimistic": 0.95
                },
            },
            "disclaimer": "ROI values are engineering estimation ranges, not guaranteed financial outcomes."
        }

    def _get_factors(self, scenario: str) -> Tuple[float, float, float]:
        """Return (deployment, adoption, maintenance_quality) for a scenario."""
        rf = self._config["reduction_factors"]
        return (
            rf["deployment_factor"][scenario],
            rf["adoption_factor"][scenario],
            rf["maintenance_quality_factor"][scenario],
        )

    def _effective_multiplier(self, scenario: str) -> float:
        """Compute effective reduction multiplier for a scenario."""
        d, a, m = self._get_factors(scenario)
        return round(d * a * m, 4)

    def _effective_reduction(self, theoretical_pct: float, scenario: str) -> float:
        """Apply all three factors to a theoretical reduction percentage."""
        return round(theoretical_pct * self._effective_multiplier(scenario), 1)

    def _define_phases(self) -> Dict[UpgradePhase, List[SensorUpgrade]]:
        """Define the three-phase sensor upgrade plan with industrial cost estimates."""

        return {
            UpgradePhase.PHASE_1: [
                SensorUpgrade(
                    sensor_name="Vibration Sensor (IEPE Accelerometer)",
                    phase=UpgradePhase.PHASE_1,
                    target_problems=[
                        "Bearing wear/fatigue",
                        "Rotor imbalance",
                        "Shaft misalignment",
                        "Gear mesh degradation",
                        "Mechanical looseness",
                    ],
                    unit_cost=350,
                    installation_cost=120,
                    annual_maintenance_cost=45,
                    deployment_complexity="low",
                    deployment_months=3,
                    expected_accuracy_gain=0.35,
                    theoretical_failure_coverage_pct=45,
                    theoretical_downtime_coverage_pct=30,
                    priority=1,
                ),
                SensorUpgrade(
                    sensor_name="Vibration Data Collector + FFT Analyzer",
                    phase=UpgradePhase.PHASE_1,
                    target_problems=[
                        "Frequency-domain anomaly detection",
                        "Resonance identification",
                        "Harmonic analysis for rotating equipment",
                    ],
                    unit_cost=2800,
                    installation_cost=500,
                    annual_maintenance_cost=200,
                    deployment_complexity="low",
                    deployment_months=3,
                    expected_accuracy_gain=0.10,
                    theoretical_failure_coverage_pct=10,
                    theoretical_downtime_coverage_pct=5,
                    priority=1,
                ),
            ],
            UpgradePhase.PHASE_2: [
                SensorUpgrade(
                    sensor_name="Current Spectrum Sensor (Hall-effect + Rogowski Coil)",
                    phase=UpgradePhase.PHASE_2,
                    target_problems=[
                        "Motor winding degradation",
                        "Rotor bar defects (induction motors)",
                        "Electrical supply imbalance",
                        "Power quality anomalies",
                        "Overload detection",
                    ],
                    unit_cost=480,
                    installation_cost=180,
                    annual_maintenance_cost=60,
                    deployment_complexity="medium",
                    deployment_months=4,
                    expected_accuracy_gain=0.20,
                    theoretical_failure_coverage_pct=25,
                    theoretical_downtime_coverage_pct=15,
                    priority=2,
                ),
                SensorUpgrade(
                    sensor_name="Harmonic Analysis Module (Power Quality)",
                    phase=UpgradePhase.PHASE_2,
                    target_problems=[
                        "THD (Total Harmonic Distortion) monitoring",
                        "Transient surge detection",
                        "Power factor degradation",
                    ],
                    unit_cost=1200,
                    installation_cost=300,
                    annual_maintenance_cost=150,
                    deployment_complexity="medium",
                    deployment_months=4,
                    expected_accuracy_gain=0.08,
                    theoretical_failure_coverage_pct=10,
                    theoretical_downtime_coverage_pct=8,
                    priority=2,
                ),
            ],
            UpgradePhase.PHASE_3: [
                SensorUpgrade(
                    sensor_name="Infrared Thermal Imaging Camera (Fixed-mount)",
                    phase=UpgradePhase.PHASE_3,
                    target_problems=[
                        "Overheating prediction (pre-thermal-runaway)",
                        "Insulation degradation",
                        "Electrical connection hot spots",
                        "Cooling system efficiency loss",
                        "Critical failure early warning",
                    ],
                    unit_cost=2200,
                    installation_cost=350,
                    annual_maintenance_cost=180,
                    deployment_complexity="high",
                    deployment_months=6,
                    expected_accuracy_gain=0.25,
                    theoretical_failure_coverage_pct=30,
                    theoretical_downtime_coverage_pct=20,
                    priority=3,
                ),
                SensorUpgrade(
                    sensor_name="Thermal Trend Analysis Software",
                    phase=UpgradePhase.PHASE_3,
                    target_problems=[
                        "Multi-point thermal trend modeling",
                        "Predictive overheating alerts",
                        "Thermal signature pattern recognition",
                    ],
                    unit_cost=800,
                    installation_cost=100,
                    annual_maintenance_cost=300,
                    deployment_complexity="medium",
                    deployment_months=6,
                    expected_accuracy_gain=0.12,
                    theoretical_failure_coverage_pct=10,
                    theoretical_downtime_coverage_pct=5,
                    priority=3,
                ),
            ],
        }

    # ── Public API ──────────────────────────────────────────────────────

    def generate_upgrade_plan(self) -> pd.DataFrame:
        """Generate the phased sensor upgrade plan (sensor_upgrade_plan.csv)."""
        rows = []
        for phase in [UpgradePhase.PHASE_1, UpgradePhase.PHASE_2, UpgradePhase.PHASE_3]:
            for sensor in self._phases[phase]:
                # Coverage note: rephrase "reduction" → "coverage" language
                failure_note = (
                    f"覆盖约{sensor.theoretical_failure_coverage_pct}%的"
                    f"{'机械类' if phase == UpgradePhase.PHASE_1 else '电气类' if phase == UpgradePhase.PHASE_2 else '热控类'}"
                    f"故障模式（理论值，实际效果依赖部署质量、人员执行、运维水平）"
                )
                rows.append({
                    "phase": self._phase_label(phase),
                    "phase_order": sensor.priority,
                    "sensor_name": sensor.sensor_name,
                    "target_problems": "; ".join(sensor.target_problems),
                    "unit_cost_usd": sensor.unit_cost,
                    "installation_cost_usd": sensor.installation_cost,
                    "total_cost_per_machine": sensor.unit_cost + sensor.installation_cost,
                    "total_capex": (sensor.unit_cost + sensor.installation_cost) * self.num_machines,
                    "annual_opex": sensor.annual_maintenance_cost * self.num_machines,
                    "deployment_complexity": sensor.deployment_complexity,
                    "deployment_months": sensor.deployment_months,
                    "expected_accuracy_gain": sensor.expected_accuracy_gain,
                    "theoretical_failure_coverage_pct": sensor.theoretical_failure_coverage_pct,
                    "theoretical_downtime_coverage_pct": sensor.theoretical_downtime_coverage_pct,
                    "priority": sensor.priority,
                    "cumulative_youden_j": self._cumulative_youden_j(phase, sensor),
                    "coverage_note": failure_note,
                })
        df = pd.DataFrame(rows)
        return df.sort_values(["phase_order", "priority"]).reset_index(drop=True)

    def generate_roi_analysis(self) -> pd.DataFrame:
        """Generate three-scenario ROI analysis for each phase (sensor_roi_analysis.csv)."""
        rows = []
        for phase in [UpgradePhase.PHASE_1, UpgradePhase.PHASE_2, UpgradePhase.PHASE_3]:
            model = self.calculate_roi(phase)
            phase_sensors = self._phases[phase]

            total_failure_coverage = sum(
                s.theoretical_failure_coverage_pct for s in phase_sensors
            )
            total_downtime_coverage = sum(
                s.theoretical_downtime_coverage_pct for s in phase_sensors
            )

            rows.append({
                "phase": self._phase_label(phase),
                "phase_order": phase_sensors[0].priority,
                "num_sensors": len(phase_sensors),
                "total_investment": model.total_investment,
                "annual_opex": model.annual_opex,
                # Conservative scenario
                "conservative_annual_saving": model.conservative.annual_saving,
                "conservative_payback_months": model.conservative.payback_months,
                "conservative_roi_5yr_pct": model.conservative.roi_5yr_percent,
                # Expected scenario
                "expected_annual_saving": model.expected.annual_saving,
                "expected_payback_months": model.expected.payback_months,
                "expected_roi_5yr_pct": model.expected.roi_5yr_percent,
                # Optimistic scenario
                "optimistic_annual_saving": model.optimistic.annual_saving,
                "optimistic_payback_months": model.optimistic.payback_months,
                "optimistic_roi_5yr_pct": model.optimistic.roi_5yr_percent,
                # ROI range string
                "roi_range": f"{model.conservative.roi_5yr_percent:.0f}% – {model.optimistic.roi_5yr_percent:.0f}%",
                # Factors applied (expected scenario)
                "deployment_factor": model.deployment_factor,
                "adoption_factor": model.adoption_factor,
                "maintenance_quality_factor": model.maintenance_quality_factor,
                # Effective multipliers per scenario
                "conservative_multiplier": self._effective_multiplier("conservative"),
                "expected_multiplier": self._effective_multiplier("expected"),
                "optimistic_multiplier": self._effective_multiplier("optimistic"),
                # Theoretical coverage
                "theoretical_failure_coverage_pct": total_failure_coverage,
                "theoretical_downtime_coverage_pct": total_downtime_coverage,
                "key_assumptions": "; ".join(model.key_assumptions[:3]),
            })
        df = pd.DataFrame(rows)
        return df.sort_values("phase_order").reset_index(drop=True)

    def generate_phase_summary(self) -> pd.DataFrame:
        """Generate phase-level summary with ROI ranges (sensor_phase_summary.csv)."""
        rows = []
        current_youden = 0.075

        for phase in [UpgradePhase.PHASE_1, UpgradePhase.PHASE_2, UpgradePhase.PHASE_3]:
            phase_sensors = self._phases[phase]
            roi = self.calculate_roi(phase)

            total_accuracy_gain = sum(s.expected_accuracy_gain for s in phase_sensors)
            cumulative_youden = min(0.90, current_youden + sum(
                s.expected_accuracy_gain
                for p in [UpgradePhase.PHASE_1, UpgradePhase.PHASE_2, UpgradePhase.PHASE_3]
                if p.value <= phase.value
                for s in self._phases[p]
            ))

            complexity_map = {"low": 1, "medium": 2, "high": 3}
            max_complexity = max(
                complexity_map.get(s.deployment_complexity, 2) for s in phase_sensors
            )
            complexity_label = {1: "Low", 2: "Medium", 3: "High"}[max_complexity]

            rows.append({
                "phase": self._phase_label(phase),
                "phase_order": phase_sensors[0].priority,
                "sensors_added": len(phase_sensors),
                "cumulative_youden_j": round(cumulative_youden, 3),
                "youden_j_gain": round(total_accuracy_gain, 3),
                "deployment_complexity": complexity_label,
                "deployment_duration_months": max(s.deployment_months for s in phase_sensors),
                "total_investment": roi.total_investment,
                # ROI range
                "conservative_roi_pct": roi.conservative.roi_5yr_percent,
                "expected_roi_pct": roi.expected.roi_5yr_percent,
                "optimistic_roi_pct": roi.optimistic.roi_5yr_percent,
                "roi_range": f"{roi.conservative.roi_5yr_percent:.0f}% – {roi.optimistic.roi_5yr_percent:.0f}%",
                # Payback
                "payback_months_expected": roi.expected.payback_months,
                "payback_range": f"{roi.optimistic.payback_months}–{roi.conservative.payback_months} months",
                "industrial_value": self._assess_industrial_value(phase),
                "recommended_timing": self._recommend_timing(phase),
            })
        df = pd.DataFrame(rows)
        return df.sort_values("phase_order").reset_index(drop=True)

    def calculate_roi(self, phase: UpgradePhase) -> ROIModel:
        """
        Calculate probabilistic three-scenario ROI for a given upgrade phase.

        Effective reduction formula:
          effective = theoretical_coverage_pct
                    × deployment_factor
                    × adoption_factor
                    × maintenance_quality_factor

        Applied independently for conservative / expected / optimistic scenarios
        using per-scenario factor values from sensor_roi_factors.json.

        Annual saving:
          saving = (effective_downtime_coverage × current_downtime_cost)
                 + (effective_failure_coverage × current_failure_cost)
                 + labor_saving

        5-year ROI:
          roi_5yr = ((annual_saving × 5) - total_investment) / total_investment × 100
        """
        sensors = self._phases[phase]
        n = self.num_machines

        # Aggregate costs
        total_capex = sum(
            (s.unit_cost + s.installation_cost) * n for s in sensors
        )
        total_annual_opex = sum(s.annual_maintenance_cost * n for s in sensors)
        total_investment = total_capex + total_annual_opex

        # Current baseline costs
        current_downtime_cost = (
            self.current_annual_downtime_hours * self.avg_downtime_cost_per_hour
        )
        current_failure_cost = (
            self.current_annual_failures * self.avg_failure_cost_per_incident
        )

        # Theoretical coverage (aggregate across sensors, capped)
        theoretical_downtime = min(
            sum(s.theoretical_downtime_coverage_pct for s in sensors), 60
        )
        theoretical_failure = min(
            sum(s.theoretical_failure_coverage_pct for s in sensors), 70
        )
        labor_saving = self._estimate_labor_saving(phase)

        # ── Compute scenarios ──
        def _scenario_roi(scenario: str) -> ScenarioROI:
            mult = self._effective_multiplier(scenario)
            eff_downtime = theoretical_downtime * mult / 100.0
            eff_failure = theoretical_failure * mult / 100.0
            saving = (
                eff_downtime * current_downtime_cost
                + eff_failure * current_failure_cost
                + labor_saving * mult  # labor saving also scaled
            )
            monthly = saving / 12.0
            payback = int(np.ceil(total_investment / monthly)) if monthly > 0 else 999
            roi_5yr = ((saving * 5) - total_investment) / total_investment * 100
            return ScenarioROI(
                scenario=Scenario(scenario),
                annual_saving=round(saving, -3),
                payback_months=max(1, min(60, payback)),
                roi_5yr_percent=round(roi_5yr, 1),
                effective_multiplier=round(mult, 4),
            )

        cons = _scenario_roi("conservative")
        expt = _scenario_roi("expected")
        optm = _scenario_roi("optimistic")

        # Factors from expected scenario for display
        d, a, m = self._get_factors("expected")

        risk_reduction = min(
            (theoretical_downtime + theoretical_failure) * expt.effective_multiplier / 100.0,
            0.80
        ) * 100

        return ROIModel(
            phase=phase,
            total_investment=round(total_investment, -3),
            annual_opex=round(total_annual_opex, -2),
            conservative=cons,
            expected=expt,
            optimistic=optm,
            annual_saving_low=cons.annual_saving,
            annual_saving_high=optm.annual_saving,
            annual_saving_expected=expt.annual_saving,
            payback_months_low=optm.payback_months,
            payback_months_high=cons.payback_months,
            payback_months_expected=expt.payback_months,
            roi_5yr_percent=expt.roi_5yr_percent,
            risk_reduction_pct=round(risk_reduction, 1),
            deployment_factor=d,
            adoption_factor=a,
            maintenance_quality_factor=m,
            key_assumptions=[
                f"Downtime cost: ${self.avg_downtime_cost_per_hour}/hr (CNC production loss estimate)",
                f"Failure cost: ${self.avg_failure_cost_per_incident}/incident (repair+scrap+labor)",
                f"Baseline: {self.current_annual_failures} failures/yr, {self.current_annual_downtime_hours}h downtime/yr",
                f"Effective multiplier (expected): {expt.effective_multiplier} = deployment × adoption × maintenance",
                f"{n} machines, phased rollout over {max(s.deployment_months for s in self._phases[phase])} months",
                "Conservative/optimistic scenarios span ±50% around expected",
            ],
        )

    def estimate_payback_period(self, phase: UpgradePhase) -> Dict[str, int]:
        """Return payback period estimates (low/expected/high) in months."""
        roi = self.calculate_roi(phase)
        return {
            "payback_months_low": roi.optimistic.payback_months,
            "payback_months_expected": roi.expected.payback_months,
            "payback_months_high": roi.conservative.payback_months,
        }

    def estimate_risk_reduction(self, phase: UpgradePhase) -> float:
        """Return estimated risk reduction percentage for a phase."""
        roi = self.calculate_roi(phase)
        return roi.risk_reduction_pct

    def get_disclaimer(self) -> str:
        """Return the industrial disclaimer from the JSON config."""
        return self._config.get("disclaimer",
            "ROI values are engineering estimation ranges, not guaranteed financial outcomes.")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _phase_label(self, phase: UpgradePhase) -> str:
        labels = {
            UpgradePhase.PHASE_1: "Phase 1: Vibration Monitoring",
            UpgradePhase.PHASE_2: "Phase 2: Current Spectrum Analysis",
            UpgradePhase.PHASE_3: "Phase 3: Thermal Imaging",
        }
        return labels.get(phase, str(phase))

    def _cumulative_youden_j(self, phase: UpgradePhase,
                              sensor: SensorUpgrade) -> float:
        """Calculate cumulative Youden's J after adding this sensor."""
        base = 0.075
        cumulative = base
        phases_in_order = [UpgradePhase.PHASE_1, UpgradePhase.PHASE_2, UpgradePhase.PHASE_3]
        for p in phases_in_order:
            for s in self._phases[p]:
                cumulative += s.expected_accuracy_gain
                if p == phase and s is sensor:
                    return round(min(0.90, cumulative), 3)
        return round(min(0.90, cumulative), 3)

    def _estimate_labor_saving(self, phase: UpgradePhase) -> float:
        """Estimate annual labor savings from automated monitoring."""
        sensors = self._phases[phase]
        labor_hours_saved_per_machine = len(sensors) * 12
        hourly_labor_rate = 35
        return labor_hours_saved_per_machine * self.num_machines * hourly_labor_rate

    def _assess_industrial_value(self, phase: UpgradePhase) -> str:
        """Qualitative assessment of industrial value for each phase."""
        assessments = {
            UpgradePhase.PHASE_1: (
                "Highest ROI per dollar invested. Mechanical faults account for ~40% of CNC "
                "failures. Vibration monitoring provides the single largest accuracy gain at "
                "the lowest cost. Recommended as the immediate first step."
            ),
            UpgradePhase.PHASE_2: (
                "Addresses electrical fault signatures invisible to vibration alone. Motor "
                "winding and power quality issues account for ~25% of failures. Combined "
                "with Phase 1, pushes Youden's J above 0.60 — approaching usable ML territory."
            ),
            UpgradePhase.PHASE_3: (
                "Highest strategic value despite higher CAPEX. Thermal imaging provides "
                "early warning for the most catastrophic failure modes (thermal runaway, "
                "insulation breakdown). Completes the multi-physics monitoring suite."
            ),
        }
        return assessments.get(phase, "Industrial value assessment pending.")

    def _recommend_timing(self, phase: UpgradePhase) -> str:
        """Recommend implementation timing based on ROI and complexity."""
        timings = {
            UpgradePhase.PHASE_1: "Immediate (Q3 2026) — Quick win, 3-month deployment",
            UpgradePhase.PHASE_2: "Short-term (Q4 2026-Q1 2027) — Build on Phase 1 infrastructure",
            UpgradePhase.PHASE_3: "Medium-term (Q2-Q3 2027) — Requires Phase 1+2 data foundation",
        }
        return timings.get(phase, "Timing TBD")


# ============================================================================
# Standalone runner
# ============================================================================

if __name__ == "__main__":
    engine = SensorUpgradeRoadmapEngine(num_machines=100)

    print("=" * 60)
    print("SENSOR UPGRADE ROADMAP — Probabilistic Industrial ROI Model v2.0")
    print("=" * 60)

    # Plan
    plan = engine.generate_upgrade_plan()
    print(f"\n[1] Upgrade Plan: {len(plan)} sensor deployments")
    print(plan[["phase", "sensor_name", "total_capex", "cumulative_youden_j"]].to_string(index=False))

    # ROI
    roi = engine.generate_roi_analysis()
    print(f"\n[2] ROI Analysis (Three-Scenario):")
    print(roi[["phase", "total_investment",
               "conservative_roi_5yr_pct", "expected_roi_5yr_pct", "optimistic_roi_5yr_pct",
               "roi_range"]].to_string(index=False))

    # Summary
    summary = engine.generate_phase_summary()
    print(f"\n[3] Phase Summary:")
    print(summary[["phase", "cumulative_youden_j", "roi_range",
                    "payback_range", "industrial_value"]].to_string(index=False))

    print("\n" + "=" * 60)
    print(engine.get_disclaimer())
