"""Validate SHAP explainability output — structure, completeness, sanity."""
import json


def test_shap_json_exists(decision_dir):
    assert (decision_dir / "shap_dashboard.json").exists(), \
        "shap_dashboard.json not found. Run: python agent_orchestrator.py --shap"


def test_shap_json_structure(decision_dir):
    with open(decision_dir / "shap_dashboard.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    for key in ["meta", "global_importance", "category_summary",
                "top_risk_machines", "machines"]:
        assert key in data, f"Missing key: {key}"


def test_shap_100_machines(decision_dir):
    with open(decision_dir / "shap_dashboard.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["meta"]["total_machines"] == 100
    assert len(data["machines"]) == 100


def test_shap_top20_ordered(decision_dir):
    with open(decision_dir / "shap_dashboard.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    scores = [m["final_risk_score"] for m in data["top_risk_machines"]]
    assert scores == sorted(scores, reverse=True), "Not sorted descending"


def test_shap_machine_signals(decision_dir):
    with open(decision_dir / "shap_dashboard.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    for mid in ["CNC_067", "CNC_012", "CNC_025"]:
        m = data["machines"].get(mid, {})
        assert "key_anomaly_signals" in m, f"{mid}: missing key_anomaly_signals"
        assert "natural_summary" in m, f"{mid}: missing natural_summary"
        assert len(m["natural_summary"]) > 20, f"{mid}: summary too short"


def test_shap_global_importance_count(decision_dir):
    with open(decision_dir / "shap_dashboard.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["global_importance"]) == 8, \
        f"Expected 8 features, got {len(data['global_importance'])}"


def test_shap_category_summary_valid(decision_dir):
    with open(decision_dir / "shap_dashboard.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    total = sum(data["category_summary"].values())
    assert 0.9 < total < 1.1, f"Category sum {total:.3f} not near 1.0"
