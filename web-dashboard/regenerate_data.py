#!/usr/bin/env python3
"""修正 dashboard 数据文件，使与原始数据集保持一致"""
import csv, json, os, sys, math

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def read_csv(path):
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fieldnames):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

# ============================================================
# 1. Fix variance_decomp.csv — normalize percentages to 100%
# ============================================================
print("1. Fixing variance_decomp.csv ...")
vd = read_csv(os.path.join(DATA_DIR, 'variance_decomp.csv'))
for row in vd:
    inter = float(row['inter_pct'])
    intra = float(row['intra_pct'])
    total = inter + intra
    row['inter_pct'] = str(round(inter / total * 100, 2))
    row['intra_pct'] = str(round(intra / total * 100, 2))
write_csv(os.path.join(DATA_DIR, 'variance_decomp.csv'), vd,
          ['parameter','total','inter_machine','intra_machine','inter_pct','intra_pct'])
print(f"   Fixed {len(vd)} parameters → now sum to 100%")

# ============================================================
# 2. Fix cost_risk.csv — proper risk tiers using tertiles
# ============================================================
print("2. Fixing cost_risk.csv risk tiers ...")
cr = read_csv(os.path.join(DATA_DIR, 'cost_risk.csv'))
costs = sorted([float(row['cost_at_risk']) for row in cr])
n = len(costs)
t1 = costs[n // 3]       # 33rd percentile
t2 = costs[2 * n // 3]    # 66th percentile
print(f"   Tertile thresholds: Low≤${t1:.0f} <Medium≤${t2:.0f} <High")

for row in cr:
    c = float(row['cost_at_risk'])
    if c <= t1: row['risk_tier'] = 'Low'
    elif c <= t2: row['risk_tier'] = 'Medium'
    else: row['risk_tier'] = 'High'
write_csv(os.path.join(DATA_DIR, 'cost_risk.csv'), cr, list(cr[0].keys()))
print(f"   Tiers: {sum(1 for r in cr if r['risk_tier']=='High')} High, "
      f"{sum(1 for r in cr if r['risk_tier']=='Medium')} Medium, "
      f"{sum(1 for r in cr if r['risk_tier']=='Low')} Low")

# ============================================================
# 3. Fix work_orders.csv — correct z-score values in suggestions
# ============================================================
print("3. Fixing work_orders.csv z-score references ...")
zs = read_csv(os.path.join(DATA_DIR, 'z_scores.csv'))
wo = read_csv(os.path.join(DATA_DIR, 'work_orders.csv'))

# Build per-machine max abs z-scores
machine_z = {}
for row in zs:
    mid = row['Equipment.Id']
    zv = abs(float(row['z_Voltage']))
    za = abs(float(row['z_Amperage']))
    zt = abs(float(row['z_Temperature']))
    zc = abs(float(row['z_composite']))
    if mid not in machine_z:
        machine_z[mid] = {'V': zv, 'A': za, 'T': zt, 'C': zc}
    else:
        machine_z[mid]['V'] = max(machine_z[mid]['V'], zv)
        machine_z[mid]['A'] = max(machine_z[mid]['A'], za)
        machine_z[mid]['T'] = max(machine_z[mid]['T'], zt)
        machine_z[mid]['C'] = max(machine_z[mid]['C'], zc)

for row in wo:
    mid = row['machine_id']
    if mid in machine_z:
        mz = machine_z[mid]
        sug = row['suggestion']
        # Fix "Amperage (z=X.X)" pattern
        import re
        sug = re.sub(r'Amperage \(z=[\d.]+\)',
                     f"Amperage (z={mz['A']:.1f})", sug)
        sug = re.sub(r'Voltage \(z=[\d.-]+\)',
                     f"Voltage (z={mz['V']:.1f})", sug)
        sug = re.sub(r'Temperature \(z=[\d.-]+\)',
                     f"Temperature (z={mz['T']:.1f})", sug)
        sug = re.sub(r'Z-score max = [\d.]+',
                     f"Z-score max = {mz['C']:.1f}", sug)
        row['suggestion'] = sug

write_csv(os.path.join(DATA_DIR, 'work_orders.csv'), wo, list(wo[0].keys()))
print(f"   Fixed {len(wo)} work orders")

# ============================================================
# 4. Fix decision_summary.json — reaggregate from source CSVs
# ============================================================
print("4. Fixing decision_summary.json ...")

# Build per-machine mean z_composite for classification
from collections import defaultdict
machine_z_list = defaultdict(list)
for row in zs:
    machine_z_list[row['Equipment.Id']].append(float(row['z_composite']))

# Classify: work_order machines use their alert_level, remaining use mean z_composite
wo_alerts = {row['machine_id']: row['alert_level'] for row in wo}
alert_dist = {'ALARM': 0, 'WARNING': 0, 'WATCH': 0, 'NORMAL': 0}

for mid in machine_z_list:
    if mid in wo_alerts:
        alert_dist[wo_alerts[mid]] += 1
    else:
        mz = sum(machine_z_list[mid]) / len(machine_z_list[mid])
        if mz >= 2.5: alert_dist['ALARM'] += 1
        elif mz >= 2.0: alert_dist['WARNING'] += 1
        elif mz >= 1.5: alert_dist['WATCH'] += 1
        else: alert_dist['NORMAL'] += 1

# Action distribution from work orders
action_dist = {}
for row in wo:
    a = row['action_type']
    action_dist[a] = action_dist.get(a, 0) + 1

# Top 5 urgent
top5 = sorted(wo, key=lambda r: (-float(r['urgency_score']), -float(r.get('cost_at_risk', 0))))[:5]
top5_list = []
for w in top5:
    top5_list.append({
        'machine_id': w['machine_id'],
        'urgency': round(float(w['urgency_score'])),
        'action': w['action_type'],
        'cost': round(float(w['cost_at_risk']), 2)
    })

summary = {
    'n_machines_evaluated': len(machine_z_list),
    'alert_distribution': alert_dist,
    'action_distribution': action_dist,
    'n_work_orders': len(wo),
    'top_5_urgent': top5_list
}

with open(os.path.join(DATA_DIR, 'decision_summary.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f"   Alert dist: {alert_dist}")
print(f"   Action dist: {action_dist}")
print(f"   Top 5 urgent saved")

print("\nAll data fixes applied.")
