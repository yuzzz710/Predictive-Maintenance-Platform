import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

df = pd.read_csv(r'C:\Users\ASUS\PycharmProjects\PythonProject\MACHINE_LOG_DATA._2025.csv')

fault_labels = {
    0: 'No Fault (0)',
    1: 'Fault Type 1',
    2: 'Fault Type 2',
    3: 'Fault Type 3',
    4: 'Fault Type 4',
    5: 'Fault Type 5',
    6: 'Fault Type 6',
    7: 'Fault Type 7',
    8: 'Fault Type 8',
    9: 'Fault Type 9',
}

# ============ 1. Overall record count by fault type ============
record_counts = df['Failure.Equipment.Type'].value_counts().sort_index()
record_pct = (record_counts / record_counts.sum() * 100).round(2)

# ============ 2. Devices experiencing each fault type ============
device_fault = df.groupby('Failure.Equipment.Type')['Equipment.Id'].nunique().sort_index()
device_pct = (device_fault / df['Equipment.Id'].nunique() * 100).round(2)

# ============ 3. Per-device dominant fault (most frequent non-zero fault per device) ============
fault_only = df[df['Failure.Equipment.Type'] != 0]
dominant = fault_only.groupby(['Equipment.Id', 'Failure.Equipment.Type']).size().reset_index(name='count')
dominant = dominant.loc[dominant.groupby('Equipment.Id')['count'].idxmax()]

# ============ Print statistics ============
print("=" * 70)
print("1. 记录级统计 - 各故障类型记录数及比例 (Record-level count & proportion)")
print("=" * 70)
print(f"{'故障类型':<14} {'记录数':<10} {'比例(%)':<12}")
print("-" * 36)
for ft in sorted(fault_labels):
    cnt = record_counts.get(ft, 0)
    pct = record_pct.get(ft, 0)
    label = fault_labels[ft]
    print(f"{label:<14} {cnt:<10} {pct:<12}")

print(f"\n总记录数: {record_counts.sum()}")

print("\n" + "=" * 70)
print("2. 设备级统计 - 每种故障类型出现在多少台设备上")
print("=" * 70)
print(f"{'故障类型':<14} {'设备数':<10} {'设备比例(%)':<12}")
print("-" * 36)
for ft in sorted(fault_labels):
    dc = device_fault.get(ft, 0)
    dp = device_pct.get(ft, 0)
    label = fault_labels[ft]
    print(f"{label:<14} {dc:<10} {dp:<12}")

print(f"\n总设备数: {df['Equipment.Id'].nunique()}")

print("\n" + "=" * 70)
print("3. 每台设备的主要故障类型 (非0故障中次数最多的类型)")
print("=" * 70)
dom_counts = dominant['Failure.Equipment.Type'].value_counts().sort_index()
for ft in sorted(dom_counts.index):
    print(f"  Fault Type {ft}: {dom_counts[ft]} 台设备")

# ============ Plotting ============
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('Machine Fault Type Analysis - 100 Devices', fontsize=16, fontweight='bold')

types = list(range(10))
colors = ['#2ecc71'] + [plt.cm.Reds(v) for v in np.linspace(0.4, 0.9, 9)]

# --- Plot A: Record count bar chart ---
ax1 = axes[0, 0]
bars1 = ax1.bar(types, [record_counts.get(i, 0) for i in types], color=colors, edgecolor='black')
ax1.set_title('A. Record Count by Fault Type', fontsize=13, fontweight='bold')
ax1.set_xlabel('Fault Type')
ax1.set_ylabel('Number of Records')
ax1.set_xticks(types)
for bar, val in zip(bars1, [record_counts.get(i, 0) for i in types]):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, str(val),
             ha='center', va='bottom', fontsize=9, fontweight='bold')

# --- Plot B: Record proportion pie chart (fault types 1-9 only) ---
ax2 = axes[0, 1]
fault_mask = [i for i in range(1, 10)]
fault_vals = [record_counts.get(i, 0) for i in fault_mask]
pie_colors = plt.cm.tab10(np.linspace(0, 1, 9))
wedges, texts, autotexts = ax2.pie(fault_vals, labels=[f'Type {i}' for i in fault_mask],
                                     autopct='%1.1f%%', colors=pie_colors,
                                     explode=[0.02]*9, pctdistance=0.75)
ax2.set_title('B. Fault Type Distribution (Types 1-9, excluding No-Fault)', fontsize=13, fontweight='bold')
for t in autotexts:
    t.set_fontsize(8)

# --- Plot C: Device count by fault type ---
ax3 = axes[1, 0]
bars3 = ax3.bar(types, [device_fault.get(i, 0) for i in types], color=colors, edgecolor='black')
ax3.set_title('C. Number of Devices Experiencing Each Fault Type', fontsize=13, fontweight='bold')
ax3.set_xlabel('Fault Type')
ax3.set_ylabel('Number of Devices')
ax3.set_xticks(types)
ax3.set_ylim(0, 105)
for bar, val in zip(bars3, [device_fault.get(i, 0) for i in types]):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, str(val),
             ha='center', va='bottom', fontsize=9, fontweight='bold')

# --- Plot D: Dominant fault type per device ---
ax4 = axes[1, 1]
dom_vals = [dom_counts.get(i, 0) for i in range(1, 10)]
bars4 = ax4.bar(range(1, 10), dom_vals, color=plt.cm.Oranges(np.linspace(0.4, 0.9, 9)), edgecolor='black')
ax4.set_title('D. Dominant Fault Type per Device (most frequent non-zero)', fontsize=13, fontweight='bold')
ax4.set_xlabel('Fault Type')
ax4.set_ylabel('Number of Devices')
ax4.set_xticks(range(1, 10))
for bar, val in zip(bars4, dom_vals):
    ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(val),
             ha='center', va='bottom', fontsize=9, fontweight='bold')

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig(r'C:\Users\ASUS\PycharmProjects\PythonProject\fault_type_analysis.png', dpi=150, bbox_inches='tight')
plt.show()
print("\n图表已保存至: fault_type_analysis.png")
print("""
A. 按故障类型的记录计数
这里列出的是各种故障类型出现的总次数（即所有设备中该故障被记录的频次之和）。

但数据呈现不一致：Type 3 给出了绝对数 832，而其他类型（Type 4~10）只给出了百分比（12.5%、9.9%等）。
推测：832 可能是所有故障记录的总数，而 Type 3 的百分比被误写成绝对数；或者 832 就是 Type 3 的实际次数，那么总记录数需要根据百分比反推（例如 Type 4 占 12.5%，则总记录数 = 832 / ? 矛盾）。
更合理的解释：832 是总记录数，且 Type 3 的占比应为 12.5% 左右（与 B 部分 Type 3 的 12.5% 吻合），此处可能排版错位。因此，A 部分的实际含义是各故障类型的记录数占总记录数的百分比。

B. 故障类型分布（类型 1~9，排除"无故障"）
这里列出了 Type 1 到 Type 10 的百分比（标题说 1~9 但实际包含 10）。

各类型占比接近，在 9.7%~12.5% 之间，说明故障类型分布相对均匀。

注意：Type 3 在此占 12.5%，与 A 部分中 Type 3 的绝对数 832 可能存在对应关系（如果总记录数 = 832 / 0.125 = 6656，但其他百分比总和为 100% 吗？粗略加总 B 部分：9.7+11.0+12.5+9.9+11.4+11.3+11.3+10.6+12.0+11.6 = 111.3？显然有误，实际应总和 100%。可能是手抄错误，但趋势明确：各类故障出现次数相近。）

C. 经历每种故障类型的设备数量
统计的是至少发生过一次该故障的设备台数（同一设备可同时有多种故障）。

数据范围：Type 1 有 87 台，Type 2 有 91 台，…… Type 9 有 93 台。

总和远大于 100（计算得 833），证实了"一设备多故障"的情况。

各类型的设备覆盖面很广（87~96 台），说明几乎所有设备都经历过大多数故障类型。

D. 每台设备的主要故障类型（出现次数最多的非零故障）
对每台设备，找出其发生频率最高的故障类型（若多个并列则取其一？未说明）。

统计结果：以 Type 1 为主导的设备有 21 台，Type 2 有 13 台，Type 3~8 各有 9 台。

已列出的设备数总和为 21+13+9×6 = 21+13+54 = 88 台。剩余 12 台可能以 Type 9 或 Type 10 为主导，或存在无故障设备（未列出）。

这说明不同设备有各自"最常犯"的故障，但分布不均：Type 1 作为主导的比例明显偏高。
""")