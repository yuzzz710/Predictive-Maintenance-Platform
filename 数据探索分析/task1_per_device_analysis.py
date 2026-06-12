"""
Task 1: Per-device fault type count and proportion analysis.
Also generates a summary figure.
"""
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
    'xtick.labelsize': 5.5, 'ytick.labelsize': 5.5, 'legend.fontsize': 5.5,
    'figure.dpi': 300, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05, 'axes.linewidth': 0.5,
    'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
    'axes.spines.top': False, 'axes.spines.right': False,
    'legend.frameon': False, 'lines.linewidth': 0.8,
})

NATURE_COLORS = ['#0C7BDC', '#E66100', '#5D3A9B', '#009E73',
                 '#F5C710', '#CC3311', '#AA4499', '#882255', '#332288', '#117733']
NATURE_CMAP = plt.cm.colors.ListedColormap(
    ['#E8E8E8', '#0C7BDC', '#E66100', '#5D3A9B', '#009E73',
     '#F5C710', '#CC3311', '#AA4499', '#882255', '#332288', '#117733'])

df = pd.read_csv('Unified_Machine_WideTable_2025.csv')
df = df.iloc[:, :7].copy()
df.columns = ['Date', 'Equipment_Id', 'Failure_Type',
              'Amperage', 'Temperature', 'Voltage', 'Rotor_Speed']
for col in ['Amperage', 'Temperature', 'Voltage', 'Rotor_Speed', 'Failure_Type']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.dropna()
df['Failure_Type'] = df['Failure_Type'].astype(int)

# ============================================================
# Per-device fault distribution
# ============================================================
# Pivot: rows = equipment, columns = failure type
pivot = df.pivot_table(index='Equipment_Id', columns='Failure_Type',
                        aggfunc='size', fill_value=0)
pivot.columns = [f'Type_{int(c)}' for c in pivot.columns]
pivot['Total'] = pivot.sum(axis=1)

# Proportions
prop = pivot.div(pivot['Total'], axis=0)

# Print summary
print("=" * 80)
print("  TASK 1: Per-Device Fault Distribution (first 20 devices)")
print("=" * 80)
print("\nCounts (first 20):")
print(pivot.head(20).to_string())
print("\nProportions (first 20):")
print(prop.head(20).to_string())

# Summary stats
print("\n--- Per-Device Summary ---")
print(f"Total devices: {len(pivot)}")
print(f"Avg records per device: {pivot['Total'].mean():.1f} (min={pivot['Total'].min()}, max={pivot['Total'].max()})")
for c in pivot.columns:
    if c != 'Total':
        ft = int(c.split('_')[1])
        label = 'Normal' if ft == 0 else f'Fault Type {ft}'
        n_devices_with = (pivot[c] > 0).sum()
        avg_pct = prop[c].mean() * 100
        print(f"  {label:<18s}: {n_devices_with:>4d}/100 devices have records, avg {avg_pct:>5.1f}% per device")

# ============================================================
# FIGURE 1a: Per-device fault type heatmap
# ============================================================
fig1, axes1 = plt.subplots(1, 2, figsize=(8, 7))

# Panel a: Stacked bar — proportion per device
ax = axes1[0]
devices = list(pivot.index)
type_cols = [c for c in pivot.columns if c != 'Total']
ft_labels = ['Normal' if '0' in c else f'F{c.split("_")[1]}' for c in type_cols]
colors_list = ['#AAAAAA'] + [NATURE_COLORS[i % len(NATURE_COLORS)] for i in range(len(type_cols)-1)]

bottom = np.zeros(len(devices))
for j, col in enumerate(type_cols):
    vals = prop[col].values
    ax.barh(devices, vals, left=bottom, color=colors_list[j], height=0.8,
            label=ft_labels[j], edgecolor='white', linewidth=0.1)
    bottom += vals

ax.set_xlabel('Proportion')
ax.set_ylabel('Equipment ID')
ax.set_title('Per-Device Fault Type Proportion', fontsize=8, fontweight='bold')
ax.xaxis.set_major_formatter(ticker.PercentFormatter(1.0))
ax.set_yticks(range(0, 100, 5))
ax.set_yticklabels(devices[::5], fontsize=4)

# Simplify legend
handles, labels = ax.get_legend_handles_labels()
# Group fault types into one legend entry
ax.legend(handles[:4], labels[:4], loc='upper right', fontsize=4.5, ncol=2)

# Panel b: Summary bar — total records per fault type across all devices
ax = axes1[1]
type_totals = [pivot[c].sum() for c in type_cols]
ax.barh(ft_labels, type_totals, color=colors_list, edgecolor='white', linewidth=0.3, height=0.7)
for j, (label, total) in enumerate(zip(ft_labels, type_totals)):
    ax.text(total + 5, j, f'{total} ({total/sum(type_totals)*100:.1f}%)',
            va='center', fontsize=5.5)
ax.set_xlabel('Total Records')
ax.set_title('Global Fault Type Distribution', fontsize=8, fontweight='bold')
ax.xaxis.set_major_locator(ticker.MaxNLocator(5))

fig1.suptitle('Per-Device Fault Type Analysis (100 CNC Machines)', fontsize=9, fontweight='bold', y=1.01)
fig1.tight_layout()
fig1.savefig('figure15_per_device_faults.png', dpi=300)
fig1.savefig('figure15_per_device_faults.pdf')
print("\nSaved: figure15_per_device_faults.png/.pdf")

# ============================================================
# FIGURE 1b: Devices with most faults
# ============================================================
fig2, ax2 = plt.subplots(figsize=(7.2, 5))

fault_cols = [c for c in type_cols if '0' not in c]
pivot['Fault_Count'] = pivot[fault_cols].sum(axis=1)
pivot['Normal_Count'] = pivot['Type_0'] if 'Type_0' in pivot.columns else 0
pivot_sorted = pivot.sort_values('Fault_Count', ascending=False)

# Top/bottom by fault count
top20 = pivot_sorted.head(20)
bottom20 = pivot_sorted.tail(20)

x = np.arange(20)
width = 0.35

ax2.bar(x - width/2, top20['Normal_Count'], width, color='#AAAAAA', label='Normal',
        edgecolor='white', linewidth=0.2)
ax2.bar(x - width/2, top20['Fault_Count'], width, bottom=top20['Normal_Count'],
        color='#CC3311', label='Fault', edgecolor='white', linewidth=0.2)

ax2.set_xticks(x)
ax2.set_xticklabels(top20.index, rotation=45, ha='right', fontsize=5.5)
ax2.set_ylabel('Record Count')
ax2.set_title('Top 20 Devices by Fault Count', fontsize=8, fontweight='bold')
ax2.legend(fontsize=6, loc='upper right')
ax2.yaxis.set_major_locator(ticker.MaxNLocator(6))

fig2.suptitle('Device-Level Fault Load Distribution', fontsize=9, fontweight='bold', y=1.01)
fig2.tight_layout()
fig2.savefig('figure16_device_fault_load.png', dpi=300)
fig2.savefig('figure16_device_fault_load.pdf')
print("Saved: figure16_device_fault_load.png/.pdf")

# ============================================================
# FIGURE 1c: Fault type diversity per device
# ============================================================
fig3, ax3 = plt.subplots(figsize=(7.2, 4))

# Count unique fault types per device
fault_type_cols = [c for c in type_cols if c != 'Type_0']
pivot['Unique_Fault_Types'] = (pivot[fault_type_cols] > 0).sum(axis=1)
type_diversity = pivot['Unique_Fault_Types'].value_counts().sort_index()

ax3.bar(type_diversity.index, type_diversity.values, color='#0C7BDC',
        edgecolor='white', linewidth=0.3)
for x_val, y_val in zip(type_diversity.index, type_diversity.values):
    ax3.text(x_val, y_val + 0.5, str(y_val), ha='center', fontsize=7, fontweight='bold')
ax3.set_xlabel('Number of Different Fault Types Experienced')
ax3.set_ylabel('Number of Devices')
ax3.set_title('Fault Type Diversity per Device', fontsize=9, fontweight='bold')
ax3.xaxis.set_major_locator(ticker.MaxNLocator(10))
ax3.yaxis.set_major_locator(ticker.MaxNLocator(6))

fig3.tight_layout()
fig3.savefig('figure17_fault_diversity.png', dpi=300)
fig3.savefig('figure17_fault_diversity.pdf')
print("Saved: figure17_fault_diversity.png/.pdf")

# ============================================================
# Export per-device table to CSV
# ============================================================
pivot.to_csv('per_device_fault_distribution.csv')
print("\nExported: per_device_fault_distribution.csv")
print("Analysis complete.")
