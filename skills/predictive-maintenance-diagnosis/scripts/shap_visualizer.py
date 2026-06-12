#!/usr/bin/env python3
"""
SHAP Visualizer — Dashboard JSON Export ONLY
=============================================
No PNG files. No matplotlib. Exports a single shap_dashboard.json that
the ECharts frontend renders dynamically.
"""

import json
import os


def export_dashboard_json(
    machines: dict,
    global_importance: list,
    output_dir: str,
    filename: str = "shap_dashboard.json"
) -> str:
    """
    Export shap_dashboard.json for the web dashboard.

    Parameters
    ----------
    machines : dict
        {machine_id: LocalExplainer output dict}
    global_importance : list
        [{"feature": ..., "label": ..., "importance": ...}, ...]
    output_dir : str
        Output directory path
    filename : str
        Output filename

    Returns
    -------
    str — path to the created JSON file
    """
    # Build top risk machines list (sorted by risk_score desc, top 20)
    top_machines = sorted(
        machines.items(),
        key=lambda x: x[1].get("final_risk_score", 0),
        reverse=True
    )[:20]

    # Compute category summary across all machines
    category_totals = {}
    for mid, mdata in machines.items():
        for cat, pct in mdata.get("risk_category_breakdown", {}).items():
            category_totals[cat] = category_totals.get(cat, 0.0) + pct

    n_machines = len(machines) or 1
    category_summary = {
        k: round(v / n_machines, 4) for k, v in
        sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    }

    dashboard = {
        "meta": {
            "total_machines": len(machines),
            "top_n": len(top_machines),
            "generated_from": "RiskDecomposer + StatLayerSHAP",
        },
        "global_importance": global_importance,
        "category_summary": category_summary,
        "top_risk_machines": [
            {
                "machine_id": mid,
                "final_risk_score": mdata["final_risk_score"],
                "risk_level": mdata["risk_level"],
                "natural_summary": mdata["natural_summary"],
                "risk_category_breakdown": mdata["risk_category_breakdown"],
                "top_risk_factor_1": mdata.get("top_risk_factor_1", ""),
                "top_risk_factor_2": mdata.get("top_risk_factor_2", ""),
                "top_risk_factor_3": mdata.get("top_risk_factor_3", ""),
                "shap_risk_summary": mdata.get("shap_risk_summary", ""),
            }
            for mid, mdata in top_machines
        ],
        "machines": {
            mid: {
                "final_risk_score": mdata["final_risk_score"],
                "risk_level": mdata["risk_level"],
                "risk_category_breakdown": mdata["risk_category_breakdown"],
                "top_contributors": mdata["top_contributors"],
                "natural_summary": mdata["natural_summary"],
                "inspection_checklist": mdata["inspection_checklist"],
                "key_anomaly_signals": mdata.get("key_anomaly_signals", []),
                "top_risk_factor_1": mdata.get("top_risk_factor_1", ""),
                "top_risk_factor_2": mdata.get("top_risk_factor_2", ""),
                "top_risk_factor_3": mdata.get("top_risk_factor_3", ""),
                "shap_risk_summary": mdata.get("shap_risk_summary", ""),
                "decomposition": mdata.get("decomposition", {}),
            }
            for mid, mdata in machines.items()
        },
    }

    output_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(output_path)
    print(f"  shap_dashboard.json written: {file_size / 1024:.1f} KB "
          f"({len(machines)} machines, {len(top_machines)} top-risk)")

    return output_path


def merge_shap_to_work_orders(
    decision_dir: str,
    machines: dict,
    output_dir: str = None
) -> str:
    """
    Merge SHAP explanation fields into industrial_maintenance_plan.csv.

    Reads the existing CSV, adds 5 SHAP columns matched by machine_id,
    and writes back. If output_dir is provided, writes there instead.

    Returns path to the enriched CSV.
    """
    import pandas as pd

    plan_path = os.path.join(decision_dir, "industrial_maintenance_plan.csv")
    if not os.path.exists(plan_path):
        print(f"  WARNING: {plan_path} not found, skipping merge")
        return ""

    df = pd.read_csv(plan_path)

    # Add SHAP columns if not present
    for col in ["top_risk_factor_1", "top_risk_factor_2", "top_risk_factor_3",
                "shap_explanation", "shap_risk_summary"]:
        if col not in df.columns:
            df[col] = ""

    # Merge SHAP data
    for mid, mdata in machines.items():
        mask = df["machine_id"] == mid
        if mask.any():
            idx = df[mask].index[0]
            df.at[idx, "top_risk_factor_1"] = mdata.get("top_risk_factor_1", "")
            df.at[idx, "top_risk_factor_2"] = mdata.get("top_risk_factor_2", "")
            df.at[idx, "top_risk_factor_3"] = mdata.get("top_risk_factor_3", "")
            df.at[idx, "shap_explanation"] = mdata.get("natural_summary", "")
            df.at[idx, "shap_risk_summary"] = mdata.get("shap_risk_summary", "")

    save_path = plan_path
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "industrial_maintenance_plan.csv")

    df.to_csv(save_path, index=False, encoding="utf-8")
    print(f"  SHAP columns merged to: {save_path}")

    # Also merge into maintenance_work_orders.csv if it exists
    wo_path = os.path.join(decision_dir, "maintenance_work_orders.csv")
    if os.path.exists(wo_path):
        wo_df = pd.read_csv(wo_path)
        for col in ["top_risk_factor_1", "top_risk_factor_2", "top_risk_factor_3",
                    "shap_explanation", "shap_risk_summary"]:
            if col not in wo_df.columns:
                wo_df[col] = ""

        for mid, mdata in machines.items():
            mask = wo_df["machine_id"] == mid
            if mask.any():
                idx = wo_df[mask].index[0]
                wo_df.at[idx, "top_risk_factor_1"] = mdata.get("top_risk_factor_1", "")
                wo_df.at[idx, "top_risk_factor_2"] = mdata.get("top_risk_factor_2", "")
                wo_df.at[idx, "top_risk_factor_3"] = mdata.get("top_risk_factor_3", "")
                wo_df.at[idx, "shap_explanation"] = mdata.get("natural_summary", "")
                wo_df.at[idx, "shap_risk_summary"] = mdata.get("shap_risk_summary", "")

        wo_save = save_path.replace("industrial_maintenance_plan", "maintenance_work_orders") if output_dir else wo_path
        wo_df.to_csv(wo_save, index=False, encoding="utf-8")
        print(f"  SHAP columns merged to: {wo_save}")

    return save_path
