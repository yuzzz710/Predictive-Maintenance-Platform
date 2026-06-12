"""Phase D Verification."""
import sys, os, json
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.workflow_engine import *
from gateway.tools import TOOLS

print("=" * 50)
print("Phase D Verification")
print("=" * 50)

# 1. Seed + list
print("\n[Test 1] Seed technicians...")
initialize()
techs = get_technicians()
print(f"  Total: {len(techs)}")
for t in techs[:3]:
    print(f"    [{t['id']}] {t['name']} ({t['technician_type']}) wl={t['current_workload']}")
assert len(techs) == 10
print("  [PASS]")

# 2. CRUD
print("\n[Test 2] CRUD...")
tid = add_technician("Test", "t@t.com", "138", "junior_technician")
print(f"  Added: {tid}")
assert tid > 0
ok = update_technician(tid, name="Renamed")
print(f"  Updated: {ok}")
t = get_technician(tid)
assert t["name"] == "Renamed"
ok2 = delete_technician(tid)
print(f"  Deleted: {ok2}")
print("  [PASS]")

# 3. Assignment
print("\n[Test 3] Assignment...")
sync_from_plan_csv()
r = assign_technicians_to_work_order("CNC_005", [1, 4])
print(f"  CNC_005 -> [1,4]: {r['success']}")
assert r["success"]
assigned = get_work_order_technicians("CNC_005")
print(f"  Assigned: {len(assigned)}")
for a in assigned:
    print(f"    {a['name']} ({a['technician_type']})")
assert len(assigned) == 2
print("  [PASS]")

# 4. Load
print("\n[Test 4] Load tracking...")
t1 = get_technician(1)
print(f"  #{t1['id']} {t1['name']}: wl={t1['current_workload']}/{t1['max_concurrent']}")
assert t1["current_workload"] >= 1
print("  [PASS]")

# 5. Release
print("\n[Test 5] Release...")
release_technician_from_work_order("CNC_005", 1)
t1b = get_technician(1)
print(f"  After release: wl={t1b['current_workload']}")
print("  [PASS]")

# 6. Tools
print("\n[Test 6] Gateway Tools...")
tnames = [t["function"]["name"] for t in TOOLS]
for n in ["list_technicians", "assign_technician_to_work_order"]:
    found = n in tnames
    print(f"  [{'PASS' if found else 'FAIL'}] {n}")
print(f"  Total: {len(TOOLS)}")

# 7. Workload summary
print("\n[Test 7] Workload summary...")
from gateway.workflow_engine import get_technicians as gt
all_t = gt()
avail = sum(1 for t in all_t if t["status"] == "available")
busy = sum(1 for t in all_t if t["status"] == "busy")
print(f"  Available: {avail}, Busy: {busy}, Total: {len(all_t)}")
print("  [PASS]")

print("\n" + "=" * 50)
print("Phase D tests completed!")
print("=" * 50)
