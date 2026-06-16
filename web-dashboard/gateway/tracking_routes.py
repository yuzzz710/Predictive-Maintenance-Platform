"""
Work Order Tracking API Routes — Phase A Process Automation.
================================================================
Provides REST endpoints for the work-order-tracking.html page
and for external integrations.

Endpoints:
  GET  /api/work-order-tracking/list          — filtered work order list
  GET  /api/work-order-tracking/detail/{mid}  — single work order full detail
  GET  /api/work-order-tracking/statistics    — aggregate statistics
  POST /api/work-order/update-status           — update work order status
  POST /api/work-order/assign                 — assign + notify work order
"""

from fastapi import APIRouter, Body, HTTPException
from typing import Optional

from gateway.workflow_engine import (
    get_work_orders, get_work_order_detail, get_statistics,
    get_available_technicians, sync_from_plan_csv, transition, STATUS_LABELS,
)
from gateway.notification_service import (
    send_work_order_assignment, send_status_change, _is_configured,
)

router = APIRouter(prefix="/api/work-order-tracking", tags=["work-order-tracking"])

# ── Also mount update-status under /api/work-order for simplicity ──
router2 = APIRouter(prefix="/api/work-order", tags=["work-order"])


@router.get("/list")
async def list_work_orders(
    status: Optional[str] = None,
    technician: Optional[str] = None,
    search: Optional[str] = None,
    strategy: Optional[str] = None,
):
    """Get filtered work order tracking list with optional strategy filter."""
    import csv
    from gateway.config import DASHBOARD_DATA

    wos = get_work_orders(
        status_filter=status,
        technician_filter=technician,
        search=search,
    )

    # Strategy filter from DB column
    if strategy:
        wos = [w for w in wos if w.get("maintenance_strategy", "") == strategy]

    # Enrich with plan CSV summary data
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    plan_map = {}
    if plan_path.exists():
        with open(plan_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = row.get("machine_id", "").strip()
                if mid:
                    plan_map[mid] = {
                        "maintenance_priority": row.get("maintenance_priority", row.get("priority", "")),
                        "primary_pattern": row.get("primary_pattern", ""),
                        "recommended_action": row.get("recommended_action", row.get("action_type", "")),
                        "downtime_window": row.get("recommended_downtime_window", ""),
                        "health_score": row.get("health_score", ""),
                        "cost_at_risk": row.get("cost_at_risk", ""),
                        "technician_type": row.get("technician_type", ""),
                        "technician_count": row.get("technician_count", 1),
                        "reasoning": (row.get("reasoning", "") or "")[:200],
                        "spare_parts": row.get("spare_parts", "[]"),
                        "acceptance_standard": row.get("acceptance_standard", ""),
                        "estimated_cost": row.get("estimated_cost", ""),
                        "expected_savings": row.get("expected_savings", ""),
                        "sla_target_hours": row.get("sla_target_hours", ""),
                    }

    result_list = []
    for wo in wos:
        enriched = dict(wo)
        mid = wo["machine_id"]
        summary = plan_map.get(mid, {})
        # Build context for machines not in plan CSV
        if not summary:
            try:
                from gateway.work_order_builder import build_work_order_context
                built = build_work_order_context(mid)
                summary = {
                    "maintenance_priority": built.get("maintenance_priority", ""),
                    "primary_pattern": built.get("primary_pattern", ""),
                    "recommended_action": built.get("recommended_action", ""),
                    "downtime_window": built.get("recommended_downtime_window", ""),
                    "health_score": built.get("health_score", ""),
                    "cost_at_risk": built.get("cost_at_risk", ""),
                    "technician_type": built.get("technician_type", ""),
                    "technician_count": built.get("technician_count", "1"),
                    "reasoning": built.get("reasoning", ""),
                    "spare_parts": built.get("spare_parts", "[]"),
                    "acceptance_standard": built.get("acceptance_standard", ""),
                    "estimated_cost": built.get("estimated_cost", ""),
                    "expected_savings": built.get("expected_savings", ""),
                    "sla_target_hours": built.get("sla_target_hours", ""),
                }
            except Exception:
                pass
        enriched["plan_summary"] = summary
        enriched["status_label"] = STATUS_LABELS.get(wo["status"], wo["status"])
        result_list.append(enriched)

    stats = get_statistics()
    labeled_counts = {}
    for k, v in stats.get("by_status", {}).items():
        labeled_counts[STATUS_LABELS.get(k, k)] = v
    stats["by_status_labeled"] = labeled_counts

    from gateway.workflow_engine import get_work_orders_by_strategy
    strategy_counts = get_work_orders_by_strategy()

    techs = get_available_technicians()

    return {
        "work_orders": result_list,
        "total": len(result_list),
        "statistics": stats,
        "strategy_counts": strategy_counts,
        "available_technicians": [t["technician_type"] for t in techs],
        "status_labels": STATUS_LABELS,
    }


@router.get("/detail/{machine_id}")
async def work_order_detail(machine_id: str):
    """Get full tracking detail for a single work order."""
    detail = get_work_order_detail(machine_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Work order not found: {machine_id}")

    detail["status_label"] = STATUS_LABELS.get(detail.get("status", ""), detail.get("status", ""))

    # Label history transitions
    for h in detail.get("state_history", []):
        h["from_label"] = STATUS_LABELS.get(h.get("from_status", ""), h.get("from_status", "—"))
        h["to_label"] = STATUS_LABELS.get(h.get("to_status", ""), h.get("to_status", ""))

    return detail


@router.get("/statistics")
async def statistics():
    """Get aggregate work order statistics."""
    sync_from_plan_csv()
    stats = get_statistics()

    labeled_counts = {}
    for k, v in stats.get("by_status", {}).items():
        labeled_counts[STATUS_LABELS.get(k, k)] = v
    stats["by_status_labeled"] = labeled_counts

    return stats


# ── Actions (under /api/work-order) ──

@router2.post("/update-status")
async def update_work_order_status(data: dict = Body(...)):
    """
    Update work order status with validation and notification.

    Request body:
        machine_id (str): Device ID
        new_status (str): Target status
        notes (str, optional): Status change notes
        triggered_by (str, optional): Who triggered this
    """
    machine_id = data.get("machine_id", "")
    new_status = data.get("new_status", "")
    notes = data.get("notes", "")
    triggered_by = data.get("triggered_by", "user")

    if not machine_id or not new_status:
        raise HTTPException(status_code=400, detail="machine_id and new_status are required")

    if new_status not in STATUS_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {new_status}. Valid: {list(STATUS_LABELS.keys())}"
        )

    # Get old status for notification
    detail_before = get_work_order_detail(machine_id)
    old_status = detail_before.get("status", "unknown") if detail_before else "unknown"

    # Execute transition
    ok, msg = transition(machine_id, new_status, triggered_by=triggered_by, notes=notes)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Get updated detail
    detail_after = get_work_order_detail(machine_id)

    # Send notification for significant transitions
    email_sent = False
    if new_status in ("assigned", "in_progress", "pending_acceptance", "completed", "rejected"):
        email_sent = send_status_change(
            machine_id, old_status, new_status,
            detail=detail_after or {},
            notes=notes,
        )

    return {
        "success": True,
        "machine_id": machine_id,
        "old_status": old_status,
        "new_status": new_status,
        "message": msg,
        "email_sent": email_sent,
        "smtp_configured": _is_configured(),
    }


@router2.post("/create")
async def create_work_order(data: dict = Body(...)):
    """Manually create a work order from home page. Supports force mode for strategy transfer."""
    import csv
    from gateway.workflow_engine import create_work_order as cwo, _get_conn, _init_db, _lock
    from gateway.config import DASHBOARD_DATA
    machine_id = data.get("machine_id", "")
    strategy = data.get("strategy", "production_efficiency")
    force = data.get("force", False)
    if not machine_id:
        raise HTTPException(status_code=400, detail="machine_id is required")

    # Read plan data for this machine
    plan_data = {}
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    if plan_path.exists():
        with open(plan_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("machine_id", "").strip() == machine_id:
                    plan_data = dict(row)
                    break
    # If not in plan CSV, dynamically build context from Z-Scores + health data
    if not plan_data:
        from gateway.work_order_builder import build_work_order_context
        plan_data = build_work_order_context(machine_id)

    # Check existing
    conn = _get_conn(); _init_db(conn)
    existing = conn.execute("SELECT maintenance_strategy FROM work_order_state WHERE machine_id=?", (machine_id,)).fetchone()
    conn.close()

    if existing:
        old_strategy = existing["maintenance_strategy"] or ""
        if old_strategy == strategy:
            return {"success": False, "exists": True, "same_strategy": True, "old_strategy": old_strategy}
        if not force:
            return {"success": False, "exists": True, "different_strategy": True, "old_strategy": old_strategy}
        # Force = delete old and recreate
        conn2 = _get_conn()
        with _lock:
            conn2.execute("DELETE FROM technician_assignments WHERE machine_id=?", (machine_id,))
            conn2.execute("DELETE FROM work_order_state_history WHERE machine_id=?", (machine_id,))
            conn2.execute("DELETE FROM work_order_state WHERE machine_id=?", (machine_id,))
            conn2.commit()
        conn2.close()

    ok = cwo(machine_id, strategy, plan_data if plan_data else None)
    return {"success": True, "machine_id": machine_id, "strategy": strategy, "transferred": existing is not None}


@router2.delete("/delete/{machine_id}")
async def delete_single_work_order(machine_id: str):
    """Delete a single work order."""
    from gateway.workflow_engine import _get_conn, _init_db, _lock
    conn = _get_conn(); _init_db(conn)
    with _lock:
        conn.execute("DELETE FROM technician_assignments WHERE machine_id=?", (machine_id,))
        conn.execute("DELETE FROM work_order_state_history WHERE machine_id=?", (machine_id,))
        conn.execute("DELETE FROM work_order_state WHERE machine_id=?", (machine_id,))
        conn.commit()
    conn.close()
    return {"success": True, "deleted": machine_id}


@router2.post("/clear")
async def clear_work_orders():
    """Clear all work order tracking data."""
    from gateway.workflow_engine import clear_all_work_orders
    count = clear_all_work_orders()
    return {"success": True, "cleared": count}


@router2.post("/assign")
async def assign_work_order(data: dict = Body(...)):
    """
    Auto-assign technician to a pending work order and send email.

    Request body:
        machine_id (str): Device ID
        technician_email (str, optional): Technician's email
    """
    machine_id = data.get("machine_id", "")
    technician_email = data.get("technician_email", "")

    if not machine_id:
        raise HTTPException(status_code=400, detail="machine_id is required")

    # Check current state
    detail = get_work_order_detail(machine_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Work order not found: {machine_id}")

    current_status = detail.get("status", "")
    if current_status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Work order {machine_id} is {current_status}, only pending orders can be auto-assigned"
        )

    # Transition to assigned
    ok, msg = transition(
        machine_id, "assigned",
        triggered_by="system",
        notes="自动分配技师",
        technician_email=technician_email,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Refresh detail
    detail = get_work_order_detail(machine_id)

    # Send notification
    email_sent = send_work_order_assignment(
        machine_id, detail or {},
        to_email=technician_email if technician_email else None,
    )

    return {
        "success": True,
        "machine_id": machine_id,
        "status": "assigned",
        "email_sent": email_sent,
        "smtp_configured": _is_configured(),
        "message": msg,
    }


# ══════════════════════════════════════════════════════════════
# Workflow Management API
# ══════════════════════════════════════════════════════════════

router3 = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router3.get("/status")
async def workflow_status():
    """Get all scheduled job statuses with last execution info."""
    from gateway.workflow_engine import get_job_history
    from gateway.scheduled_jobs import register_all_jobs

    job_configs = {
        "wo_timeout_check": {"name": "工单超时检测", "schedule": "每15分钟"},
        "daily_health_check": {"name": "每日健康巡检", "schedule": "每天 06:00"},
        "weekly_report": {"name": "周报生成与分发", "schedule": "每周一 07:00"},
    }

    jobs_status = []
    for job_id, config in job_configs.items():
        history = get_job_history(job_id=job_id, limit=1)
        last_run = history[0] if history else None
        jobs_status.append({
            "job_id": job_id,
            "job_name": config["name"],
            "schedule": config["schedule"],
            "last_run": {
                "started_at": last_run["started_at"] if last_run else None,
                "finished_at": last_run["finished_at"] if last_run else None,
                "status": last_run["status"] if last_run else "never",
                "result_summary": last_run["result_summary"] if last_run else "",
                "duration_seconds": last_run["duration_seconds"] if last_run else None,
                "error_message": last_run["error_message"] if last_run else "",
            } if last_run else None,
        })

    return {"jobs": jobs_status, "total": len(jobs_status)}


@router3.get("/history")
async def workflow_history(job_id: Optional[str] = None, limit: int = 50):
    """Get scheduled job execution history."""
    from gateway.workflow_engine import get_job_history
    history = get_job_history(job_id=job_id or "", limit=limit)
    return {"history": history, "total": len(history)}


@router3.post("/trigger/{job_id}")
async def trigger_job(job_id: str):
    """Manually trigger a scheduled job."""
    from gateway.scheduled_jobs import wo_timeout_check, daily_health_check, weekly_report_job

    job_map = {
        "wo_timeout_check": wo_timeout_check,
        "daily_health_check": daily_health_check,
        "weekly_report": weekly_report_job,
    }

    if job_id not in job_map:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")

    import threading
    def run_job():
        try:
            job_map[job_id]()
        except Exception as e:
            print(f"[workflows] Job {job_id} failed: {e}")

    t = threading.Thread(target=run_job, daemon=True)
    t.start()

    return {
        "success": True,
        "job_id": job_id,
        "message": f"Job {job_id} triggered in background",
    }


@router3.get("/config")
async def get_workflow_config():
    """Get current workflow configuration."""
    from gateway.scheduled_jobs import _get_current_strategy
    strat_map = {
        "cost_efficiency": "成本效率",
        "production_efficiency": "生产效率",
        "quality_first": "质量优先",
    }
    raw = _get_current_strategy()
    return {
        "strategy": raw,
        "strategy_label": strat_map.get(raw, raw),
        "daily_health_time": "06:00",
        "weekly_report_time": "周一 07:00",
        "health_threshold": 40,
        "timeout_hours": 24,
        "smtp_configured": _is_configured(),
    }


# ══════════════════════════════════════════════════════════════
# Inventory Management API
# ══════════════════════════════════════════════════════════════

router4 = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router4.get("/stock")
async def inventory_stock():
    """Get inventory overview with demand comparison."""
    from gateway.inventory_connector import check_stock, load_inventory
    result = check_stock()
    inv = load_inventory()
    return {"stock": result, "raw_inventory": inv}


@router4.get("/procurement")
async def procurement_orders(status: Optional[str] = None):
    """Get procurement orders, optionally filtered by status."""
    from gateway.inventory_connector import get_procurement_orders
    orders = get_procurement_orders(status_filter=status or "")
    return {"orders": orders, "total": len(orders)}


@router4.post("/restock")
async def restock_part(data: dict = Body(...)):
    """Receive parts into inventory."""
    from gateway.inventory_connector import restock
    part_name = data.get("part_name", "")
    qty = data.get("qty", 0)
    if not part_name or qty <= 0:
        raise HTTPException(status_code=400, detail="part_name and qty (>0) required")
    return restock(part_name, int(qty))


@router4.post("/adjust")
async def adjust_stock(data: dict = Body(...)):
    """Manually set or adjust inventory stock. Accepts absolute 'new_stock' or relative 'delta'."""
    from gateway.inventory_connector import load_inventory, save_inventory
    part_name = data.get("part_name", "")
    new_stock = data.get("new_stock")  # absolute value
    delta = data.get("delta")  # relative change (+/-)
    if not part_name:
        raise HTTPException(status_code=400, detail="part_name required")
    if new_stock is None and delta is None:
        raise HTTPException(status_code=400, detail="new_stock or delta required")

    inventory = load_inventory()
    found = False
    for item in inventory:
        if item["part_name"] == part_name:
            old = item["current_stock"]
            if new_stock is not None:
                item["current_stock"] = int(new_stock)
            else:
                item["current_stock"] = max(0, old + int(delta))
            save_inventory(inventory)

            # Log
            from gateway.workflow_engine import _get_conn, _init_db, _now
            conn = _get_conn(); _init_db(conn)
            conn.execute(
                "INSERT INTO inventory_log (part_name, change_qty, reason, new_stock, created_at) VALUES (?,?,?,?,?)",
                (part_name, item["current_stock"] - old, "手动调整", item["current_stock"], _now()),
            )
            conn.commit(); conn.close()
            found = True
            print(f"[inventory] Manual adjust: {part_name} {old} -> {item['current_stock']}")
            return {"success": True, "part_name": part_name, "old_stock": old, "new_stock": item["current_stock"]}

    raise HTTPException(status_code=404, detail=f"Part not found: {part_name}")


@router4.post("/procurement/generate")
async def generate_orders():
    """Auto-generate procurement orders for parts with shortage."""
    from gateway.inventory_connector import generate_procurement_orders
    new = generate_procurement_orders()
    return {"success": True, "generated": len(new), "orders": new}


@router4.post("/procurement/update-status")
async def update_order_status(data: dict = Body(...)):
    """Update procurement order status."""
    from gateway.inventory_connector import update_procurement_status
    order_id = data.get("order_id", "")
    new_status = data.get("status", "")
    if not order_id or not new_status:
        raise HTTPException(status_code=400, detail="order_id and status required")
    return update_procurement_status(order_id, new_status)


@router4.delete("/procurement/delete/{order_id}")
async def delete_procurement_order(order_id: str):
    """Delete a completed procurement order."""
    from gateway.inventory_connector import delete_procurement_order
    result = delete_procurement_order(order_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))
    return result


@router4.get("/logs")
async def inventory_logs(limit: int = 50):
    """Get inventory change logs."""
    from gateway.inventory_connector import get_inventory_logs
    return {"logs": get_inventory_logs(limit)}


# ══════════════════════════════════════════════════════════════
# Technician Management API
# ══════════════════════════════════════════════════════════════

router5 = APIRouter(prefix="/api/technicians", tags=["technicians"])


@router5.get("")
async def list_technicians(tech_type: str = "", status: str = ""):
    """List all technicians with workload counts."""
    from gateway.workflow_engine import get_technicians
    techs = get_technicians(tech_type=tech_type, status=status)
    return {"technicians": techs, "total": len(techs)}


@router5.get("/{tech_id}")
async def technician_detail(tech_id: int):
    """Get single technician detail with assigned work orders."""
    from gateway.workflow_engine import get_technician
    t = get_technician(tech_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Technician {tech_id} not found")
    return t


@router5.post("")
async def add_technician_api(data: dict = Body(...)):
    """Create a new technician."""
    from gateway.workflow_engine import add_technician
    tid = add_technician(
        name=data.get("name", ""),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        tech_type=data.get("technician_type", ""),
        max_concurrent=data.get("max_concurrent", 3),
        skills=data.get("skills", ""),
        notes=data.get("notes", ""),
    )
    return {"success": True, "id": tid}


@router5.put("/{tech_id}")
async def update_technician_api(tech_id: int, data: dict = Body(...)):
    """Update a technician."""
    from gateway.workflow_engine import update_technician
    ok = update_technician(tech_id, **data)
    if not ok:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    return {"success": True}


@router5.delete("/{tech_id}")
async def delete_technician_api(tech_id: int):
    """Delete a technician (only if no active assignments)."""
    from gateway.workflow_engine import delete_technician
    ok = delete_technician(tech_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete: technician has active assignments")
    return {"success": True}


@router5.post("/assign")
async def assign_technicians_api(data: dict = Body(...)):
    """Assign technicians to a work order. Body: {machine_id, technician_ids: [1,2,...]}"""
    from gateway.workflow_engine import assign_technicians_to_work_order, transition
    machine_id = data.get("machine_id", "")
    tech_ids = data.get("technician_ids", [])
    if not machine_id or not tech_ids:
        raise HTTPException(status_code=400, detail="machine_id and technician_ids required")
    result = assign_technicians_to_work_order(machine_id, tech_ids)
    if result["success"]:
        # Update work order status to assigned
        from gateway.workflow_engine import get_technicians
        techs = get_technicians()
        names = [next((t["name"] for t in techs if t["id"] == tid), str(tid)) for tid in tech_ids]
        transition(machine_id, "assigned", triggered_by="user",
                   notes=f"分配技师: {', '.join(names)}")
        # Send notifications
        from gateway.notification_service import send_work_order_assignment
        from gateway.workflow_engine import get_work_order_detail
        detail = get_work_order_detail(machine_id)
        if detail:
            for tid in tech_ids:
                t_info = next((t for t in techs if t["id"] == tid), None)
                if t_info and t_info.get("email"):
                    send_work_order_assignment(machine_id, detail, to_email=t_info["email"])
    return result


@router5.get("/workloads/summary")
async def technician_workload_summary():
    """Get workload summary for all technicians."""
    from gateway.workflow_engine import get_technicians
    techs = get_technicians()
    summary = {
        "total": len(techs),
        "available": sum(1 for t in techs if t["status"] == "available"),
        "busy": sum(1 for t in techs if t["status"] == "busy"),
        "off_duty": sum(1 for t in techs if t["status"] == "off_duty"),
        "total_assignments": sum(t.get("current_workload", 0) for t in techs),
        "by_type": {},
    }
    for t in techs:
        tt = t["technician_type"]
        if tt not in summary["by_type"]:
            summary["by_type"][tt] = {"total": 0, "available": 0}
        summary["by_type"][tt]["total"] += 1
        if t["status"] == "available":
            summary["by_type"][tt]["available"] += 1
    return summary
