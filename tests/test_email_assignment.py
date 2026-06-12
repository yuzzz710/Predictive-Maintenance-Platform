"""End-to-end test: assign technicians and verify emails."""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.workflow_engine import initialize, get_technicians, assign_technicians_to_work_order, get_work_order_detail
from gateway.notification_service import send_work_order_assignment, _is_configured

print("=" * 50)
print("Email Assignment End-to-End Test")
print("=" * 50)

initialize()
techs = get_technicians()
print(f"\nSMTP configured: {_is_configured()}")
print(f"Technicians ({len(techs)}):")
for t in techs:
    print(f"  [{t['id']}] {t['name']} | email={t['email']} | type={t['technician_type']}")

# Assign CNC_012 to 王热控 (id=3) and 赵温度 (id=4)
print("\n--- Assigning CNC_012 to 王热控 + 赵温度 ---")
r = assign_technicians_to_work_order("CNC_012", [3, 4])
print(f"Result: {r['success']}")

# Get detail and send emails
detail = get_work_order_detail("CNC_012")
if detail:
    plan = detail.get("plan_data", {})
    print(f"Fault: {plan.get('primary_pattern', '?')}")
    print(f"Action: {plan.get('recommended_action', '?')}")

    for tid in [3, 4]:
        t_info = next((t for t in techs if t["id"] == tid), None)
        if t_info:
            print(f"\nSending to: {t_info['name']} <{t_info['email']}>")
            ok = send_work_order_assignment("CNC_012", detail, to_email=t_info["email"])
            print(f"  Result: {'SENT - check QQ mailbox!' if ok else 'FAILED (SMTP may need real credentials)'}")
else:
    print("No detail found for CNC_012")

print("\nDone!")
