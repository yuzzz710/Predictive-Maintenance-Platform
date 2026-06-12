"""
Cross-table Association Analysis — Four-Table Joint Mining
===========================================================
Merges LOG + SUMMARY + ASSEMBLY + TESTS to uncover multi-dimensional
association rules for the predictive maintenance dashboard.

Association Rules:
  R1: Maintenance frequency → Parameter stability
  R2: Fault type → Cost loss
  R3: Parameter anomaly → Product defect rate
  R4: Maintenance cycle → Fault probability

Output:
  - cross_table_metrics.csv  (per-machine cross-table metrics for dashboard)
  - 6–7 Nature-figure PNGs saved to outputs/
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ── Paths ──
DATA_DIR = Path(r"..\原始数据集")
OUT_DIR = Path("outputs_cross_table")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Nature-figure style ──
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 7, 'axes.titlesize': 9, 'axes.labelsize': 8,
    'xtick.labelsize': 6, 'ytick.labelsize': 6, 'legend.fontsize': 6,
    'figure.dpi': 200, 'savefig.dpi': 200, 'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05, 'axes.linewidth': 0.5,
    'axes.spines.top': False, 'axes.spines.right': False,
    'legend.frameon': False,
})
NATURE_COLORS = ['#0C7BDC', '#E66100', '#5D3A9B', '#009E73', '#F5C710',
                 '#CC3311', '#AA4499', '#882255', '#332288', '#117733']


def fig_path(name):
    return str(OUT_DIR / name)


# ══════════════════════════════════════════════════════════════════════════
# 1. LOAD & PREPROCESS
# ══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("  CROSS-TABLE ASSOCIATION ANALYSIS")
print("=" * 60)

log = pd.read_csv(DATA_DIR / "MACHINE_LOG_DATA._2025.csv")
summary = pd.read_csv(DATA_DIR / "MACHINE_SUMMARY_DATA._2025.csv")
assembly = pd.read_csv(DATA_DIR / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv")
tests = pd.read_csv(DATA_DIR / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv")

# Parse dates
ref_date = pd.Timestamp("2025-05-20")
summary["Last_Repair_Date"] = pd.to_datetime(summary["Last Repair Date"], errors="coerce")
summary["Last_Service_Date"] = pd.to_datetime(summary["Last Service Date"], errors="coerce")
summary["Next_Service_Date"] = pd.to_datetime(summary["Next Service Date"], errors="coerce")
summary["days_since_repair"] = (ref_date - summary["Last_Repair_Date"]).dt.days
summary["days_since_service"] = (ref_date - summary["Last_Service_Date"]).dt.days
summary["service_interval_days"] = (
    summary["Next_Service_Date"] - summary["Last_Service_Date"]
).dt.days

# ══════════════════════════════════════════════════════════════════════════
# 2. PER-MACHINE METRICS
# ══════════════════════════════════════════════════════════════════════════

# ── 2a. LOG → parameter stability + fault stats ──
log_metrics = log.groupby("Equipment.Id").agg(
    voltage_mean=("Op.Voltage", "mean"),
    voltage_cv=("Op.Voltage", lambda x: np.std(x) / np.mean(x) * 100 if np.mean(x) > 0 else 0),
    amperage_mean=("Op.Amperage", "mean"),
    amperage_cv=("Op.Amperage", lambda x: np.std(x) / np.mean(x) * 100 if np.mean(x) > 0 else 0),
    temperature_mean=("Op.Temperature", "mean"),
    temperature_cv=("Op.Temperature", lambda x: np.std(x) / np.mean(x) * 100 if np.mean(x) > 0 else 0),
    rotor_speed_mean=("Rotor Speed", "mean"),
    rotor_speed_cv=("Rotor Speed", lambda x: np.std(x) / np.mean(x) * 100 if np.mean(x) > 0 else 0),
    total_records=("Failure.Equipment.Type", "count"),
    fault_count=("Failure.Equipment.Type", lambda x: (x != 0).sum()),
).reset_index()
log_metrics["fault_rate_pct"] = (
    log_metrics["fault_count"] / log_metrics["total_records"] * 100
)
# Composite parameter CV (average of 4 CVs)
log_metrics["param_cv_avg"] = log_metrics[
    ["voltage_cv", "amperage_cv", "temperature_cv", "rotor_speed_cv"]
].mean(axis=1)

# Dominant fault type per machine (mode of fault types)
fault_type_counts = (
    log[log["Failure.Equipment.Type"] != 0]
    .groupby(["Equipment.Id", "Failure.Equipment.Type"])
    .size().reset_index(name="count")
)
dominant_fault = fault_type_counts.loc[
    fault_type_counts.groupby("Equipment.Id")["count"].idxmax(),
    ["Equipment.Id", "Failure.Equipment.Type"]
].copy()
dominant_fault.columns = ["Equipment.Id", "dominant_fault_type"]
# Also get all fault types per machine as gap-separated string for display
fault_types_per_machine = fault_type_counts.groupby("Equipment.Id")["Failure.Equipment.Type"].apply(
    lambda x: ",".join(sorted(str(int(v)) for v in x.unique()))
).reset_index(name="all_fault_types")

log_metrics = log_metrics.merge(dominant_fault, on="Equipment.Id", how="left")
log_metrics = log_metrics.merge(fault_types_per_machine, on="Equipment.Id", how="left")
log_metrics["dominant_fault_type"] = log_metrics["dominant_fault_type"].fillna(0).astype(int)
log_metrics["all_fault_types"] = log_metrics["all_fault_types"].fillna("")

# Fault group mapping
fault_group_map = {
    0: "Normal", 1: "Subtle", 2: "Subtle", 3: "Thermal",
    4: "High-Voltage", 5: "High-Voltage", 6: "Thermal",
    7: "Thermal", 8: "Thermal", 9: "Thermal",
}
log_metrics["fault_group"] = log_metrics["dominant_fault_type"].map(fault_group_map)

# ── 2b. SUMMARY → cost, production, maintenance ──
summary_metrics = summary[["Equipment.Id", "Units Produced Per day",
                            "Unit Cost of Production", "days_since_repair",
                            "days_since_service", "service_interval_days"]].copy()
summary_metrics.columns = ["Equipment.Id", "daily_output", "unit_cost",
                           "days_since_repair", "days_since_service",
                           "service_interval_days"]
summary_metrics["daily_value"] = (
    summary_metrics["daily_output"] * summary_metrics["unit_cost"]
)
summary_metrics["cost_at_risk"] = (
    summary_metrics["daily_value"] * 0.5  # conservative: 0.5 day output at risk
)
summary_metrics["maintenance_overdue"] = (
    summary_metrics["days_since_service"] > summary_metrics["service_interval_days"]
).astype(int)

# ── 2c. ASSEMBLY → product quality per machine ──
test_cols = [
    "ANALOG TESTS", "BOUNDARY SCAN TESTS", "CONTACT TEST",
    "DISCHARGING CAPACITORS", "FRAMESCAN", "HIGH_RANGE_VALUE_TESTS",
    "LOW_RANGE_VALUE_TESTS", "POWERED ANALOG", "POWER UP",
    "SHORTS TESTING", "TESTJET",
]
assembly["total_tests"] = assembly[test_cols].sum(axis=1)
assembly["is_defective"] = (assembly["FAILED_TESTS"] > 0).astype(int)

assy_metrics = assembly.groupby("MACHINE").agg(
    total_products=("SERIAL NO", "nunique"),
    total_test_runs=("total_tests", "sum"),
    failed_tests=("FAILED_TESTS", "sum"),
    defective_runs=("is_defective", "sum"),
).reset_index()
assy_metrics.columns = ["Equipment.Id", "total_products", "total_test_runs",
                         "failed_tests", "defective_runs"]
assy_metrics["defect_rate_pct"] = (
    assy_metrics["defective_runs"] / assy_metrics["total_products"] * 100
)

# ── 2d. TESTS → out-of-spec rate per machine ──
tests["out_of_spec"] = (
    (tests["MEASMT_VALUE"] < tests["LWR_SPEC_LIMIT"])
    | (tests["MEASMT_VALUE"] > tests["UPR_SPEC_LIMIT"])
).astype(int)
tests["spec_violation_magnitude"] = np.where(
    tests["MEASMT_VALUE"] < tests["LWR_SPEC_LIMIT"],
    (tests["LWR_SPEC_LIMIT"] - tests["MEASMT_VALUE"]) / tests["LWR_SPEC_LIMIT"],
    np.where(
        tests["MEASMT_VALUE"] > tests["UPR_SPEC_LIMIT"],
        (tests["MEASMT_VALUE"] - tests["UPR_SPEC_LIMIT"]) / tests["UPR_SPEC_LIMIT"],
        0,
    ),
)

test_metrics = tests.groupby("MACHINE").agg(
    total_measurements=("MEASMT_VALUE", "count"),
    out_of_spec_count=("out_of_spec", "sum"),
    avg_violation_magnitude=("spec_violation_magnitude", "mean"),
).reset_index()
test_metrics.columns = ["Equipment.Id", "total_measurements",
                         "out_of_spec_count", "avg_violation_magnitude"]
test_metrics["out_of_spec_rate_pct"] = (
    test_metrics["out_of_spec_count"] / test_metrics["total_measurements"] * 100
)

# ══════════════════════════════════════════════════════════════════════════
# 3. MERGE ALL METRICS
# ══════════════════════════════════════════════════════════════════════════

# Level 1: LOG + SUMMARY (100 machines — all have both)
wide = log_metrics.merge(summary_metrics, on="Equipment.Id", how="left")

# Level 2: LOG + SUMMARY + ASSEMBLY + TESTS (15 machines — product testing subset)
wide_full = wide.merge(assy_metrics, on="Equipment.Id", how="left")
wide_full = wide_full.merge(test_metrics, on="Equipment.Id", how="left")

# Flag whether machine has product test data
wide_full["has_product_data"] = wide_full["total_products"].notna().astype(int)

# ══════════════════════════════════════════════════════════════════════════
# 4. ASSOCIATION RULES
# ══════════════════════════════════════════════════════════════════════════

# R1: days since service → parameter CV% (continuous, not binary)
wide_clean = wide.dropna(subset=["days_since_service", "param_cv_avg"])
if len(wide_clean) >= 10:
    r1_r, r1_p = scipy_stats.pearsonr(wide_clean["days_since_service"], wide_clean["param_cv_avg"])
    r1_spearman_r, r1_spearman_p = scipy_stats.spearmanr(wide_clean["days_since_service"], wide_clean["param_cv_avg"])
else:
    r1_r = r1_p = r1_spearman_r = r1_spearman_p = float("nan")
# For boxplot: bin days_since_service into tertiles
wide["maintenance_tertile"] = pd.cut(
    wide["days_since_service"], bins=3,
    labels=["近期保养(<35天)", "中期保养(35-70天)", "远期保养(>70天)"]
)
tertile_groups = [wide[wide["maintenance_tertile"] == t]["param_cv_avg"].dropna().values
                   for t in wide["maintenance_tertile"].cat.categories]
r1_stat, r1_kruskal_p = scipy_stats.kruskal(*tertile_groups)

# R2: fault group → daily cost at risk
fault_cost = wide.groupby("fault_group").agg(
    machine_count=("Equipment.Id", "count"),
    avg_daily_value=("daily_value", "mean"),
    avg_fault_rate=("fault_rate_pct", "mean"),
    avg_param_cv=("param_cv_avg", "mean"),
    total_cost_at_risk=("cost_at_risk", "sum"),
).reset_index()
r2_kruskal_stat, r2_kruskal_p = scipy_stats.kruskal(
    *[wide[wide["fault_group"] == g]["daily_value"].values
      for g in fault_cost["fault_group"].unique() if g != "Normal"]
)

# R3: parameter CV% → defect rate (15-machine subset with product data)
r3_data = wide_full[wide_full["has_product_data"] == 1].dropna(
    subset=["defect_rate_pct", "param_cv_avg"]
)
if len(r3_data) >= 5:
    r3_r, r3_p = scipy_stats.pearsonr(r3_data["param_cv_avg"], r3_data["defect_rate_pct"])
    r3_spearman_r, r3_spearman_p = scipy_stats.spearmanr(
        r3_data["param_cv_avg"], r3_data["defect_rate_pct"]
    )
else:
    r3_r = r3_p = r3_spearman_r = r3_spearman_p = float("nan")

# R4: days since repair → fault rate
r4_data = wide.dropna(subset=["days_since_repair", "fault_rate_pct"])
if len(r4_data) >= 10:
    r4_r, r4_p = scipy_stats.pearsonr(r4_data["days_since_repair"], r4_data["fault_rate_pct"])
else:
    r4_r = r4_p = float("nan")

print(f"\nR1: Days since service → param CV%: Spearman ρ={r1_spearman_r:.3f}, p={r1_spearman_p:.4f}")
print(f"R2: Fault group → cost: Kruskal-Wallis p={r2_kruskal_p:.4f}")
print(f"R3: Param CV% → defect rate: Pearson r={r3_r:.3f}, p={r3_p:.4f}")
print(f"R4: Days since repair → fault rate: Pearson r={r4_r:.3f}, p={r4_p:.4f}")

# ══════════════════════════════════════════════════════════════════════════
# 5. CHARTS
# ══════════════════════════════════════════════════════════════════════════

# ── Fig 1: Days since service → parameter CV% (R1, continuous) ──
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5))
# Left: scatter + regression
ax1.scatter(wide_clean["days_since_service"], wide_clean["param_cv_avg"],
            c="#0C7BDC", s=30, alpha=0.5, edgecolors="none")
z = np.polyfit(wide_clean["days_since_service"], wide_clean["param_cv_avg"], 1)
ax1.plot(wide_clean["days_since_service"].sort_values(),
         np.poly1d(z)(wide_clean["days_since_service"].sort_values()),
         "-", color="#CC3311", linewidth=1.5)
ax1.set_xlabel("距上次保养天数")
ax1.set_ylabel("参数CV%均值")
ax1.set_title(f"Spearman ρ={r1_spearman_r:.3f} p={r1_spearman_p:.3f}", fontsize=8)
# Right: boxplot by tertile
tertile_data = [wide[wide["maintenance_tertile"] == t]["param_cv_avg"].dropna().values
                for t in wide["maintenance_tertile"].cat.categories]
bp = ax2.boxplot(tertile_data, positions=[0, 1, 2], widths=0.4, patch_artist=True,
                 medianprops={"color": "#CC3311", "linewidth": 1.5})
for i, box in enumerate(bp["boxes"]):
    box.set_facecolor(NATURE_COLORS[i])
ax2.set_xticklabels(wide["maintenance_tertile"].cat.categories, rotation=10, fontsize=6)
ax2.set_ylabel("参数变异系数均值 (%)")
ax2.set_title(f"Kruskal-Wallis p={r1_kruskal_p:.4f}", fontsize=8)
fig.suptitle("R1: 保养周期 → 参数稳定性 (100台)", fontsize=9, fontweight="bold")
fig.tight_layout()
fig.savefig(fig_path("fig1_maintenance_vs_stability.png"))
plt.close(fig)
print("  [Fig 1] saved")

# ── Fig 2: Fault group → daily cost at risk (R2) ──
fig, ax1 = plt.subplots(figsize=(6, 3.5))
fc_sorted = fault_cost.sort_values("avg_daily_value", ascending=True)
colors = {"Thermal": "#E66100", "High-Voltage": "#CC3311",
          "Subtle": "#0C7BDC", "Normal": "#009E73"}
bar_colors = [colors.get(g, "#888") for g in fc_sorted["fault_group"]]
ax1.barh(range(len(fc_sorted)), fc_sorted["avg_daily_value"] / 1000,
         color=bar_colors, alpha=0.85, height=0.6)
ax1.set_yticks(range(len(fc_sorted)))
ax1.set_yticklabels([f"{g} ({int(c)}台)" for g, c in
                      zip(fc_sorted["fault_group"], fc_sorted["machine_count"])])
ax1.set_xlabel("日均产值 ($k)")
ax1.set_title(f"R2: 故障类型 → 成本损失\nKruskal-Wallis p={r2_kruskal_p:.4f}", fontsize=8)
ax2 = ax1.twiny()
ax2.barh(range(len(fc_sorted)), fc_sorted["avg_fault_rate"],
         color="#5D3A9B", alpha=0.3, height=0.3)
ax2.set_xlabel("平均故障率 (%)", color="#5D3A9B")
ax2.tick_params(axis="x", colors="#5D3A9B")
fig.tight_layout()
fig.savefig(fig_path("fig2_fault_vs_cost.png"))
plt.close(fig)
print("  [Fig 2] saved")

# ── Fig 3: Parameter CV% → defect rate scatter (R3) ──
fig, ax = plt.subplots(figsize=(5, 3.5))
if len(r3_data) >= 5:
    ax.scatter(r3_data["param_cv_avg"], r3_data["defect_rate_pct"],
               c="#0C7BDC", s=50, alpha=0.7, edgecolors="white", linewidth=0.5)
    for _, row in r3_data.iterrows():
        ax.annotate(row["Equipment.Id"].replace("CNC_", ""),
                    (row["param_cv_avg"], row["defect_rate_pct"]),
                    fontsize=5, alpha=0.7, textcoords="offset points", xytext=(3, 3))
    z = np.polyfit(r3_data["param_cv_avg"], r3_data["defect_rate_pct"], 1)
    p_line = np.poly1d(z)
    x_line = np.linspace(r3_data["param_cv_avg"].min(), r3_data["param_cv_avg"].max(), 50)
    ax.plot(x_line, p_line(x_line), "--", color="#CC3311", linewidth=1, alpha=0.7)
    ax.set_xlabel("参数变异系数均值 (%)")
    ax.set_ylabel("产品缺陷率 (%)")
    ax.set_title(f"R3: 参数异常度 → 产品合格率 (15台有产品数据)\n"
                 f"Pearson r={r3_r:.3f} p={r3_p:.3f} | Spearman ρ={r3_spearman_r:.3f}",
                 fontsize=8)
fig.tight_layout()
fig.savefig(fig_path("fig3_param_vs_defect.png"))
plt.close(fig)
print("  [Fig 3] saved")

# ── Fig 4: Days since repair → fault rate (R4) ──
fig, ax = plt.subplots(figsize=(5, 3.5))
if len(r4_data) >= 10:
    ax.scatter(r4_data["days_since_repair"], r4_data["fault_rate_pct"],
               c="#009E73", s=40, alpha=0.6, edgecolors="white", linewidth=0.5)
    ax.set_xlabel("距上次维修天数")
    ax.set_ylabel("故障率 (%)")
    ax.set_title(f"R4: 维护周期 → 故障概率 (n={len(r4_data)})\n"
                 f"Pearson r={r4_r:.3f} p={r4_p:.3f}", fontsize=8)
    # Add loess-like trend
    bins = pd.cut(r4_data["days_since_repair"], bins=10)
    trend = r4_data.groupby(bins).agg(
        x=("days_since_repair", "median"), y=("fault_rate_pct", "mean"),
        n=("Equipment.Id", "count")
    )
    ax.plot(trend["x"], trend["y"], "-", color="#CC3311", linewidth=2, alpha=0.8)
fig.tight_layout()
fig.savefig(fig_path("fig4_repair_cycle_vs_fault.png"))
plt.close(fig)
print("  [Fig 4] saved")

# ── Fig 5: Cost risk heatmap — fault group × maintenance tertile ──
fig, ax = plt.subplots(figsize=(6.5, 3))
heat_data = wide.pivot_table(
    values="cost_at_risk", index="fault_group",
    columns="maintenance_tertile", aggfunc="mean"
)
im = ax.imshow(heat_data.values, cmap="YlOrRd", aspect="auto")
ax.set_xticks(range(len(heat_data.columns)))
ax.set_xticklabels([str(c) for c in heat_data.columns], fontsize=7)
ax.set_yticks(range(len(heat_data.index)))
ax.set_yticklabels(heat_data.index)
for i in range(len(heat_data)):
    for j in range(len(heat_data.columns)):
        val = heat_data.values[i, j]
        if not np.isnan(val):
            ax.text(j, i, f"${val/1000:.0f}k", ha="center", va="center", fontsize=7,
                    color="white" if val > np.nanmean(heat_data.values) else "#333")
ax.set_title("R2扩展: 故障组 × 保养周期 → 平均成本风险", fontsize=8)
plt.colorbar(im, ax=ax, label="平均成本风险 ($)")
fig.tight_layout()
fig.savefig(fig_path("fig5_cost_risk_heatmap.png"))
plt.close(fig)
print("  [Fig 5] saved")

# ── Fig 6: Cross-table correlation matrix (key features) ──
corr_cols = [
    "fault_rate_pct", "param_cv_avg", "daily_value", "cost_at_risk",
    "days_since_repair", "days_since_service",
]
corr_labels = ["故障率%", "参数CV%", "日产值", "成本风险", "距维修天数", "距保养天数"]
corr_data = wide[corr_cols].dropna()
corr_matrix = corr_data.corr(method="spearman")
fig, ax = plt.subplots(figsize=(5.5, 4.5))
im = ax.imshow(corr_matrix.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
ax.set_xticks(range(len(corr_labels)))
ax.set_xticklabels(corr_labels, rotation=30, ha="right")
ax.set_yticks(range(len(corr_labels)))
ax.set_yticklabels(corr_labels)
for i in range(len(corr_labels)):
    for j in range(len(corr_labels)):
        ax.text(j, i, f"{corr_matrix.values[i,j]:.2f}", ha="center", va="center",
                fontsize=7, color="white" if abs(corr_matrix.values[i,j]) > 0.3 else "#333")
ax.set_title("跨表关联矩阵 · Spearman ρ (100台)", fontsize=8)
plt.colorbar(im, ax=ax, label="Spearman ρ", shrink=0.8)
fig.tight_layout()
fig.savefig(fig_path("fig6_cross_correlation_matrix.png"))
plt.close(fig)
print("  [Fig 6] saved")

# ══════════════════════════════════════════════════════════════════════════
# 6. OUTPUT CSV FOR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════

# Per-machine cross-table metrics (all 100 machines)
dashboard_cols = [
    "Equipment.Id", "fault_rate_pct", "param_cv_avg",
    "dominant_fault_type", "fault_group", "daily_output", "unit_cost",
    "daily_value", "cost_at_risk", "days_since_repair",
    "days_since_service", "maintenance_overdue",
    "total_products", "defect_rate_pct", "out_of_spec_rate_pct",
]
out_df = wide_full[dashboard_cols].copy()
out_df.columns = [
    "machine_id", "fault_rate_pct", "param_cv_avg_pct",
    "dominant_fault_type", "fault_group", "daily_output", "unit_cost",
    "daily_value", "cost_at_risk", "days_since_repair",
    "days_since_service", "maintenance_overdue",
    "total_products", "defect_rate_pct", "out_of_spec_rate_pct",
]
out_df.to_csv(OUT_DIR / "cross_table_metrics.csv", index=False, encoding="utf-8")

# Association rules summary
rules_summary = pd.DataFrame([
    {
        "rule_id": "R1", "rule_name": "保养周期→参数稳定性",
        "method": "Spearman ρ", "statistic": round(float(r1_spearman_r), 3),
        "p_value": round(float(r1_spearman_p), 4),
        "significant": float(r1_spearman_p) < 0.05 if not np.isnan(r1_spearman_p) else False,
        "finding": f"Spearman ρ={r1_spearman_r:.3f}" if not np.isnan(r1_spearman_r) else "N/A",
    },
    {
        "rule_id": "R2", "rule_name": "故障类型→成本损失",
        "method": "Kruskal-Wallis", "statistic": round(r2_kruskal_stat, 2),
        "p_value": round(r2_kruskal_p, 4), "significant": r2_kruskal_p < 0.05,
        "finding": f"High-Voltage组日均产值${fault_cost[fault_cost['fault_group']=='High-Voltage']['avg_daily_value'].values[0]:,.0f}" if "High-Voltage" in fault_cost["fault_group"].values else "N/A",
    },
    {
        "rule_id": "R3", "rule_name": "参数异常→产品缺陷率",
        "method": "Pearson + Spearman", "statistic": round(float(r3_r), 3) if not np.isnan(r3_r) else float('nan'),
        "p_value": round(float(r3_p), 4) if not np.isnan(r3_p) else float('nan'),
        "significant": float(r3_p) < 0.05 if not np.isnan(r3_p) else False,
        "finding": f"Spearman ρ={r3_spearman_r:.3f}" if not np.isnan(r3_spearman_r) else "N/A",
    },
    {
        "rule_id": "R4", "rule_name": "维护周期→故障概率",
        "method": "Pearson r", "statistic": round(float(r4_r), 3) if not np.isnan(r4_r) else float('nan'),
        "p_value": round(float(r4_p), 4) if not np.isnan(r4_p) else float('nan'),
        "significant": float(r4_p) < 0.05 if not np.isnan(r4_p) else False,
        "finding": f"r={r4_r:.3f}" if not np.isnan(r4_r) else "N/A",
    },
])
rules_summary.to_csv(OUT_DIR / "association_rules_summary.csv", index=False, encoding="utf-8")

print(f"\nOutputs:")
print(f"  cross_table_metrics.csv — {len(out_df)} rows")
print(f"  association_rules_summary.csv — {len(rules_summary)} rows")
print(f"  6 figures in {OUT_DIR.resolve()}/")
print(f"\nDone.")
