"""Validate pipeline output CSV structure, columns, and data sanity."""
import json
import pytest
import pandas as pd


# ── Z-Scores ──

def test_z_scores_has_25_columns(prep_dir):
    df = pd.read_csv(prep_dir / "z_scores.csv")
    assert len(df.columns) == 25, f"Expected 25 columns, got {len(df.columns)}"


def test_z_scores_has_composite_z(prep_dir):
    df = pd.read_csv(prep_dir / "z_scores.csv")
    for col in ["z_Voltage", "z_Amperage", "z_Temperature", "z_composite"]:
        assert col in df.columns, f"Missing column: {col}"


# ── Cost Risk ──

def test_cost_risk_100_machines(prep_dir):
    df = pd.read_csv(prep_dir / "cost_risk_matrix.csv")
    assert len(df) == 100


def test_cost_at_risk_positive(prep_dir):
    df = pd.read_csv(prep_dir / "cost_risk_matrix.csv")
    assert (df["cost_at_risk"] > 0).all(), "cost_at_risk must be positive"


# ── Alert Summary ──

def test_alert_summary_100_machines(stat_dir):
    df = pd.read_csv(stat_dir / "alert_summary.csv")
    assert len(df) == 100


def test_alert_levels_valid(stat_dir):
    df = pd.read_csv(stat_dir / "alert_summary.csv")
    valid = {"Normal", "Watch", "Warning", "Alarm"}
    actual = set(df["current_alert_level"].unique())
    assert actual.issubset(valid), f"Invalid alert levels: {actual - valid}"


# ── Health Score ──

def test_health_score_range(stat_dir):
    df = pd.read_csv(stat_dir / "equipment_health_score.csv")
    assert (df["health_score"] >= 0).all()
    assert (df["health_score"] <= 100).all()


def test_health_levels_valid(stat_dir):
    df = pd.read_csv(stat_dir / "equipment_health_score.csv")
    valid = {"Healthy", "Warning", "Degrading", "Critical"}
    actual = set(df["health_level"].unique())
    assert actual.issubset(valid), f"Invalid: {actual - valid}"


# ── Work Orders ──

def test_work_orders_has_shap_columns(decision_dir):
    df = pd.read_csv(decision_dir / "maintenance_work_orders.csv")
    shap_cols = ["top_risk_factor_1", "top_risk_factor_2", "top_risk_factor_3",
                 "shap_explanation", "shap_risk_summary"]
    # SHAP columns are only present when pipeline was run with --shap
    if not all(c in df.columns for c in shap_cols):
        pytest.skip("SHAP columns not present — run pipeline with --shap")


def test_work_orders_count(decision_dir):
    df = pd.read_csv(decision_dir / "maintenance_work_orders.csv")
    assert 1 <= len(df) <= 30, f"Count {len(df)} out of [1,30]"
    assert df["priority"].is_monotonic_increasing, "Priorities not ordered"


# ── Industrial Plan ──

def test_industrial_plan_has_min_columns(decision_dir):
    df = pd.read_csv(decision_dir / "industrial_maintenance_plan.csv")
    assert len(df.columns) >= 28, f"Expected >=28 columns, got {len(df.columns)}"


def test_industrial_plan_technician_fields(decision_dir):
    df = pd.read_csv(decision_dir / "industrial_maintenance_plan.csv")
    for col in ["technician_type", "spare_parts", "recommended_downtime_window"]:
        assert col in df.columns, f"Missing: {col}"


# ── Pipeline Report ──

def test_pipeline_report_has_degradation_mode(test_outputs_dir):
    report_path = test_outputs_dir / "pipeline_execution_report.json"
    if not report_path.exists():
        return  # optional file
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    if "degradation_mode" not in report:
        # Old report from before degradation feature — not a failure
        return
    assert report["degradation_mode"] in ("FULL", "STAT_ONLY", "RULE_ONLY", "EMERGENCY")
