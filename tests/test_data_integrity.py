"""Validate raw input data integrity — 4 CSV files, 100 machines, required columns."""
import pandas as pd

REQUIRED_CSVS = [
    "MACHINE_LOG_DATA._2025.csv",
    "MACHINE_SUMMARY_DATA._2025.csv",
    "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv",
    "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv",
]


def test_all_raw_csvs_exist(raw_data_dir):
    for fname in REQUIRED_CSVS:
        assert (raw_data_dir / fname).exists(), f"Missing: {fname}"


def test_all_raw_csvs_non_empty(raw_data_dir):
    for fname in REQUIRED_CSVS:
        assert (raw_data_dir / fname).stat().st_size > 0, f"Empty: {fname}"


def test_log_has_100_machines(raw_data_dir):
    df = pd.read_csv(raw_data_dir / "MACHINE_LOG_DATA._2025.csv")
    assert df["Equipment.Id"].nunique() == 100


def test_log_has_required_columns(raw_data_dir):
    df = pd.read_csv(raw_data_dir / "MACHINE_LOG_DATA._2025.csv")
    for col in ["Date", "Equipment.Id", "Failure.Equipment.Type",
                "Op.Voltage", "Op.Amperage", "Op.Temperature", "Rotor Speed"]:
        assert col in df.columns, f"Missing column: {col}"


def test_summary_has_required_columns(raw_data_dir):
    df = pd.read_csv(raw_data_dir / "MACHINE_SUMMARY_DATA._2025.csv")
    for col in ["Equipment.Id", "Units Produced Per day", "Unit Cost of Production"]:
        assert col in df.columns, f"Missing column: {col}"
