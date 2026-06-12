"""Fix figure 14: Thermal load with proper relative risk analysis."""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

plt.rcParams.update({
    'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 7, 'axes.titlesize': 8, 'axes.labelsize': 7,
    'xtick.labelsize': 6, 'ytick.labelsize': 6, 'legend.fontsize': 6,
    'figure.dpi': 300, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05, 'axes.linewidth': 0.5,
    'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
    'axes.spines.top': False, 'axes.spines.right': False,
    'legend.frameon': False, 'lines.linewidth': 0.8, 'patch.linewidth': 0.5,
})

NATURE_COLORS = ['#0C7BDC', '#E66100', '#5D3A9B', '#009E73',
                 '#F5C710', '#CC3311', '#AA4499', '#882255', '#332288', '#117733']

# Load data
df = pd.read_csv('Unified_Machine_WideTable_2025.csv')
df = df.iloc[:, :7].copy()
df.columns = ['Date', 'Equipment_Id', 'Failure_Type',
              'Amperage', 'Temperature', 'Voltage', 'Rotor_Speed']
for col in ['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed', 'Failure_Type']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.dropna()
df['Failure_Type'] = df['Failure_Type'].astype(int)
df['Thermal_Load'] = df['Temperature'] / df['Amperage']

normal_df = df[df['Failure_Type'] == 0]
fault_df = df[df['Failure_Type'] != 0]
fault_types = sorted(fault_df['Failure_Type'].unique())
baseline_fault_rate = len(fault_df) / len(df)

def add_label(ax, label, x=-0.12, y=1.05):
    ax.text(x, y, label, transform=ax.transAxes, fontsize=9, fontweight='bold', va='top', ha='left')

# Stats
normal_tl_mean = normal_df['Thermal_Load'].mean()
normal_tl_std = normal_df['Thermal_Load'].std()
fault_tl_mean = fault_df['Thermal_Load'].mean()
fault_tl_std = fault_df['Thermal_Load'].std()

tl_normal_p50 = np.percentile(normal_df['Thermal_Load'], 50)
tl_normal_p90 = np.percentile(normal_df['Thermal_Load'], 90)
tl_normal_p95 = np.percentile(normal_df['Thermal_Load'], 95)
tl_normal_p99 = np.percentile(normal_df['Thermal_Load'], 99)

# Binning for relative risk
bins = np.linspace(df['Thermal_Load'].min(), df['Thermal_Load'].max(), 30)
fault_prob = []
relative_risk = []
bin_centers = []
for j in range(len(bins) - 1):
    mask = (df['Thermal_Load'] >= bins[j]) & (df['Thermal_Load'] < bins[j+1])
    if mask.sum() >= 10:
        fp = df.loc[mask, 'Failure_Type'].apply(lambda x: 1 if x != 0 else 0).mean()
        fault_prob.append(fp)
        relative_risk.append(fp / baseline_fault_rate)
        bin_centers.append((bins[j] + bins[j+1]) / 2)

warning_threshold = tl_normal_p90
risk_threshold = tl_normal_p95
critical_threshold = tl_normal_p99

print(f"Baseline fault rate: {baseline_fault_rate:.1%}")
print(f"Normal P50: {tl_normal_p50:.2f}  P90 (Warning): {warning_threshold:.2f}  P95 (Alarm): {risk_threshold:.2f}  P99 (Critical): {critical_threshold:.2f}")
print(f"Normal TL: {normal_tl_mean:.2f} +/- {normal_tl_std:.2f}")
print(f"Fault TL:  {fault_tl_mean:.2f} +/- {fault_tl_std:.2f}")

# ============= FIGURE =============
fig14, axes14 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes14 = axes14.flatten()

# Panel a: Distribution
ax = axes14[0]
sns.kdeplot(normal_df['Thermal_Load'], ax=ax, color='#0C7BDC', label='Normal', linewidth=1.2, fill=True, alpha=0.15)
sns.kdeplot(fault_df['Thermal_Load'], ax=ax, color='#CC3311', label='Fault', linewidth=1.2, fill=True, alpha=0.15)
for thr, ls, lbl in [(warning_threshold, ':', 'Warn'), (risk_threshold, '--', 'Alarm'), (critical_threshold, '-.', 'Crit')]:
    ax.axvline(thr, color='black', linewidth=0.6, linestyle=ls)
    ax.text(thr, ax.get_ylim()[1]*0.97, f'{lbl}', fontsize=4.5, va='top', color='black', rotation=90)
ax.set_xlabel('Thermal Load (C/A)')
ax.set_ylabel('Density')
ax.legend(fontsize=6)
ax.text(0.97, 0.97, f"Normal: {normal_tl_mean:.1f}+/-{normal_tl_std:.1f}\nFault: {fault_tl_mean:.1f}+/-{fault_tl_std:.1f}",
        transform=ax.transAxes, fontsize=5, va='top', ha='right', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))
add_label(ax, 'a')

# Panel b: Relative Risk vs Thermal Load
ax = axes14[1]
ax.plot(bin_centers, relative_risk, 'o-', color='#E66100', markersize=2, linewidth=0.8)
ax.axhline(y=1.0, color='black', linewidth=0.5, linestyle='-', alpha=0.5)
ax.axhline(y=1.1, color='black', linewidth=0.5, linestyle='--', alpha=0.3)
ax.fill_between(bin_centers, 1.0, relative_risk, alpha=0.15, color='#E66100', where=np.array(relative_risk) >= 1.0)
ax.fill_between(bin_centers, 1.0, relative_risk, alpha=0.05, color='#0C7BDC', where=np.array(relative_risk) < 1.0)
ax.set_xlabel('Thermal Load (C/A)')
ax.set_ylabel('Relative Risk (vs baseline)')
ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
ax.text(0.97, 0.97, f'Baseline = {baseline_fault_rate:.1%}\nRR>1 = elevated risk\nRR>1.1 = high risk',
        transform=ax.transAxes, fontsize=5, va='top', ha='right',
        bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', linewidth=0.3, alpha=0.85))
add_label(ax, 'b')

# Panel c: Temperature vs Amperage with thermal load zones
ax = axes14[2]
sc1 = ax.scatter(normal_df['Amperage'], normal_df['Temperature'],
                 c='#0C7BDC', s=1, alpha=0.3, label='Normal')
sc2 = ax.scatter(fault_df['Amperage'], fault_df['Temperature'],
                 c='#CC3311', s=1, alpha=0.3, label='Fault')
a_range = np.linspace(df['Amperage'].min(), df['Amperage'].max(), 100)
zone_data = [
    (warning_threshold, 'Warning\n(P90)', '#F5C710', ':'),
    (risk_threshold, 'Alarm\n(P95)', '#E66100', '--'),
    (critical_threshold, 'Critical\n(P99)', '#CC3311', '-'),
]
for tl_val, zone_label, zone_color, ls in zone_data:
    ax.plot(a_range, tl_val * a_range, color=zone_color, linestyle=ls, linewidth=0.6, alpha=0.6)
    ax.text(a_range[-1], tl_val * a_range[-1], f' {zone_label}', fontsize=4, color=zone_color, alpha=0.8)
ax.set_xlabel('Amperage (A)')
ax.set_ylabel('Temperature (C)')
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
ax.axhline(y=warning_threshold, color='#F5C710', linewidth=0.6, linestyle=':', alpha=0.7)
ax.axhline(y=risk_threshold, color='#E66100', linewidth=0.6, linestyle='--', alpha=0.7)
ax.text(len(plot_data)-0.5, risk_threshold, f'P95={risk_threshold:.1f}', fontsize=4.5, va='bottom', ha='right', color='#E66100')
ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=5)
ax.set_ylabel('Thermal Load (C/A)')
add_label(ax, 'd')

fig14.suptitle('Thermal Load Indicator: Temperature / Current Relationship',
              fontsize=9, fontweight='bold', y=1.02)
fig14.tight_layout()
fig14.savefig('figure14_thermal_load.png', dpi=300)
fig14.savefig('figure14_thermal_load.pdf')
print("\nSaved: figure14_thermal_load.png/.pdf (fixed)")
