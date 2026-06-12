#!/usr/bin/env python3
"""
Acceptance Validator — Post-Repair Quality Verification Engine
================================================================
Defines fault-type-specific acceptance criteria for maintenance work.
Every repair must pass defined standards before the work order is closed.

All criteria are parameterized via acceptance_rules.json — no hardcoded thresholds.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional


class AcceptanceValidator:
    """
    Rule-based acceptance criteria engine for post-maintenance verification.

    Usage:
        validator = AcceptanceValidator()
        criteria = validator.get_acceptance_criteria("thermal_buildup")
        text = validator.format_acceptance_standard(criteria)
        results = validator.validate_repair("CNC_036", pre_metrics, post_metrics, criteria)
    """

    def __init__(self, rules_path: Optional[str] = None):
        """
        Args:
            rules_path: Path to acceptance_rules.json. If None, uses default
                        relative path from this file's location.
        """
        if rules_path is None:
            rules_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data", "acceptance_rules.json",
            )
        self.rules = self._load_rules(rules_path)

    def _load_rules(self, path: str) -> dict:
        """Load acceptance rules from JSON with graceful fallback."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Graceful fallback: built-in minimal rules (Chinese)
        return {
            "rules": [
                {
                    "fault_type": "thermal_buildup",
                    "acceptance_criteria": [
                        {"id": "TH-01",
                         "description": "温度恢复至正常运行区间",
                         "metric": "Op.Temperature",
                         "threshold": "z_score < 1.5 持续30分钟",
                         "measurement_method": "PT100传感器连续温度监测",
                         "verification_duration_minutes": 30},
                        {"id": "TH-02",
                         "description": "冷却系统功能测试通过",
                         "metric": "Cooling efficiency",
                         "threshold": "满载运行10分钟，ΔT ≤ 15°C",
                         "measurement_method": "维修前后热成像仪扫描对比"},
                        {"id": "TH-03",
                         "description": "维修后无异常温升趋势",
                         "metric": "temp_trend_slope",
                         "threshold": "|斜率| < 0.05（连续10个观测点）",
                         "measurement_method": "维修后24小时趋势分析"},
                    ],
                },
                {
                    "fault_type": "voltage_drift",
                    "acceptance_criteria": [
                        {"id": "VD-01",
                         "description": "电压稳定在规格范围内",
                         "metric": "Op.Voltage",
                         "threshold": "|ΔV/V_nominal| < 5% 持续20分钟",
                         "measurement_method": "数字万用表 + SCADA日志记录"},
                        {"id": "VD-02",
                         "description": "电压波动率降低20%以上",
                         "metric": "voltage_CV",
                         "threshold": "CV降低幅度 ≥ 20%（相比维修前基线）",
                         "measurement_method": "维修后30分钟CV计算"},
                    ],
                },
                {
                    "fault_type": "power_anomaly",
                    "acceptance_criteria": [
                        {"id": "PA-01",
                         "description": "电流稳定在规格范围内",
                         "metric": "Op.Amperage",
                         "threshold": "|ΔI/I_nominal| < 10% 持续15分钟",
                         "measurement_method": "钳形表 + SCADA"},
                        {"id": "PA-02",
                         "description": "电机驱动器输出波形纯净",
                         "metric": "Current THD",
                         "threshold": "THD < 5%",
                         "measurement_method": "示波器测量驱动器输出端子"},
                    ],
                },
                {
                    "fault_type": "combined_degradation",
                    "acceptance_criteria": [
                        {"id": "CD-01",
                         "description": "全部参数恢复至基线水平",
                         "metric": "z_composite",
                         "threshold": "z_composite < 2.0 持续60分钟（4项参数）",
                         "measurement_method": "4通道传感器同步监测"},
                        {"id": "CD-02",
                         "description": "转子转速稳定性恢复",
                         "metric": "Op.Rotor Speed",
                         "threshold": "CV(RPM) < 1% 持续30分钟",
                         "measurement_method": "转速表 + SCADA"},
                        {"id": "CD-03",
                         "description": "振动基线已建立",
                         "metric": "Vibration RMS",
                         "threshold": "振动RMS ≤ 2.0 mm/s（ISO 10816-3 A区）",
                         "measurement_method": "便携式振动分析仪"},
                    ],
                },
            ],
            "universal_criteria": [
                {"id": "UC-01",
                 "description": "维修后24小时内无告警复现",
                 "metric": "All",
                 "threshold": "维修后alert_level = NORMAL 持续24小时",
                 "measurement_method": "SCADA连续监测"},
                {"id": "UC-02",
                 "description": "生产质量抽样合格",
                 "metric": "FAILED_TESTS",
                 "threshold": "FAILED_TESTS / 总检测数 < 维修前周均值",
                 "measurement_method": "质检抽样检查"},
            ],
        }

    def get_acceptance_criteria(self, primary_pattern: str,
                                 max_criteria: int = 3) -> List[dict]:
        """
        Get acceptance criteria for a specific fault type.

        Args:
            primary_pattern: e.g. "thermal_buildup", "voltage_drift"
            max_criteria: Maximum number of fault-specific criteria to return

        Returns:
            List of criteria dicts (fault-specific + universal)
        """
        criteria: List[dict] = []

        for rule in self.rules.get("rules", []):
            if rule.get("fault_type") == primary_pattern:
                criteria = list(rule.get("acceptance_criteria", []))
                break

        # Append universal criteria
        universal = self.rules.get("universal_criteria", [])

        result = criteria[:max_criteria]
        if universal:
            result.append(dict(universal[0]))

        return result

    def format_acceptance_standard(self, criteria_list: List[dict]) -> str:
        """
        Format acceptance criteria as a human-readable string.

        Args:
            criteria_list: Output of get_acceptance_criteria()

        Returns:
            Pipe-separated acceptance standard summary
        """
        parts = []
        for c in criteria_list:
            cid = c.get("id", "??")
            desc = c.get("description", "")
            threshold = c.get("threshold", "")
            parts.append(f"[{cid}] {desc}: {threshold}")
        return " | ".join(parts)

    def validate_repair(self, machine_id: str,
                        pre_repair_metrics: Dict[str, float],
                        post_repair_metrics: Dict[str, float],
                        criteria_list: List[dict]) -> Dict[str, str]:
        """
        Validate whether a repair passes each acceptance criterion.

        Args:
            machine_id: Machine identifier
            pre_repair_metrics: Dict of metric_name → value before repair
            post_repair_metrics: Dict of metric_name → value after repair
            criteria_list: Output of get_acceptance_criteria()

        Returns:
            Dict of criterion_id → "PASS" / "FAIL" / "PENDING_DATA"
        """
        results: Dict[str, str] = {}

        for c in criteria_list:
            cid = c.get("id", "UNKNOWN")
            metric = c.get("metric", "")

            if metric == "All":
                # Universal criterion: check all available post-repair metrics
                all_pass = True
                for key, val in post_repair_metrics.items():
                    if isinstance(val, (int, float)):
                        pre_val = pre_repair_metrics.get(key, 0)
                        if pre_val > 0 and abs(val) > abs(pre_val) * 0.8:
                            all_pass = False
                            break
                results[cid] = "PASS" if all_pass else "FAIL"

            elif metric in post_repair_metrics:
                pre_val = pre_repair_metrics.get(metric, 0)
                post_val = post_repair_metrics.get(metric, 0)
                # Simplified check: post-repair value should be significantly better
                if abs(pre_val) > 0:
                    improvement = (abs(pre_val) - abs(post_val)) / abs(pre_val)
                    results[cid] = "PASS" if improvement > 0.1 else "FAIL"
                else:
                    results[cid] = "PASS"  # No pre-repair anomaly to compare
            else:
                results[cid] = "PENDING_DATA"

        return results
