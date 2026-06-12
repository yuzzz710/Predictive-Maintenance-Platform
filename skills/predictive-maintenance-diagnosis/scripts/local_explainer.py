#!/usr/bin/env python3
"""
Local Explainer — Industrial Attribution & Root Cause Classification
====================================================================
Translates mathematical feature contributions into industrial explanations
that maintenance engineers can act on.

"No z_amperage_mean +0.21" → "设备出现持续性电流偏离，可能存在电气负载异常或驱动系统老化风险"
"""

import numpy as np

# ══════════════════════════════════════════════════════════════════════════
# Root Cause Category Mapping
# ══════════════════════════════════════════════════════════════════════════

ROOT_CAUSE_CATEGORIES = {
    "electrical": {
        "label": "电气风险",
        "icon": "⚡",
        "keywords": [
            "z_voltage", "z_amperage", "z_Voltage", "z_Amperage",
            "voltage_trend", "amperage_trend", "voltage_instability",
            "电压", "电流",
        ],
    },
    "thermal": {
        "label": "热风险",
        "icon": "🔥",
        "keywords": [
            "z_temperature", "z_Temperature", "temp_trend",
            "temperature_slope", "thermal",
            "温度",
        ],
    },
    "mechanical": {
        "label": "机械风险",
        "icon": "⚙️",
        "keywords": [
            "rotor_speed", "hotelling_t2", "t2_max",
            "转速", "联合异常",
        ],
    },
    "maintenance": {
        "label": "维护风险",
        "icon": "🔧",
        "keywords": [
            "maintenance_overdue", "overdue_ratio", "days_since_service",
            "overdue", "保养", "维护",
        ],
    },
    "process_quality": {
        "label": "质量风险",
        "icon": "📊",
        "keywords": [
            "failure_rate", "quality_failure", "out_of_spec_rate",
            "cost_at_risk", "cost",
            "故障率", "质量", "成本",
        ],
    },
}


def classify_feature(feature_name: str) -> str:
    """Map a feature name to its root cause category."""
    for category, info in ROOT_CAUSE_CATEGORIES.items():
        for kw in info["keywords"]:
            if kw.lower() in feature_name.lower():
                return category
    return "electrical"  # default fallback


# ══════════════════════════════════════════════════════════════════════════
# Industrial Explanation Templates
# ══════════════════════════════════════════════════════════════════════════

# Maps feature patterns → industrial explanations (not math descriptions)
INDUSTRIAL_EXPLANATIONS = [
    # (keyword_match, condition_desc, explanation_template)
    ("z_amperage", "电流异常",
     "设备出现持续性电流偏离，可能存在电气负载异常或驱动系统老化风险"),
    ("z_voltage", "电压异常",
     "电压偏离设备正常基线，可能存在电源模块不稳定或母线电压波动"),
    ("z_temperature", "温度异常",
     "运行温度显著高于该设备历史正常区间，需排查散热系统或轴承磨损"),
    ("temp_trend", "温度持续上升",
     "温度呈持续上升趋势，可能存在渐进性热失效风险，建议检查冷却系统"),
    ("voltage_trend", "电压漂移",
     "电压出现方向性漂移，提示电源调节系统可能存在性能退化"),
    ("amperage_trend", "电流趋势变化",
     "电流呈现趋势性变化，可能反映负载特性改变或驱动系统老化"),
    ("hotelling_t2", "多参数联合异常",
     "多参数联合统计量异常，提示设备可能存在系统性退化而非单一传感器漂移"),
    ("t2_max", "多参数联合异常",
     "多参数联合统计量异常，提示设备可能存在系统性退化而非单一传感器漂移"),
    ("maintenance_overdue", "保养超期",
     "保养周期已超期，缺乏定期维护可能导致性能退化累积"),
    ("overdue", "保养超期",
     "保养周期已超期，缺乏定期维护可能导致性能退化累积"),
    ("cost_at_risk", "高成本风险",
     "该设备故障将造成较高经济损失，属于高价值关键设备，建议优先保障"),
    ("failure_rate", "历史故障率高",
     "该设备历史故障频率较高，可能存在系统性的可靠性问题"),
    ("health_score", "健康评分偏低",
     "设备综合健康评分偏低，多维度风险因素叠加"),
    ("z_composite", "综合统计异常",
     "多传感器综合统计量偏离正常范围，设备整体运行状态存在异常"),
    ("n_alarm", "历史告警频繁",
     "该设备历史告警次数较多，可能存在未根本解决的潜在问题"),
]


def get_industrial_explanation(feature_name: str, contribution: float) -> dict:
    """
    Given a feature name and its risk contribution, return an industrial
    explanation with category, natural language, and inspection guidance.
    """
    category = classify_feature(feature_name)
    direction = "risk_increase" if contribution > 0 else "risk_decrease"

    # Find best-matching explanation template
    explanation = ""
    condition = feature_name
    for keyword, cond, tmpl in INDUSTRIAL_EXPLANATIONS:
        if keyword.lower() in feature_name.lower():
            condition = cond
            explanation = tmpl
            break

    if not explanation:
        explanation = f"特征 {feature_name} 对风险评分产生{'正向' if contribution > 0 else '负向'}贡献"

    return {
        "feature": condition,
        "feature_raw": feature_name,
        "category": category,
        "category_label": ROOT_CAUSE_CATEGORIES[category]["label"],
        "contribution": round(float(contribution), 4),
        "direction": direction,
        "explanation": explanation,
    }


# ══════════════════════════════════════════════════════════════════════════
# Inspection Checklist Generator
# ══════════════════════════════════════════════════════════════════════════

INSPECTION_BY_CATEGORY = {
    "electrical": [
        "检查驱动系统电流稳定性",
        "测量电源模块输出电压",
        "排查母线电压波动来源",
        "检查电气连接端子是否松动",
    ],
    "thermal": [
        "排查散热风扇及通风通道",
        "检查轴承润滑状态",
        "测量关键部位温度分布",
        "确认冷却系统运行正常",
    ],
    "mechanical": [
        "检查转子动平衡状态",
        "排查机械传动部件磨损",
        "测量振动及异常噪音",
        "确认紧固件扭矩",
    ],
    "maintenance": [
        "确认保养记录并安排预防性维护",
        "检查易损件更换周期",
        "评估润滑油脂老化状态",
        "更新维护计划时间表",
    ],
    "process_quality": [
        "检查产品加工质量记录",
        "排查工艺参数偏移",
        "确认来料质量稳定性",
        "评估刀具/模具磨损状态",
    ],
}


def generate_inspection_checklist(category_breakdown: dict, top_n: int = 4) -> list:
    """
    Generate prioritized inspection checklist based on risk category breakdown.
    Higher-risk categories get more items.
    """
    checklist = []
    seen = set()

    # Sort categories by risk contribution (descending)
    sorted_cats = sorted(category_breakdown.items(), key=lambda x: x[1], reverse=True)

    for cat, risk_pct in sorted_cats:
        if risk_pct < 0.05:  # skip negligible categories
            continue
        items = INSPECTION_BY_CATEGORY.get(cat, [])
        # Take 1-2 items per category based on risk proportion
        n_items = 2 if risk_pct > 0.20 else 1
        for item in items[:n_items]:
            if item not in seen:
                checklist.append(item)
                seen.add(item)
        if len(checklist) >= top_n:
            break

    return checklist[:top_n]


# ══════════════════════════════════════════════════════════════════════════
# Natural Language Summary Builder
# ══════════════════════════════════════════════════════════════════════════

def build_natural_summary(top_contributors: list, category_breakdown: dict,
                          risk_score: float, risk_level: str,
                          key_anomaly_signals: list = None) -> str:
    """
    Build a natural-language Chinese summary of why this machine triggered an alert.

    Prioritizes sensor anomaly signals (current/temperature/voltage deviations)
    over abstract risk factors (cost/ML density) for industrial readability.

    Example output:
    "该设备处于高风险状态。传感器监测到电流严重偏离基线(z=7.87)、
    温度持续上升(trend=0.02)，叠加维护周期超期及高成本暴露，
    共同推高综合风险评分至0.86。建议在48小时内安排电气专项检修。"
    """
    level_desc = {
        "High": "该设备处于高风险状态",
        "Medium": "该设备处于中等风险状态",
        "Low": "该设备处于低风险关注状态",
        "Normal": "该设备运行状态正常",
    }

    # ── Build sensor anomaly narrative (preferred for industrial readability) ──
    sensor_clauses = []
    if key_anomaly_signals:
        for sig in key_anomaly_signals:
            label = sig.get("feature_label", sig.get("sensor", ""))
            value_label = sig.get("value_label", "")
            sensor_clauses.append(f"{label}({value_label})")

    # ── Build cost/ML narrative (secondary, from top contributors) ──
    aux_clauses = []
    for c in top_contributors[:5]:
        if c["contribution"] > 0.03:
            cat = c.get("category", "")
            if cat in ("electrical", "thermal", "mechanical"):
                continue  # sensor anomalies already covered above
            aux_clauses.append(c["feature"])

    # ── Compose final summary ──
    if sensor_clauses:
        sensor_text = "、".join(sensor_clauses)
        aux_text = ("，叠加" + "、".join(aux_clauses)) if aux_clauses else ""
        cause_text = f"传感器监测到{sensor_text}{aux_text}"
    else:
        # Fallback to contribution-based causes
        causes = [c["feature"] for c in top_contributors[:3] if c["contribution"] > 0.01]
        if not causes:
            return f"{level_desc.get(risk_level, '设备')}，各监测参数在正常范围内。"
        cause_text = "、".join(causes)

    # Primary risk category
    sorted_cats = sorted(category_breakdown.items(), key=lambda x: x[1], reverse=True)
    primary_cat = sorted_cats[0][0] if sorted_cats else "electrical"
    primary_label = ROOT_CAUSE_CATEGORIES[primary_cat]["label"] if primary_cat in ROOT_CAUSE_CATEGORIES else "综合"

    # Urgency
    if risk_level == "High":
        urgency = "建议在48小时内安排专项检修。"
    elif risk_level == "Medium":
        urgency = "建议在下次计划维护中优先处理。"
    else:
        urgency = "建议持续监控，按常规计划维护。"

    summary = (
        f"{level_desc.get(risk_level, '设备')}。"
        f"{cause_text}，共同推高综合风险评分至{risk_score:.2f}。"
        f"主要风险集中在{primary_label}领域。"
        f"{urgency}"
    )

    return summary


# ══════════════════════════════════════════════════════════════════════════
# Main LocalExplainer
# ══════════════════════════════════════════════════════════════════════════

class LocalExplainer:
    """
    Generates per-machine industrial explanations from decomposed risk scores.
    """

    def __init__(self):
        pass

    def explain_machine(self, machine_id: str, decomposition: dict,
                        stat_shap: dict = None) -> dict:
        """
        Build a complete single-machine explanation.

        Parameters
        ----------
        machine_id : str
        decomposition : dict
            Output from RiskDecomposer.decompose()
        stat_shap : dict or None
            Optional per-machine SHAP values from StatLayerSHAP.
            Keys are feature names, values are SHAP contributions.

        Returns
        -------
        dict with full industrial explanation
        """
        risk_score = decomposition["final_risk_score"]
        risk_level = decomposition["risk_level"]

        # --- Collect all sub-factor contributions ---
        all_contribs = []

        # Stat sub-factors
        for name, info in decomposition["decomposition"]["stat_score"]["sub_factors"].items():
            all_contribs.append({
                "feature_raw": name,
                "contribution": info["contribution"],
            })

        # Trend sub-factors
        for name, info in decomposition["decomposition"]["trend_score"]["sub_factors"].items():
            all_contribs.append({
                "feature_raw": name,
                "contribution": info["contribution"],
            })

        # Cost and ML as single factors
        all_contribs.append({
            "feature_raw": "cost_at_risk",
            "contribution": decomposition["decomposition"]["cost_score"]["contribution"],
        })
        all_contribs.append({
            "feature_raw": "ml_fault_density",
            "contribution": decomposition["decomposition"]["ml_score"]["contribution"],
        })

        # Add stat-layer SHAP values if available (overrides proportional split)
        if stat_shap:
            for feat_name, shap_val in stat_shap.items():
                # Find and update matching contributor
                for c in all_contribs:
                    if feat_name in c["feature_raw"] or c["feature_raw"] in feat_name:
                        c["contribution"] = float(shap_val)
                        break

        # --- Apply industrial explanations ---
        explained = [
            get_industrial_explanation(c["feature_raw"], c["contribution"])
            for c in all_contribs
        ]

        # Sort by absolute contribution (descending)
        explained.sort(key=lambda x: abs(x["contribution"]), reverse=True)

        # --- Compute category breakdown ---
        category_breakdown = {}
        for exp in explained:
            cat = exp["category"]
            category_breakdown[cat] = category_breakdown.get(cat, 0.0) + abs(exp["contribution"])

        # Normalize to proportions
        total_cat = sum(category_breakdown.values()) or 1.0
        category_breakdown = {
            k: round(v / total_cat, 4) for k, v in category_breakdown.items()
        }

        # --- Extract key anomaly signals from raw sensor readings ---
        # These are based on actual z-score magnitudes, NOT risk contributions.
        # A machine with z_amperage=7.8 should flag "电流严重异常" even if
        # cost_at_risk dominates the risk score.
        key_anomaly_signals = self._extract_key_anomaly_signals(decomposition)

        # --- Build top contributors (keep real contribution order) ---
        top_contributors = explained[:5]

        # --- Natural summary ---
        natural_summary = build_natural_summary(
            top_contributors, category_breakdown, risk_score, risk_level,
            key_anomaly_signals,
        )

        # --- Inspection checklist ---
        checklist = generate_inspection_checklist(category_breakdown)

        # --- Top risk factors (3 for work order) ---
        top3 = top_contributors[:3]

        return {
            "machine_id": machine_id,
            "final_risk_score": risk_score,
            "risk_level": risk_level,
            "risk_category_breakdown": {
                ROOT_CAUSE_CATEGORIES.get(k, {}).get("label", k): v
                for k, v in sorted(category_breakdown.items(),
                                   key=lambda x: x[1], reverse=True)
            },
            "top_contributors": top_contributors,
            "key_anomaly_signals": key_anomaly_signals,
            "natural_summary": natural_summary,
            "inspection_checklist": checklist,
            "top_risk_factor_1": top3[0]["explanation"] if len(top3) > 0 else "",
            "top_risk_factor_2": top3[1]["explanation"] if len(top3) > 1 else "",
            "top_risk_factor_3": top3[2]["explanation"] if len(top3) > 2 else "",
            "shap_risk_summary": " | ".join(
                f"{v['category_label']}={int(v['contribution']*100)}%" if v['contribution'] > 0.03
                else "" for v in top_contributors[:4]
            ).strip(" | "),
        }

    def _extract_key_anomaly_signals(self, decomposition: dict) -> list:
        """
        Extract top sensor-level anomalies from raw z-score values.
        Returns up to 3 signals, sorted by |z-score| magnitude (descending).
        Does NOT use risk contributions — purely based on sensor readings.
        """
        signals = []

        # Stat-layer sub_factors have raw z-score values (or T² for hotelling)
        # Normalize each type by its decision-engine threshold so severity ~1 = borderline
        T2_CRITICAL = 11.34  # chi-square critical value at alpha=0.01, df=3
        Z_THRESHOLD = 3.0    # decision engine normalizes z/3 for z_signal
        stat_subs = decomposition.get("decomposition", {}).get("stat_score", {}).get("sub_factors", {})
        for name, info in stat_subs.items():
            raw_val = info.get("value", 0)
            is_t2 = "t2" in name.lower() or "hotelling" in name.lower()
            if is_t2:
                severity = abs(raw_val) / T2_CRITICAL
                if severity < 1.0:
                    continue
            else:
                severity = abs(raw_val) / Z_THRESHOLD
                if severity < 0.5:  # |z| < 1.5 not meaningful
                    continue

            exp = get_industrial_explanation(name, 0)
            signals.append({
                "sensor": name,
                "value": raw_val,
                "value_label": f"T²={raw_val:.0f}" if is_t2 else f"z={raw_val:.1f}",
                "severity": severity,
                "is_t2": is_t2,
                "feature_label": exp["feature"],
                "explanation": exp["explanation"],
                "category": exp["category"],
                "category_label": exp["category_label"],
            })

        # Trend-layer sub_factors
        # build_feature_matrix computes slope of z-score VALUES (not diffs).
        # z-score changing by 1.5 over 5 points → slope=0.3 per step (moderate).
        # Normalize: |slope|/0.3 → severity=1.0 (moderate), severity=3.0 (steep).
        TREND_THRESHOLD = 0.3
        trend_subs = decomposition.get("decomposition", {}).get("trend_score", {}).get("sub_factors", {})
        for name, info in trend_subs.items():
            abs_val = abs(info.get("value", 0))
            if abs_val < 0.05:  # below minimum meaningful slope
                continue
            exp = get_industrial_explanation(name, 0)
            signals.append({
                "sensor": name,
                "value": info.get("value", 0),
                "value_label": f"斜率={info.get('value', 0):.3f}",
                "severity": abs_val / TREND_THRESHOLD,
                "is_t2": False,
                "feature_label": exp["feature"],
                "explanation": exp["explanation"],
                "category": exp["category"],
                "category_label": exp["category_label"],
            })

        # Sort by severity (normalized across z-score / T² / trend)
        signals.sort(key=lambda s: s.get("severity", 0), reverse=True)

        return signals[:3]
