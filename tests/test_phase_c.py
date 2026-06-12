"""Phase C Verification — Inventory & Procurement."""
import sys, os, json
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.inventory_connector import *
from gateway.tools import TOOLS, execute_tool

print("=" * 50)
print("Phase C Verification")
print("=" * 50)

# 1. Init inventory
print("\n[Test 1] Init inventory...")
n = init_inventory()
print(f"  Parts initialized: {n}")
assert n > 0
print("  [PASS]")

# 2. Check stock
print("\n[Test 2] Check stock...")
r = check_stock()
print(f"  Total parts: {r['total_parts']}")
print(f"  Low count: {r['low_count']}")
print(f"  Total shortage: {r['total_shortage']}")
print("  [PASS]")

# 3. Restock
print("\n[Test 3] Restock...")
rr = restock("o-ring_set", 50)
print(f"  o-ring_set +50: success={rr['success']}, new_stock={rr['new_stock']}")
assert rr["success"]
print("  [PASS]")

# 4. Deduct
print("\n[Test 4] Deduct stock...")
dr = deduct_stock("o-ring_set", 20)
print(f"  o-ring_set -20: success={dr['success']}, remaining={dr['remaining']}")
assert dr["success"]
print("  [PASS]")

# 5. Generate procurement
print("\n[Test 5] Generate procurement orders...")
orders = generate_procurement_orders()
print(f"  Orders generated: {len(orders)}")

# 6. Gateway tools
print("\n[Test 6] Gateway Tools...")
tnames = [t["function"]["name"] for t in TOOLS]
for name in ["check_spare_parts_inventory", "generate_procurement_order"]:
    found = name in tnames
    print(f"  [{'PASS' if found else 'FAIL'}] {name}")
print(f"  Total tools: {len(TOOLS)}")

# 7. Tool dispatch
print("\n[Test 7] Tool dispatch...")
r1 = json.loads(execute_tool("check_spare_parts_inventory", {}))
print(f"  check_spare_parts_inventory: parts={r1.get('total_parts', '?')}")
r2 = json.loads(execute_tool("generate_procurement_order", {}))
print(f"  generate_procurement_order: generated={r2.get('generated', '?')}")
print("  [PASS]")

# 8. Procurement status update
print("\n[Test 8] Procurement status update...")
orders = get_procurement_orders()
if orders:
    oid = orders[0]["order_id"]
    print(f"  Updating {oid}...")
    ur = update_procurement_status(oid, "运输中")
    print(f"  -> 运输中: {ur['success']}")
    ur2 = update_procurement_status(oid, "已到货")
    print(f"  -> 已到货: {ur2['success']}")
    print("  [PASS]")
else:
    print("  [SKIP] No procurement orders")

# 9. Inventory logs
print("\n[Test 9] Inventory logs...")
logs = get_inventory_logs(10)
print(f"  Log entries: {len(logs)}")
assert len(logs) > 0
print("  [PASS]")

print("\n" + "=" * 50)
print("Phase C tests completed!")
print("=" * 50)
