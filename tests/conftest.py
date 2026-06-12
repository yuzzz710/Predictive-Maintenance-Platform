"""Shared fixtures: paths and data loading for all tests."""
import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def raw_data_dir(project_root):
    return project_root / "原始数据集"


@pytest.fixture(scope="session")
def test_outputs_dir(project_root):
    return project_root / "agent-mcp架构" / "outputs_test"


@pytest.fixture(scope="session")
def prep_dir(test_outputs_dir):
    return test_outputs_dir / "output_data_prep"


@pytest.fixture(scope="session")
def stat_dir(test_outputs_dir):
    return test_outputs_dir / "output_stat_inference"


@pytest.fixture(scope="session")
def decision_dir(test_outputs_dir):
    return test_outputs_dir / "output_decision"
