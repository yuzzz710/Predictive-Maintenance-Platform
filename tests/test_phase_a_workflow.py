"""Phase A Verification Script — Work Order State Machine + Notification."""
import sys
import os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(PROJ, 'web-dashboard')
sys.path.insert(0, WEB)
os.chdir(WEB)

from gateway.workflow_engine import (
    _init_db, _get_conn, sync_from_plan_csv, transition,
    get_work_orders, get_work_order_detail, get_statistics,
    check_timeouts, VALID_TRANSITIONS, STATUS_LABELS, DB_PATH, initialize,
)
from gateway.config import DASHBOARD_DATA

def test_all():
    print("=" * 60)
    print("Phase A Verification - Work Order State Machine")
    print("=" * 60)

    # 1. DB Init
    print("\n[Test 1] Database initialization...")
    conn = _get_conn()
    _init_db(conn)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    print(f"  Tables: {table_names}")
    assert "work_order_state" in table_names
    assert "work_order_state_history" in table_names
    print("  [PASS]")
    conn.close()

    # 2. CSV Sync
    print("\n[Test 2] CSV sync...")
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    print(f"  Plan CSV: {plan_path}, exists={plan_path.exists()}")
    n_new = sync_from_plan_csv()
    print(f"  New work orders: {n_new}")

    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM work_order_state").fetchone()[0]
    print(f"  Total in DB: {total}")
    assert total > 0, "No work orders in DB after sync"
    print("  [PASS]")

    first = conn.execute(
        "SELECT machine_id, status FROM work_order_state WHERE status='pending' LIMIT 1"
    ).fetchone()
    print(f"  Sample pending: {first['machine_id'] if first else 'N/A'}")
    conn.close()

    # 3. State transitions
    print("\n[Test 3] State transitions...")
    conn = _get_conn()
    row = conn.execute(
        "SELECT machine_id FROM work_order_state WHERE status='pending' LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        print("  [SKIP] No pending work orders")
    else:
        mid = row["machine_id"]
        # Valid transitions
        steps = [
            ("assigned", "pending -> assigned"),
            ("in_progress", "assigned -> in_progress"),
            ("pending_acceptance", "in_progress -> pending_acceptance"),
            ("completed", "pending_acceptance -> completed"),
            ("archived", "completed -> archived"),
        ]
        for new_status, desc in steps:
            ok, msg = transition(mid, new_status, triggered_by="test", notes=f"Test: {desc}")
            status = "PASS" if ok else "FAIL"
            print(f"  {desc}: [{status}] {msg}")

        # Invalid transition
        ok, msg = transition(mid, "pending", triggered_by="test")
        status = "PASS" if not ok else "FAIL"
        print(f"  archived -> pending (should FAIL): [{status}] {msg}")

    # 4. Timeout detection
    print("\n[Test 4] Timeout detection...")
    conn = _get_conn()
    row2 = conn.execute(
        "SELECT machine_id FROM work_order_state WHERE status='pending' LIMIT 1"
    ).fetchone()
    conn.close()

    if row2:
        mid2 = row2["machine_id"]
        transition(mid2, "assigned", triggered_by="test")
        # Set assigned_at to 25 hours ago
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(hours=25)).isoformat()
        conn3 = _get_conn()
        conn3.execute(
            "UPDATE work_order_state SET assigned_at = ? WHERE machine_id = ?",
            (old, mid2)
        )
        conn3.commit()
        conn3.close()

        escalated = check_timeouts()
        print(f"  Escalated: {len(escalated)} work order(s)")
        if escalated:
            print(f"    {escalated[0]['machine_id']} - assigned at {escalated[0]['assigned_at']}")
        print(f"  [{'PASS' if len(escalated) > 0 else 'FAIL'}]")
    else:
        print("  [SKIP] No pending work orders")

    # 5. Statistics
    print("\n[Test 5] Statistics...")
    stats = get_statistics()
    print(f"  Total: {stats['total_work_orders']}")
    print(f"  By status: {stats['by_status']}")
    print("  [PASS]")

    # 6. Work order listing
    print("\n[Test 6] Listing & filtering...")
    wos = get_work_orders()
    print(f"  All: {len(wos)}")
    wos_p = get_work_orders(status_filter="pending")
    print(f"  Pending: {len(wos_p)}")
    wos_s = get_work_orders(search="CNC_0")
    print(f"  Search 'CNC_0': {len(wos_s)}")
    print("  [PASS]")

    # 7. Detail query
    print("\n[Test 7] Detail query...")
    if wos:
        detail = get_work_order_detail(wos[0]["machine_id"])
        print(f"  Machine: {detail['machine_id']}")
        print(f"  Status: {detail['status']}")
        history = detail.get("state_history", [])
        print(f"  History: {len(history)} entries")
        for h in history[-3:]:
            print(f"    {h['created_at'][:19]}: {h['from_status']} -> {h['to_status']}")
        has_plan = "plan_data" in detail and detail["plan_data"]
        print(f"  Has plan data: {has_plan}")
        print("  [PASS]")

    # 8. Notification service
    print("\n[Test 8] Notification service...")
    from gateway.notification_service import _is_configured, _build_work_order_html
    print(f"  SMTP configured: {_is_configured()}")
    if wos and wos[0]:
        detail = get_work_order_detail(wos[0]["machine_id"])
        html = _build_work_order_html(wos[0]["machine_id"], detail or {}, "Test")
        print(f"  HTML email: {len(html)} chars")
        assert wos[0]["machine_id"] in html
        print("  [PASS]")

    # 9. Transition validation
    print("\n[Test 9] Transition table...")
    for state, valid_next in VALID_TRANSITIONS.items():
        for ns in valid_next:
            assert ns in VALID_TRANSITIONS or ns in STATUS_LABELS, f"Unknown state: {ns}"
    print(f"  {len(VALID_TRANSITIONS)} states defined")
    for s, v in VALID_TRANSITIONS.items():
        cn = STATUS_LABELS.get(s, s)
        next_cn = [STATUS_LABELS.get(x, x) for x in v]
        print(f"    {cn}: {next_cn}")
    print("  [PASS]")

    # 10. SQLite-CSV consistency
    print("\n[Test 10] SQLite-CSV consistency...")
    import csv
    conn = _get_conn()
    db_ids = set(r[0] for r in conn.execute("SELECT machine_id FROM work_order_state").fetchall())
    conn.close()

    csv_ids = set()
    if plan_path.exists():
        with open(plan_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = row.get("machine_id", "").strip()
                if mid:
                    csv_ids.add(mid)

    missing_in_db = csv_ids - db_ids
    extra_in_db = db_ids - csv_ids
    print(f"  CSV work orders: {len(csv_ids)}")
    print(f"  DB work orders: {len(db_ids)}")
    print(f"  Missing in DB: {len(missing_in_db)}")
    print(f"  Extra in DB (removed from CSV): {len(extra_in_db)}")
    if missing_in_db:
        print(f"    Missing: {sorted(missing_in_db)[:5]}...")
    if extra_in_db:
        print(f"    Extra: {sorted(extra_in_db)[:5]}...")
    print(f"  [{'PASS' if len(missing_in_db) == 0 else 'WARN'}]")

    print("\n" + "=" * 60)
    print("All Phase A tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_all()
