#!/usr/bin/env python3
"""
Nature-style polished figures for Predictive Maintenance baseline analysis.
Audited against nature-figure skill standards:
  - SVG + PDF + TIFF exports with editable text
  - Frame-off legends per Nature convention
  - n-annotations + source-data traceability in every figure
  - Balanced luminance palette, low-saturation family for multi-class
"""

import os
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import seaborn as sns

# ============================================================================
# Nature-journal rcParams (per nature-figure skill)
# ============================================================================

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",         # editable text in SVG
    "pdf.fonttype": 42,             # editable TrueType in PDF
    "font.size": 7,
    "axes.titlesize": 8,
    "axes.labelsize": 7,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6.5,
    "figure.dpi": 300,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.4,
    "ytick.major.width": 0.4,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "lines.linewidth": 0.9,
    "grid.linewidth": 0.25,
    "grid.alpha": 0.25,
})

# Low-saturation palette: one neutral family + one signal family + accent
C = {
    "blue":    "#517E9C",   # muted steel blue
    "red":     "#C2685A",   # muted brick red
    "green":   "#5F8B6F",   # muted sage
    "orange":  "#C8945F",   # muted amber
    "gray":    "#7A7A7A",
    "cluster": ["#517E9C", "#5F8B6F", "#C2685A"],
}

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_outputs")

# ============================================================================
# Export helper
# ============================================================================

def save_pub(fig, stem):
    """Save figure as SVG, PDF, and TIFF with editable text."""
    fig.savefig(f"{stem}.svg", bbox_inches="tight")
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(f"{stem}.tiff", dpi=600, bbox_inches="tight", pil_kwargs={"compression": "tiff_lzw"})
    print(f"  [OK] {stem}.svg + .pdf + .tiff")


# ============================================================================
# Data
# ============================================================================

def load():
    data = {}
    for key, fname in [
        ("df_z", "z_scores.csv"),
        ("var_decomp", "variance_decomposition.csv"),
        ("cost_risk", "cost_risk_matrix.csv"),
        ("sig_df", "failure_signatures.csv"),
        ("clusters", "machine_clusters.csv"),
        ("t2_df", "hotelling_t2.csv"),
    ]:
        data[key] = pd.read_csv(os.path.join(OUT, fname))
    return data


# ============================================================================
# Fig A — Variance Decomposition (replaces Fig 1)
# ============================================================================

def figA_variance(data):
    """
    Claim: Inter-machine variance dominates (61-73%), therefore per-machine
           baselines are mandatory and global thresholds are invalid.
    Evidence: Variance decomposition on 832 normal observations × 100 machines.
    """
    df = data["var_decomp"]
    params = [s.replace(" (V)", "").replace(" (A)", "").replace(" (°C)", "")
              for s in df["parameter"]]
    inter = df["inter_pct"].values
    intra = df["intra_pct"].values

    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    x = np.arange(len(params))
    w = 0.32

    b1 = ax.bar(x - w/2, inter, w, color=C["green"], edgecolor="white", lw=0.3,
                label="Inter-machine")
    b2 = ax.bar(x + w/2, intra, w, color=C["orange"], edgecolor="white", lw=0.3,
                label="Intra-machine")

    for bar, val in zip(b1, inter):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.3,
                f"{val:.0f}%", ha="center", fontsize=6, fontweight="bold", color=C["green"])
    for bar, val in zip(b2, intra):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.3,
                f"{val:.0f}%", ha="center", fontsize=6, color=C["orange"])

    ax.set_ylabel("Variance proportion (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(params)
    ax.set_ylim(0, 82)
    ax.legend(frameon=False, loc="upper right", handlelength=1.0)

    ax.text(0.01, 0.96,
            "Inter-machine variance dominates (61–73%).\n"
            "Per-machine baselines are required.",
            transform=ax.transAxes, fontsize=5.8, va="top",
            bbox=dict(boxstyle="round,pad=0.35", fc="0.97", ec="0.8", lw=0.3))

    # Source data note
    ax.text(1.0, -0.12, "n = 832 normal observations, 100 machines",
            transform=ax.transAxes, fontsize=5.2, ha="right", color="0.5")

    ax.set_title("Variance decomposition by parameter", fontweight="bold", loc="left", pad=10)
    save_pub(fig, os.path.join(OUT, "figA_variance_decomposition"))


# ============================================================================
# Fig B — Z-Score Threshold Performance (replaces Fig 3)
# ============================================================================

def figB_thresholds(data):
    """
    Claim: z > 2.0 balances precision (84%) and acceptable FPR (20%) for
           operational predictive maintenance dispatch.
    Evidence: 2,999 observations × 100 machines, composite z = sqrt(z_V^2+z_A^2+z_T^2).
    """
    df_z = data["df_z"]
    y_true = (df_z["Failure.Equipment.Type"] > 0).astype(int)

    thresholds = np.linspace(0.4, 4.0, 37)
    m = {"threshold": [], "precision": [], "recall": [], "f1": [], "fpr": []}
    for t in thresholds:
        y_pred = (df_z["z_composite"] > t).astype(int)
        tp = ((y_true == 1) & (y_pred == 1)).sum()
        fp = ((y_true == 0) & (y_pred == 1)).sum()
        fn = ((y_true == 1) & (y_pred == 0)).sum()
        tn = ((y_true == 0) & (y_pred == 0)).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0
        m["threshold"].append(t)
        m["precision"].append(prec * 100)
        m["recall"].append(rec * 100)
        m["fpr"].append(fp / (fp + tn) * 100 if (fp + tn) > 0 else 0)
        m["f1"].append(2 * prec * rec / (prec + rec) * 100 if (prec + rec) > 0 else 0)
    m = pd.DataFrame(m)

    fig, ax = plt.subplots(figsize=(5.0, 3.2))

    ax.plot(m["threshold"], m["precision"], "o-", color=C["blue"], ms=2.5, lw=1.0, label="Precision")
    ax.plot(m["threshold"], m["recall"],    "s-", color=C["green"], ms=2.5, lw=1.0, label="Recall")
    ax.plot(m["threshold"], m["f1"],        "D-", color=C["red"],   ms=2.5, lw=1.2, label="F1 score")
    ax.plot(m["threshold"], m["fpr"],       "^-", color=C["gray"],  ms=2.5, lw=0.8, label="FPR", alpha=0.6)

    # Operational zones
    for t_val, label, ls in [(1.5, "Watch", (0, (4, 2))), (2.0, "Warning", (0, (3, 1, 1, 1))), (2.5, "Alarm", (0, (1, 2)))]:
        ax.axvline(t_val, color="0.5", linestyle=ls, lw=0.55, alpha=0.6)
        ax.text(t_val + 0.04, 96, label, fontsize=5.5, rotation=90, va="top", color="0.4")

    # Callout box: best operating point
    best_row = m.loc[m["f1"].idxmax()]
    ax.annotate(f"z={best_row['threshold']:.1f}\nP={best_row['precision']:.0f}% R={best_row['recall']:.0f}%",
                xy=(best_row["threshold"], best_row["f1"]),
                xytext=(best_row["threshold"] + 0.8, best_row["f1"] - 8),
                fontsize=5.5, ha="center",
                arrowprops=dict(arrowstyle="->", color="0.4", lw=0.5),
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7", lw=0.3))

    ax.set_xlabel("Composite Z-score threshold")
    ax.set_ylabel("Percentage (%)")
    ax.set_xlim(0.3, 4.1)
    ax.set_ylim(-2, 104)
    ax.legend(frameon=False, loc="center right", handlelength=1.2, ncol=1)

    ax.text(1.0, -0.16, "n = 2,999 observations, 100 machines  |  composite z = (z_V^2+z_A^2+z_T^2)^{1/2}",
            transform=ax.transAxes, fontsize=5.2, ha="right", color="0.5")

    ax.set_title("Baseline detection performance vs. threshold", fontweight="bold", loc="left", pad=10)
    save_pub(fig, os.path.join(OUT, "figB_threshold_performance"))


# ============================================================================
# Fig C — Z-Score Distribution Normal vs Failure (replaces Fig 7)
# ============================================================================

def figC_distributions(data):
    """
    Claim: Normal and failure distributions overlap heavily below z < 2.0;
           ~22% of failures are indistinguishable by static parameter deviation
           alone, requiring temporal or pattern features.
    Evidence: 832 normal vs 2,167 failure observations, composite z-score.
    """
    df_z = data["df_z"]
    normal_z  = df_z[df_z["Failure.Equipment.Type"] == 0]["z_composite"].values
    failure_z = df_z[df_z["Failure.Equipment.Type"] > 0]["z_composite"].values

    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    bins = np.linspace(0, 8, 45)

    ax.hist(normal_z, bins=bins, alpha=0.55, color=C["blue"], edgecolor="white", lw=0.2,
            density=True, label=f"Normal  (n={len(normal_z)})")
    ax.hist(failure_z, bins=bins, alpha=0.45, color=C["red"], edgecolor="white", lw=0.2,
            density=True, label=f"Failure (n={len(failure_z)})")

    # Medians as rug
    for arr, color, y in [(normal_z, C["blue"], 0.03), (failure_z, C["red"], 0.07)]:
        med = np.median(arr)
        ax.axvline(med, color=color, lw=1.2, ls="--", alpha=0.7)
        ax.text(med + 0.12, ax.get_ylim()[1] * 0.78, f"med={med:.2f}",
                fontsize=5.8, color=color, fontweight="bold")

    # Thresholds
    for t_val, label, ls in [(1.5, "Watch", (0, (4, 2))), (2.0, "Warn", (0, (3, 1, 1, 1))), (2.5, "Alarm", (0, (1, 2)))]:
        ax.axvline(t_val, color="0.45", linestyle=ls, lw=0.55, alpha=0.55)
        ax.text(t_val + 0.06, ax.get_ylim()[1] * 0.92, label, fontsize=5.5,
                rotation=90, va="top", color="0.4")

    # Failure rate in alarm zone
    alarm_fail = (failure_z > 2.5).sum() / len(failure_z) * 100
    ax.text(3.2, ax.get_ylim()[1] * 0.55,
            f"Only {alarm_fail:.0f}% of failures\nexceed Alarm threshold",
            fontsize=5.8, ha="center",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.7", lw=0.3))

    ax.set_xlabel("Composite Z-score")
    ax.set_ylabel("Density")
    ax.legend(frameon=False, loc="upper right", handlelength=1.0)

    ax.text(1.0, -0.16,
            "832 normal + 2,167 failure observations, 100 machines  |  composite z = (z_V^2+z_A^2+z_T^2)^{1/2}",
            transform=ax.transAxes, fontsize=5.2, ha="right", color="0.5")

    ax.set_title("Composite Z-score: normal vs failure distributions", fontweight="bold", loc="left", pad=10)
    save_pub(fig, os.path.join(OUT, "figC_zscore_distributions"))


# ============================================================================
# Fig D — Multi-panel composite: Clusters + Failure Signatures (new)
# ============================================================================

def figD_clusters_and_signatures(data):
    """
    Claim: Machines group into 3 operating regimes; failure types have distinct
           parameter-deviation signatures enabling stratified alert thresholds.
    Evidence: K-means (K=3) on normal-operation profiles; per-type delta from normal mean.
    """
    # Panel map: left = clusters, right = failure signatures
    fig = plt.figure(figsize=(7.5, 3.2))

    # --- Panel D1: Machine clusters ---
    ax1 = fig.add_subplot(1, 2, 1)
    cl = data["clusters"]
    df_z = data["df_z"]
    normal = df_z[df_z["Failure.Equipment.Type"] == 0]
    profiles = normal.groupby("Equipment.Id").agg(
        v_mean=("Op.Voltage", "mean"), t_mean=("Op.Temperature", "mean")
    ).reset_index()
    profiles = profiles.merge(cl[["Equipment.Id", "cluster"]], on="Equipment.Id")

    markers = ["o", "s", "D"]
    cnames = {0: "Medium-V, High-A", 1: "High-V, Low-A", 2: "Low-V, High-T"}
    for cid in sorted(profiles["cluster"].unique()):
        cd = profiles[profiles["cluster"] == cid]
        n = len(cd)
        ax1.scatter(cd["v_mean"], cd["t_mean"], marker=markers[cid], s=28,
                    c=C["cluster"][cid], edgecolors="white", lw=0.25, alpha=0.82,
                    label=f"{cnames[cid]} (n={n})")

    ax1.set_xlabel("Mean normal Voltage (V)")
    ax1.set_ylabel("Mean normal Temperature (°C)")
    ax1.legend(frameon=False, fontsize=5.5, handlelength=0.8, markerscale=0.7)
    ax1.set_title("Machine operating clusters (K=3)", fontweight="bold", loc="left",
                  fontsize=7.5, pad=8)

    # --- Panel D2: Failure signatures ---
    ax2 = fig.add_subplot(1, 2, 2)
    sig = data["sig_df"]
    param_cols = ["Op.Voltage_delta", "Op.Amperage_delta", "Op.Temperature_delta"]
    matrix = sig[param_cols].values
    row_labels = [f"T{int(t)}" if t > 0 else "N" for t in sig["failure_type"]]

    vmax = max(abs(matrix.min()), abs(matrix.max()))
    im = ax2.imshow(matrix.T, cmap="RdBu_r", aspect="auto", vmin=-vmax, vmax=vmax)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            fc = "white" if abs(val) > vmax * 0.55 else "black"
            ax2.text(i, j, f"{val:+.1f}", ha="center", va="center", fontsize=5.8,
                     fontweight="bold" if abs(val) > 4 else "normal", color=fc)

    ax2.set_xticks(range(len(row_labels)))
    ax2.set_xticklabels(row_labels, fontsize=5.8)
    ax2.set_yticks([0, 1, 2])
    ax2.set_yticklabels(["Voltage", "Amperage", "Temperature"], fontsize=6)
    ax2.set_xlabel("Failure type")

    # Group color strip below xticks
    gcolors = {"Normal": "#BBBBBB", "Subtle": C["blue"], "Thermal": C["orange"],
               "High-Voltage": C["red"]}
    for i, gl in enumerate(sig["failure_group"]):
        ax2.add_patch(plt.Rectangle((i - 0.46, -0.85), 0.92, 0.18,
                                    fc=gcolors.get(gl, "#888888"),
                                    ec="white", lw=0.2, clip_on=False))

    cbar = plt.colorbar(im, ax=ax2, shrink=0.82, pad=0.02)
    cbar.set_label("Delta from normal", fontsize=6)
    cbar.ax.tick_params(labelsize=5.5)
    ax2.set_title("Failure-type deviation signatures", fontweight="bold", loc="left",
                  fontsize=7.5, pad=8)

    # Shared source line
    fig.text(0.98, 0.01, "n = 832 normal obs, 100 machines, 10 failure types (0–9)",
             fontsize=5.2, ha="right", color="0.5")

    fig.suptitle("", fontsize=1)  # spacer
    save_pub(fig, os.path.join(OUT, "figD_clusters_signatures"))


# ============================================================================
# Fig E — Cost-Weighted Risk Bubble (replaces Fig 6)
# ============================================================================

def figE_cost_risk(data):
    """
    Claim: Priority maintenance ranking must combine failure rate, unit cost,
           and daily output volume. CNC_095 (extreme unit cost) and CNC_036
           (high cost + high failure) are the top intervention targets.
    Evidence: 100 machines with cost/output metadata merged with observed failure rates.
    """
    cr = data["cost_risk"].copy()
    size = cr["cost_at_risk"].values
    size_n = 18 + (size - size.min()) / (size.max() - size.min()) * 160

    tier_color = {"High": C["red"], "Medium": C["orange"], "Low": C["green"]}
    colors = [tier_color[t] for t in cr["risk_tier"]]

    fig, ax = plt.subplots(figsize=(5.8, 3.8))

    ax.scatter(cr["failure_rate"], cr["Unit Cost of Production"],
               s=size_n, c=colors, alpha=0.65, edgecolors="white", lw=0.3, zorder=3)

    # Label top-6
    for _, row in cr.head(6).iterrows():
        dx, dy = (5, 3)
        if row["Equipment.Id"] == "CNC_095":
            dy = -6
        ax.annotate(row["Equipment.Id"],
                    (row["failure_rate"], row["Unit Cost of Production"]),
                    textcoords="offset points", xytext=(dx, dy),
                    fontsize=5.3, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color="0.4", lw=0.35))

    # Tier legend
    for label, color in [("High risk", C["red"]), ("Medium risk", C["orange"]), ("Low risk", C["green"])]:
        ax.scatter([], [], s=40, c=color, edgecolors="white", lw=0.3, label=label)
    ax.legend(frameon=False, loc="upper right", fontsize=6, handlelength=0.6,
              title="Risk tier", title_fontsize=6.5)

    ax.set_xlabel("Machine failure rate (%)")
    ax.set_ylabel("Unit cost of production")
    ax.set_title("Cost-weighted risk: failure rate × unit cost × daily output",
                 fontweight="bold", loc="left", pad=10)

    ax.text(0.01, 0.96,
            "Risk = P(failure) × unit_cost × daily_output.\n"
            "Bubble size encodes cost-at-risk magnitude.",
            transform=ax.transAxes, fontsize=5.5, va="top",
            bbox=dict(boxstyle="round,pad=0.3", fc="0.97", ec="0.8", lw=0.3))

    ax.text(1.0, -0.14, "100 machines | source: MACHINE_SUMMARY + MACHINE_LOG merged",
            transform=ax.transAxes, fontsize=5.2, ha="right", color="0.5")

    save_pub(fig, os.path.join(OUT, "figE_cost_risk_bubble"))


# ============================================================================
# Fig F — Per-Machine Baseline Ranges (replaces Fig 2)
# ============================================================================

def figF_machine_ranges(data):
    """
    Claim: Voltage operating setpoints vary by >130V across machines,
           proving that global thresholds cannot work for anomaly detection.
    Evidence: 15 representative machines sorted by voltage mean, normal-state only.
    """
    df_z = data["df_z"]
    normal = df_z[df_z["Failure.Equipment.Type"] == 0]
    stats = normal.groupby("Equipment.Id").agg(
        n=("Op.Voltage", "count"), v_mean=("Op.Voltage", "mean"), v_std=("Op.Voltage", "std")
    ).reset_index()
    selected = stats.nlargest(15, "n").sort_values("v_mean")

    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    ys = range(len(selected))

    for i, (_, r) in enumerate(selected.iterrows()):
        mu, sg = r["v_mean"], r["v_std"]
        cv_flag = sg / mu >= 0.15
        color = C["red"] if cv_flag else C["blue"]
        ax.errorbar(mu, i, xerr=2 * sg, fmt="o", color=color,
                    capsize=2.5, capthick=0.6, ms=4.5, elinewidth=0.9,
                    markeredgecolor="white", markeredgewidth=0.3)
        ax.text(mu + 2 * sg + 4, i, f"[{mu-2*sg:.0f}, {mu+2*sg:.0f}]",
                fontsize=5, va="center", color="0.45")

    ax.set_yticks(list(ys))
    ax.set_yticklabels(selected["Equipment.Id"].values, fontsize=5.8)
    ax.set_xlabel("Voltage (V)")

    # Legend
    ax.scatter([], [], marker="o", c=C["blue"], edgecolors="white", lw=0.3,
               s=30, label="CV < 15% (stable)")
    ax.scatter([], [], marker="o", c=C["red"], edgecolors="white", lw=0.3,
               s=30, label="CV >= 15% (high variance)")
    ax.legend(frameon=False, loc="lower right", fontsize=6, handlelength=0.6)

    ax.text(0.01, 0.97,
            "Voltage setpoints span >130V. Global threshold cannot\ndiscriminate failure across all machines simultaneously.",
            transform=ax.transAxes, fontsize=5.5, va="top",
            bbox=dict(boxstyle="round,pad=0.3", fc="0.97", ec="0.8", lw=0.3))

    ax.text(1.0, -0.10, "Normal-state only (Type 0), 15 representative machines of 100  |  μ ± 2σ",
            transform=ax.transAxes, fontsize=5.2, ha="right", color="0.5")

    ax.set_title("Per-machine normal Voltage operating ranges", fontweight="bold", loc="left", pad=10)
    save_pub(fig, os.path.join(OUT, "figF_machine_baseline_ranges"))


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 55)
    print("  Nature-style Figure Suite (audited)")
    print("=" * 55)
    data = load()
    figA_variance(data)
    figB_thresholds(data)
    figC_distributions(data)
    figD_clusters_and_signatures(data)
    figE_cost_risk(data)
    figF_machine_ranges(data)
    print(f"\n  Done → {OUT}")


if __name__ == "__main__":
    main()
