"""
Advanced machine failure analysis — Tasks 5–14
Nature-figure style plots for publication.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Ellipse, FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns
from scipy import stats as scipy_stats
from sklearn.metrics import roc_curve, auc
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# Nature-figure style
# ============================================================
def set_nature_style():
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 7, 'axes.titlesize': 8, 'axes.labelsize': 7,
        'xtick.labelsize': 6, 'ytick.labelsize': 6, 'legend.fontsize': 6,
        'figure.dpi': 300, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05, 'axes.linewidth': 0.5,
        'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
        'xtick.major.size': 2, 'ytick.major.size': 2,
        'axes.spines.top': False, 'axes.spines.right': False,
        'legend.frameon': False, 'lines.linewidth': 0.8, 'patch.linewidth': 0.5,
    })

set_nature_style()

# ============================================================
# Load & prep data
# ============================================================
df = pd.read_csv('Unified_Machine_WideTable_2025.csv')
df = df.iloc[:, :7].copy()
df.columns = ['Date', 'Equipment_Id', 'Failure_Type',
              'Amperage', 'Temperature', 'Voltage', 'Rotor_Speed']
for col in ['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed', 'Failure_Type']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.dropna()
df['Failure_Type'] = df['Failure_Type'].astype(int)

PARAMS = ['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed']
PARAM_LABELS = {
    'Amperage': 'Operating Amperage (A)',
    'Temperature': 'Operating Temperature (°C)',
    'Voltage': 'Operating Voltage (V)',
    'Rotor_Speed': 'Rotor Speed (RPM)'
}
UNITS = {'Amperage': 'A', 'Temperature': '°C', 'Voltage': 'V', 'Rotor_Speed': 'RPM'}
NATURE_COLORS = ['#0C7BDC', '#E66100', '#5D3A9B', '#009E73',
                 '#F5C710', '#CC3311', '#AA4499', '#882255', '#332288', '#117733']

# Derived features — must be added BEFORE splitting
df['Power'] = df['Voltage'] * df['Amperage']        # VA
df['Efficiency'] = df['Rotor_Speed'] / df['Amperage']  # RPM/A
df['Thermal_Load'] = df['Temperature'] / df['Amperage']  # °C/A

normal_df = df[df['Failure_Type'] == 0]
fault_df = df[df['Failure_Type'] != 0]
fault_types = sorted(fault_df['Failure_Type'].unique())

def add_label(ax, label, x=-0.12, y=1.05):
    ax.text(x, y, label, transform=ax.transAxes, fontsize=9,
            fontweight='bold', va='top', ha='left')

# ============================================================
# Helper: compute threshold via Youden's J
# ============================================================
def find_optimal_threshold(normal_vals, fault_vals):
    """Find optimal threshold using Youden's J statistic."""
    all_vals = np.concatenate([normal_vals, fault_vals])
    labels = np.concatenate([np.zeros(len(normal_vals)), np.ones(len(fault_vals))])
    fpr, tpr, thresholds = roc_curve(labels, all_vals)
    j_scores = tpr - fpr
    best_idx = np.argmax(j_scores)
    return thresholds[best_idx], j_scores[best_idx], fpr, tpr, thresholds

# ============================================================
# TASK 5: Box plot — offset from normal for each parameter
# ============================================================
print("\n" + "="*60)
print("  TASK 5: Box plot — parameter offset from normal")
print("="*60)

fig5, axes5 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes5 = axes5.flatten()

for i, param in enumerate(PARAMS):
    ax = axes5[i]
    normal_vals = normal_df[param].values
    normal_median = np.median(normal_vals)
    normal_q1, normal_q3 = np.percentile(normal_vals, [25, 75])

    # Calculate offset (absolute deviation from normal median)
    plot_data, plot_labels, plot_colors = [], [], []
    # Normal offset = 0 reference
    plot_data.append(normal_vals - normal_median)
    plot_labels.append('Normal')
    plot_colors.append('#AAAAAA')

    for j, ft in enumerate(fault_types):
        ft_vals = fault_df[fault_df['Failure_Type'] == ft][param].values
        plot_data.append(ft_vals - normal_median)
        plot_labels.append(f'F{ft}')
        plot_colors.append(NATURE_COLORS[j % len(NATURE_COLORS)])

    bp = ax.boxplot(plot_data, patch_artist=True, widths=0.6,
                    medianprops={'linewidth': 0.8, 'color': 'black'},
                    whiskerprops={'linewidth': 0.5}, capprops={'linewidth': 0.5},
                    flierprops={'markersize': 1.2, 'markerfacecolor': 'black', 'markeredgewidth': 0.3})

    for patch, c in zip(bp['boxes'], plot_colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)

    # Reference zero line
    ax.axhline(y=0, color='black', linewidth=0.6, linestyle='--', alpha=0.4)

    ax.set_xticklabels(plot_labels, rotation=45, ha='right', fontsize=5)
    ax.set_ylabel(f'Δ {PARAM_LABELS[param]}')
    ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
    add_label(ax, chr(97 + i))

fig5.suptitle('Parameter Offset from Normal Median During Fault Conditions',
              fontsize=9, fontweight='bold', y=1.02)
fig5.tight_layout()
fig5.savefig('figure5_offset_boxplots.png', dpi=300)
fig5.savefig('figure5_offset_boxplots.pdf')
print("Saved: figure5_offset_boxplots.png/.pdf")

# ============================================================
# TASK 6: Identify parameters with significant shift & quantify
# ============================================================
print("\n" + "="*60)
print("  TASK 6: Significant parameter shift identification")
print("="*60)

shift_results = []
for param in PARAMS:
    normal_vals = normal_df[param].values
    fault_vals = fault_df[param].values
    normal_mean, fault_mean = np.mean(normal_vals), np.mean(fault_vals)
    normal_std, fault_std = np.std(normal_vals), np.std(fault_vals)
    abs_shift = fault_mean - normal_mean
    pct_shift = (abs_shift / normal_mean) * 100
    # Cohen's d effect size
    pooled_std = np.sqrt((normal_std**2 + fault_std**2) / 2)
    cohens_d = abs_shift / pooled_std if pooled_std > 0 else 0
    # KS test
    ks_stat, ks_p = scipy_stats.ks_2samp(normal_vals, fault_vals)
    # Mann-Whitney U
    u_stat, u_p = scipy_stats.mannwhitneyu(normal_vals, fault_vals, alternative='two-sided')

    significance = '***' if ks_p < 0.001 else ('**' if ks_p < 0.01 else ('*' if ks_p < 0.05 else 'ns'))
    shift_results.append({
        'Parameter': param,
        'Normal_Mean': normal_mean, 'Fault_Mean': fault_mean,
        'Abs_Shift': abs_shift, 'Pct_Shift': pct_shift,
        'Cohens_d': cohens_d, 'KS_Stat': ks_stat, 'KS_p': ks_p,
        'MW_p': u_p, 'Significance': significance
    })
    print(f"  {param:>15s}: Δ={abs_shift:+.4f} ({pct_shift:+.2f}%)  "
          f"Cohen's d={cohens_d:.4f}  KS={ks_stat:.4f} (p={ks_p:.2e}) {significance}")

# Bar chart of percentage shift
fig6, ax6 = plt.subplots(figsize=(7.2, 2.5))
params_labels = [PARAM_LABELS[p] for p in PARAMS]
pct_shifts = [r['Pct_Shift'] for r in shift_results]
colors_bar = ['#CC3311' if abs(s) > 1 else '#0C7BDC' for s in pct_shifts]
bars = ax6.barh(params_labels, pct_shifts, color=colors_bar, edgecolor='white', linewidth=0.3, height=0.6)
for bar, val, r in zip(bars, pct_shifts, shift_results):
    ax6.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
             f'{val:+.2f}%  (d={r["Cohens_d"]:.3f})', va='center', fontsize=6)
ax6.axvline(x=0, color='black', linewidth=0.5)
ax6.set_xlabel('Shift from Normal Mean (%)')
ax6.set_title('Parameter Mean Shift During Fault Conditions', fontsize=9, fontweight='bold')
ax6.xaxis.set_major_locator(ticker.MaxNLocator(6))
fig6.tight_layout()
fig6.savefig('figure6_parameter_shift.png', dpi=300)
fig6.savefig('figure6_parameter_shift.pdf')
print("Saved: figure6_parameter_shift.png/.pdf")

# ============================================================
# TASK 7: Historical extreme value analysis
# ============================================================
print("\n" + "="*60)
print("  TASK 7: Historical extreme value analysis")
print("="*60)

extreme_results = []
for param in PARAMS:
    vals = df[param].values
    extreme_results.append({
        'Parameter': param,
        'Global_Min': vals.min(), 'Global_Max': vals.max(),
        'Normal_Min': normal_df[param].min(), 'Normal_Max': normal_df[param].max(),
        'Fault_Min': fault_df[param].min(), 'Fault_Max': fault_df[param].max(),
        'Normal_P1': np.percentile(normal_df[param], 1),
        'Normal_P99': np.percentile(normal_df[param], 99),
        'Normal_P0_1': np.percentile(normal_df[param], 0.1),
        'Normal_P99_9': np.percentile(normal_df[param], 99.9),
    })
    r = extreme_results[-1]
    print(f"  {param:>15s}: Global [{r['Global_Min']:.2f}, {r['Global_Max']:.2f}]  "
          f"Normal [{r['Normal_Min']:.2f}, {r['Normal_Max']:.2f}]  "
          f"Fault [{r['Fault_Min']:.2f}, {r['Fault_Max']:.2f}]")

# Plot: historical range with normal envelope
fig7, axes7 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes7 = axes7.flatten()
for i, param in enumerate(PARAMS):
    ax = axes7[i]
    r = extreme_results[i]
    # Draw range bars
    categories = ['Global\n(all data)', 'Normal\n(Type 0)', 'Fault\n(Type ≠ 0)']
    mins = [r['Global_Min'], r['Normal_Min'], r['Fault_Min']]
    maxs = [r['Global_Max'], r['Normal_Max'], r['Fault_Max']]
    means_all = [np.mean(df[param]), np.mean(normal_df[param]), np.mean(fault_df[param])]
    colors = ['#555555', '#0C7BDC', '#CC3311']

    for j, (cat, lo, hi, m, c) in enumerate(zip(categories, mins, maxs, means_all, colors)):
        ax.barh(j, hi - lo, left=lo, height=0.5, color=c, alpha=0.5, edgecolor=c, linewidth=0.5)
        ax.plot(m, j, 'D', color='black', markersize=4, markeredgewidth=0.3)

    ax.set_yticks(range(3))
    ax.set_yticklabels(categories, fontsize=6)
    ax.set_xlabel(PARAM_LABELS[param])
    ax.xaxis.set_major_locator(ticker.MaxNLocator(5))
    add_label(ax, chr(97 + i))

fig7.suptitle('Historical Extreme Value Range: Normal vs Fault Conditions',
              fontsize=9, fontweight='bold', y=1.02)
fig7.tight_layout()
fig7.savefig('figure7_extreme_values.png', dpi=300)
fig7.savefig('figure7_extreme_values.pdf')
print("Saved: figure7_extreme_values.png/.pdf")

# ============================================================
# TASK 8: Safe operating range (from normal data)
# ============================================================
print("\n" + "="*60)
print("  TASK 8: Safe operating range")
print("="*60)

safe_ranges = {}
for param in PARAMS:
    nv = normal_df[param].values
    # Multiple methods
    mean_3sigma_lo = np.mean(nv) - 3 * np.std(nv)
    mean_3sigma_hi = np.mean(nv) + 3 * np.std(nv)
    p01, p99 = np.percentile(nv, [1, 99])
    p0_1, p99_9 = np.percentile(nv, [0.1, 99.9])
    iqr = np.percentile(nv, 75) - np.percentile(nv, 25)
    tukey_lo = np.percentile(nv, 25) - 1.5 * iqr
    tukey_hi = np.percentile(nv, 75) + 1.5 * iqr

    safe_ranges[param] = {
        'mean_3sigma': (mean_3sigma_lo, mean_3sigma_hi),
        'percentile_99': (p01, p99),
        'percentile_99_9': (p0_1, p99_9),
        'tukey': (tukey_lo, tukey_hi),
        'mean': np.mean(nv), 'std': np.std(nv)
    }
    sr = safe_ranges[param]
    # Check violation rate in fault data
    fv = fault_df[param].values
    violation_3s = np.sum((fv < mean_3sigma_lo) | (fv > mean_3sigma_hi)) / len(fv) * 100
    violation_tukey = np.sum((fv < tukey_lo) | (fv > tukey_hi)) / len(fv) * 100
    violation_p99 = np.sum((fv < p01) | (fv > p99)) / len(fv) * 100

    print(f"\n  {param}:")
    print(f"    Mean ± 3σ:  [{mean_3sigma_lo:.2f}, {mean_3sigma_hi:.2f}]  — fault violation: {violation_3s:.1f}%")
    print(f"    99%ile:      [{p01:.2f}, {p99:.2f}]  — fault violation: {violation_p99:.1f}%")
    print(f"    Tukey fence: [{tukey_lo:.2f}, {tukey_hi:.2f}]  — fault violation: {violation_tukey:.1f}%")

fig8, axes8 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes8 = axes8.flatten()
for i, param in enumerate(PARAMS):
    ax = axes8[i]
    nv = normal_df[param].values
    fv = fault_df[param].values
    sr = safe_ranges[param]
    lo, hi = sr['percentile_99']

    # KDE of normal and fault
    sns.kdeplot(nv, ax=ax, color='#0C7BDC', label='Normal', linewidth=1.2)
    sns.kdeplot(fv, ax=ax, color='#CC3311', label='Fault', linewidth=1.2)
    # Safe range
    ax.axvspan(lo, hi, alpha=0.1, color='#0C7BDC')
    ax.axvline(lo, color='#0C7BDC', linewidth=0.5, linestyle='--')
    ax.axvline(hi, color='#0C7BDC', linewidth=0.5, linestyle='--')

    # Violation rate
    violation = np.sum((fv < lo) | (fv > hi)) / len(fv) * 100
    ax.text(0.97, 0.97, f"Safe range:\n[{lo:.1f}, {hi:.1f}]\nFault violation: {violation:.1f}%",
            transform=ax.transAxes, fontsize=5.5, va='top', ha='right', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))

    ax.set_xlabel(PARAM_LABELS[param])
    ax.set_ylabel('Density')
    add_label(ax, chr(97 + i))

handles, labels = axes8[0].get_legend_handles_labels()
fig8.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=6, frameon=False)
fig8.suptitle('Safe Operating Range (99%ile of Normal Data)', fontsize=9, fontweight='bold', y=1.08)
fig8.tight_layout()
fig8.savefig('figure8_safe_range.png', dpi=300)
fig8.savefig('figure8_safe_range.pdf')
print("Saved: figure8_safe_range.png/.pdf")

# ============================================================
# TASK 9: Critical threshold identification (ROC/Youden)
# ============================================================
print("\n" + "="*60)
print("  TASK 9: Critical threshold identification")
print("="*60)

fig9, axes9 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes9 = axes9.flatten()

threshold_results = []
for i, param in enumerate(PARAMS):
    ax = axes9[i]
    nv = normal_df[param].values
    fv = fault_df[param].values
    best_thresh, best_j, fpr, tpr, thresholds = find_optimal_threshold(nv, fv)

    # KDE plot with threshold
    sns.kdeplot(nv, ax=ax, color='#0C7BDC', label='Normal', linewidth=1.2, fill=True, alpha=0.15)
    sns.kdeplot(fv, ax=ax, color='#CC3311', label='Fault', linewidth=1.2, fill=True, alpha=0.15)
    ax.axvline(best_thresh, color='black', linewidth=0.8, linestyle='--')
    ax.text(best_thresh, ax.get_ylim()[1] * 0.95, f'  Threshold\n  {best_thresh:.2f}',
            fontsize=5.5, va='top', color='black')

    # Sensitivity, specificity
    # For values above threshold -> fault
    # Sensitivity = TP / (TP+FN)
    sens = np.sum(fv > best_thresh) / len(fv)
    spec = np.sum(nv <= best_thresh) / len(nv)
    threshold_results.append({
        'Parameter': param, 'Threshold': best_thresh,
        'Youden_J': best_j, 'Sensitivity': sens, 'Specificity': spec,
        'Direction': 'above'
    })
    print(f"  {param:>15s}: Threshold={best_thresh:.4f}  J={best_j:.4f}  "
          f"Sensitivity={sens:.3f}  Specificity={spec:.3f}")

    # Check if below might be better
    sens_below = np.sum(fv < best_thresh) / len(fv)
    spec_below = np.sum(nv >= best_thresh) / len(nv)
    if sens_below > sens:
        # Re-run with inverted labels
        best_thresh2, best_j2, fpr2, tpr2, thresholds2 = find_optimal_threshold(fv, nv)
        sens2 = np.sum(fv < best_thresh2) / len(fv)
        spec2 = np.sum(nv >= best_thresh2) / len(nv)
        threshold_results[-1] = {
            'Parameter': param, 'Threshold': best_thresh2,
            'Youden_J': best_j2, 'Sensitivity': sens2, 'Specificity': spec2,
            'Direction': 'below'
        }
        ax.axvline(best_thresh2, color='#E66100', linewidth=0.8, linestyle=':')
        print(f"    (inverted) Threshold={best_thresh2:.4f}  J={best_j2:.4f}  "
              f"Sensitivity={sens2:.3f}  Specificity={spec2:.3f}")

    ax.text(0.97, 0.97, f"J={threshold_results[-1]['Youden_J']:.3f}\n"
            f"Se={threshold_results[-1]['Sensitivity']:.3f}\n"
            f"Sp={threshold_results[-1]['Specificity']:.3f}\n"
            f"Thr={threshold_results[-1]['Threshold']:.2f}",
            transform=ax.transAxes, fontsize=5.5, va='top', ha='right', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))

    ax.set_xlabel(PARAM_LABELS[param])
    ax.set_ylabel('Density')
    add_label(ax, chr(97 + i))

handles, labels = axes9[0].get_legend_handles_labels()
fig9.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=6, frameon=False)
fig9.suptitle('Critical Threshold Identification (Youden\'s J Method)',
              fontsize=9, fontweight='bold', y=1.08)
fig9.tight_layout()
fig9.savefig('figure9_thresholds.png', dpi=300)
fig9.savefig('figure9_thresholds.pdf')
print("Saved: figure9_thresholds.png/.pdf")

# ============================================================
# TASK 10: Normal state correlation matrix
# ============================================================
print("\n" + "="*60)
print("  TASK 10: Normal state correlation matrix")
print("="*60)

normal_corr = normal_df[PARAMS].corr()
print(normal_corr.to_string())

fig10, ax10 = plt.subplots(figsize=(4.5, 4))
mask = np.triu(np.ones_like(normal_corr, dtype=bool), k=1)
cmap = sns.diverging_palette(240, 10, as_cmap=True)
sns.heatmap(normal_corr, mask=mask, annot=True, fmt='.3f', cmap=cmap,
            vmin=-1, vmax=1, center=0, square=True, linewidths=0.5,
            cbar_kws={'shrink': 0.8, 'label': 'Pearson r'},
            annot_kws={'fontsize': 7}, ax=ax10)
ax10.set_title('Normal Operation Correlation Matrix', fontsize=9, fontweight='bold')
fig10.tight_layout()
fig10.savefig('figure10_normal_correlation.png', dpi=300)
fig10.savefig('figure10_normal_correlation.pdf')
print("Saved: figure10_normal_correlation.png/.pdf")

# ============================================================
# TASK 11: Correlation change during faults
# ============================================================
print("\n" + "="*60)
print("  TASK 11: Abnormal state correlation change")
print("="*60)

fault_corr = fault_df[PARAMS].corr()
delta_corr = fault_corr - normal_corr
print("Fault correlation:")
print(fault_corr.to_string())
print("\nDelta (Fault - Normal):")
print(delta_corr.to_string())

fig11, axes11 = plt.subplots(1, 3, figsize=(9, 3.5))
cbar_ax = fig11.add_axes([0.92, 0.15, 0.015, 0.7])

# Normal corr
sns.heatmap(normal_corr, annot=True, fmt='.2f', cmap=cmap, vmin=-1, vmax=1,
            center=0, square=True, linewidths=0.5, cbar=False,
            annot_kws={'fontsize': 6}, ax=axes11[0])
axes11[0].set_title('Normal', fontsize=8)

# Fault corr
sns.heatmap(fault_corr, annot=True, fmt='.2f', cmap=cmap, vmin=-1, vmax=1,
            center=0, square=True, linewidths=0.5, cbar=False,
            annot_kws={'fontsize': 6}, ax=axes11[1])
axes11[1].set_title('Fault', fontsize=8)

# Delta
delta_cmap = sns.diverging_palette(240, 10, as_cmap=True)
sns.heatmap(delta_corr, annot=True, fmt='.3f', cmap=delta_cmap, vmin=-0.3, vmax=0.3,
            center=0, square=True, linewidths=0.5, cbar=True,
            cbar_ax=cbar_ax, annot_kws={'fontsize': 6}, ax=axes11[2])
axes11[2].set_title('Δ (Fault − Normal)', fontsize=8)

fig11.suptitle('Correlation Matrix: Normal vs. Fault Conditions', fontsize=9, fontweight='bold', y=1.03)
fig11.tight_layout(rect=[0, 0, 0.91, 1])
fig11.savefig('figure11_correlation_change.png', dpi=300)
fig11.savefig('figure11_correlation_change.pdf')
print("Saved: figure11_correlation_change.png/.pdf")

# ============================================================
# TASK 12: Power = Voltage × Amperage
# ============================================================
print("\n" + "="*60)
print("  TASK 12: Power analysis (V × I)")
print("="*60)

normal_power_mean = normal_df['Power'].mean()
normal_power_std = normal_df['Power'].std()
fault_power_mean = fault_df['Power'].mean()
fault_power_std = fault_df['Power'].std()
print(f"  Normal: Power = {normal_power_mean:.2f} ± {normal_power_std:.2f} VA")
print(f"  Fault:  Power = {fault_power_mean:.2f} ± {fault_power_std:.2f} VA")
print(f"  Shift:  Δ = {fault_power_mean - normal_power_mean:+.2f} VA ({(fault_power_mean/normal_power_mean - 1)*100:+.2f}%)")

fig12, axes12 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes12 = axes12.flatten()

# Panel a: Power distribution normal vs fault
ax = axes12[0]
sns.kdeplot(normal_df['Power'], ax=ax, color='#0C7BDC', label='Normal', linewidth=1.2, fill=True, alpha=0.15)
sns.kdeplot(fault_df['Power'], ax=ax, color='#CC3311', label='Fault', linewidth=1.2, fill=True, alpha=0.15)
ax.set_xlabel('Power (VA)')
ax.set_ylabel('Density')
ax.legend(fontsize=6)
ax.text(0.97, 0.97, f"Normal: {normal_power_mean:.0f}±{normal_power_std:.0f} VA\n"
        f"Fault: {fault_power_mean:.0f}±{fault_power_std:.0f} VA",
        transform=ax.transAxes, fontsize=5.5, va='top', ha='right', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))
add_label(ax, 'a')

# Panel b: Power per fault type
ax = axes12[1]
plot_data = [normal_df['Power'].values]
for ft in fault_types:
    plot_data.append(fault_df[fault_df['Failure_Type'] == ft]['Power'].values)
labels = ['Normal'] + [f'F{ft}' for ft in fault_types]
colors = ['#AAAAAA'] + [NATURE_COLORS[j % len(NATURE_COLORS)] for j in range(len(fault_types))]
bp = ax.boxplot(plot_data, patch_artist=True, widths=0.6,
                medianprops={'linewidth': 0.8, 'color': 'black'},
                whiskerprops={'linewidth': 0.5}, capprops={'linewidth': 0.5},
                flierprops={'markersize': 1.2, 'markerfacecolor': 'black', 'markeredgewidth': 0.3})
for patch, c in zip(bp['boxes'], colors):
    patch.set_facecolor(c); patch.set_alpha(0.7)
ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=5)
ax.set_ylabel('Power (VA)')
add_label(ax, 'b')

# Panel c: V vs I scatter with power isolines
ax = axes12[2]
sc = ax.scatter(normal_df['Voltage'], normal_df['Amperage'], c=normal_df['Power'],
                cmap='Blues', s=1, alpha=0.4, label='Normal')
sc2 = ax.scatter(fault_df['Voltage'], fault_df['Amperage'], c=fault_df['Power'],
                 cmap='Reds', s=1, alpha=0.4, label='Fault')
# Power isolines
v_range = np.linspace(df['Voltage'].min(), df['Voltage'].max(), 100)
for p_kw in [3, 5, 7, 10, 15]:
    ax.plot(v_range, p_kw * 1000 / v_range, 'k--', linewidth=0.3, alpha=0.3)
    ax.text(v_range[-1], p_kw * 1000 / v_range[-1], f'{p_kw}kW', fontsize=4, alpha=0.4)
ax.set_xlabel('Voltage (V)')
ax.set_ylabel('Amperage (A)')
ax.legend(markerscale=3, fontsize=5, loc='upper right')
add_label(ax, 'c')

# Panel d: Power deviation per fault type
ax = axes12[3]
power_by_type = {}
power_by_type['Normal'] = {'mean': normal_power_mean, 'std': normal_power_std}
for ft in fault_types:
    ft_power = fault_df[fault_df['Failure_Type'] == ft]['Power']
    power_by_type[f'F{ft}'] = {'mean': ft_power.mean(), 'std': ft_power.std()}

cats = list(power_by_type.keys())
means = [power_by_type[c]['mean'] for c in cats]
stds = [power_by_type[c]['std'] for c in cats]
bar_colors = ['#AAAAAA'] + [NATURE_COLORS[j % len(NATURE_COLORS)] for j in range(len(fault_types))]
ax.barh(cats, means, xerr=stds, color=bar_colors, edgecolor='white', linewidth=0.3,
        height=0.6, capsize=1.5, error_kw={'linewidth': 0.5})
ax.set_xlabel('Power (VA)')
ax.xaxis.set_major_locator(ticker.MaxNLocator(5))
add_label(ax, 'd')

fig12.suptitle('Power Analysis: Voltage × Amperage', fontsize=9, fontweight='bold', y=1.02)
fig12.tight_layout()
fig12.savefig('figure12_power_analysis.png', dpi=300)
fig12.savefig('figure12_power_analysis.pdf')
print("Saved: figure12_power_analysis.png/.pdf")

# ============================================================
# TASK 13: Efficiency = Rotor Speed / Amperage
# ============================================================
print("\n" + "="*60)
print("  TASK 13: Efficiency index (RPM/A)")
print("="*60)

normal_eff_mean = normal_df['Efficiency'].mean()
normal_eff_std = normal_df['Efficiency'].std()
fault_eff_mean = fault_df['Efficiency'].mean()
fault_eff_std = fault_df['Efficiency'].std()
print(f"  Normal: Efficiency = {normal_eff_mean:.2f} ± {normal_eff_std:.2f} RPM/A")
print(f"  Fault:  Efficiency = {fault_eff_mean:.2f} ± {fault_eff_std:.2f} RPM/A")
print(f"  Shift:  Δ = {fault_eff_mean - normal_eff_mean:+.2f} RPM/A ({(fault_eff_mean/normal_eff_mean - 1)*100:+.2f}%)")

fig13, axes13 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes13 = axes13.flatten()

ax = axes13[0]
sns.kdeplot(normal_df['Efficiency'], ax=ax, color='#0C7BDC', label='Normal', linewidth=1.2, fill=True, alpha=0.15)
sns.kdeplot(fault_df['Efficiency'], ax=ax, color='#CC3311', label='Fault', linewidth=1.2, fill=True, alpha=0.15)
ax.set_xlabel('Efficiency (RPM/A)')
ax.set_ylabel('Density')
ax.legend(fontsize=6)
ax.text(0.97, 0.97, f"Normal: {normal_eff_mean:.1f}±{normal_eff_std:.1f}\n"
        f"Fault: {fault_eff_mean:.1f}±{fault_eff_std:.1f}",
        transform=ax.transAxes, fontsize=5.5, va='top', ha='right', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))
add_label(ax, 'a')

ax = axes13[1]
plot_data = [normal_df['Efficiency'].values]
for ft in fault_types:
    plot_data.append(fault_df[fault_df['Failure_Type'] == ft]['Efficiency'].values)
labels = ['Normal'] + [f'F{ft}' for ft in fault_types]
colors = ['#AAAAAA'] + [NATURE_COLORS[j % len(NATURE_COLORS)] for j in range(len(fault_types))]
bp = ax.boxplot(plot_data, patch_artist=True, widths=0.6,
                medianprops={'linewidth': 0.8, 'color': 'black'},
                whiskerprops={'linewidth': 0.5}, capprops={'linewidth': 0.5},
                flierprops={'markersize': 1.2, 'markerfacecolor': 'black', 'markeredgewidth': 0.3})
for patch, c in zip(bp['boxes'], colors):
    patch.set_facecolor(c); patch.set_alpha(0.7)
ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=5)
ax.set_ylabel('Efficiency (RPM/A)')
add_label(ax, 'b')

ax = axes13[2]
sc = ax.scatter(normal_df['Amperage'], normal_df['Rotor_Speed'], c='#0C7BDC', s=1, alpha=0.4, label='Normal')
sc2 = ax.scatter(fault_df['Amperage'], fault_df['Rotor_Speed'], c='#CC3311', s=1, alpha=0.4, label='Fault')
# Efficiency isolines
a_range = np.linspace(df['Amperage'].min(), df['Amperage'].max(), 100)
for eff in [5, 8, 12, 16, 20]:
    ax.plot(a_range, eff * a_range, 'k--', linewidth=0.3, alpha=0.3)
    ax.text(a_range[-1], eff * a_range[-1], f'{eff}', fontsize=4, alpha=0.4)
ax.set_xlabel('Amperage (A)')
ax.set_ylabel('Rotor Speed (RPM)')
ax.legend(markerscale=3, fontsize=5, loc='upper left')
add_label(ax, 'c')

ax = axes13[3]
eff_by_type = {'Normal': {'mean': normal_eff_mean, 'std': normal_eff_std}}
for ft in fault_types:
    ft_eff = fault_df[fault_df['Failure_Type'] == ft]['Efficiency']
    eff_by_type[f'F{ft}'] = {'mean': ft_eff.mean(), 'std': ft_eff.std()}
cats = list(eff_by_type.keys())
means = [eff_by_type[c]['mean'] for c in cats]
stds = [eff_by_type[c]['std'] for c in cats]
bar_colors = ['#AAAAAA'] + [NATURE_COLORS[j % len(NATURE_COLORS)] for j in range(len(fault_types))]
ax.barh(cats, means, xerr=stds, color=bar_colors, edgecolor='white', linewidth=0.3,
        height=0.6, capsize=1.5, error_kw={'linewidth': 0.5})
ax.set_xlabel('Efficiency (RPM/A)')
ax.xaxis.set_major_locator(ticker.MaxNLocator(5))
add_label(ax, 'd')

fig13.suptitle('Efficiency Index: Rotor Speed / Amperage', fontsize=9, fontweight='bold', y=1.02)
fig13.tight_layout()
fig13.savefig('figure13_efficiency.png', dpi=300)
fig13.savefig('figure13_efficiency.pdf')
print("Saved: figure13_efficiency.png/.pdf")

# ============================================================
# TASK 14: Thermal load — Temperature / Current relationship
# ============================================================
print("\n" + "="*60)
print("  TASK 14: Thermal load indicator (T vs I)")
print("="*60)

normal_tl_mean = normal_df['Thermal_Load'].mean()
normal_tl_std = normal_df['Thermal_Load'].std()
fault_tl_mean = fault_df['Thermal_Load'].mean()
fault_tl_std = fault_df['Thermal_Load'].std()
print(f"  Normal: Thermal Load = {normal_tl_mean:.2f} ± {normal_tl_std:.2f} °C/A")
print(f"  Fault:  Thermal Load = {fault_tl_mean:.2f} ± {fault_tl_std:.2f} °C/A")
print(f"  Shift:  Δ = {fault_tl_mean - normal_tl_mean:+.2f} °C/A ({(fault_tl_mean/normal_tl_mean - 1)*100:+.2f}%)")

# Find thermal load threshold where fault probability becomes high (>50%)
# Use normal data 95th percentile as baseline threshold
tl_normal_p95 = np.percentile(normal_df['Thermal_Load'], 95)
tl_normal_p99 = np.percentile(normal_df['Thermal_Load'], 99)

# Binning thermal load and computing fault probability
bins = np.linspace(df['Thermal_Load'].min(), df['Thermal_Load'].max(), 30)
fault_prob = []
bin_centers = []
for j in range(len(bins) - 1):
    mask = (df['Thermal_Load'] >= bins[j]) & (df['Thermal_Load'] < bins[j+1])
    if mask.sum() >= 10:
        fault_prob.append(df.loc[mask, 'Failure_Type'].apply(lambda x: 1 if x != 0 else 0).mean())
        bin_centers.append((bins[j] + bins[j+1]) / 2)

# Find where fault prob crosses 50%
risk_threshold = None
for bc, fp in zip(bin_centers, fault_prob):
    if fp >= 0.5:
        risk_threshold = bc
        break
if risk_threshold is None:
    risk_threshold = tl_normal_p95

print(f"  Normal P95 thermal load: {tl_normal_p95:.2f} °C/A")
print(f"  Normal P99 thermal load: {tl_normal_p99:.2f} °C/A")
print(f"  Risk threshold (fault prob ≥ 50%): {risk_threshold:.2f} °C/A")

fig14, axes14 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes14 = axes14.flatten()

# Panel a: Thermal load distribution
ax = axes14[0]
sns.kdeplot(normal_df['Thermal_Load'], ax=ax, color='#0C7BDC', label='Normal', linewidth=1.2, fill=True, alpha=0.15)
sns.kdeplot(fault_df['Thermal_Load'], ax=ax, color='#CC3311', label='Fault', linewidth=1.2, fill=True, alpha=0.15)
ax.axvline(risk_threshold, color='black', linewidth=0.8, linestyle='--')
ax.text(risk_threshold, ax.get_ylim()[1]*0.95, f'  Risk\n  {risk_threshold:.1f}',
        fontsize=5.5, va='top', color='black')
ax.set_xlabel('Thermal Load (°C/A)')
ax.set_ylabel('Density')
ax.legend(fontsize=6)
ax.text(0.97, 0.97, f"Normal: {normal_tl_mean:.1f}±{normal_tl_std:.1f}\n"
        f"Fault: {fault_tl_mean:.1f}±{fault_tl_std:.1f}",
        transform=ax.transAxes, fontsize=5.5, va='top', ha='right', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))
add_label(ax, 'a')

# Panel b: Fault probability vs thermal load
ax = axes14[1]
ax.plot(bin_centers, fault_prob, 'o-', color='#CC3311', markersize=2, linewidth=0.8)
ax.axhline(y=0.5, color='black', linewidth=0.5, linestyle='--', alpha=0.5)
ax.axvline(x=risk_threshold, color='black', linewidth=0.5, linestyle='--', alpha=0.5)
ax.fill_between(bin_centers, 0, fault_prob, alpha=0.15, color='#CC3311')
ax.set_xlabel('Thermal Load (°C/A)')
ax.set_ylabel('Fault Probability')
ax.yaxis.set_major_formatter(ticker.PercentFormatter(1.0))
ax.text(risk_threshold, 0.52, f'Threshold:\n{risk_threshold:.1f}', fontsize=5.5, ha='left')
add_label(ax, 'b')

# Panel c: Temperature vs Amperage scatter with thermal load zones
ax = axes14[2]
# Normal: blue, Fault: red
sc1 = ax.scatter(normal_df['Amperage'], normal_df['Temperature'],
                 c='#0C7BDC', s=1, alpha=0.3, label='Normal')
sc2 = ax.scatter(fault_df['Amperage'], fault_df['Temperature'],
                 c='#CC3311', s=1, alpha=0.3, label='Fault')
# Thermal load isolines
a_range = np.linspace(df['Amperage'].min(), df['Amperage'].max(), 100)
for tl in [1.5, risk_threshold, 6, 10]:
    ls = '--' if tl == risk_threshold else ':'
    lw = 0.8 if tl == risk_threshold else 0.3
    ax.plot(a_range, tl * a_range, 'k', linestyle=ls, linewidth=lw, alpha=0.4)
    if tl == risk_threshold:
        ax.text(a_range[-1], tl * a_range[-1], f'Risk {tl:.1f}', fontsize=4, alpha=0.6)
ax.set_xlabel('Amperage (A)')
ax.set_ylabel('Temperature (°C)')
ax.legend(markerscale=3, fontsize=5, loc='upper left')
add_label(ax, 'c')

# Panel d: Thermal load per fault type
ax = axes14[3]
plot_data = [normal_df['Thermal_Load'].values]
for ft in fault_types:
    plot_data.append(fault_df[fault_df['Failure_Type'] == ft]['Thermal_Load'].values)
labels = ['Normal'] + [f'F{ft}' for ft in fault_types]
colors = ['#AAAAAA'] + [NATURE_COLORS[j % len(NATURE_COLORS)] for j in range(len(fault_types))]
bp = ax.boxplot(plot_data, patch_artist=True, widths=0.6,
                medianprops={'linewidth': 0.8, 'color': 'black'},
                whiskerprops={'linewidth': 0.5}, capprops={'linewidth': 0.5},
                flierprops={'markersize': 1.2, 'markerfacecolor': 'black', 'markeredgewidth': 0.3})
for patch, c in zip(bp['boxes'], colors):
    patch.set_facecolor(c); patch.set_alpha(0.7)
ax.axhline(y=risk_threshold, color='black', linewidth=0.6, linestyle='--', alpha=0.5)
ax.text(len(plot_data) - 0.5, risk_threshold, f'Risk={risk_threshold:.1f}', fontsize=5, va='bottom', ha='right')
ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=5)
ax.set_ylabel('Thermal Load (°C/A)')
add_label(ax, 'd')

fig14.suptitle('Thermal Load Indicator: Temperature / Current Relationship',
              fontsize=9, fontweight='bold', y=1.02)
fig14.tight_layout()
fig14.savefig('figure14_thermal_load.png', dpi=300)
fig14.savefig('figure14_thermal_load.pdf')
print("Saved: figure14_thermal_load.png/.pdf")

# ============================================================
# Summary table for tasks 12-14
# ============================================================
print("\n" + "="*80)
print("  DERIVED METRICS SUMMARY")
print("="*80)
for name, normal_mean, normal_std, fault_mean, fault_std, unit in [
    ('Power (V×I)', normal_power_mean, normal_power_std, fault_power_mean, fault_power_std, 'VA'),
    ('Efficiency (RPM/A)', normal_eff_mean, normal_eff_std, fault_eff_mean, fault_eff_std, 'RPM/A'),
    ('Thermal Load (°C/A)', normal_tl_mean, normal_tl_std, fault_tl_mean, fault_tl_std, '°C/A'),
]:
    delta = fault_mean - normal_mean
    pct = (fault_mean / normal_mean - 1) * 100
    cohens_d = abs(delta) / np.sqrt((normal_std**2 + fault_std**2) / 2)
    print(f"  {name:<25s}: Normal={normal_mean:>10.2f}±{normal_std:>8.2f}  "
          f"Fault={fault_mean:>10.2f}±{fault_std:>8.2f}  "
          f"Δ={delta:>+10.2f} ({pct:>+6.2f}%)  d={cohens_d:.4f}")

print("\nAll figures generated successfully.")
