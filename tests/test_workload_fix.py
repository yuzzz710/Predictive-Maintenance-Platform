"""Verify assigned_machines appears in list query."""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.workflow_engine import get_technicians, assign_technicians_to_work_order

# Assign CNC_025 to 王热控(3) + 赵温度(4)
print("Assigning CNC_025 to [3,4]...")
assign_technicians_to_work_order("CNC_025", [3, 4])

# Check list query includes assigned_machines
techs = get_technicians()
for t in techs[:5]:
    machines = t.get("assigned_machines", [])
    machine_ids = [m["machine_id"] for m in machines]
    print(f"  {t['name']}: wl={t['current_workload']}, machines={machine_ids}")

# Clean up
from gateway.workflow_engine import release_technician_from_work_order
for a in (t.get("assigned_machines", []) for t in get_technicians() if t.get("assigned_machines")):
    for m in a:
        for tid in [3,4]:
            release_technician_from_work_order(m["machine_id"], tid)
print("Cleaned up!")
