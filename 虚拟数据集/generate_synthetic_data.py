#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟数据集生成器 v1.0
输出到 虚拟数据集/ 目录
"""
import pandas as pd
import numpy as np
import sys, os
from pathlib import Path

# 强制UTF-8输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

np.random.seed(42)

BASE = Path(__file__).resolve().parent
RAW = BASE / "原始数据集"
OUT = BASE / "虚拟数据集"
OUT.mkdir(exist_ok=True)

# ════════════════════════════════════════════════
# Step 0: 提取统计参数
# ════════════════════════════════════════════════

log_raw = pd.read_csv(RAW / "MACHINE_LOG_DATA._2025.csv")
summary_raw = pd.read_csv(RAW / "MACHINE_SUMMARY_DATA._2025.csv")
assembly_raw = pd.read_csv(RAW / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv")
tests_raw = pd.read_csv(RAW / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv")

normal_raw = log_raw[log_raw["Failure.Equipment.Type"] == 0]
PARAMS = ["Op.Voltage", "Op.Amperage", "Op.Temperature", "Rotor Speed"]

# 逐设备正常mu/sigma
device_stats = {}
for mid, grp in normal_raw.groupby("Equipment.Id"):
    device_stats[mid] = {
        c: {"mu": float(grp[c].mean()), "sigma": max(float(grp[c].std()), 0.5)}
        for c in PARAMS
    }

# 故障组偏移
fault_offsets = {}
for group_name, type_list in [
    ("high_voltage", [4, 5]),
    ("thermal", [3, 6, 7, 8, 9]),
    ("subtle", [1, 2]),
]:
    subset = log_raw[log_raw["Failure.Equipment.Type"].isin(type_list)]
    fault_offsets[group_name] = {
        c: float(subset[c].mean() - normal_raw[c].mean()) for c in PARAMS
    }

# 故障类型分布
ft_counts = log_raw["Failure.Equipment.Type"].value_counts().to_dict()
fault_type_probs = np.array([ft_counts.get(i, 0) for i in range(1, 10)], dtype=float)
fault_type_probs = fault_type_probs / fault_type_probs.sum()

# 逐设备故障率
per_machine_fr = {}
for mid, grp in log_raw.groupby("Equipment.Id"):
    per_machine_fr[mid] = float((grp["Failure.Equipment.Type"] > 0).mean())

def fault_group(ft):
    if ft in (4, 5): return "high_voltage"
    if ft in (3, 6, 7, 8, 9): return "thermal"
    return "subtle"

TIMESTAMPS = [
    "0:00", "0:14", "0:28", "0:43", "0:57",
    "1:12", "1:26", "1:40", "1:55", "2:09",
    "2:24", "2:38", "2:52", "3:07", "3:21",
    "3:36", "3:50", "4:04", "4:19", "4:33",
    "4:48", "5:02", "5:16", "5:31", "5:45",
    "6:00", "6:14", "6:28", "6:43", "6:57"
]
N_DAYS = 10
N_STEPS = len(TIMESTAMPS)
MACHINES = sorted(device_stats.keys())

print(f"[STATS] {len(MACHINES)} machines x {N_DAYS} days x {N_STEPS} steps = {len(MACHINES)*N_DAYS*N_STEPS} log records")

# ════════════════════════════════════════════════
# Step 1: 生成 MACHINE_LOG (30,000行)
# ════════════════════════════════════════════════

print("\n[1/4] Generating MACHINE_LOG...")

# 目标总故障率 ~40%（比原始72%低，模拟10天生产中偶尔出问题）
TARGET_FAULT_RATE = 0.40

# 为每台设备设计故障计划
device_fault_plan = {}
for mid in MACHINES:
    orig_fr = per_machine_fr.get(mid, 0.72)
    # 保留原始设备的相对故障倾向: 高危设备仍然高危, 只是比率调低
    scaled_fr = orig_fr * (TARGET_FAULT_RATE / 0.72)  # 72%->40% scale
    scaled_fr = np.clip(scaled_fr, 0.20, 0.65)

    # 目标故障记录数
    target_faults = int(N_STEPS * N_DAYS * scaled_fr)
    # 每个故障事件占 4-8 条记录
    events_needed = max(1, target_faults // 6)

    # 随机选择故障发生的step位置（在整个10天中）
    all_steps = list(range(N_STEPS * N_DAYS))
    event_centers = sorted(np.random.choice(all_steps, size=min(events_needed, len(all_steps)), replace=False))

    fault_schedule = {}  # global_step -> fault_type
    for center in event_centers:
        ft = int(np.random.choice(range(1, 10), p=fault_type_probs))
        duration = int(np.random.randint(4, 9))
        for offset in range(duration):
            gs = center + offset
            if gs < N_STEPS * N_DAYS:
                if gs not in fault_schedule:
                    fault_schedule[gs] = ft

    # 渐进漂移: 故障前3步开始过渡
    for center in event_centers:
        ft = fault_schedule.get(center, 1)
        for pre in range(1, 4):
            gs = center - pre
            if gs >= 0 and gs not in fault_schedule:
                fault_schedule[gs] = -ft  # 负值标记为漂移阶段

    device_fault_plan[mid] = fault_schedule

# 生成LOG
rows = []
for mid in MACHINES:
    mu_i = device_stats[mid]
    fault_schedule = device_fault_plan[mid]

    for d in range(N_DAYS):
        date_str = f"2025/5/{18 + d}"
        for s in range(N_STEPS):
            t = TIMESTAMPS[s]
            gs = d * N_STEPS + s  # global step

            fs_entry = fault_schedule.get(gs, 0)
            is_drift = fs_entry < 0
            ft = abs(fs_entry)

            if ft > 0 and not is_drift:
                current_type = ft
                fg = fault_group(ft)
                offset = fault_offsets[fg]
            elif is_drift:
                current_type = 0
                fg = fault_group(ft)
                offset = fault_offsets[fg]
            else:
                current_type = 0
                fg = None
                offset = {c: 0.0 for c in PARAMS}

            noise_v = np.random.normal(0, mu_i["Op.Voltage"]["sigma"])
            noise_a = np.random.normal(0, mu_i["Op.Amperage"]["sigma"])
            noise_t = np.random.normal(0, mu_i["Op.Temperature"]["sigma"])
            noise_r = np.random.normal(0, mu_i["Rotor Speed"]["sigma"])

            # 漂移比例
            if is_drift:
                ramp = 0.3  # 故障前轻微预兆
            elif current_type > 0:
                ramp = 1.0
            else:
                ramp = 0.0

            V = mu_i["Op.Voltage"]["mu"] + noise_v + offset.get("Op.Voltage", 0) * ramp
            A = mu_i["Op.Amperage"]["mu"] + noise_a + offset.get("Op.Amperage", 0) * ramp
            T = mu_i["Op.Temperature"]["mu"] + noise_t + offset.get("Op.Temperature", 0) * ramp
            R = mu_i["Rotor Speed"]["mu"] + noise_r + offset.get("Rotor Speed", 0) * ramp

            # V-A弱耦合
            A += (noise_v / max(mu_i["Op.Voltage"]["sigma"], 0.5)) * mu_i["Op.Amperage"]["sigma"] * 0.12

            # 日内温升
            warmup = max(0, 1.0 - s / 10.0) * 0.015
            T += T * warmup
            A += A * warmup * 0.3

            V = np.clip(V, 50, 500)
            A = np.clip(A, 8, 65)
            T = np.clip(T, 35, 210)
            R = np.clip(R, 80, 720)

            rows.append({
                "Date": f"{date_str} {t}",
                "Equipment.Id": mid,
                "Failure.Equipment.Type": current_type,
                "Op.Amperage": round(A, 6),
                "Op.Temperature": round(T, 6),
                "Op.Voltage": round(V, 6),
                "Rotor Speed": round(R, 6),
            })

log_df = pd.DataFrame(rows)
log_df = log_df[[
    "Date", "Equipment.Id", "Failure.Equipment.Type",
    "Op.Amperage", "Op.Temperature", "Op.Voltage", "Rotor Speed"
]]

ft_new = log_df["Failure.Equipment.Type"].value_counts(normalize=True).sort_index()
dates_s = log_df["Date"].str.split(" ").str[0]
print(f"  Rows: {len(log_df)}")
print(f"  Machines: {log_df['Equipment.Id'].nunique()}")
print(f"  Normal(Type=0): {ft_new.get(0, 0)*100:.1f}%")
print(f"  Fault(Type>0): {(1-ft_new.get(0,0))*100:.1f}%")
print(f"  Date range: {dates_s.min()} ~ {dates_s.max()}")

log_df.to_csv(OUT / "MACHINE_LOG_DATA._2025.csv", index=False, encoding="utf-8")
print("  [OK] MACHINE_LOG_DATA._2025.csv")

# ════════════════════════════════════════════════
# Step 2: 复制 SUMMARY (100行不变)
# ════════════════════════════════════════════════

print("\n[2/4] Copying MACHINE_SUMMARY...")
summary_raw.to_csv(OUT / "MACHINE_SUMMARY_DATA._2025.csv", index=False, encoding="utf-8")
print(f"  [OK] MACHINE_SUMMARY_DATA._2025.csv ({len(summary_raw)} rows)")

# ════════════════════════════════════════════════
# Step 3: 生成 PRODUCT_ASSEMBLY (100台 x 9 = 900行)
# ════════════════════════════════════════════════

print("\n[3/4] Generating PRODUCT_ASSEMBLY...")

def sample_failed_tests(fault_rate):
    if fault_rate < 0.30:
        probs = [0.75, 0.10, 0.10, 0.03, 0.02]
    elif fault_rate < 0.50:
        probs = [0.53, 0.10, 0.19, 0.07, 0.11]
    else:
        probs = [0.30, 0.08, 0.28, 0.14, 0.20]
    return int(np.random.choice([0, 1, 2, 3, 4], p=np.array(probs) / sum(probs)))

TEST_BASE = {
    "ANALOG TESTS": 0.05, "BOUNDARY SCAN TESTS": 0.05,
    "CONTACT TEST": 0.05, "DISCHARGING CAPACITORS": 0.05,
    "FRAMESCAN": 0.03, "POWER UP": 0.05,
    "SHORTS TESTING": 0.03, "TESTJET": 0.05,
}

assembly_rows = []
line_opts = ["Line1", "Line2", "Line3"]

for i, mid in enumerate(MACHINES, 1):
    fr = per_machine_fr.get(mid, 0.72)
    scaled_fr = fr * (TARGET_FAULT_RATE / 0.72)  # align with log fault rate
    case_id = f"CA{i}"
    line = line_opts[i % 3]
    products = []

    # 3 CAPACITOR
    for cj in range(1, 4):
        cid = f"CR{i*10 + cj}"
        products.append(("CAPACITOR_LOAD", f"C{i*100 + cj*10 + 1}", case_id, cid))
    # 3 CIRCUIT
    for cj in range(1, 4):
        cid = f"CR{i*10 + cj}"
        products.append(("CIRCUIT_LOAD", cid, case_id, None))
    # 3 CASE
    for cj in range(1, 4):
        products.append(("CASE_LOAD", f"{case_id}_T{cj}", None, None))

    for wtype, serial, pcase, pcirc in products:
        ft_val = sample_failed_tests(scaled_fr)
        row = {
            "ANALOG TESTS": int(np.random.random() < TEST_BASE["ANALOG TESTS"]),
            "BOUNDARY SCAN TESTS": int(np.random.random() < TEST_BASE["BOUNDARY SCAN TESTS"]),
            "CONTACT TEST": int(np.random.random() < TEST_BASE["CONTACT TEST"]),
            "DISCHARGING CAPACITORS": int(np.random.random() < TEST_BASE["DISCHARGING CAPACITORS"]),
            "FAILED_TESTS": ft_val,
            "FRAMESCAN": int(np.random.random() < TEST_BASE["FRAMESCAN"]),
            "HIGH_RANGE_VALUE_TESTS": int(np.clip(np.random.poisson(1.2 + scaled_fr * 2.5), 0, 4)),
            "LINE": line,
            "LOW_RANGE_VALUE_TESTS": int(np.clip(np.random.poisson(1.2 + scaled_fr * 2.5), 0, 4)),
            "MACHINE": mid,
            "PARENT_CASE_NO": pcase,
            "PARENT_CIRCUIT_NO": pcirc,
            "POWERED ANALOG": 0,
            "POWER UP": int(np.random.random() < TEST_BASE["POWER UP"]),
            "SERIAL NO": serial,
            "SHORTS TESTING": int(np.random.random() < TEST_BASE["SHORTS TESTING"]),
            "TESTJET": int(np.random.random() < TEST_BASE["TESTJET"]),
            "WRKSTN_NM": wtype,
        }
        assembly_rows.append(row)

assembly_df = pd.DataFrame(assembly_rows)
assembly_df = assembly_df[assembly_raw.columns.tolist()]

ft_asm = assembly_df["FAILED_TESTS"].value_counts(normalize=True).sort_index()
print(f"  Rows: {len(assembly_df)}")
print(f"  Machines: {assembly_df['MACHINE'].nunique()}")
print(f"  FAILED_TESTS: 0={ft_asm.get(0,0)*100:.0f}% 1={ft_asm.get(1,0)*100:.0f}% 2={ft_asm.get(2,0)*100:.0f}% 3={ft_asm.get(3,0)*100:.0f}% 4={ft_asm.get(4,0)*100:.0f}%")

assembly_df.to_csv(OUT / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv", index=False, encoding="utf-8")
print("  [OK] PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv")

# ════════════════════════════════════════════════
# Step 4: 生成 PRODUCT_TESTS (约2,800行)
# ════════════════════════════════════════════════

print("\n[4/4] Generating PRODUCT_TESTS...")

PARAM_DIST = [
    ("Boundary scan tests", "farad", 0.186),
    ("Discharging capacitors", "farad", 0.186),
    ("Contact Test", "farad", 0.186),
    ("Power up UUT", "Pass", 0.186),
    ("Testjet", "farad", 0.062),
    ("Analog tests", "Voltage", 0.062),
    ("Powered analog", "Voltage", 0.062),
    ("Shorts testing", "Failed", 0.036),
    ("FrameScan", "farad", 0.036),
]
p_names = [x[0] for x in PARAM_DIST]
p_units = {x[0]: x[1] for x in PARAM_DIST}
p_probs = np.array([x[2] for x in PARAM_DIST])
p_probs = p_probs / p_probs.sum()

TESTS_DATES = ["2025/5/28", "2025/5/29", "2025/5/30", "2025/5/31", "2025/6/1"]

def map_oos(fr):
    if fr < 0.30: return np.random.uniform(0.03, 0.12)
    elif fr < 0.50: return np.random.uniform(0.20, 0.40)
    else: return np.random.uniform(0.45, 0.85)

# 构建 assembly serial -> 元数据 映射
serial_meta = {}
for _, row in assembly_df.iterrows():
    serial_meta[row["SERIAL NO"]] = {
        "machine": row["MACHINE"],
        "pcase": row["PARENT_CASE_NO"] if pd.notna(row["PARENT_CASE_NO"]) else None,
        "pcirc": row["PARENT_CIRCUIT_NO"] if pd.notna(row["PARENT_CIRCUIT_NO"]) else None,
        "wtype": row["WRKSTN_NM"],
    }

tests_rows = []
for mid in MACHINES:
    fr = per_machine_fr.get(mid, 0.72)
    scaled_fr = fr * (TARGET_FAULT_RATE / 0.72)
    oos_rate = map_oos(scaled_fr)
    line = line_opts[MACHINES.index(mid) % 3]

    # 每台设备的所有产品serial
    my_serials = [s for s, m in serial_meta.items() if m["machine"] == mid]

    for serial in my_serials:
        n_params = int(np.random.choice([3, 4], p=[0.5, 0.5]))
        chosen = list(np.random.choice(p_names, size=min(n_params, len(p_names)), replace=False, p=p_probs))

        for param in chosen:
            is_oos = np.random.random() < oos_rate
            if is_oos:
                measmt = int(np.random.uniform(1, 9)) if np.random.random() < 0.5 else int(np.random.uniform(101, 160))
            else:
                measmt = int(np.clip(np.random.normal(45, 25), 10, 100))

            unit = p_units[param]
            if param in ("Power up UUT", "Shorts testing"):
                unit = "Pass" if not is_oos else "Failed"

            meta = serial_meta[serial]
            date = np.random.choice(TESTS_DATES)

            tests_rows.append({
                "DATE": date,
                "LINE": line,
                "MACHINE": mid,
                "SERIAL NO": serial,
                "PARENT_CIRCUIT_NO": meta["pcirc"],
                "PARENT_CASE_NO": meta["pcase"],
                "PARAMETER": param,
                "MEASMT_VALUE": measmt,
                "LWR_SPEC_LIMIT": 10,
                "UPR_SPEC_LIMIT": 100,
                "WRKSTN_NM": meta["wtype"],
                "UNIT_OF_MEAS": unit,
            })

tests_df = pd.DataFrame(tests_rows)
tests_df = tests_df[tests_raw.columns.tolist()]

oos_pct = ((tests_df["MEASMT_VALUE"] < 10) | (tests_df["MEASMT_VALUE"] > 100)).mean() * 100
print(f"  Rows: {len(tests_df)}")
print(f"  Machines: {tests_df['MACHINE'].nunique()}")
print(f"  Out-of-spec rate: {oos_pct:.1f}%")
print(f"  Unique serials: {tests_df['SERIAL NO'].nunique()}")

tests_df.to_csv(OUT / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv", index=False, encoding="utf-8")
print("  [OK] PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv")

# ════════════════════════════════════════════════
# Step 5: 验证
# ════════════════════════════════════════════════

print("\n" + "=" * 60)
print("FINAL VALIDATION")
print("=" * 60)

log_v = pd.read_csv(OUT / "MACHINE_LOG_DATA._2025.csv")
n_m = log_v["Equipment.Id"].nunique()
rpp = log_v.groupby("Equipment.Id").size()
t0 = (log_v["Failure.Equipment.Type"] == 0).mean() * 100

print(f"\n[LOG] {len(log_v)} rows, {n_m} machines")
print(f"  Records/machine: {rpp.min()}-{rpp.max()} (mean={rpp.mean():.0f})")
print(f"  Normal: {t0:.1f}%, Fault: {100-t0:.1f}%")
for c in PARAMS:
    v = log_v[c]
    print(f"  {c}: {v.mean():.1f} +/- {v.std():.1f} [{v.min():.0f}, {v.max():.0f}]")

asm_v = pd.read_csv(OUT / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv")
tst_v = pd.read_csv(OUT / "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv")
asm_m = set(asm_v["MACHINE"].unique())
tst_m = set(tst_v["MACHINE"].unique())

print(f"\n[ASSEMBLY] {len(asm_v)} rows, {asm_v['MACHINE'].nunique()} machines")
print(f"[TESTS]   {len(tst_v)} rows, {tst_v['MACHINE'].nunique()} machines")
print(f"[CROSS]   Machines identical: {asm_m == tst_m}")

# 验证 ASSEMBLY serials 覆盖 TESTS serials
asm_s = set(asm_v["SERIAL NO"].unique())
tst_s = set(tst_v["SERIAL NO"].unique())
print(f"[CROSS]   Assembly serials: {len(asm_s)}, Tests serials: {len(tst_s)}")
print(f"[CROSS]   Tests serials subset of Assembly: {tst_s.issubset(asm_s)}")

print(f"\nAll files in: {OUT}")
