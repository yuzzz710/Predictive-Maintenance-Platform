"""Clean up test assignment data from test_email_assignment.py."""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.workflow_engine import release_technician_from_work_order, get_technician, get_work_order_technicians

# Check CNC_012 assignments
assigned = get_work_order_technicians("CNC_012")
print(f"CNC_012 assigned technicians: {len(assigned)}")
for a in assigned:
    print(f"  [{a['id']}] {a['name']}")

# Release all CNC_012 assignments
for a in assigned:
    release_technician_from_work_order("CNC_012", a["id"])
    print(f"  Released: {a['name']}")

# Also check CNC_005 (from earlier Phase D test)
assigned2 = get_work_order_technicians("CNC_005")
print(f"\nCNC_005 assigned technicians: {len(assigned2)}")
for a in assigned2:
    release_technician_from_work_order("CNC_005", a["id"])
    print(f"  Released: {a['name']}")

# Verify
t3 = get_technician(3)
t4 = get_technician(4)
print(f"\nAfter cleanup:")
print(f"  王热控 (id=3): workload={t3['current_workload']}")
print(f"  赵温度 (id=4): workload={t4['current_workload']}")
print("Done!")
