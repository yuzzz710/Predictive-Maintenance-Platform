"""Validate degradation status output — 4-level fallback integrity."""
import json
import pytest


@pytest.fixture
def degradation_status(decision_dir):
    """Load degradation_status.json if it exists, else skip."""
    path = decision_dir / "degradation_status.json"
    if not path.exists():
        pytest.skip("degradation_status.json not found — run orchestrator first")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_degradation_mode_valid(degradation_status):
    valid = {"FULL", "STAT_ONLY", "RULE_ONLY", "EMERGENCY"}
    assert degradation_status["mode"] in valid, \
        f"Invalid mode: {degradation_status['mode']}"


def test_degradation_components_present(degradation_status):
    for key in ["ml_available", "stat_available", "rule_available"]:
        assert key in degradation_status["components"], f"Missing: {key}"
        assert isinstance(degradation_status["components"][key], bool), \
            f"{key} not bool"


def test_degradation_label_valid(degradation_status):
    assert "label" in degradation_status
    assert len(degradation_status["label"]) > 5, \
        f"Label too short: {degradation_status['label']}"
