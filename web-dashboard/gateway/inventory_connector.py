"""
Inventory Connector — CSV-based spare parts inventory management.
===================================================================
Simulates ERP inventory data. Stores stock levels in inventory_snapshot.csv
and procurement orders in procurement_orders.csv under DASHBOARD_DATA.

When real ERP integration is needed, replace the CSV read/write functions
with API calls — the public interface (check_stock, restock, etc.) stays same.

Workflow:
  1. init_inventory() → auto-populate initial stock from catalog × 2
  2. check_stock() → compare demand vs stock, return status
  3. generate_procurement_orders() → create purchase orders for shortages
  4. restock() → receive parts, update stock, close procurement order
  5. deduct_stock() → consume parts when work order is completed
"""

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from gateway.config import DASHBOARD_DATA, PROJECT_ROOT

INVENTORY_PATH = DASHBOARD_DATA / "inventory_snapshot.csv"
PROCUREMENT_PATH = DASHBOARD_DATA / "procurement_orders.csv"
CATALOG_PATH = PROJECT_ROOT / "skills" / "predictive-maintenance-decision" / "scripts" / "data" / "spare_parts_catalog.json"

STATUS_LABELS = {
    "ok": "充足",
    "low": "不足",
    "out": "缺货",
}

PROCUREMENT_STATUS = [
    "申请中", "已下单", "运输中", "已到货", "已入库",
]

SUPPLIERS = {
    "rotor_assembly": "精密机械供应",
    "bearing_kit": "SKF授权代理",
    "seal_kit": "密封技术公司",
    "lubrication_kit": "润滑材料公司",
    "o-ring_set": "标准件供应",
    "cooling_fan_assembly": "散热设备厂",
    "thermal_paste": "导热材料公司",
    "temperature_sensor_pt100": "传感器科技",
    "heat_sink_assembly": "散热设备厂",
    "power_supply_module": "电源模块公司",
    "voltage_regulator_ic": "电子元件供应",
    "capacitor_bank": "电子元件供应",
    "motor_driver_module": "驱动设备公司",
    "current_sensor_hall": "传感器科技",
    "power_cable_set": "电缆供应",
    "fastener_kit": "标准件供应",
    "cleaning_kit": "清洁用品公司",
}


def _load_catalog() -> List[Dict]:
    """Load the spare parts catalog JSON."""
    if CATALOG_PATH.exists():
        try:
            data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            catalog = data.get("catalog", [])
            common = data.get("common_parts", [])
            parts = []
            for entry in catalog:
                parts.extend(entry.get("parts", []))
            parts.extend(common)
            return parts
        except Exception as e:
            print(f"[inventory] Failed to load catalog: {e}")

    # Fallback
    return [
        {"name": "rotor_assembly", "part_number": "ROT-001", "unit_cost": 2800, "lead_time_days": 7, "quantity_per_machine": 1},
        {"name": "bearing_kit", "part_number": "BRG-001", "unit_cost": 85, "lead_time_days": 3, "quantity_per_machine": 2},
        {"name": "seal_kit", "part_number": "SL-001", "unit_cost": 45, "lead_time_days": 2, "quantity_per_machine": 1},
        {"name": "lubrication_kit", "part_number": "LUB-001", "unit_cost": 30, "lead_time_days": 2, "quantity_per_machine": 1},
        {"name": "o-ring_set", "part_number": "OR-001", "unit_cost": 8, "lead_time_days": 1, "quantity_per_machine": 1},
        {"name": "cooling_fan_assembly", "part_number": "CFA-001", "unit_cost": 180, "lead_time_days": 5, "quantity_per_machine": 1},
        {"name": "thermal_paste", "part_number": "TP-001", "unit_cost": 25, "lead_time_days": 2, "quantity_per_machine": 1},
        {"name": "temperature_sensor_pt100", "part_number": "TS-001", "unit_cost": 95, "lead_time_days": 3, "quantity_per_machine": 1},
        {"name": "heat_sink_assembly", "part_number": "HSA-001", "unit_cost": 320, "lead_time_days": 5, "quantity_per_machine": 1},
        {"name": "power_supply_module", "part_number": "PSM-001", "unit_cost": 450, "lead_time_days": 6, "quantity_per_machine": 1},
        {"name": "voltage_regulator_ic", "part_number": "VR-001", "unit_cost": 12, "lead_time_days": 2, "quantity_per_machine": 1},
        {"name": "capacitor_bank", "part_number": "CB-001", "unit_cost": 65, "lead_time_days": 2, "quantity_per_machine": 1},
    ]


def _compute_demand() -> Dict[str, int]:
    """Aggregate current spare parts demand from spare_parts_plan.csv."""
    plan_path = DASHBOARD_DATA / "spare_parts_plan.csv"
    demand = {}
    if not plan_path.exists():
        return demand

    parts_list = _load_catalog()
    qty_lookup = {p["name"]: p.get("quantity_per_machine", 1) for p in parts_list}

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("part_name", "").strip()
                if name:
                    qty = qty_lookup.get(name, 1)
                    demand[name] = demand.get(name, 0) + qty
    except Exception:
        pass
    return demand


def init_inventory() -> int:
    """Auto-generate initial inventory: stock = demand × 2, safety_stock = demand."""
    demand = _compute_demand()
    if not demand:
        print("[inventory] No demand data, skipping init")
        return 0

    parts_list = _load_catalog()
    catalog_map = {p["name"]: p for p in parts_list}

    rows = []
    for name, qty_needed in sorted(demand.items()):
        cat = catalog_map.get(name, {})
        safety = max(qty_needed, 5)
        rows.append({
            "part_name": name,
            "part_number": cat.get("part_number", ""),
            "unit_cost": cat.get("unit_cost", 0),
            "current_stock": qty_needed * 2,  # Initial: double the demand
            "safety_stock": safety,
            "reorder_point": safety,
            "supplier": SUPPLIERS.get(name, "通用供应商"),
            "lead_time_days": cat.get("lead_time_days", 3),
            "last_ordered": "",
            "location": f"W-{hash(name) % 100:02d}",
        })

    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "part_name", "part_number", "unit_cost", "current_stock",
            "safety_stock", "reorder_point", "supplier", "lead_time_days",
            "last_ordered", "location",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[inventory] Initialized {len(rows)} parts")
    return len(rows)


def load_inventory() -> List[Dict]:
    """Read inventory snapshot."""
    if not INVENTORY_PATH.exists():
        init_inventory()

    rows = []
    try:
        with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["current_stock"] = int(row.get("current_stock", 0) or 0)
                row["safety_stock"] = int(row.get("safety_stock", 0) or 0)
                row["reorder_point"] = int(row.get("reorder_point", 0) or 0)
                row["unit_cost"] = float(row.get("unit_cost", 0) or 0)
                row["lead_time_days"] = int(row.get("lead_time_days", 3) or 3)
                rows.append(row)
    except Exception:
        pass
    return rows


def save_inventory(rows: List[Dict]):
    """Write inventory snapshot back."""
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "part_name", "part_number", "unit_cost", "current_stock",
            "safety_stock", "reorder_point", "supplier", "lead_time_days",
            "last_ordered", "location",
        ])
        writer.writeheader()
        writer.writerows(rows)


def check_stock(part_name: str = "") -> Dict:
    """Check stock level for a part (or all parts). Returns status with demand comparison."""
    inventory = load_inventory()
    demand = _compute_demand()

    if part_name:
        inventory = [r for r in inventory if r["part_name"] == part_name]

    results = []
    for item in inventory:
        name = item["part_name"]
        needed = demand.get(name, 0)
        stock = item["current_stock"]
        shortage = max(0, needed - stock)

        if shortage == 0:
            status = "ok"
        elif stock > item["safety_stock"]:
            status = "low"
        else:
            status = "out"

        results.append({
            "part_name": name,
            "part_number": item["part_number"],
            "current_stock": stock,
            "safety_stock": item["safety_stock"],
            "demand": needed,
            "shortage": shortage,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "unit_cost": item["unit_cost"],
            "supplier": item["supplier"],
            "lead_time_days": item["lead_time_days"],
            "location": item["location"],
            "procurement_needed": shortage > 0,
            "suggested_order_qty": max(shortage, item["safety_stock"]) if shortage > 0 else 0,
        })

    total_shortage = sum(r["shortage"] for r in results)
    low_count = sum(1 for r in results if r["status"] != "ok")

    text_lines = [f"库存检查: {len(results)} 种零件, {low_count} 种不足, 总缺口 {total_shortage} 件"]
    for r in results:
        if r["status"] != "ok":
            text_lines.append(f"  {r['part_name']}: 库存{r['current_stock']}, 需求{r['demand']}, 缺口{r['shortage']}")

    return {
        "parts": results if not part_name else results,
        "total_parts": len(results),
        "low_count": low_count,
        "total_shortage": total_shortage,
        "text_summary": "\n".join(text_lines),
    }


def restock(part_name: str, qty: int) -> Dict:
    """Receive parts into inventory. Returns updated stock level."""
    inventory = load_inventory()
    success = False

    for item in inventory:
        if item["part_name"] == part_name:
            item["current_stock"] += qty
            item["last_ordered"] = datetime.now().isoformat()[:10]
            success = True
            break

    if not success:
        return {"success": False, "error": f"Part not found: {part_name}"}

    save_inventory(inventory)

    # Log to SQLite
    try:
        from gateway.workflow_engine import _get_conn, _init_db, _now
        conn = _get_conn()
        _init_db(conn)
        new_stock = next(r["current_stock"] for r in inventory if r["part_name"] == part_name)
        conn.execute(
            "INSERT INTO inventory_log (part_name, change_qty, reason, new_stock, created_at) VALUES (?, ?, ?, ?, ?)",
            (part_name, qty, "入库", new_stock, _now()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[inventory] Log warning: {e}")

    # Update procurement order status if exists
    _update_related_procurement(part_name)

    print(f"[inventory] Restocked: {part_name} +{qty}")
    return {
        "success": True,
        "part_name": part_name,
        "added": qty,
        "new_stock": next(r["current_stock"] for r in inventory if r["part_name"] == part_name),
    }


def deduct_stock(part_name: str, qty: int) -> Dict:
    """Deduct stock when a work order consumes parts."""
    inventory = load_inventory()

    for item in inventory:
        if item["part_name"] == part_name:
            if item["current_stock"] < qty:
                return {"success": False, "error": f"Insufficient stock: have {item['current_stock']}, need {qty}"}
            item["current_stock"] -= qty
            save_inventory(inventory)

            from gateway.workflow_engine import _get_conn, _init_db, _now
            conn = _get_conn()
            _init_db(conn)
            conn.execute(
                "INSERT INTO inventory_log (part_name, change_qty, reason, new_stock, created_at) VALUES (?, ?, ?, ?, ?)",
                (part_name, -qty, "工单消耗", item["current_stock"], _now()),
            )
            conn.commit()
            conn.close()

            print(f"[inventory] Deducted: {part_name} -{qty}, remaining {item['current_stock']}")
            return {"success": True, "part_name": part_name, "deducted": qty, "remaining": item["current_stock"]}

    return {"success": False, "error": f"Part not found: {part_name}"}


def _update_related_procurement(part_name: str):
    """When stock is restocked, mark related procurement orders as received."""
    if not PROCUREMENT_PATH.exists():
        return
    orders = get_procurement_orders()
    changed = False
    for o in orders:
        if o["part_name"] == part_name and o["status"] == "运输中":
            o["status"] = "已到货"
            changed = True
    if changed:
        _save_procurement(orders)


# ══════════════════════════════════════════════════════════════
# Procurement Orders
# ══════════════════════════════════════════════════════════════

def generate_procurement_orders() -> List[Dict]:
    """Auto-generate procurement orders for parts with shortage."""
    stock_result = check_stock()
    short_parts = [p for p in stock_result["parts"] if p["procurement_needed"]]

    existing = get_procurement_orders()
    existing_parts = {o["part_name"] for o in existing if o["status"] in ("申请中", "已下单", "运输中")}

    new_orders = []
    today = datetime.now()
    idx = len(existing) + 1

    for p in short_parts:
        if p["part_name"] in existing_parts:
            continue  # Already ordered

        lead = p["lead_time_days"]
        order = {
            "order_id": f"PO-{idx:04d}",
            "part_name": p["part_name"],
            "quantity_ordered": p["suggested_order_qty"],
            "unit_cost": p["unit_cost"],
            "total_cost": round(p["suggested_order_qty"] * p["unit_cost"], 2),
            "supplier": p["supplier"],
            "order_date": today.strftime("%Y-%m-%d"),
            "expected_arrival": (today + timedelta(days=lead)).strftime("%Y-%m-%d"),
            "status": "申请中",
            "related_machines": "",
            "notes": f"库存不足自动生成: 库存{p['current_stock']}, 需求{p['demand']}, 缺口{p['shortage']}",
        }
        new_orders.append(order)
        idx += 1

    if new_orders:
        existing.extend(new_orders)
        _save_procurement(existing)
        print(f"[inventory] Generated {len(new_orders)} procurement orders")

    return new_orders


def get_procurement_orders(status_filter: str = "") -> List[Dict]:
    """Get procurement orders, optionally filtered by status."""
    if not PROCUREMENT_PATH.exists():
        return []

    orders = []
    try:
        with open(PROCUREMENT_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["quantity_ordered"] = int(row.get("quantity_ordered", 0) or 0)
                row["unit_cost"] = float(row.get("unit_cost", 0) or 0)
                row["total_cost"] = float(row.get("total_cost", 0) or 0)
                if status_filter and row.get("status", "") != status_filter:
                    continue
                orders.append(row)
    except Exception:
        pass
    return orders


def update_procurement_status(order_id: str, new_status: str) -> Dict:
    """Update procurement order status."""
    if new_status not in PROCUREMENT_STATUS:
        return {"success": False, "error": f"Invalid status: {new_status}. Valid: {PROCUREMENT_STATUS}"}

    orders = get_procurement_orders()
    updated = False

    for o in orders:
        if o["order_id"] == order_id:
            o["status"] = new_status
            updated = True

            # Auto-restock when marked as 已入库
            if new_status == "已入库":
                restock_result = restock(o["part_name"], o["quantity_ordered"])
                if not restock_result["success"]:
                    return restock_result
            break

    if not updated:
        return {"success": False, "error": f"Order not found: {order_id}"}

    _save_procurement(orders)
    return {"success": True, "order_id": order_id, "new_status": new_status}


def _save_procurement(orders: List[Dict]):
    """Save procurement orders to CSV."""
    PROCUREMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCUREMENT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "order_id", "part_name", "quantity_ordered", "unit_cost", "total_cost",
            "supplier", "order_date", "expected_arrival", "status",
            "related_machines", "notes",
        ])
        writer.writeheader()
        writer.writerows(orders)


def get_inventory_logs(limit: int = 50) -> List[Dict]:
    """Get inventory change logs."""
    try:
        from gateway.workflow_engine import _get_conn, _init_db
        conn = _get_conn()
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM inventory_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []
