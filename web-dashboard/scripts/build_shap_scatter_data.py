"""
build_shap_scatter_data.py — SHAP 交互式探索数据准备
======================================================
从 shap_dashboard.json 提取 SHAP 贡献值，
从 equipment_health_score.csv + z_scores.csv 提取特征原始值，
合并输出 shap_scatter_data.json 供前端散点图使用。

输入（只读）:
  - data/shap_dashboard.json        → SHAP 贡献值（top_contributors）
  - data/equipment_health_score.csv → cost_at_risk, failure_rate, temperature_slope, voltage_instability
  - data/z_scores.csv              → 最新 z_composite/z_Temperature + z_Amperage 斜率

输出:
  - data/shap_scatter_data.json

运行: python scripts/build_shap_scatter_data.py
      （在 web-dashboard 目录下执行）
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SHAP_PATH = DATA_DIR / "shap_dashboard.json"
HEALTH_PATH = DATA_DIR / "equipment_health_score.csv"
Z_SCORES_PATH = DATA_DIR / "z_scores.csv"
OUTPUT_PATH = DATA_DIR / "shap_scatter_data.json"

# ── Feature definitions ────────────────────────────────────────────────────
FEATURES = [
    {
        "id": "cost_at_risk",
        "name": "成本风险",
        "unit": "$k/天",
        "desc": "设备故障将造成的每日经济损失预估",
        "source": "health",
        "col": "cost_at_risk",
        "compute": "direct",
    },
    {
        "id": "ml_fault_density",
        "name": "ML故障密度",
        "unit": "%",
        "desc": "机器学习模型预测的故障发生密度（百分比）",
        "source": "health",
        "col": "failure_rate",
        "compute": "multiply_100",
    },
    {
        "id": "hotelling_t2",
        "name": "多参数联合异常(T²)",
        "unit": "σ",
        "desc": "Hotelling T² 多变量统计量，综合评估多参数联合偏离程度",
        "source": "z_scores",
        "col": "z_composite",
        "compute": "latest",
    },
    {
        "id": "voltage_trend",
        "name": "电压不稳定性",
        "unit": "%",
        "desc": "电压相对于设备基线的波动幅度",
        "source": "health",
        "col": "voltage_instability",
        "compute": "direct",
    },
    {
        "id": "temp_trend",
        "name": "温度变化趋势",
        "unit": "斜率",
        "desc": "温度随时间的线性变化速率（正值=持续升温）",
        "source": "health",
        "col": "temperature_slope",
        "compute": "direct",
    },
    {
        "id": "z_temperature",
        "name": "温度异常(Z-score)",
        "unit": "σ",
        "desc": "当前温度偏离设备正常基线的标准差倍数",
        "source": "z_scores",
        "col": "z_Temperature",
        "compute": "latest",
    },
    {
        "id": "amperage_trend",
        "name": "电流变化趋势",
        "unit": "Z/天",
        "desc": "电流 Z-Score 随时间的线性变化斜率（正值=持续恶化）",
        "source": "z_scores",
        "col": "z_Amperage",
        "compute": "slope",
    },
]


def load_health_scores():
    """Load equipment_health_score.csv → {mid: {col: value}}."""
    result = {}
    with open(HEALTH_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = row["Equipment.Id"].strip()
            result[mid] = {
                "cost_at_risk": float(row.get("cost_at_risk", 0) or 0),
                "failure_rate": float(row.get("failure_rate", 0) or 0),
                "temperature_slope": float(row.get("temperature_slope", 0) or 0),
                "voltage_instability": float(row.get("voltage_instability", 0) or 0),
                "health_score": float(row.get("health_score", 50) or 50),
                "health_level": row.get("health_level", "Warning").strip(),
            }
    return result


def load_z_scores():
    """Load z_scores.csv → {mid: {z_composite_latest, z_Temperature_latest, z_Amperage_slope}}."""
    # Read with pandas for grouping
    df = pd.read_csv(Z_SCORES_PATH)
    result = {}

    for mid, group in df.groupby("Equipment.Id"):
        mid = str(mid).strip()
        # Sort by index (time order)
        group = group.sort_index()
        latest = group.iloc[-1]

        result[mid] = {
            "z_composite": float(latest.get("z_composite", 0) or 0),
            "z_Temperature": float(latest.get("z_Temperature", 0) or 0),
        }

        # Compute z_Amperage slope via linear regression
        z_amps = group["z_Amperage"].values.astype(float)
        if len(z_amps) >= 3:
            x = np.arange(len(z_amps))
            slope, _ = np.polyfit(x, z_amps, 1)
            result[mid]["z_Amperage_slope"] = round(float(slope), 4)
        else:
            result[mid]["z_Amperage_slope"] = 0.0

    return result


def load_shap_contributions():
    """Load shap_dashboard.json → {mid: {feature_raw: contribution}}."""
    with open(SHAP_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = {}
    machines = data.get("machines", {})
    for mid, mdata in machines.items():
        contribs = {}
        for tc in mdata.get("top_contributors", []):
            fr = tc.get("feature_raw", "")
            contrib = float(tc.get("contribution", 0))
            contribs[fr] = contrib

        result[mid] = {
            "contributions": contribs,
            "risk_score": float(mdata.get("final_risk_score", 0)),
        }

    return result


def get_feature_value(fid, feat_def, health_data, z_data):
    """Extract the raw feature value for a given machine from health/z_data."""
    source = feat_def["source"]
    compute = feat_def["compute"]

    if source == "health":
        hd = health_data
        if compute == "direct":
            return hd.get(feat_def["col"], 0)
        elif compute == "multiply_100":
            return round(hd.get(feat_def["col"], 0) * 100, 2)
    elif source == "z_scores":
        zd = z_data
        if compute == "latest":
            return zd.get(feat_def["col"], 0)
        elif compute == "slope":
            return zd.get("z_Amperage_slope", 0)

    return 0


def main():
    print("[build_shap_scatter] Loading data...")

    # Load all data sources
    health_data = load_health_scores()
    print(f"  health_scores: {len(health_data)} machines")

    z_data = load_z_scores()
    print(f"  z_scores: {len(z_data)} machines")

    shap_data = load_shap_contributions()
    print(f"  shap_dashboard: {len(shap_data)} machines")

    # Build output
    output = {
        "meta": {
            "total_machines": len(shap_data),
            "features": [{"feature_id": f["id"], "display_name": f["name"],
                          "unit": f["unit"], "description": f["desc"]} for f in FEATURES],
            "generated_at": pd.Timestamp.now().isoformat(),
        },
        "machines": {},
    }

    for mid in sorted(shap_data.keys()):
        hd = health_data.get(mid, {})
        zd = z_data.get(mid, {})
        sd = shap_data.get(mid, {})

        features = {}
        for feat in FEATURES:
            fid = feat["id"]
            value = get_feature_value(mid, feat, hd, zd)
            contribution = sd.get("contributions", {}).get(fid, 0.0)
            features[fid] = {
                "value": round(value, 4) if isinstance(value, float) else value,
                "contribution": round(contribution, 4),
            }

        output["machines"][mid] = {
            "health_score": round(hd.get("health_score", 50), 1),
            "health_level": hd.get("health_level", "Warning"),
            "risk_score": round(sd.get("risk_score", 0), 4),
            "features": features,
        }

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = round(OUTPUT_PATH.stat().st_size / 1024, 1)
    print(f"\n[build_shap_scatter] Done → {OUTPUT_PATH} ({size_kb} KB)")
    print(f"  Machines: {output['meta']['total_machines']}")
    print(f"  Features: {len(FEATURES)}")

    # Quick stats per feature
    for feat in FEATURES:
        fid = feat["id"]
        non_zero = sum(
            1 for m in output["machines"].values()
            if abs(m["features"].get(fid, {}).get("contribution", 0)) > 0.0001
        )
        mean_contrib = np.mean([
            m["features"].get(fid, {}).get("contribution", 0)
            for m in output["machines"].values()
        ])
        print(f"  {fid:20s}: {non_zero:3d}/100 non-zero, mean_contrib={mean_contrib:.4f}")


if __name__ == "__main__":
    main()
