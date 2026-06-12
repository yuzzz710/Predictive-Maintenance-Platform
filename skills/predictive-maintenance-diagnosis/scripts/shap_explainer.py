#!/usr/bin/env python3
"""
SHAP Explainer — Risk Decomposition + Stat-Layer TreeSHAP
==========================================================
Directly decomposes the final_risk_score fusion formula (NO surrogate model).
TreeSHAP is applied ONLY to the statistical anomaly sub-layer to attribute
per-parameter contributions within the stat_score.

Architecture:
  final_risk_score = w_stat * stat_score + w_cost * cost_score
                   + w_ml * ml_score + w_trend * trend_score

  RiskDecomposer → rule-based decomposition of cost/trend/ml layers
  StatLayerSHAP → TreeSHAP attribution of z_voltage/z_amperage/z_temperature/T²
                   contributions within the stat_score
"""

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════
# Risk Decomposer — Direct Formula Decomposition (NO surrogate model)
# ══════════════════════════════════════════════════════════════════════════

class RiskDecomposer:
    """
    Decomposes final_risk_score by directly applying the known fusion weights.
    Each sub-score is computed from its documented formula and then multiplied
    by its fusion weight to get the contribution to the final risk score.

    The fusion formula (from maintenance_decision_engine.py):
      risk = w_ml * ml_sig + w_stat * stat_sig + w_cost * cost_sig + w_trend * trend_sig

    Default weights (production_efficiency):
      stat=0.40, cost=0.25, ml=0.25, trend=0.10
    """

    def __init__(self, cost_p50=4500.0, cost_p75=5000.0, cost_p90=5500.0,
                 strategy="production_efficiency"):
        # Cost percentile thresholds for piecewise cost_sig
        self.cost_p50 = cost_p50
        self.cost_p75 = cost_p75
        self.cost_p90 = cost_p90

        # Fusion weights per strategy
        self.weights = {
            "production_efficiency": {"stat": 0.40, "cost": 0.25, "ml": 0.25, "trend": 0.10},
            "cost_efficiency":        {"stat": 0.35, "cost": 0.40, "ml": 0.15, "trend": 0.10},
            "quality_first":          {"stat": 0.45, "cost": 0.15, "ml": 0.20, "trend": 0.20},
        }
        self.w = self.weights.get(strategy, self.weights["production_efficiency"])

    def decompose(self, signals: dict) -> dict:
        """
        Decompose final_risk_score into layered contributions.

        Parameters
        ----------
        signals : dict with keys:
            z_v, z_a, z_t          — latest per-parameter z-scores
            z_comp_mean, z_comp_max — composite z-score stats (last 5 windows)
            t2_max                  — max Hotelling T² (last 5 windows)
            thermal_over_p95        — count of temp |z|>2 in last 5
            voltage_trend_slope     — abs slope of voltage z-score diffs
            temp_trend_slope        — abs slope of temperature z-score diffs
            amperage_trend_slope    — abs slope of amperage z-score diffs
            ml_fault_density        — ML predicted fault density [0,1]
            cost_at_risk            — economic exposure ($)

        Returns
        -------
        dict with final_risk_score and full decomposition tree
        """
        # --- stat_score decomposition ---
        z_mean = float(signals.get("z_comp_mean", 0))
        z_max  = float(signals.get("z_comp_max", 0))
        thermal = float(signals.get("thermal_over_p95", 0))

        # z_signal: weighted blend of mean and max composite z
        z_signal = np.clip(z_mean / 3.0, 0, 1) * 0.7 + np.clip(z_max / 5.0, 0, 1) * 0.3
        # t_signal: thermal exceedance
        t_signal = np.clip(thermal / 5.0, 0, 1)
        stat_score = float(0.75 * z_signal + 0.25 * t_signal)

        # --- cost_score decomposition ---
        cost = float(signals.get("cost_at_risk", self.cost_p50))
        cost_score = self._compute_cost_score(cost)

        # --- ml_score ---
        ml_score = float(np.clip(signals.get("ml_fault_density", 0), 0, 1))

        # --- trend_score decomposition ---
        v_trend = abs(float(signals.get("voltage_trend_slope", 0)))
        t_trend = abs(float(signals.get("temp_trend_slope", 0)))
        a_trend = abs(float(signals.get("amperage_trend_slope", 0)))

        trend_score = float(np.clip(
            np.clip(v_trend / 0.02, 0, 1) * 0.40 +
            np.clip(t_trend / 0.02, 0, 1) * 0.35 +
            np.clip(a_trend / 0.02, 0, 1) * 0.25,
            0, 1
        ))

        # --- final risk score ---
        risk = float(np.clip(
            self.w["stat"] * stat_score +
            self.w["cost"] * cost_score +
            self.w["ml"]  * ml_score +
            self.w["trend"] * trend_score,
            0, 1
        ))

        # --- Build decomposition tree ---
        # Each sub-score contribution = weight * sub_score
        stat_contrib  = self.w["stat"] * stat_score
        cost_contrib  = self.w["cost"] * cost_score
        ml_contrib    = self.w["ml"]  * ml_score
        trend_contrib = self.w["trend"] * trend_score

        # stat sub-factors (proportional attribution within stat_score)
        # z_signal contributes 75% of stat_score, t_signal 25%
        z_contrib  = stat_contrib * 0.75
        t2_contrib = stat_contrib * 0.25

        # Further break down z_signal into per-parameter contributions
        # based on relative magnitude of individual z-scores
        z_v = abs(float(signals.get("z_v", 0)))
        z_a = abs(float(signals.get("z_a", 0)))
        z_t = abs(float(signals.get("z_t", 0)))
        z_sum = z_v + z_a + z_t
        if z_sum > 1e-8:
            zv_contrib = z_contrib * (z_v / z_sum)
            za_contrib = z_contrib * (z_a / z_sum)
            zt_contrib = z_contrib * (z_t / z_sum)
        else:
            zv_contrib = za_contrib = zt_contrib = 0.0

        # trend sub-factors (proportional within trend_score)
        v_trend_norm = np.clip(v_trend / 0.02, 0, 1)
        t_trend_norm = np.clip(t_trend / 0.02, 0, 1)
        a_trend_norm = np.clip(a_trend / 0.02, 0, 1)
        trend_sum = v_trend_norm * 0.40 + t_trend_norm * 0.35 + a_trend_norm * 0.25
        if trend_sum > 1e-8:
            vt_contrib = trend_contrib * (v_trend_norm * 0.40) / trend_sum
            tt_contrib = trend_contrib * (t_trend_norm * 0.35) / trend_sum
            at_contrib = trend_contrib * (a_trend_norm * 0.25) / trend_sum
        else:
            vt_contrib = tt_contrib = at_contrib = 0.0

        return {
            "final_risk_score": round(risk, 4),
            "risk_level": self._risk_level(risk),
            "expected_risk": 0.0,  # will be set by caller as population mean
            "decomposition": {
                "stat_score": {
                    "value": round(stat_score, 4),
                    "weight": self.w["stat"],
                    "contribution": round(stat_contrib, 4),
                    "sub_factors": {
                        "z_voltage":     {"value": round(z_v, 3), "contribution": round(zv_contrib, 4)},
                        "z_amperage":    {"value": round(z_a, 3), "contribution": round(za_contrib, 4)},
                        "z_temperature": {"value": round(z_t, 3), "contribution": round(zt_contrib, 4)},
                        "hotelling_t2":  {"value": round(float(signals.get("t2_max", 0)), 1),
                                          "contribution": round(t2_contrib, 4)},
                    }
                },
                "cost_score": {
                    "value": round(cost_score, 4),
                    "weight": self.w["cost"],
                    "contribution": round(cost_contrib, 4),
                },
                "ml_score": {
                    "value": round(ml_score, 4),
                    "weight": self.w["ml"],
                    "contribution": round(ml_contrib, 4),
                },
                "trend_score": {
                    "value": round(trend_score, 4),
                    "weight": self.w["trend"],
                    "contribution": round(trend_contrib, 4),
                    "sub_factors": {
                        "voltage_trend":  {"value": round(v_trend, 4), "contribution": round(vt_contrib, 4)},
                        "temp_trend":     {"value": round(t_trend, 4), "contribution": round(tt_contrib, 4)},
                        "amperage_trend": {"value": round(a_trend, 4), "contribution": round(at_contrib, 4)},
                    }
                },
            }
        }

    def _compute_cost_score(self, cost: float) -> float:
        """Piecewise cost risk signal (matches decision engine exactly)."""
        if cost >= self.cost_p90:
            return 0.95
        elif cost >= self.cost_p75:
            return 0.70 + 0.25 * (cost - self.cost_p75) / (self.cost_p90 - self.cost_p75 + 1)
        elif cost >= self.cost_p50:
            return 0.40 + 0.30 * (cost - self.cost_p50) / (self.cost_p75 - self.cost_p50 + 1)
        else:
            return 0.30 * cost / (self.cost_p50 + 1)

    @staticmethod
    def _risk_level(score: float) -> str:
        if score >= 0.75: return "High"
        elif score >= 0.55: return "Medium"
        elif score >= 0.35: return "Low"
        else: return "Normal"


# ══════════════════════════════════════════════════════════════════════════
# Stat-Layer SHAP — TreeSHAP on Statistical Anomaly Sub-Layer ONLY
# ══════════════════════════════════════════════════════════════════════════

class StatLayerSHAP:
    """
    Trains a lightweight XGBoost regressor to predict stat_score from raw
    z-score features, then uses TreeSHAP for per-parameter attribution.

    This is the ONLY place SHAP is used — it explains which sensor parameters
    drive the statistical anomaly score for each machine.
    """

    # Features used to predict stat_score (must match build_feature_matrix columns)
    FEATURE_NAMES = [
        "z_voltage_last",
        "z_amperage_last",
        "z_temperature_last",
        "z_comp_max",
        "z_comp_mean",
        "t2_max",
        "n_alarm_windows",
        "n_warning_windows",
    ]

    # Display names for each feature
    FEATURE_LABELS = {
        "z_voltage_last":     "电压异常 (z_Voltage)",
        "z_amperage_last":    "电流异常 (z_Amperage)",
        "z_temperature_last": "温度异常 (z_Temperature)",
        "z_comp_max":         "综合异常峰值 (z_max)",
        "z_comp_mean":        "综合异常均值 (z_mean)",
        "t2_max":             "多参数联合异常 (T²)",
        "n_alarm_windows":    "历史告警次数",
        "n_warning_windows":  "历史预警次数",
    }

    def __init__(self):
        self.model = None
        self.explainer = None
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        """
        Train a small XGBoost to predict stat_score.

        Parameters
        ----------
        X : np.ndarray shape (n_machines, n_features)
        y : np.ndarray shape (n_machines,) — stat_score values
        """
        import xgboost as xgb

        self.model = xgb.XGBRegressor(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )
        self.model.fit(X, y)
        self._fitted = True
        return self

    def explain(self, X: np.ndarray) -> np.ndarray:
        """
        Compute SHAP values for all samples.

        Returns
        -------
        np.ndarray shape (n_samples, n_features) — SHAP values
        """
        if not self._fitted:
            raise RuntimeError("StatLayerSHAP not fitted yet — call .fit() first")

        if self.explainer is None:
            import shap
            self.explainer = shap.TreeExplainer(self.model)

        return self.explainer.shap_values(X)

    def global_importance(self, shap_values: np.ndarray) -> list:
        """Compute mean |SHAP| per feature for global importance ranking."""
        mean_abs = np.abs(shap_values).mean(axis=0)
        ranked = sorted(
            zip(self.FEATURE_NAMES, mean_abs, [self.FEATURE_LABELS.get(n, n) for n in self.FEATURE_NAMES]),
            key=lambda x: x[1], reverse=True
        )
        return [
            {"feature": name, "label": label, "importance": round(float(val), 4)}
            for name, val, label in ranked
        ]


# ══════════════════════════════════════════════════════════════════════════
# Feature Matrix Builder
# ══════════════════════════════════════════════════════════════════════════

def build_feature_matrix(alert_df: pd.DataFrame, z_df: pd.DataFrame,
                         t2_df: pd.DataFrame, cost_df: pd.DataFrame,
                         health_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Build per-machine feature matrix for risk decomposition + SHAP.

    Returns a DataFrame with one row per machine and all signals needed
    by RiskDecomposer.decompose() + StatLayerSHAP.fit().
    """
    rows = []

    for _, arow in alert_df.iterrows():
        mid = arow.get("machine_id", arow.get("Equipment.Id", ""))

        # Per-parameter z-scores (from alert_summary)
        z_v = float(arow.get("z_v_last", 0))
        z_a = float(arow.get("z_a_last", 0))
        z_t = float(arow.get("z_t_last", 0))
        z_comp_mean = float(arow.get("z_comp_mean", 0))
        z_comp_max  = float(arow.get("z_comp_max", 0))
        n_alarm  = int(arow.get("n_alarm_windows", 0))
        n_warn   = int(arow.get("n_warning_windows", 0))

        # T² max from hotelling_t2 (last 5 windows per machine)
        t2_max = 0.0
        if t2_df is not None and "Equipment.Id" in t2_df.columns:
            t2_machine = t2_df[t2_df["Equipment.Id"] == mid]
            if len(t2_machine) > 0:
                t2_max = float(t2_machine["T2"].tail(5).max())

        # Trend slopes from z_scores (compute from last 5 z-score diffs)
        v_trend = 0.0
        t_trend_abs = 0.0
        a_trend = 0.0
        if z_df is not None and "Equipment.Id" in z_df.columns:
            z_machine = z_df[z_df["Equipment.Id"] == mid]
            if len(z_machine) >= 5:
                try:
                    z_machine = z_machine.sort_values("Date")
                    last5 = z_machine.tail(5)
                    for col, key in [("z_Voltage", "v"), ("z_Temperature", "t"), ("z_Amperage", "a")]:
                        vals = last5[col].values
                        if len(vals) >= 2:
                            slope = np.polyfit(range(len(vals)), vals, 1)[0]
                            if key == "v":
                                v_trend = slope
                            elif key == "t":
                                t_trend_abs = slope
                            else:
                                a_trend = slope
                except Exception:
                    pass

        # Thermal exceedance count
        thermal_over_p95 = 0
        if z_df is not None and "Equipment.Id" in z_df.columns:
            z_machine = z_df[z_df["Equipment.Id"] == mid]
            if len(z_machine) >= 5:
                last5_tz = z_machine.sort_values("Date").tail(5)["z_Temperature"]
                thermal_over_p95 = int((last5_tz.abs() > 2.0).sum())

        # Cost at risk
        cost_at_risk = 5000.0
        if cost_df is not None:
            cost_col = "cost_at_risk"
            id_col = "Equipment.Id" if "Equipment.Id" in cost_df.columns else "machine_id"
            cost_row = cost_df[cost_df[id_col] == mid]
            if len(cost_row) > 0:
                cost_at_risk = float(cost_row.iloc[0][cost_col])

        # ML fault density (from health score or default)
        ml_fault_density = 0.5
        if health_df is not None:
            id_col = "Equipment.Id" if "Equipment.Id" in health_df.columns else "machine_id"
            hrow = health_df[health_df[id_col] == mid]
            if len(hrow) > 0:
                # Use failure_rate as proxy for ml_fault_density
                ml_fault_density = float(hrow.iloc[0].get("failure_rate", 0.5))
                if ml_fault_density > 1:
                    ml_fault_density = ml_fault_density / 100.0
                ml_fault_density = np.clip(ml_fault_density, 0, 1)

        # Health score
        health_score = 50.0
        if health_df is not None:
            id_col = "Equipment.Id" if "Equipment.Id" in health_df.columns else "machine_id"
            hrow = health_df[health_df[id_col] == mid]
            if len(hrow) > 0:
                health_score = float(hrow.iloc[0].get("health_score", 50.0))

        # Maintenance overdue days
        overdue_days = 0.0
        if health_df is not None:
            id_col = "Equipment.Id" if "Equipment.Id" in health_df.columns else "machine_id"
            hrow = health_df[health_df[id_col] == mid]
            if len(hrow) > 0:
                overdue_days = float(hrow.iloc[0].get("maintenance_overdue_days", 0.0))

        # Alert level from alert_summary
        alert_level = str(arow.get("current_alert_level", "Normal"))

        rows.append({
            "machine_id": mid,
            "z_v": z_v,
            "z_a": z_a,
            "z_t": z_t,
            "z_comp_mean": z_comp_mean,
            "z_comp_max": z_comp_max,
            "t2_max": t2_max,
            "thermal_over_p95": thermal_over_p95,
            "voltage_trend_slope": v_trend,
            "temp_trend_slope": t_trend_abs,
            "amperage_trend_slope": a_trend,
            "cost_at_risk": cost_at_risk,
            "ml_fault_density": ml_fault_density,
            "health_score": health_score,
            "overdue_days": overdue_days,
            "alert_level": alert_level,
            # StatLayerSHAP features
            "z_voltage_last": z_v,
            "z_amperage_last": z_a,
            "z_temperature_last": z_t,
            "n_alarm_windows": n_alarm,
            "n_warning_windows": n_warn,
        })

    return pd.DataFrame(rows)
