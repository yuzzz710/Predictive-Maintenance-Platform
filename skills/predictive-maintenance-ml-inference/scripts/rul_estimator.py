#!/usr/bin/env python3
"""
RUL (Remaining Useful Life) — Degradation Rate Estimator
=========================================================
Track A: 基于健康分退化轨迹的RUL估计器。

核心思路:
  利用已有的8维健康分时序，将健康分的衰减速率映射为剩余时间。

  RUL = (H_now - H_critical) / |退化速率|
  95% CI: Bootstrap残差重采样 → 分位数区间

输入: 健康分时序 DataFrame (每设备每时间步一行)
输出: rul_degradation.csv (100设备 × RUL天数 + CI + 退化速率 + 元数据)

设计约束:
  - 最少5个健康分快照，否则标记为"数据不足"
  - 退化速率≥0（健康分不降或上升）→ RUL=None, reason="NoDegradationSignal"
  - 线性+指数双模型，AIC择优
  - 无新增依赖（仅numpy/scipy）
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class RULResult:
    """单台设备的RUL估计结果。"""
    equipment_id: str
    rul_steps: Optional[float] = None       # RUL in time steps (None = unavailable)
    rul_hours: Optional[float] = None       # RUL in hours (step × 14min / 60)
    rul_ci_95_steps: Tuple[float, float] = (0, 0)
    rul_ci_95_hours: Tuple[float, float] = (0, 0)
    degradation_rate: float = 0.0           # health_score loss per step
    degradation_rate_per_day: float = 0.0   # health_score loss per day (for reporting)
    health_score_current: float = 100.0
    health_score_projected_7d: Optional[float] = None
    health_score_projected_14d: Optional[float] = None
    model_type: str = ""                    # "linear" or "exponential"
    r_squared: float = 0.0
    trend: str = "Stable"                   # "Degrading", "Stable", "Improving"
    status: str = "ok"                      # "ok", "no_degradation", "insufficient_data"
    status_reason: str = ""
    warnings: List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Core Estimator
# ══════════════════════════════════════════════════════════════════════════

class DegradationRUL:
    """
    基于健康分轨迹的退化速率 RUL 估计器。

    对每台设备:
      1. 提取健康分时序 H(t₁), H(t₂), ..., H(t_now)
      2. 线性拟合 H(t) = α + β·t  (β < 0 = 退化)
      3. 指数拟合 H(t) = α·exp(-β·t)  (更适合加速退化场景)
      4. AIC/BIC 选择更优模型
      5. RUL = (H_now - H_critical) / |β|
      6. Bootstrap残差重采样 → 95% CI

    参数:
      critical_threshold: 健康分失效阈值，默认40 (与现有健康分体系对齐)
      min_data_points: 最少健康分快照数，默认5
      rul_max_steps: RUL截断上限，超过此值截断（默认30，即数据最大跨度）
      step_minutes: 每步对应的分钟数，默认14
    """

    def __init__(
        self,
        critical_threshold: float = 40.0,
        min_data_points: int = 5,
        rul_max_steps: int = 30,
        step_minutes: int = 14,
    ):
        self.critical_threshold = critical_threshold
        self.min_data_points = min_data_points
        self.rul_max_steps = rul_max_steps
        self.step_minutes = step_minutes

    # ── Model Fitting ──────────────────────────────────────────────────

    def fit_trajectory(
        self,
        health_scores: np.ndarray,
        timestamps: np.ndarray,
    ) -> dict:
        """
        对单台设备的健康分序列拟合退化轨迹。

        Args:
          health_scores: 健康分数组 H(t)
          timestamps: 时间步数组 (0, 1, 2, ... 或实际时间戳)

        Returns:
          dict with keys: model_type, params, r_squared, slope, aic, bic, residuals
        """
        n = len(health_scores)
        t = np.arange(n, dtype=float)  # use step indices for stable fitting

        # ── Linear fit: H(t) = α + β·t ──
        X_lin = np.column_stack([np.ones(n), t])
        beta_lin, residuals_lin, _, _ = np.linalg.lstsq(X_lin, health_scores, rcond=None)
        alpha_lin, beta_lin_slope = beta_lin[0], beta_lin[1]
        h_pred_lin = alpha_lin + beta_lin_slope * t
        rss_lin = np.sum((health_scores - h_pred_lin) ** 2)

        # R² for linear
        ss_tot = np.sum((health_scores - np.mean(health_scores)) ** 2)
        r2_lin = 1 - rss_lin / ss_tot if ss_tot > 0 else 0.0

        # AIC / BIC (k=2 for linear: α, β)
        if rss_lin > 0 and n > 2:
            aic_lin = n * np.log(rss_lin / n) + 2 * 2
            bic_lin = n * np.log(rss_lin / n) + 2 * np.log(n)
        else:
            aic_lin = 1e9
            bic_lin = 1e9

        # ── Exponential fit: H(t) = α·exp(-β·t) ──
        # log(H) = log(α) - β·t  (only valid if all H > 0)
        exp_failed = False
        aic_exp = 1e9
        bic_exp = 1e9
        r2_exp = 0.0

        if np.all(health_scores > 0):
            try:
                log_h = np.log(health_scores)
                X_exp = np.column_stack([np.ones(n), t])
                beta_exp_raw, _, _, _ = np.linalg.lstsq(X_exp, log_h, rcond=None)
                log_alpha, neg_beta = beta_exp_raw[0], beta_exp_raw[1]
                alpha_exp = np.exp(log_alpha)
                beta_exp_slope = -neg_beta  # positive = degrading

                h_pred_exp = alpha_exp * np.exp(-beta_exp_slope * t)
                rss_exp = np.sum((health_scores - h_pred_exp) ** 2)
                r2_exp = 1 - rss_exp / ss_tot if ss_tot > 0 else 0.0

                if rss_exp > 0 and n > 2:
                    aic_exp = n * np.log(rss_exp / n) + 2 * 2
                    bic_exp = n * np.log(rss_exp / n) + 2 * np.log(n)
            except (ValueError, RuntimeWarning):
                exp_failed = True
        else:
            exp_failed = True

        # ── Model selection (AIC) ──
        if not exp_failed and aic_exp < aic_lin:
            model_type = "exponential"
            r_squared = r2_exp
            aic = aic_exp
            bic = bic_exp
            # For exponential: instantaneous slope at last point = -α*β*exp(-β*t_n)
            slope = -alpha_exp * beta_exp_slope * np.exp(-beta_exp_slope * t[-1])
            residuals = health_scores - h_pred_exp
            params = {"alpha": alpha_exp, "beta": beta_exp_slope}
        else:
            model_type = "linear"
            r_squared = max(0.0, r2_lin)
            aic = aic_lin
            bic = bic_lin
            slope = beta_lin_slope
            residuals = health_scores - h_pred_lin
            params = {"alpha": alpha_lin, "beta": beta_lin_slope}

        return {
            "model_type": model_type,
            "params": params,
            "r_squared": round(r_squared, 4),
            "slope": round(float(slope), 6),
            "aic": round(float(aic), 1),
            "bic": round(float(bic), 1),
            "residuals": residuals,
            "n_points": n,
        }

    # ── RUL Estimation ─────────────────────────────────────────────────

    def estimate_rul(
        self,
        current_health: float,
        slope: float,
        threshold: Optional[float] = None,
    ) -> Optional[float]:
        """
        基于当前健康分和退化速率估算RUL。

        Args:
          current_health: 当前健康分 H_now
          slope: 退化速率 (负值 = 退化中)
          threshold: 失效阈值，默认 self.critical_threshold

        Returns:
          RUL步数，或 None（退化信号不可用）
        """
        if threshold is None:
            threshold = self.critical_threshold

        # No degradation: health is stable or improving
        if slope >= 0:
            return None

        health_gap = current_health - threshold

        # Already at or below critical
        if health_gap <= 0:
            return 0.0

        rul = health_gap / abs(slope)

        # Cap at max steps
        if rul > self.rul_max_steps:
            return float(self.rul_max_steps)

        return float(rul)

    # ── Bootstrap Confidence Interval ─────────────────────────────────

    def bootstrap_ci(
        self,
        health_scores: np.ndarray,
        timestamps: np.ndarray,
        n_bootstrap: int = 1000,
        ci_level: float = 95.0,
        random_seed: int = 42,
    ) -> Tuple[float, float]:
        """
        Bootstrap残差重采样 → RUL置信区间。

        方法: 对拟合残差做Bootstrap重采样，重新拟合并计算RUL，
        取 2.5%/97.5% 分位数。

        Returns:
          (lower, upper) RUL步数的95% CI
        """
        rng = np.random.RandomState(random_seed)
        n = len(health_scores)
        t = np.arange(n, dtype=float)

        # Fit original model
        fit = self.fit_trajectory(health_scores, timestamps)
        residuals = fit["residuals"]
        h_pred = health_scores - residuals
        current_health = float(health_scores[-1])
        slope_orig = fit["slope"]

        rul_samples = []
        for _ in range(n_bootstrap):
            # Resample residuals with replacement
            idx = rng.randint(0, n, size=n)
            resampled_residuals = residuals[idx]
            boot_h = h_pred + resampled_residuals
            boot_h = np.clip(boot_h, 0.1, 100.0)  # valid range

            # Refit
            boot_fit = self.fit_trajectory(boot_h, timestamps)
            boot_slope = boot_fit["slope"]

            # Estimate RUL from bootstrapped slope + original current health
            # (current health is fixed; slope varies)
            boot_rul = self.estimate_rul(current_health, boot_slope)
            if boot_rul is not None:
                rul_samples.append(boot_rul)

        if len(rul_samples) < 100:
            # Not enough valid bootstrap samples; use asymptotic approximation
            return (0.0, float(self.rul_max_steps))

        alpha = (100 - ci_level) / 2
        lower = np.percentile(rul_samples, alpha)
        upper = np.percentile(rul_samples, 100 - alpha)

        return (round(float(lower), 1), round(float(upper), 1))

    # ── Single Machine Evaluation ─────────────────────────────────────

    def evaluate_machine(
        self,
        health_scores: np.ndarray,
        machine_id: str = "unknown",
    ) -> RULResult:
        """
        对单台设备执行完整的RUL估计流程。

        Args:
          health_scores: 健康分时间序列 (按时间升序)
          machine_id: 设备ID

        Returns:
          RULResult dataclass
        """
        n = len(health_scores)

        # ── Guard: minimum data points ──
        if n < self.min_data_points:
            return RULResult(
                equipment_id=machine_id,
                health_score_current=float(health_scores[-1]) if n > 0 else 100.0,
                trend="Stable",
                status="insufficient_data",
                status_reason=f"Only {n} health score snapshots (need ≥{self.min_data_points})",
                warnings=[f"Insufficient data: {n}/{self.min_data_points} points"],
            )

        timestamps = np.arange(n, dtype=float)
        current_health = float(health_scores[-1])

        # ── Fit trajectory ──
        fit = self.fit_trajectory(health_scores, timestamps)
        slope = fit["slope"]
        r_squared = fit["r_squared"]
        model_type = fit["model_type"]

        # ── Trend classification ──
        if slope < -0.01:
            trend = "Degrading"
        elif slope > 0.01:
            trend = "Improving"
        else:
            trend = "Stable"

        # ── Estimate RUL (only if actually degrading) ──
        if trend == "Degrading":
            rul_steps = self.estimate_rul(current_health, slope)
        else:
            rul_steps = None  # Stable or Improving → RUL unavailable

        warnings = []

        if rul_steps is None:
            if trend == "Stable":
                status = "no_degradation"
                reason = f"No degradation signal detected (slope={slope:.4f}, near zero)"
                warnings.append("Health score trajectory is stable — RUL unavailable")
            elif trend == "Improving":
                status = "no_degradation"
                reason = f"Health score improving (slope={slope:.4f} > 0)"
                warnings.append("Health score improving — RUL unavailable")
            else:
                status = "no_degradation"
                reason = "RUL estimate returned None (health gap too small or slope positive)"
                warnings.append("RUL unavailable")
        else:
            status = "ok"
            reason = ""

            # Warn about weak signal
            if r_squared < 0.3:
                warnings.append(f"Degradation signal weak (R2={r_squared:.2f}), CI widened accordingly")

            if n < 10:
                warnings.append(f"Limited history ({n} points), RUL estimate has high uncertainty")

        # ── Bootstrap CI ──
        ci_steps = (0.0, 0.0)
        ci_hours = (0.0, 0.0)
        if rul_steps is not None and rul_steps > 0 and n >= self.min_data_points:
            try:
                ci_steps = self.bootstrap_ci(health_scores, timestamps)
            except Exception:
                ci_steps = (max(0, rul_steps * 0.5), min(self.rul_max_steps, rul_steps * 2.0))

        # ── Unit conversions ──
        rul_hours = (rul_steps * self.step_minutes / 60.0) if rul_steps is not None else None
        ci_hours = (ci_steps[0] * self.step_minutes / 60.0,
                     ci_steps[1] * self.step_minutes / 60.0)

        # Degradation rate per day (for reporting)
        # ~102.9 steps per day (24h * 60min / 14min)
        steps_per_day = 24 * 60 / self.step_minutes
        deg_rate_per_day = abs(slope) * steps_per_day if slope < 0 else 0.0

        # Projected health scores
        h_proj_7d = None
        h_proj_14d = None
        if slope < 0:
            steps_7d = int(7 * steps_per_day)
            steps_14d = int(14 * steps_per_day)
            h_proj_7d = round(float(max(0, current_health + slope * steps_7d)), 1)
            h_proj_14d = round(float(max(0, current_health + slope * steps_14d)), 1)

        return RULResult(
            equipment_id=machine_id,
            rul_steps=round(rul_steps, 1) if rul_steps is not None else None,
            rul_hours=round(rul_hours, 1) if rul_hours is not None else None,
            rul_ci_95_steps=ci_steps,
            rul_ci_95_hours=ci_hours,
            degradation_rate=round(float(abs(slope)) if slope < 0 else 0.0, 6),
            degradation_rate_per_day=round(deg_rate_per_day, 4),
            health_score_current=round(current_health, 1),
            health_score_projected_7d=h_proj_7d,
            health_score_projected_14d=h_proj_14d,
            model_type=model_type,
            r_squared=r_squared,
            trend=trend,
            status=status,
            status_reason=reason,
            warnings=warnings,
        )

    # ── Batch Evaluation ──────────────────────────────────────────────

    def evaluate_all_machines(
        self,
        timeseries_df: pd.DataFrame,
        id_col: str = "Equipment.Id",
        time_col: str = "time_step",
        health_col: str = "health_score",
    ) -> pd.DataFrame:
        """
        对所有设备批量执行RUL估计。

        Args:
          timeseries_df: 健康分时序DataFrame
          id_col: 设备ID列名
          time_col: 时间步列名
          health_col: 健康分列名

        Returns:
          DataFrame: 每设备一行的RUL结果
        """
        results = []
        machine_ids = sorted(timeseries_df[id_col].unique())

        for mid in machine_ids:
            subset = timeseries_df[timeseries_df[id_col] == mid].sort_values(time_col)
            health_scores = subset[health_col].values.astype(float)

            result = self.evaluate_machine(health_scores, machine_id=str(mid))
            results.append(result)

        return self._results_to_dataframe(results)

    def _results_to_dataframe(self, results: List[RULResult]) -> pd.DataFrame:
        """将RULResult列表转换为DataFrame。"""
        rows = []
        for r in results:
            rows.append({
                "Equipment.Id": r.equipment_id,
                "rul_steps": r.rul_steps,
                "rul_hours": r.rul_hours,
                "rul_ci_lower_steps": r.rul_ci_95_steps[0],
                "rul_ci_upper_steps": r.rul_ci_95_steps[1],
                "rul_ci_lower_hours": r.rul_ci_95_hours[0],
                "rul_ci_upper_hours": r.rul_ci_95_hours[1],
                "degradation_rate": r.degradation_rate,
                "degradation_rate_per_day": r.degradation_rate_per_day,
                "health_score_current": r.health_score_current,
                "health_score_projected_7d": r.health_score_projected_7d,
                "health_score_projected_14d": r.health_score_projected_14d,
                "model_type": r.model_type,
                "r_squared": r.r_squared,
                "trend": r.trend,
                "status": r.status,
                "status_reason": r.status_reason,
                "warnings": " | ".join(r.warnings) if r.warnings else "",
            })

        df = pd.DataFrame(rows)
        # Sort: RUL available first (ascending = most urgent first), then unavailable
        df["_sort_key"] = df["rul_steps"].fillna(9999)
        df = df.sort_values("_sort_key").drop(columns=["_sort_key"]).reset_index(drop=True)
        return df


# ══════════════════════════════════════════════════════════════════════════
# Summary Report Generator
# ══════════════════════════════════════════════════════════════════════════

def generate_rul_summary(rul_df: pd.DataFrame) -> dict:
    """
    生成RUL汇总统计，用于Dashboard和报告。

    Args:
      rul_df: evaluate_all_machines() 的输出DataFrame

    Returns:
      dict: 汇总指标
    """
    available = rul_df[rul_df["status"] == "ok"]
    no_degrad = rul_df[rul_df["status"] == "no_degradation"]
    insufficient = rul_df[rul_df["status"] == "insufficient_data"]

    total = len(rul_df)
    n_available = len(available)
    n_no_degrad = len(no_degrad)
    n_insufficient = len(insufficient)

    # RUL statistics (only for machines with available RUL)
    if n_available > 0:
        rul_vals = available["rul_hours"].dropna()
        avg_rul = round(float(rul_vals.mean()), 1) if len(rul_vals) > 0 else 0
        median_rul = round(float(rul_vals.median()), 1) if len(rul_vals) > 0 else 0
        rul_lt_7d = int((available["rul_hours"] < 168).sum())  # 7 days = 168 hours
        rul_lt_1d = int((available["rul_hours"] < 24).sum())

        avg_deg_rate = round(float(available["degradation_rate_per_day"].mean()), 4)
    else:
        avg_rul = 0
        median_rul = 0
        rul_lt_7d = 0
        rul_lt_1d = 0
        avg_deg_rate = 0

    # Model type distribution
    n_linear = int((available["model_type"] == "linear").sum()) if n_available > 0 else 0
    n_exponential = int((available["model_type"] == "exponential").sum()) if n_available > 0 else 0

    # Average R²
    avg_r2 = round(float(available["r_squared"].mean()), 3) if n_available > 0 else 0

    # Critical machines (current health < 40)
    n_critical = int((rul_df["health_score_current"] < 40).sum())

    return {
        "total_machines": total,
        "rul_available": n_available,
        "rul_unavailable_no_degradation": n_no_degrad,
        "rul_unavailable_insufficient_data": n_insufficient,
        "coverage_rate": round(n_available / total, 3) if total > 0 else 0,
        "avg_rul_hours": avg_rul,
        "median_rul_hours": median_rul,
        "avg_rul_days": round(avg_rul / 24, 1),
        "median_rul_days": round(median_rul / 24, 1),
        "rul_lt_7_days": rul_lt_7d,
        "rul_lt_1_day": rul_lt_1d,
        "avg_degradation_rate_per_day": avg_deg_rate,
        "model_type_linear": n_linear,
        "model_type_exponential": n_exponential,
        "avg_r_squared": avg_r2,
        "n_critical_health": n_critical,
        "critical_threshold": 40,
        "step_minutes": 14,
    }


# ══════════════════════════════════════════════════════════════════════════
# Integration Entry Point
# ══════════════════════════════════════════════════════════════════════════

def run_rul_pipeline(
    timeseries_df: pd.DataFrame,
    critical_threshold: float = 40.0,
    min_data_points: int = 5,
) -> Tuple[pd.DataFrame, dict]:
    """
    RUL管线入口：从健康分时序到RUL结果。

    Args:
      timeseries_df: 健康分时序DataFrame
      critical_threshold: 失效阈值
      min_data_points: 最少数据点

    Returns:
      (rul_df, summary_dict)
    """
    estimator = DegradationRUL(
        critical_threshold=critical_threshold,
        min_data_points=min_data_points,
    )

    rul_df = estimator.evaluate_all_machines(timeseries_df)
    summary = generate_rul_summary(rul_df)

    # Print summary
    print(f"\n{'='*60}")
    print(f"RUL Estimation — Degradation Rate Method (Track A)")
    print(f"{'='*60}")
    print(f"  Total machines:           {summary['total_machines']}")
    print(f"  RUL available:            {summary['rul_available']} ({summary['coverage_rate']:.1%})")
    print(f"  No degradation signal:    {summary['rul_unavailable_no_degradation']}")
    print(f"  Insufficient data:        {summary['rul_unavailable_insufficient_data']}")
    print(f"  Avg RUL:                  {summary['avg_rul_hours']:.1f}h ({summary['avg_rul_days']:.1f}d)")
    print(f"  Median RUL:               {summary['median_rul_hours']:.1f}h ({summary['median_rul_days']:.1f}d)")
    print(f"  RUL < 7 days:             {summary['rul_lt_7_days']}")
    print(f"  RUL < 1 day:              {summary['rul_lt_1_day']}")
    print(f"  Avg R2:                   {summary['avg_r_squared']:.3f}")
    print(f"  Model: Linear={summary['model_type_linear']} Exponential={summary['model_type_exponential']}")
    print(f"  Avg degradation rate:     {summary['avg_degradation_rate_per_day']:.4f} health_score/day")
    print(f"{'='*60}\n")

    return rul_df, summary


# ══════════════════════════════════════════════════════════════════════════
# Self-Test
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== RUL Estimator Self-Test ===\n")

    # Generate synthetic health score trajectories
    rng = np.random.RandomState(42)

    test_results = []

    # Test 1: Clear degradation (linear)
    print("Test 1: Linear degradation")
    t = np.arange(25, dtype=float)
    h_degrading = 85.0 - 1.2 * t + rng.normal(0, 2.0, size=25)
    h_degrading = np.clip(h_degrading, 10, 100)

    estimator = DegradationRUL()
    result = estimator.evaluate_machine(h_degrading, "TEST_DEGRADING")
    print(f"  Status: {result.status}")
    print(f"  Health: {result.health_score_current:.1f}")
    print(f"  Slope: {result.degradation_rate:.4f}/step")
    print(f"  RUL: {result.rul_steps} steps ({result.rul_hours}h)")
    print(f"  CI: {result.rul_ci_95_steps}")
    print(f"  R2: {result.r_squared:.3f}")
    print(f"  Model: {result.model_type}")
    print(f"  Warnings: {result.warnings}")

    assert result.status == "ok", f"Expected 'ok', got '{result.status}'"
    assert result.rul_steps is not None, "Expected RUL estimate"
    assert result.rul_steps > 0, f"Expected positive RUL, got {result.rul_steps}"
    assert result.rul_ci_95_steps[0] < result.rul_ci_95_steps[1], "CI bounds invalid"
    print("  [PASSED]\n")

    # Test 2: No degradation (stable)
    print("Test 2: Stable health score")
    # Use a very slightly positive slope to guarantee stable/improving
    t2 = np.arange(25, dtype=float)
    h_stable = 82.0 + 0.005 * t2 + rng.normal(0, 0.5, size=25)  # tiny upward drift
    h_stable = np.clip(h_stable, 10, 100)

    result2 = estimator.evaluate_machine(h_stable, "TEST_STABLE")
    print(f"  Status: {result2.status}")
    print(f"  RUL: {result2.rul_steps}")
    print(f"  Reason: {result2.status_reason}")

    assert result2.status == "no_degradation", f"Expected 'no_degradation', got '{result2.status}'"
    assert result2.rul_steps is None, f"Expected None RUL, got {result2.rul_steps}"
    print("  [PASSED]\n")

    # Test 3: Insufficient data
    print("Test 3: Insufficient data (only 3 points)")
    h_short = np.array([82.0, 80.0, 78.0])
    result3 = estimator.evaluate_machine(h_short, "TEST_SHORT")
    print(f"  Status: {result3.status}")
    print(f"  Reason: {result3.status_reason}")

    assert result3.status == "insufficient_data", f"Expected 'insufficient_data', got '{result3.status}'"
    print("  [PASSED]\n")

    # Test 4: Already critical
    print("Test 4: Already at critical level")
    h_critical = 40.0 - 0.3 * np.arange(25) + rng.normal(0, 1.0, size=25)
    h_critical = np.clip(h_critical, 5, 100)

    result4 = estimator.evaluate_machine(h_critical, "TEST_CRITICAL")
    print(f"  Status: {result4.status}")
    print(f"  Health: {result4.health_score_current:.1f}")
    print(f"  RUL: {result4.rul_steps}")

    assert result4.health_score_current < 40, "Expected health < 40"
    # RUL should be 0 or near 0
    if result4.rul_steps is not None:
        assert result4.rul_steps < 5, f"Expected near-zero RUL, got {result4.rul_steps}"
    print("  [PASSED]\n")

    # Test 5: Batch evaluation
    print("Test 5: Batch evaluation")
    ts_data = []
    for i in range(10):
        n_pts = rng.randint(10, 30)
        t_i = np.arange(n_pts, dtype=float)
        base_h = rng.uniform(60, 95)
        slope_i = rng.uniform(-2.0, 0.5)  # mix of degrading and stable
        h_i = base_h + slope_i * t_i + rng.normal(0, 2.0, size=n_pts)
        h_i = np.clip(h_i, 5, 100)
        for j, h_val in enumerate(h_i):
            ts_data.append({
                "Equipment.Id": f"TEST_{i:03d}",
                "time_step": j,
                "health_score": h_val,
            })

    ts_df = pd.DataFrame(ts_data)
    rul_df, summary = run_rul_pipeline(ts_df)
    print(f"  Rows in output: {len(rul_df)}")
    print(f"  RUL coverage: {summary['coverage_rate']:.1%}")
    assert len(rul_df) == 10, f"Expected 10 rows, got {len(rul_df)}"
    assert summary["total_machines"] == 10
    print("  [PASSED]\n")

    # Test 6: Exponential degradation
    print("Test 6: Exponential degradation (accelerating)")
    t6 = np.arange(25, dtype=float)
    h_exp = 90.0 * np.exp(-0.03 * t6) + rng.normal(0, 1.5, size=25)
    h_exp = np.clip(h_exp, 5, 100)

    result6 = estimator.evaluate_machine(h_exp, "TEST_EXP")
    print(f"  Model selected: {result6.model_type}")
    print(f"  RUL: {result6.rul_steps} steps")
    print(f"  Health 7d projection: {result6.health_score_projected_7d}")
    print(f"  Health 14d projection: {result6.health_score_projected_14d}")

    assert result6.status == "ok", f"Expected 'ok', got '{result6.status}'"
    # Exponential should be selected for accelerating degradation
    print(f"  (Model selection: {result6.model_type} — exponential expected for accelerating decay)")
    print("  [PASSED]\n")

    print("=== All Tests Passed ===")
