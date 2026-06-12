"""Phase A Verification — Gateway Tools dispatch."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web-dashboard'))
os.chdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web-dashboard'))

from gateway.tools import TOOLS, execute_tool

print("=" * 60)
print("Phase A Verification — Gateway Tools")
print("=" * 60)

print(f"\nTotal tools: {len(TOOLS)}")
expected_new = ['list_work_order_status', 'assign_and_notify_work_order',
                'update_work_order_status', 'get_work_order_tracking_detail']
for name in expected_new:
    found = any(t["function"]["name"] == name for t in TOOLS)
    print(f"  [{('PASS' if found else 'FAIL')}] {name}")

# Test tool dispatch
print("\n--- Tool: list_work_order_status ---")
result = json.loads(execute_tool("list_work_order_status", {}))
print(f"  work_orders count: {len(result.get('work_orders', []))}")
print(f"  total: {result.get('total', '?')}")
print(f"  statistics: total_wo={result.get('statistics', {}).get('total_work_orders', '?')}")
print(f"  text_summary: {result.get('text_summary', '')[:80]}...")
print("  [PASS]")

print("\n--- Tool: get_work_order_tracking_detail ---")
result2 = json.loads(execute_tool("get_work_order_tracking_detail", {"machine_id": "CNC_005"}))
print(f"  success: {result2.get('success')}")
print(f"  status: {result2.get('status')} ({result2.get('status_label', '')})")
print(f"  history entries: {len(result2.get('state_history', []))}")
print(f"  plan_data: {'plan_data' in result2}")
print(f"  text_summary: {result2.get('text_summary', '')[:100]}...")
print("  [PASS]")

print("\n--- Tool: assign_and_notify_work_order ---")
# Test assign on a pending WO
result_a = json.loads(execute_tool("list_work_order_status", {"status": "pending"}))
if result_a.get("work_orders"):
    mid = result_a["work_orders"][0]["machine_id"]
    result3 = json.loads(execute_tool("assign_and_notify_work_order", {"machine_id": mid}))
    print(f"  machine: {mid}")
    print(f"  success: {result3.get('success')}")
    print(f"  status: {result3.get('status')}")
    print(f"  email_sent: {result3.get('email_sent')}")
    print(f"  message: {result3.get('message', '')}")
    print(f"  text_summary: {result3.get('text_summary', '')[:80]}...")
    print("  [PASS]")
else:
    print("  [SKIP] No pending work orders")

print("\n--- Tool: update_work_order_status ---")
# Find an assigned WO and update it
result_b = json.loads(execute_tool("list_work_order_status", {"status": "assigned"}))
if result_b.get("work_orders"):
    mid = result_b["work_orders"][0]["machine_id"]
    result4 = json.loads(execute_tool("update_work_order_status", {
        "machine_id": mid,
        "new_status": "in_progress",
        "notes": "Test: begin repair",
        "triggered_by": "test"
    }))
    print(f"  machine: {mid}")
    print(f"  success: {result4.get('success')}")
    print(f"  old_status -> new_status: {result4.get('old_status')} -> {result4.get('new_status')}")
    print(f"  email_sent: {result4.get('email_sent')}")
    print(f"  message: {result4.get('message', '')}")
    print("  [PASS]")
else:
    print("  [SKIP] No assigned work orders")

print("\n" + "=" * 60)
print("All Gateway Tools tests completed!")
print("=" * 60)
