"""Test procurement status change + auto restock."""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, 'web-dashboard'))
os.chdir(os.path.join(PROJ, 'web-dashboard'))

from gateway.inventory_connector import *
from gateway.workflow_engine import initialize
initialize()

# 1. Set stock to 0 to force shortage
print("1. Set o-ring_set stock to 0...")
from gateway.inventory_connector import load_inventory, save_inventory
inv = load_inventory()
for item in inv:
    if item["part_name"] == "o-ring_set":
        old = item["current_stock"]
        item["current_stock"] = 0
        break
save_inventory(inv)
print(f"   o-ring_set: {old} -> 0")

# 2. Generate procurement order
print("2. Generate procurement orders...")
orders = generate_procurement_orders()
print(f"   Generated: {len(orders)}")
for o in orders:
    print(f"   {o['order_id']}: {o['part_name']} x{o['quantity_ordered']} status={o['status']}")

# 3. Update to 已入库
if orders:
    oid = orders[0]["order_id"]
    print(f"\n3. Set {oid} to 已入库...")
    r = update_procurement_status(oid, "已入库")
    print(f"   Result: {r}")

    # 4. Check stock updated
    s = check_stock("o-ring_set")
    for p in s["parts"]:
        print(f"4. Stock after restock: {p['current_stock']} (was 0)")
        assert p["current_stock"] > 0, "Stock should have been updated!"
        print("   PASS!")

    # 5. Verify order status
    orders2 = get_procurement_orders()
    for o in orders2:
        if o["order_id"] == oid:
            print(f"5. Order status: {o['status']}")
            assert o["status"] == "已入库"
            print("   PASS!")

# Clean up - restore stock
inv2 = load_inventory()
for item in inv2:
    if item["part_name"] == "o-ring_set":
        item["current_stock"] = 50
save_inventory(inv2)
print("\nDone - cleaned up!")
