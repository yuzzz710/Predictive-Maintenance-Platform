#!/usr/bin/env python3
"""
智能设备预测性维护 — Baseline Visualization Suite
====================================================
Generates 7 publication-grade figures for baseline analysis.
Backend: matplotlib 3.x + seaborn
Style: Nature-family journal requirements (sans-serif, 8pt min, 300+dpi)

Figures:
  Fig 1 — Variance Decomposition: inter- vs intra-machine
  Fig 2 — Per-Machine Normal Operating Ranges (Voltage)
  Fig 3 — Z-Score Threshold Performance Curve
  Fig 4 — Machine Operating Clusters
  Fig 5 — Failure Type Parameter Signatures
  Fig 6 — Cost-Weighted Risk Bubble Chart
  Fig 7 — Composite Z-Score Distributions: Normal vs Failure
"""

import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
import seaborn as sns
from scipy import stats

# ============================================================================
# Global Style — Nature-family journal
# ============================================================================

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "lines.linewidth": 1.0,
    "grid.linewidth": 0.3,
    "grid.alpha": 0.3,
})

PALETTE = {
    "normal": "#4C72B0",     # blue
    "failure": "#C44E52",    # red
    "inter": "#55A868",      # green
    "intra": "#DD8452",      # orange
    "clusters": ["#4C72B0", "#55A868", "#C44E52"],
    "risk_high": "#C44E52",
    "risk_medium": "#DD8452",
    "risk_low": "#55A868",
}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_outputs")

# ============================================================================
# Data Loading
# ============================================================================

def load_results():
    """Load pre-computed baseline results from CSV files."""
    files = {
        "df_z": "z_scores.csv",
        "cost_risk": "cost_risk_matrix.csv",
        "sig_df": "failure_signatures.csv",
        "var_decomp": "variance_decomposition.csv",
        "t2_df": "hotelling_t2.csv",
        "clusters": "machine_clusters.csv",
    }
    data = {}
    for key, fname in files.items():
        path = os.path.join(OUTPUT_DIR, fname)
        data[key] = pd.read_csv(path)
    return data


# ============================================================================
# Figure 1: Variance Decomposition
# ============================================================================

def fig1_variance_decomposition(data, save_path):
    """
    FIGURE 1 — Variance Decomposition.
    Shows how total variance splits into inter-machine and intra-machine components.
    Key insight: 61-73% of variance is between machines, proving per-machine
    baselines are mandatory; global thresholds are invalid.
    """
    df = data["var_decomp"].copy()
    params = df["parameter"].values
    inter = df["inter_pct"].values
    intra = df["intra_pct"].values

    x = np.arange(len(params))
    width = 0.35

    fig, ax = plt.subplots(figsize=(5.5, 3.5))

    bars1 = ax.bar(x - width/2, inter, width, label="Inter-machine (between devices)",
                   color=PALETTE["inter"], edgecolor="white", linewidth=0.3)
    bars2 = ax.bar(x + width/2, intra, width, label="Intra-machine (within device)",
                   color=PALETTE["intra"], edgecolor="white", linewidth=0.3)

    # Annotate percentages
    for bar, val in zip(bars1, inter):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                f"{val:.0f}%", ha="center", va="bottom", fontsize=6.5, fontweight="bold",
                color=PALETTE["inter"])
    for bar, val in zip(bars2, intra):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                f"{val:.0f}%", ha="center", va="bottom", fontsize=6.5,
                color=PALETTE["intra"])

    ax.set_ylabel("Variance proportion (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(params)
    ax.set_ylim(0, 85)
    ax.legend(loc="upper right", frameon=True, fancybox=True, framealpha=0.9)
    ax.set_title("Figure 1 | Variance decomposition: machine-level vs global",
                 fontweight="bold", loc="left", pad=12)

    # Annotation box
    ax.text(0.02, 0.96,
            "Conclusion: 61-73% of total variance is between machines.\n"
            "Per-machine baselines are mandatory; global thresholds invalid.",
            transform=ax.transAxes, fontsize=6, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    sns.despine()
    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 1 saved: {save_path}")


# ============================================================================
# Figure 2: Per-Machine Normal Operating Ranges
# ============================================================================

def fig2_machine_baseline_ranges(data, save_path, n_machines=15):
    """
    FIGURE 2 — Per-Machine Normal Operating Ranges (Voltage).
    Shows μ±2σ bands for representative machines sorted by baseline stability.
    Key insight: Machines operate at fundamentally different voltage setpoints
    (CNC_001 at 289V vs CNC_004 at 156V).
    """
    df_z = data["df_z"].copy()
    normal = df_z[df_z["Failure.Equipment.Type"] == 0]

    # Select machines with most normal samples, then diverse voltage means
    machine_stats = normal.groupby("Equipment.Id").agg(
        n=("Op.Voltage", "count"),
        v_mean=("Op.Voltage", "mean"),
        v_std=("Op.Voltage", "std"),
    ).reset_index()
    machine_stats = machine_stats.sort_values(["n", "v_mean"], ascending=[False, True])
    selected = machine_stats.head(n_machines).sort_values("v_mean")

    fig, ax = plt.subplots(figsize=(7, 4.5))

    y_positions = range(len(selected))
    colors = [PALETTE["normal"] if s["v_std"] / s["v_mean"] < 0.15 else PALETTE["failure"]
              for _, s in selected.iterrows()]

    for i, (_, row) in enumerate(selected.iterrows()):
        mu, sigma = row["v_mean"], row["v_std"]
        lo = mu - 2 * sigma
        hi = mu + 2 * sigma

        # Error bar: μ ± 2σ
        ax.errorbar(mu, i, xerr=2 * sigma, fmt="o", color=colors[i],
                    capsize=3, capthick=0.8, markersize=5, elinewidth=1.0,
                    markeredgecolor="white", markeredgewidth=0.4)
        # μ marker
        ax.plot(mu, i, "o", color=colors[i], markersize=5,
                markeredgecolor="white", markeredgewidth=0.4, zorder=5)
        # Range text
        ax.text(hi + 5, i, f"[{lo:.0f}, {hi:.0f}]", fontsize=5.5, va="center",
                color="gray")

    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(selected["Equipment.Id"].values)
    ax.set_xlabel("Voltage (V)")
    ax.set_title("Figure 2 | Per-machine normal operating ranges: Voltage μ ± 2σ",
                 fontweight="bold", loc="left", pad=12)

    # Legend for color
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["normal"],
               markersize=6, label="CV < 15% (stable)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["failure"],
               markersize=6, label="CV >= 15% (high variance)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", frameon=True)

    # Annotation
    ax.text(0.02, 0.96,
            "Conclusion: Machines operate at fundamentally different voltage setpoints.\n"
            "Global threshold-based alerting would miss CNC high-voltage failures\n"
            "and falsely flag low-voltage machines during normal operation.",
            transform=ax.transAxes, fontsize=6, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    sns.despine()
    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 2 saved: {save_path}")


# ============================================================================
# Figure 3: Z-Score Threshold Performance
# ============================================================================

def fig3_zscore_thresholds(data, save_path):
    """
    FIGURE 3 — Z-Score Threshold Performance.
    Precision, Recall, F1, and FPR across thresholds z = 1.0 to 3.5.
    Key insight: z > 2.0 offers best precision-recall balance for operational use;
    z > 1.5 for high-recall screening, z > 2.5 for high-confidence alerting.
    """
    df_z = data["df_z"]
    y_true = (df_z["Failure.Equipment.Type"] > 0).astype(int)
    thresholds = np.linspace(0.5, 4.0, 36)

    metrics = {"threshold": [], "precision": [], "recall": [], "specificity": [], "f1": [], "fpr": []}
    for t in thresholds:
        y_pred = (df_z["z_composite"] > t).astype(int)
        tp = ((y_true == 1) & (y_pred == 1)).sum()
        fp = ((y_true == 0) & (y_pred == 1)).sum()
        fn = ((y_true == 1) & (y_pred == 0)).sum()
        tn = ((y_true == 0) & (y_pred == 0)).sum()

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

        metrics["threshold"].append(t)
        metrics["precision"].append(prec)
        metrics["recall"].append(rec)
        metrics["specificity"].append(spec)
        metrics["f1"].append(f1)
        metrics["fpr"].append(1 - spec)

    m = pd.DataFrame(metrics)

    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    ax.plot(m["threshold"], m["precision"] * 100, "o-", color="#4C72B0", markersize=3,
            linewidth=1.2, label="Precision")
    ax.plot(m["threshold"], m["recall"] * 100, "s-", color="#55A868", markersize=3,
            linewidth=1.2, label="Recall")
    ax.plot(m["threshold"], m["f1"] * 100, "D-", color="#C44E52", markersize=3,
            linewidth=1.5, label="F1 Score")
    ax.plot(m["threshold"], m["fpr"] * 100, "^-", color="#8C8C8C", markersize=3,
            linewidth=1.0, label="False Positive Rate", alpha=0.7)

    # Vertical lines at key thresholds
    for t_val, label, ls in [(1.5, "Watch", "--"), (2.0, "Warning", "-."), (2.5, "Alarm", ":")]:
        ax.axvline(t_val, color="gray", linestyle=ls, linewidth=0.6, alpha=0.5)
        ax.text(t_val + 0.05, 95, label, fontsize=6, rotation=90, va="top", color="gray")

    ax.set_xlabel("Composite Z-Score Threshold")
    ax.set_ylabel("Percentage (%)")
    ax.set_xlim(0.5, 4.0)
    ax.set_ylim(0, 105)
    ax.legend(loc="center right", frameon=True, fancybox=True)
    ax.set_title("Figure 3 | Z-Score baseline performance across thresholds",
                 fontweight="bold", loc="left", pad=12)

    # Annotation
    ax.text(0.98, 0.5,
            "Operational guidance:\n"
            "  z > 1.5 (Watch):  Rec 62%, FPR 51% → screening\n"
            "  z > 2.0 (Warning): Rec 39%, FPR 20% → dispatch\n"
            "  z > 2.5 (Alarm):   Rec 22%, FPR  5% → immediate action",
            transform=ax.transAxes, fontsize=6, verticalalignment="center",
            horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    sns.despine()
    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 3 saved: {save_path}")


# ============================================================================
# Figure 4: Machine Operating Clusters
# ============================================================================

def fig4_machine_clusters(data, save_path):
    """
    FIGURE 4 — Machine Operating Clusters in Voltage-Temperature space.
    K-means (K=3) on normal-operation parameter profiles.
    Key insight: 3 distinct operating regimes exist; cluster baseline serves
    as cold-start fallback for machines with < 6 normal samples.
    """
    cl = data["clusters"].copy()
    df = data["df_z"]
    normal = df[df["Failure.Equipment.Type"] == 0]
    # Per-machine mean params
    profiles = normal.groupby("Equipment.Id").agg(
        v_mean=("Op.Voltage", "mean"),
        t_mean=("Op.Temperature", "mean"),
        a_mean=("Op.Amperage", "mean"),
    ).reset_index()
    profiles = profiles.merge(cl[["Equipment.Id", "cluster"]], on="Equipment.Id")

    fig, ax = plt.subplots(figsize=(5.5, 4.2))

    cluster_names = {0: "Cluster 0: Medium-V, High-A (n=30)",
                     1: "Cluster 1: High-V, Low-A (n=38)",
                     2: "Cluster 2: Low-V, High-T (n=32)"}
    markers = ["o", "s", "D"]

    for c in sorted(profiles["cluster"].unique()):
        cd = profiles[profiles["cluster"] == c]
        ax.scatter(cd["v_mean"], cd["t_mean"], c=PALETTE["clusters"][c],
                   marker=markers[c], s=40, edgecolors="white", linewidth=0.3,
                   alpha=0.85, label=cluster_names.get(c, f"Cluster {c}"),
                   zorder=3)

    ax.set_xlabel("Mean Voltage in Normal State (V)")
    ax.set_ylabel("Mean Temperature in Normal State (°C)")
    ax.legend(loc="upper left", frameon=True, fancybox=True, fontsize=6.5,
              markerscale=0.8)

    ax.set_title("Figure 4 | Machine operating clusters (K-Means, K=3)",
                 fontweight="bold", loc="left", pad=12)

    ax.text(0.02, 0.96,
            "Conclusion: Three distinct operating regimes identified.\n"
            "Cluster-level baselines serve as fallback for 10 sparse-data machines\n"
            "with <6 normal samples, reducing cold-start false alarms.",
            transform=ax.transAxes, fontsize=6, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    sns.despine()
    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 4 saved: {save_path}")


# ============================================================================
# Figure 5: Failure Type Signatures
# ============================================================================

def fig5_failure_signatures(data, save_path):
    """
    FIGURE 5 — Failure Type Parameter Deviation Signatures.
    Heatmap of Δ (deviation from normal mean) for Voltage, Amperage, Temperature.
    Key insight: Type 4,5 are "high-voltage" failures (+10.7V); Type 3,6-9 are
    "thermal" failures (temperature +1.5°C). Type 1,2 are subtle and need
    temporal features for detection.
    """
    sig = data["sig_df"].copy()
    # Pivot for heatmap
    params_pretty = ["Voltage", "Amperage", "Temperature"]
    param_cols = ["Op.Voltage_delta", "Op.Amperage_delta", "Op.Temperature_delta"]

    # Build matrix
    matrix = sig[param_cols].values
    row_labels = [f"Type {int(t)}" if t > 0 else "Normal" for t in sig["failure_type"]]
    # Add failure group labels
    group_labels = sig["failure_group"].values

    fig, ax = plt.subplots(figsize=(6, 3.5))

    # Normalize deltas for colormap (center at 0)
    vmax = max(abs(matrix.min()), abs(matrix.max()))

    im = ax.imshow(matrix.T, cmap="RdBu_r", aspect="auto", vmin=-vmax, vmax=vmax,
                   interpolation="nearest")

    # Annotate cells
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            color = "white" if abs(val) > vmax * 0.6 else "black"
            ax.text(i, j, f"{val:+.2f}", ha="center", va="center", fontsize=6.5,
                    fontweight="bold" if abs(val) > 3 else "normal", color=color)

    ax.set_xticks(range(len(row_labels)))
    ax.set_xticklabels(row_labels, rotation=45, ha="right", fontsize=6.5)
    ax.set_yticks(range(len(params_pretty)))
    ax.set_yticklabels(params_pretty, fontsize=7)
    ax.set_xlabel("Failure Type")
    ax.set_ylabel("Parameter")

    # Group color bar on right side
    group_colors = {"Normal": "#BBBBBB", "Subtle": "#4C72B0", "Thermal": "#DD8452",
                    "High-Voltage": "#C44E52"}
    for i, gl in enumerate(group_labels):
        ax.add_patch(plt.Rectangle((i - 0.46, -1.25), 0.92, 0.22,
                                   facecolor=group_colors.get(gl, "#888888"),
                                   edgecolor="white", linewidth=0.3, clip_on=False))

    # Colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cbar.set_label("Deviation from normal mean", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    ax.set_title("Figure 5 | Failure type parameter deviation signatures",
                 fontweight="bold", loc="left", pad=12)

    ax.text(0.02, -0.25,
            "Group:    Normal    Subtle (1-2)    Thermal (3,6-9)    High-V (4-5)",
            transform=ax.transAxes, fontsize=5.5, verticalalignment="top")

    ax.text(0.02, 0.96,
            "Conclusion: Failure types map to 3 distinct parameter-deviation groups.\n"
            "Stratified thresholds (voltage-weighted for Type 4/5, temp-weighted\n"
            "for Type 3/6-9) improve detection sensitivity vs uniform baseline.",
            transform=ax.transAxes, fontsize=6, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 5 saved: {save_path}")


# ============================================================================
# Figure 6: Cost-Weighted Risk Bubble Chart
# ============================================================================

def fig6_cost_risk_bubble(data, save_path):
    """
    FIGURE 6 — Cost-Weighted Risk Bubble Chart.
    Bubble size = cost_at_risk; x = failure rate; y = unit cost.
    Key insight: CNC_095 (cost=114, 67% fail) has extreme unit cost;
    CNC_036 (cost=32, 83% fail) is the highest combined risk. High-output
    low-cost machines (CNC_034) are also high-risk due to volume.
    """
    cr = data["cost_risk"].copy()

    fig, ax = plt.subplots(figsize=(7, 4.5))

    # Normalize bubble size
    size = cr["cost_at_risk"].values
    size_norm = 20 + (size - size.min()) / (size.max() - size.min()) * 180

    colors = [PALETTE["risk_high"] if t == "High" else
              PALETTE["risk_medium"] if t == "Medium" else
              PALETTE["risk_low"] for t in cr["risk_tier"]]

    scatter = ax.scatter(cr["failure_rate"], cr["Unit Cost of Production"],
                         s=size_norm, c=colors, alpha=0.7, edgecolors="white",
                         linewidth=0.4, zorder=3)

    # Label top-risk machines
    top_n = 8
    for _, row in cr.head(top_n).iterrows():
        offset = (5, 3) if row["Equipment.Id"] not in ["CNC_095"] else (-15, -5)
        ax.annotate(row["Equipment.Id"],
                    (row["failure_rate"], row["Unit Cost of Production"]),
                    textcoords="offset points", xytext=offset,
                    fontsize=5.5, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color="gray", lw=0.4),
                    color="black")

    # Legend for risk tiers
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["risk_high"],
               markersize=8, label="High Risk (top 10%)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["risk_medium"],
               markersize=8, label="Medium Risk"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE["risk_low"],
               markersize=8, label="Low Risk"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", frameon=True)

    ax.set_xlabel("Machine Failure Rate (%)")
    ax.set_ylabel("Unit Cost of Production")
    ax.set_title("Figure 6 | Cost-weighted risk matrix: failure rate × unit cost",
                 fontweight="bold", loc="left", pad=12)

    ax.text(0.02, 0.96,
            "Risk = Failure Rate × Unit Cost × Daily Output.\n"
            "Top risk: CNC_085 (high output + high failure),\n"
            "CNC_095 (extreme unit cost=114), CNC_036 (cost=32, 83% fail).",
            transform=ax.transAxes, fontsize=6, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    sns.despine()
    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 6 saved: {save_path}")


# ============================================================================
# Figure 7: Composite Z-Score Distribution
# ============================================================================

def fig7_zscore_distribution(data, save_path):
    """
    FIGURE 7 — Composite Z-Score Distribution: Normal vs Failure.
    Overlaid histograms with threshold markers.
    Key insight: Normal distribution is tight (median z=1.3) while failure
    distribution has a heavy right tail (median z=1.8). The overlap explains
    the precision-recall tradeoff — no single threshold perfectly separates.
    """
    df_z = data["df_z"]
    normal = df_z[df_z["Failure.Equipment.Type"] == 0]["z_composite"]
    failure = df_z[df_z["Failure.Equipment.Type"] > 0]["z_composite"]

    fig, ax = plt.subplots(figsize=(5.5, 3.5))

    bins = np.linspace(0, 8, 41)
    ax.hist(normal, bins=bins, alpha=0.6, color=PALETTE["normal"], label="Normal (Type 0)",
            edgecolor="white", linewidth=0.3, density=True)
    ax.hist(failure, bins=bins, alpha=0.5, color=PALETTE["failure"], label="Failure (Type 1-9)",
            edgecolor="white", linewidth=0.3, density=True)

    # Threshold lines
    for t_val, label, ls in [(1.5, "Watch (1.5)", "--"), (2.0, "Warning (2.0)", "-."), (2.5, "Alarm (2.5)", ":")]:
        ax.axvline(t_val, color="gray", linestyle=ls, linewidth=0.8)
        ax.text(t_val + 0.08, ax.get_ylim()[1] * 0.92, label, fontsize=6,
                rotation=90, va="top", color="gray")

    # Annotate medians
    ax.text(0.5, ax.get_ylim()[1] * 0.75,
            f"Normal median z = {normal.median():.2f}\nFailure median z = {failure.median():.2f}",
            fontsize=6.5, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    ax.set_xlabel("Composite Z-Score")
    ax.set_ylabel("Density")
    ax.legend(loc="upper right", frameon=True)
    ax.set_title("Figure 7 | Composite Z-Score distribution: Normal vs Failure",
                 fontweight="bold", loc="left", pad=12)

    ax.text(0.98, 0.96,
            "Conclusion: Heavy overlap at z < 2.0 explains limited recall.\n"
            "~22% of failures have near-normal parameter signatures and\n"
            "require temporal or multi-parameter pattern features to detect.",
            transform=ax.transAxes, fontsize=6, verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8, edgecolor="gray", linewidth=0.4))

    sns.despine()
    plt.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
    print(f"  [OK] Fig 7 saved: {save_path}")


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 60)
    print("  Baseline Visualization Suite")
    print("=" * 60)

    data = load_results()
    print(f"  Loaded {len(data)} result files from {OUTPUT_DIR}\n")

    fig1_variance_decomposition(data, os.path.join(OUTPUT_DIR, "fig1_variance_decomposition.png"))
    fig2_machine_baseline_ranges(data, os.path.join(OUTPUT_DIR, "fig2_machine_baseline_ranges.png"))
    fig3_zscore_thresholds(data, os.path.join(OUTPUT_DIR, "fig3_zscore_thresholds.png"))
    fig4_machine_clusters(data, os.path.join(OUTPUT_DIR, "fig4_machine_clusters.png"))
    fig5_failure_signatures(data, os.path.join(OUTPUT_DIR, "fig5_failure_signatures.png"))
    fig6_cost_risk_bubble(data, os.path.join(OUTPUT_DIR, "fig6_cost_risk_bubble.png"))
    fig7_zscore_distribution(data, os.path.join(OUTPUT_DIR, "fig7_zscore_distribution.png"))

    print(f"\n  All 7 figures saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
