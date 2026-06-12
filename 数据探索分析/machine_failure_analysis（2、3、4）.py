import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# Nature-figure style configuration
# ============================================================
def set_nature_style():
    """Configure matplotlib for Nature-journal publication quality figures."""
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 7,
        'axes.titlesize': 8,
        'axes.labelsize': 7,
        'xtick.labelsize': 6,
        'ytick.labelsize': 6,
        'legend.fontsize': 6,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05,
        'axes.linewidth': 0.5,
        'xtick.major.width': 0.5,
        'ytick.major.width': 0.5,
        'xtick.major.size': 2,
        'ytick.major.size': 2,
        'xtick.minor.width': 0.3,
        'ytick.minor.width': 0.3,
        'xtick.minor.size': 1.5,
        'ytick.minor.size': 1.5,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'legend.frameon': False,
        'lines.linewidth': 0.8,
        'patch.linewidth': 0.5,
    })

set_nature_style()

# ============================================================
# Load data
# ============================================================
# The CSV has duplicate 'DATE' columns — read with pandas, let it auto-suffix
df = pd.read_csv('Unified_Machine_WideTable_2025.csv')

# Keep only the columns we need (first occurrence of each)
cols_needed = ['Date', 'Equipment.Id', 'Failure.Equipment.Type',
               'Op.Amperage', 'Op.Temperature', 'Op.Voltage', 'Rotor Speed']
# Find actual column names (pandas may have renamed duplicates)
available_cols = list(df.columns)
print("Available columns:", available_cols[:20])

# Use first columns that match
df_clean = df.iloc[:, :7].copy()
df_clean.columns = ['Date', 'Equipment_Id', 'Failure_Type',
                     'Amperage', 'Temperature', 'Voltage', 'Rotor_Speed']

# Convert numeric columns
for col in ['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed', 'Failure_Type']:
    df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')

df_clean = df_clean.dropna(subset=['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed', 'Failure_Type'])

# Convert Failure_Type to int for clean labels
df_clean['Failure_Type'] = df_clean['Failure_Type'].astype(int)

print(f"\nTotal records: {len(df_clean)}")
print(f"Failure types: {sorted(df_clean['Failure_Type'].unique())}")
print(f"\nFailure type distribution:")
print(df_clean['Failure_Type'].value_counts().sort_index())

# ============================================================
# Parameter definitions
# ============================================================
PARAMS = ['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed']
PARAM_LABELS = {
    'Amperage': 'Operating Amperage (A)',
    'Temperature': 'Operating Temperature (°C)',
    'Voltage': 'Operating Voltage (V)',
    'Rotor_Speed': 'Rotor Speed (RPM)'
}
PARAM_UNITS = {
    'Amperage': 'A',
    'Temperature': '°C',
    'Voltage': 'V',
    'Rotor_Speed': 'RPM'
}

# ============================================================
# Statistical computations
# ============================================================
def compute_stats(data, label):
    """Compute and print statistics for a dataset."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    stats = {}
    for param in PARAMS:
        values = data[param].dropna()
        stats[param] = {
            'mean': values.mean(),
            'median': values.median(),
            'std': values.std(),
            'min': values.min(),
            'max': values.max(),
            'count': len(values)
        }
        print(f"  {param:>15s}: n={len(values):>6d}  "
              f"mean={stats[param]['mean']:>10.4f}  "
              f"median={stats[param]['median']:>10.4f}  "
              f"std={stats[param]['std']:>10.4f}  "
              f"min={stats[param]['min']:>10.4f}  "
              f"max={stats[param]['max']:>10.4f}")
    return stats

# 1. Normal operation (Failure_Type == 0)
normal_data = df_clean[df_clean['Failure_Type'] == 0]
normal_stats = compute_stats(normal_data, "NORMAL OPERATION (Failure_Type = 0)")

# 2. Per fault type
fault_types = sorted(df_clean[df_clean['Failure_Type'] != 0]['Failure_Type'].unique())
fault_stats = {}
for ft in fault_types:
    ft_data = df_clean[df_clean['Failure_Type'] == ft]
    fault_stats[ft] = compute_stats(ft_data, f"FAILURE TYPE {ft}")

# 3. All faults combined
all_fault_data = df_clean[df_clean['Failure_Type'] != 0]
all_fault_stats = compute_stats(all_fault_data, "ALL FAULTS COMBINED (Failure_Type != 0)")

# ============================================================
# Plotting functions
# ============================================================
# Nature color palette — colorblind-friendly
NATURE_COLORS = ['#0C7BDC', '#E66100', '#5D3A9B', '#009E73',
                 '#F5C710', '#CC3311', '#AA4499', '#882255']
FAULT_COLORS = {0: '#555555'}  # gray for normal
FAULT_LABELS = {0: 'Normal'}

# Map failure type names
for ft in fault_types:
    FAULT_COLORS[ft] = NATURE_COLORS[ft - 1] if ft <= len(NATURE_COLORS) else NATURE_COLORS[(ft-1) % len(NATURE_COLORS)]
    FAULT_LABELS[ft] = f'Fault Type {ft}'

def add_panel_label(ax, label, x=-0.12, y=1.05):
    """Add bold panel label (a, b, c, d) to subplot."""
    ax.text(x, y, label, transform=ax.transAxes, fontsize=9,
            fontweight='bold', va='top', ha='left')

def plot_distribution_comparison(ax, datasets, labels, colors, param, title):
    """Plot overlaid KDE distributions for multiple datasets on a single axis."""
    for data, label, color in zip(datasets, labels, colors):
        values = data[param].dropna()
        if len(values) > 1:
            sns.kdeplot(values, ax=ax, color=color, label=label, linewidth=1.2, fill=False)
    ax.set_xlabel(PARAM_LABELS[param])
    ax.set_ylabel('Density')
    ax.set_title(title, fontsize=7, fontweight='normal')
    ax.yaxis.set_major_locator(ticker.MaxNLocator(4))
    ax.xaxis.set_major_locator(ticker.MaxNLocator(5))


# ============================================================
# FIGURE 1: Normal operation — distribution of all 4 parameters
# ============================================================
fig1, axes1 = plt.subplots(2, 2, figsize=(7.2, 5.5))  # Nature single-column ~89mm * 2
axes1 = axes1.flatten()

for i, param in enumerate(PARAMS):
    ax = axes1[i]
    values = normal_data[param].dropna()
    # Histogram + KDE
    sns.histplot(values, kde=True, ax=ax, color='#0C7BDC', alpha=0.6,
                 edgecolor='white', linewidth=0.3, stat='density')
    ax.set_xlabel(PARAM_LABELS[param])
    ax.set_ylabel('Density')
    # Add statistics annotation
    s = normal_stats[param]
    textstr = f"μ = {s['mean']:.2f}\nMed = {s['median']:.2f}\nσ = {s['std']:.2f}\nn = {s['count']}"
    ax.text(0.97, 0.97, textstr, transform=ax.transAxes, fontsize=5.5,
            va='top', ha='right', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor='gray', linewidth=0.3, alpha=0.85))
    add_panel_label(ax, chr(97 + i))

fig1.suptitle('Parameter Distributions During Normal Operation', fontsize=9,
              fontweight='bold', y=1.02)
fig1.tight_layout()
fig1.savefig('figure1_normal_operation.png', dpi=300)
fig1.savefig('figure1_normal_operation.pdf')
print("\nSaved: figure1_normal_operation.png / .pdf")

# ============================================================
# FIGURE 2: Per fault type — distribution comparison for each parameter
# ============================================================
n_faults = len(fault_types)
fig2, axes2 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes2 = axes2.flatten()

for i, param in enumerate(PARAMS):
    ax = axes2[i]
    # Normal reference
    sns.kdeplot(normal_data[param].dropna(), ax=ax, color='#888888',
                label='Normal', linewidth=0.8, linestyle='--', alpha=0.5)
    for ft in fault_types:
        ft_data = df_clean[df_clean['Failure_Type'] == ft]
        values = ft_data[param].dropna()
        if len(values) > 1:
            sns.kdeplot(values, ax=ax, color=FAULT_COLORS[ft],
                        label=FAULT_LABELS[ft], linewidth=1.2)
    ax.set_xlabel(PARAM_LABELS[param])
    ax.set_ylabel('Density')
    ax.yaxis.set_major_locator(ticker.MaxNLocator(4))
    ax.xaxis.set_major_locator(ticker.MaxNLocator(5))
    add_panel_label(ax, chr(97 + i))

# Single legend for all subplots
handles, labels = axes2[0].get_legend_handles_labels()
fig2.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 1.02),
            ncol=n_faults + 1, fontsize=6, frameon=False)

fig2.suptitle('Parameter Distributions by Failure Type vs. Normal Operation',
              fontsize=9, fontweight='bold', y=1.10)
fig2.tight_layout()
fig2.savefig('figure2_per_fault_type.png', dpi=300)
fig2.savefig('figure2_per_fault_type.pdf')
print("Saved: figure2_per_fault_type.png / .pdf")

# ============================================================
# FIGURE 3: All faults combined — distribution of all 4 parameters
# ============================================================
fig3, axes3 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes3 = axes3.flatten()

for i, param in enumerate(PARAMS):
    ax = axes3[i]
    fault_values = all_fault_data[param].dropna()
    normal_values = normal_data[param].dropna()

    # Overlay normal vs fault
    sns.histplot(normal_values, kde=True, ax=ax, color='#888888', alpha=0.35,
                 edgecolor='white', linewidth=0.3, stat='density', label='Normal')
    sns.histplot(fault_values, kde=True, ax=ax, color='#CC3311', alpha=0.45,
                 edgecolor='white', linewidth=0.3, stat='density', label='Fault')

    # Statistics
    fs = all_fault_stats[param]
    ns = normal_stats[param]
    textstr = (f"Fault: μ={fs['mean']:.2f}, σ={fs['std']:.2f}\n"
               f"Normal: μ={ns['mean']:.2f}, σ={ns['std']:.2f}")
    ax.text(0.97, 0.97, textstr, transform=ax.transAxes, fontsize=5.5,
            va='top', ha='right', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor='gray', linewidth=0.3, alpha=0.85))

    ax.set_xlabel(PARAM_LABELS[param])
    ax.set_ylabel('Density')
    ax.yaxis.set_major_locator(ticker.MaxNLocator(4))
    add_panel_label(ax, chr(97 + i))

handles, labels = axes3[0].get_legend_handles_labels()
fig3.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 1.02),
            ncol=2, fontsize=6, frameon=False)

fig3.suptitle('Parameter Distributions: Normal vs. Fault Conditions',
              fontsize=9, fontweight='bold', y=1.08)
fig3.tight_layout()
fig3.savefig('figure3_all_faults.png', dpi=300)
fig3.savefig('figure3_all_faults.pdf')
print("Saved: figure3_all_faults.png / .pdf")

# ============================================================
# FIGURE 4: Summary statistics comparison (mean ± std bar chart)
# ============================================================
fig4, axes4 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes4 = axes4.flatten()

x_labels = ['Normal'] + [FAULT_LABELS[ft] for ft in fault_types]
x_positions = np.arange(len(x_labels))
bar_width = 0.35

for i, param in enumerate(PARAMS):
    ax = axes4[i]
    means = [normal_stats[param]['mean']]
    stds = [normal_stats[param]['std']]
    for ft in fault_types:
        means.append(fault_stats[ft][param]['mean'])
        stds.append(fault_stats[ft][param]['std'])

    colors_bar = ['#888888'] + [FAULT_COLORS[ft] for ft in fault_types]
    bars = ax.bar(x_positions, means, bar_width, yerr=stds, capsize=2,
                  color=colors_bar, edgecolor='white', linewidth=0.3,
                  error_kw={'linewidth': 0.5, 'capsize': 1.5})

    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels, rotation=15, ha='right', fontsize=5.5)
    ax.set_ylabel(PARAM_LABELS[param], fontsize=6)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
    add_panel_label(ax, chr(97 + i))

fig4.suptitle('Mean ± Std of Parameters by Condition', fontsize=9,
              fontweight='bold', y=1.02)
fig4.tight_layout()
fig4.savefig('figure4_summary_bars.png', dpi=300)
fig4.savefig('figure4_summary_bars.pdf')
print("Saved: figure4_summary_bars.png / .pdf")

# ============================================================
# FIGURE 5: Box plot comparison
# ============================================================
fig5, axes5 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes5 = axes5.flatten()

for i, param in enumerate(PARAMS):
    ax = axes5[i]
    plot_data = []
    plot_labels = []
    plot_colors = []

    # Normal
    plot_data.append(normal_data[param].dropna().values)
    plot_labels.append('Normal')
    plot_colors.append('#888888')

    for ft in fault_types:
        ft_vals = df_clean[df_clean['Failure_Type'] == ft][param].dropna().values
        plot_data.append(ft_vals)
        plot_labels.append(FAULT_LABELS[ft])
        plot_colors.append(FAULT_COLORS[ft])

    bp = ax.boxplot(plot_data, patch_artist=True, widths=0.5,
                    medianprops={'linewidth': 0.8, 'color': 'black'},
                    whiskerprops={'linewidth': 0.5},
                    capprops={'linewidth': 0.5},
                    flierprops={'markersize': 1.5, 'markerfacecolor': 'black',
                                'markeredgewidth': 0.3})

    for patch, color in zip(bp['boxes'], plot_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_xticklabels(plot_labels, rotation=15, ha='right', fontsize=5.5)
    ax.set_ylabel(PARAM_LABELS[param], fontsize=6)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
    add_panel_label(ax, chr(97 + i))

fig5.suptitle('Parameter Distributions: Box Plot by Condition', fontsize=9,
              fontweight='bold', y=1.02)
fig5.tight_layout()
fig5.savefig('figure5_boxplots.png', dpi=300)
fig5.savefig('figure5_boxplots.pdf')
print("Saved: figure5_boxplots.png / .pdf")

# ============================================================
# FIGURE 6: Violin plot comparison
# ============================================================
fig6, axes6 = plt.subplots(2, 2, figsize=(7.2, 5.5))
axes6 = axes6.flatten()

for i, param in enumerate(PARAMS):
    ax = axes6[i]
    plot_data = []
    plot_labels = []
    plot_colors = []

    plot_data.append(normal_data[param].dropna().values)
    plot_labels.append('Normal')
    plot_colors.append('#888888')

    for ft in fault_types:
        ft_vals = df_clean[df_clean['Failure_Type'] == ft][param].dropna().values
        plot_data.append(ft_vals)
        plot_labels.append(FAULT_LABELS[ft])
        plot_colors.append(FAULT_COLORS[ft])

    positions = np.arange(len(plot_data))
    vp = ax.violinplot(plot_data, positions=positions, showmeans=True,
                       showmedians=True, widths=0.6)

    for j, body in enumerate(vp['bodies']):
        body.set_facecolor(plot_colors[j])
        body.set_alpha(0.6)
        body.set_edgecolor(plot_colors[j])
        body.set_linewidth(0.5)

    for partname in ('cbars', 'cmins', 'cmaxes', 'cmeans', 'cmedians'):
        if partname in vp:
            vp[partname].set_linewidth(0.5)
            vp[partname].set_color('black')

    ax.set_xticks(positions)
    ax.set_xticklabels(plot_labels, rotation=15, ha='right', fontsize=5.5)
    ax.set_ylabel(PARAM_LABELS[param], fontsize=6)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
    add_panel_label(ax, chr(97 + i))

fig6.suptitle('Parameter Distributions: Violin Plot by Condition', fontsize=9,
              fontweight='bold', y=1.02)
fig6.tight_layout()
fig6.savefig('figure6_violins.png', dpi=300)
fig6.savefig('figure6_violins.pdf')
print("Saved: figure6_violins.png / .pdf")

# ============================================================
# Summary statistics table
# ============================================================
print("\n" + "="*90)
print("  SUMMARY STATISTICS TABLE")
print("="*90)

# Build table
rows = []
# Normal row
row = ['Normal']
for param in PARAMS:
    s = normal_stats[param]
    row.append(f"{s['mean']:.3f}±{s['std']:.3f}")
    row.append(f"{s['median']:.3f}")
rows.append(row)

# Per fault type
for ft in fault_types:
    row = [FAULT_LABELS[ft]]
    for param in PARAMS:
        s = fault_stats[ft][param]
        row.append(f"{s['mean']:.3f}±{s['std']:.3f}")
        row.append(f"{s['median']:.3f}")
    rows.append(row)

# All faults
row = ['All Faults']
for param in PARAMS:
    s = all_fault_stats[param]
    row.append(f"{s['mean']:.3f}±{s['std']:.3f}")
    row.append(f"{s['median']:.3f}")
rows.append(row)

# Print header
header = f"{'Condition':<18s}"
for param in PARAMS:
    header += f"  {param:>24s}"
print(header)
print(f"{'':18s}" + "  ".join([f"{'Mean±Std':>12s}  {'Median':>10s}" for _ in PARAMS]))
print("-" * 120)

for row in rows:
    line = f"{row[0]:<18s}"
    for j in range(1, len(row), 2):
        line += f"  {row[j]:>12s}  {row[j+1]:>10s}"
    print(line)

print("\nAll figures saved. Analysis complete.")
