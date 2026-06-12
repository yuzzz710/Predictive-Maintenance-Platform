"""
compute_kde_params.py — Phase 1 数据天花板
=============================================
从仪表盘数据 (web-dashboard/data/) 计算4传感器正常/故障分布参数，
输出 kde_params.json 供前端交互式演示使用。

数据来源（与仪表盘保持一致）:
  - log.csv          → 传感器日志（正常/故障样本分离）
  - dim1.csv         → overlap_pct, cohens_d, youden_j
  - sensor_phase_summary.csv → 三阶段 Youden's J 升级数据

输出:
  - kde_params.json  → 4参数 × 2分布 × 200点PDF数据

运行: python scripts/compute_kde_params.py
      （在 web-dashboard 目录下执行）
"""

import json
import math
from pathlib import Path

import pandas as pd
from scipy.stats import norm

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_PATH = DATA_DIR / "log.csv"
DIM1_PATH = DATA_DIR / "dim1.csv"
PHASE_PATH = DATA_DIR / "sensor_phase_summary.csv"
OUTPUT_PATH = DATA_DIR / "kde_params.json"

# ── Parameter config ───────────────────────────────────────────────────────
PARAM_COLS = {
    "Voltage":      {"col": "Op.Voltage",      "label": "电压 (Voltage)",      "unit": "V"},
    "Amperage":     {"col": "Op.Amperage",     "label": "电流 (Amperage)",     "unit": "A"},
    "Temperature":  {"col": "Op.Temperature",  "label": "温度 (Temperature)",  "unit": "°C"},
    "Rotor_Speed":  {"col": "Rotor Speed",     "label": "转速 (Rotor Speed)",  "unit": "RPM"},
}

N_GRID = 200   # PDF采样点数
SIGMA_SPAN = 4  # X轴范围: μ ± 4σ


def load_dim1():
    """从 dim1.csv 读取 overlap_pct, cohens_d, youden_j."""
    df = pd.read_csv(DIM1_PATH)
    result = {}
    for _, row in df.iterrows():
        param = row["parameter"]
        result[param] = {
            "overlap_pct": float(str(row["fault_in_normal_pct"]).replace("%", "")),
            "cohens_d": float(row["cohens_d"]),
            "youden_j": float(row["youden_j"]),
        }
    return result


def load_phase_data():
    """从 sensor_phase_summary.csv 读取三阶段 YJ 数据."""
    df = pd.read_csv(PHASE_PATH)
    phases = []
    for _, row in df.iterrows():
        phases.append({
            "name": row["phase"],
            "youden_j": float(row["cumulative_youden_j"]),
            "sensors_added": row["sensors_added"],
            "investment": f"${int(row['total_investment']):,}",
            "roi": f"{float(row['expected_roi_pct']):.0f}%",
            "payback_months": int(row["payback_months_expected"]),
        })
    return phases


def compute_pdf_grid(normal_vals, fault_vals):
    """计算正常/故障两组的 μ, σ 并生成 200 点 PDF 网格."""
    mu_n, sigma_n = float(normal_vals.mean()), float(normal_vals.std())
    mu_f, sigma_f = float(fault_vals.mean()), float(fault_vals.std())

    # X轴范围：覆盖两组分布的 μ±4σ
    x_min = min(mu_n - SIGMA_SPAN * sigma_n, mu_f - SIGMA_SPAN * sigma_f)
    x_max = max(mu_n + SIGMA_SPAN * sigma_n, mu_f + SIGMA_SPAN * sigma_f)

    # 200点均匀网格
    x_grid = [round(x_min + i * (x_max - x_min) / (N_GRID - 1), 4) for i in range(N_GRID)]

    # PDF 值
    y_normal = [round(norm.pdf(x, mu_n, sigma_n), 6) for x in x_grid]
    y_fault = [round(norm.pdf(x, mu_f, sigma_f), 6) for x in x_grid]

    return {
        "normal": {"mu": round(mu_n, 2), "sigma": round(sigma_n, 2)},
        "fault":  {"mu": round(mu_f, 2), "sigma": round(sigma_f, 2)},
        "x_grid": x_grid,
        "y_normal": y_normal,
        "y_fault": y_fault,
    }


def main():
    print("[compute_kde_params] Loading data...")

    # Load machine log
    log = pd.read_csv(LOG_PATH)
    print(f"  log.csv: {len(log)} rows")

    # Separate normal / fault
    normal = log[log["Failure.Equipment.Type"] == 0]
    fault  = log[log["Failure.Equipment.Type"] > 0]
    print(f"  Normal samples: {len(normal)}, Fault samples: {len(fault)}")

    # Load dim1 annotations
    dim1 = load_dim1()
    print(f"  dim1.csv: {len(dim1)} parameters loaded")

    # Load phase data
    phases = load_phase_data()
    print(f"  sensor_phase_summary.csv: {len(phases)} phases loaded")

    # Build output
    kde_params = {"parameters": {}, "phases": phases}

    for param_key, cfg in PARAM_COLS.items():
        col = cfg["col"]
        pdf = compute_pdf_grid(normal[col], fault[col])
        annotation = dim1.get(param_key, {})

        kde_params["parameters"][param_key] = {
            "label": cfg["label"],
            "unit": cfg["unit"],
            "normal": pdf["normal"],
            "fault": pdf["fault"],
            "x_grid": pdf["x_grid"],
            "y_normal": pdf["y_normal"],
            "y_fault": pdf["y_fault"],
            "overlap_pct": annotation.get("overlap_pct", 0),
            "cohens_d": annotation.get("cohens_d", 0),
            "youden_j": annotation.get("youden_j", 0),
        }

    # Add baseline summary
    kde_params["baseline_youden_j"] = max(
        v["youden_j"] for v in kde_params["parameters"].values()
    )
    kde_params["baseline_summary"] = (
        f"4传感器最高 Youden's J = {kde_params['baseline_youden_j']:.3f}，"
        f"可用阈值 > 0.30。"
        f"96.3% 故障样本落在正常范围内（Voltage），"
        f"任何ML模型无法从无信息输入中学习。"
    )

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(kde_params, f, ensure_ascii=False, indent=2)

    size_kb = round(OUTPUT_PATH.stat().st_size / 1024, 1)
    print(f"\n[compute_kde_params] Done → {OUTPUT_PATH} ({size_kb} KB)")
    print(f"  Parameters: {list(kde_params['parameters'].keys())}")
    print(f"  Phases: {len(kde_params['phases'])}")
    print(f"  Baseline Youden's J: {kde_params['baseline_youden_j']:.4f}")


if __name__ == "__main__":
    main()
