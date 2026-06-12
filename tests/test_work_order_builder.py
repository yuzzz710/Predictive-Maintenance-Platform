"""Test work order builder across 100 machines."""
import sys, os, json, csv
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.work_order_builder import build_work_order_context

print("=" * 60)
print("Work Order Builder Test — All 100 Machines")
print("=" * 60)

# Read all machine IDs from z_scores.csv
z_path = WEB + "\\data\\z_scores.csv"
machine_ids = set()
with open(z_path, "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        machine_ids.add(row.get("Equipment.Id", "").strip())
machine_ids = sorted(machine_ids)
print(f"Machines in z_scores.csv: {len(machine_ids)}")

# Read plan CSV mids
plan_path = WEB + "\\data\\industrial_maintenance_plan.csv"
plan_mids = set()
if os.path.exists(plan_path):
    with open(plan_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            plan_mids.add(row.get("machine_id", "").strip())
print(f"Machines in plan CSV: {len(plan_mids)}")

# Test 5 machines: 2 in plan CSV, 3 not in plan CSV
test_machines = []
in_plan = [m for m in machine_ids if m in plan_mids][:2]
not_in_plan = [m for m in machine_ids if m not in plan_mids][:3]
test_machines = in_plan + not_in_plan

print(f"\nTesting {len(test_machines)} machines ({len(in_plan)} in plan, {len(not_in_plan)} not in plan):")
print()

all_pass = True
for mid in test_machines:
    ctx = build_work_order_context(mid)
    in_plan_flag = mid in plan_mids
    status = "PASS" if ctx.get("primary_pattern") and ctx.get("technician_type") else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"  [{status}] {mid} (in_plan={in_plan_flag}):")
    print(f"    pattern: {ctx.get('primary_pattern','?')}")
    print(f"    action: {ctx.get('recommended_action','?')}")
    print(f"    technician: {ctx.get('technician_type','?')} x{ctx.get('technician_count','?')}")
    print(f"    priority: {ctx.get('maintenance_priority','?')}")
    print(f"    health: {ctx.get('health_score','?')}")
    print(f"    cost_risk: ${ctx.get('cost_at_risk','?')}")
    parts = ctx.get('spare_parts','[]')
    print(f"    spare_parts: {parts[:80]}...")
    print(f"    reasoning: {ctx.get('reasoning','?')[:80]}")
    # Validate required fields
    required = ['primary_pattern', 'recommended_action', 'technician_type', 'technician_count',
                'maintenance_priority', 'health_score', 'cost_at_risk', 'spare_parts']
    for field in required:
        if not ctx.get(field):
            print(f"    [WARN] Missing field: {field}")
            all_pass = False
    print()

print("=" * 60)
print(f"Result: {'ALL PASS' if all_pass else 'SOME FAILED'}")
print("=" * 60)
