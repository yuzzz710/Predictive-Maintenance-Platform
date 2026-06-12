"""
Work Order State Machine — SQLite-backed lifecycle tracker.
================================================================
Tracks every work order from generation through assignment, execution,
acceptance, completion, and archival.

Database: web-dashboard/data/workflow_state.db (auto-created)
CSV sync: reads industrial_maintenance_plan.csv on startup, creates state
           entries for new machine_ids, preserves existing state for known ones.

State machine (6 states):
  pending ──→ assigned ──→ in_progress ──→ pending_acceptance ──→ completed ──→ archived
     │           │                           │                      │
     │           ├── timeout(24h) → escalated│                      │
     │           └── escalated → assigned    │                      │
     │                                       ├──→ rejected ──→ in_progress
     │                                       └──→ completed ──→ archived
     └──→ assigned (manual assign)
"""

import sqlite3
import csv
import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from gateway.config import DASHBOARD_DATA

DB_PATH = DASHBOARD_DATA / "workflow_state.db"

# ── Valid state transitions ──
VALID_TRANSITIONS: Dict[str, List[str]] = {
    "pending":             ["assigned"],
    "assigned":            ["in_progress", "escalated"],
    "escalated":           ["assigned"],
    "in_progress":         ["pending_acceptance"],
    "pending_acceptance":  ["completed", "rejected"],
    "rejected":            ["in_progress"],
    "completed":           ["archived"],
    "archived":            [],  # terminal state
}

# Display names
STATUS_LABELS = {
    "pending":             "待分配",
    "assigned":            "已分配",
    "escalated":           "已升级",
    "in_progress":         "执行中",
    "pending_acceptance":  "待验收",
    "rejected":            "验收不通过",
    "completed":           "已完成",
    "archived":            "已归档",
}

# Timeout hours for auto-escalation
ESCALATION_TIMEOUT_HOURS = 24

# Thread lock for SQLite writes
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection with WAL mode."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def _init_db(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS work_order_state (
            machine_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            maintenance_strategy TEXT DEFAULT '',
            technician_type TEXT,
            technician_count INTEGER,
            technician_email TEXT,
            assigned_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            accepted_at TEXT,
            archived_at TEXT,
            escalated INTEGER DEFAULT 0,
            escalation_count INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_order_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            triggered_by TEXT DEFAULT 'system',
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduled_job_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            job_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            result_summary TEXT,
            error_message TEXT,
            duration_seconds REAL
        );

        CREATE TABLE IF NOT EXISTS post_repair_snapshot (
            machine_id TEXT PRIMARY KEY,
            pre_z_composite REAL,
            pre_z_voltage REAL,
            pre_z_amperage REAL,
            pre_z_temperature REAL,
            pre_alert_level TEXT,
            post_z_composite REAL,
            post_z_voltage REAL,
            post_z_amperage REAL,
            post_z_temperature REAL,
            post_alert_level TEXT,
            verdict TEXT,
            confidence TEXT,
            snapshot_at TEXT NOT NULL,
            validated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS inventory_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_name TEXT NOT NULL,
            change_qty INTEGER NOT NULL,
            reason TEXT,
            new_stock INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS technicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            technician_type TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            max_concurrent INTEGER DEFAULT 3,
            skills TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS technician_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT NOT NULL,
            technician_id INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            status TEXT DEFAULT 'assigned',
            FOREIGN KEY (technician_id) REFERENCES technicians(id)
        );
    """)
    conn.commit()


def _now() -> str:
    """ISO timestamp for current time."""
    return datetime.now().isoformat()


def _read_plan_csv() -> Path:
    """Locate the industrial maintenance plan CSV."""
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    if not plan_path.exists():
        # Try fallback names
        for name in ["maintenance_work_orders.csv", "maintenance_decision_report.csv"]:
            alt = DASHBOARD_DATA / name
            if alt.exists():
                return alt
    return plan_path


def sync_from_plan_csv() -> int:
    """
    Read the plan CSV and ensure every machine_id has a state row.
    - New machines get 'pending' state.
    - Existing machines keep their current state.
    - Returns number of newly created rows.
    """
    plan_path = _read_plan_csv()
    if not plan_path.exists():
        print(f"[workflow_engine] Plan CSV not found: {plan_path}")
        return 0

    conn = _get_conn()
    _init_db(conn)

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            plan_ids = set()
            plan_technicians = {}
            for row in reader:
                mid = row.get("machine_id", "").strip()
                if mid:
                    plan_ids.add(mid)
                    plan_technicians[mid] = {
                        "technician_type": row.get("technician_type", ""),
                        "technician_count": int(row.get("technician_count", 1) or 1),
                    }

        # Get existing IDs
        existing = set(
            r[0] for r in conn.execute("SELECT machine_id FROM work_order_state").fetchall()
        )

        # Insert new ones
        new_count = 0
        now = _now()
        for mid in sorted(plan_ids - existing):
            tech = plan_technicians.get(mid, {})
            with _lock:
                conn.execute(
                    """INSERT INTO work_order_state
                       (machine_id, status, technician_type, technician_count, created_at, updated_at)
                       VALUES (?, 'pending', ?, ?, ?, ?)""",
                    (mid, tech.get("technician_type", ""), tech.get("technician_count", 1), now, now),
                )
                conn.execute(
                    """INSERT INTO work_order_state_history
                       (machine_id, from_status, to_status, triggered_by, notes, created_at)
                       VALUES (?, NULL, 'pending', 'system', 'Auto-created from CSV sync', ?)""",
                    (mid, now),
                )
            new_count += 1

        conn.commit()
        if new_count:
            print(f"[workflow_engine] Synced {new_count} new work orders from CSV ({len(plan_ids)} total)")
        return new_count

    except Exception as e:
        print(f"[workflow_engine] Error syncing from CSV: {e}")
        return 0
    finally:
        conn.close()


def transition(machine_id: str, new_status: str, triggered_by: str = "system",
               notes: str = "", technician_email: str = "") -> Tuple[bool, str]:
    """
    Execute a state transition with validation.

    Returns (success, message).
    """
    if new_status not in VALID_TRANSITIONS:
        return False, f"Unknown status: {new_status}"

    conn = _get_conn()
    _init_db(conn)

    try:
        row = conn.execute(
            "SELECT status FROM work_order_state WHERE machine_id = ?", (machine_id,)
        ).fetchone()

        if not row:
            conn.close()
            return False, f"Work order not found: {machine_id}"

        current_status = row["status"]

        # Validate transition
        allowed = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            conn.close()
            return False, (
                f"Invalid transition: {STATUS_LABELS.get(current_status, current_status)} "
                f"→ {STATUS_LABELS.get(new_status, new_status)}. "
                f"Allowed: {[STATUS_LABELS.get(s, s) for s in allowed]}"
            )

        now = _now()
        updates = {"status": new_status, "updated_at": now}

        # Set timestamp fields based on status
        if new_status == "assigned":
            updates["assigned_at"] = now
            updates["escalated"] = 0  # Clear escalation flag on re-assign
            if technician_email:
                updates["technician_email"] = technician_email
        elif new_status == "in_progress":
            updates["started_at"] = now
        elif new_status == "pending_acceptance":
            updates["completed_at"] = now
        elif new_status == "completed":
            updates["accepted_at"] = now
        elif new_status == "archived":
            updates["archived_at"] = now
        elif new_status == "escalated":
            updates["escalated"] = 1
            # Increment escalation count
            current_esc = conn.execute(
                "SELECT escalation_count FROM work_order_state WHERE machine_id = ?",
                (machine_id,)
            ).fetchone()
            updates["escalation_count"] = (current_esc["escalation_count"] or 0) + 1

        # Build SET clause
        set_parts = []
        params = []
        for col, val in updates.items():
            set_parts.append(f"{col} = ?")
            params.append(val)
        params.append(machine_id)

        with _lock:
            conn.execute(
                f"UPDATE work_order_state SET {', '.join(set_parts)} WHERE machine_id = ?",
                params,
            )
            conn.execute(
                """INSERT INTO work_order_state_history
                   (machine_id, from_status, to_status, triggered_by, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (machine_id, current_status, new_status, triggered_by, notes, now),
            )
        conn.commit()

        label_from = STATUS_LABELS.get(current_status, current_status)
        label_to = STATUS_LABELS.get(new_status, new_status)
        print(f"[workflow_engine] {machine_id}: {label_from} → {label_to} (by {triggered_by})")
        return True, f"{label_from} → {label_to}"

    except Exception as e:
        conn.rollback()
        return False, f"Error: {e}"
    finally:
        conn.close()


def get_work_orders(status_filter: Optional[str] = None,
                    technician_filter: Optional[str] = None,
                    search: Optional[str] = None) -> List[Dict]:
    """
    Query work orders with optional filters.
    Returns list of dicts with state + plan CSV columns merged.
    """
    conn = _get_conn()
    _init_db(conn)

    try:
        query = "SELECT * FROM work_order_state WHERE 1=1"
        params = []

        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                query += f" AND status IN ({placeholders})"
                params.extend(statuses)

        if technician_filter:
            query += " AND technician_type = ?"
            params.append(technician_filter)

        if search:
            query += " AND machine_id LIKE ?"
            params.append(f"%{search}%")

        query += " ORDER BY machine_id"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    finally:
        conn.close()


def get_work_order_detail(machine_id: str) -> Optional[Dict]:
    """Get full work order detail: state row + plan CSV row + history."""
    conn = _get_conn()
    _init_db(conn)

    try:
        row = conn.execute(
            "SELECT * FROM work_order_state WHERE machine_id = ?", (machine_id,)
        ).fetchone()

        if not row:
            return None

        result = dict(row)

        # Get state history
        history = conn.execute(
            """SELECT * FROM work_order_state_history
               WHERE machine_id = ? ORDER BY created_at ASC""",
            (machine_id,),
        ).fetchall()
        result["state_history"] = [dict(h) for h in history]

        # Try to merge plan CSV row
        plan_path = _read_plan_csv()
        if plan_path.exists():
            with open(plan_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for plan_row in reader:
                    if plan_row.get("machine_id", "").strip() == machine_id:
                        result["plan_data"] = dict(plan_row)
                        break

        # Fallback: if not in plan CSV, dynamically build context
        if "plan_data" not in result:
            try:
                from gateway.work_order_builder import build_work_order_context
                result["plan_data"] = build_work_order_context(machine_id)
                result["plan_data"]["maintenance_strategy"] = result.get("maintenance_strategy", "")
            except Exception:
                result["plan_data"] = {}

        return result

    finally:
        conn.close()


def check_timeouts() -> List[Dict]:
    """
    Find assigned work orders that have exceeded the escalation timeout.
    Returns list of escalated work orders.
    """
    conn = _get_conn()
    _init_db(conn)

    cutoff = (datetime.now() - timedelta(hours=ESCALATION_TIMEOUT_HOURS)).isoformat()

    try:
        rows = conn.execute(
            """SELECT machine_id, assigned_at, technician_type FROM work_order_state
               WHERE status = 'assigned' AND escalated = 0 AND assigned_at IS NOT NULL
               AND assigned_at < ?""",
            (cutoff,),
        ).fetchall()

        escalated = []
        for row in rows:
            success, msg = transition(
                row["machine_id"], "escalated",
                triggered_by="system",
                notes=f"Auto-escalated: assigned {ESCALATION_TIMEOUT_HOURS}h ago without response"
            )
            if success:
                escalated.append({
                    "machine_id": row["machine_id"],
                    "assigned_at": row["assigned_at"],
                    "technician_type": row["technician_type"],
                })
                print(f"[workflow_engine] ESCALATED: {row['machine_id']} "
                      f"(assigned at {row['assigned_at']}, timeout {ESCALATION_TIMEOUT_HOURS}h)")

        conn.commit()
        return escalated

    except Exception as e:
        print(f"[workflow_engine] Error checking timeouts: {e}")
        return []
    finally:
        conn.close()


def get_statistics() -> Dict:
    """Get aggregate statistics across all work orders."""
    conn = _get_conn()
    _init_db(conn)

    try:
        status_counts = {}
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM work_order_state GROUP BY status"
        ).fetchall()
        for r in rows:
            status_counts[r["status"]] = r["cnt"]

        total = sum(status_counts.values())
        escalated_count = conn.execute(
            "SELECT COUNT(*) FROM work_order_state WHERE escalated = 1"
        ).fetchone()[0]

        # SLA: count completed within 72h
        sla_count = 0
        completed_rows = conn.execute(
            "SELECT machine_id, created_at, completed_at FROM work_order_state WHERE status IN ('completed', 'archived')"
        ).fetchall()
        for r in completed_rows:
            try:
                created = datetime.fromisoformat(r["created_at"]) if r["created_at"] else None
                completed = datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None
                if created and completed and (completed - created) <= timedelta(hours=72):
                    sla_count += 1
            except (ValueError, TypeError):
                pass

        return {
            "total_work_orders": total,
            "by_status": status_counts,
            "escalated": escalated_count,
            "sla_met": sla_count,
            "sla_total": len(completed_rows),
            "sla_rate": round(sla_count / len(completed_rows) * 100, 1) if completed_rows else 0,
        }

    finally:
        conn.close()


def get_available_technicians() -> List[Dict]:
    """Get list of technician types currently assigned, for filter dropdowns."""
    conn = _get_conn()
    _init_db(conn)

    try:
        rows = conn.execute(
            "SELECT DISTINCT technician_type FROM work_order_state WHERE technician_type != '' ORDER BY technician_type"
        ).fetchall()
        return [{"technician_type": r["technician_type"]} for r in rows]
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════
# Scheduled Job History
# ══════════════════════════════════════════════════════════════

def log_job_start(job_id: str, job_name: str) -> int:
    """Log a scheduled job start. Returns the history record ID."""
    conn = _get_conn()
    _init_db(conn)
    now = _now()
    with _lock:
        cur = conn.execute(
            "INSERT INTO scheduled_job_history (job_id, job_name, started_at, status) VALUES (?, ?, ?, 'running')",
            (job_id, job_name, now),
        )
        conn.commit()
        return cur.lastrowid


def log_job_end(history_id: int, status: str, result_summary: str = "",
                error_message: str = "", duration_seconds: float = 0):
    """Mark a scheduled job as completed or failed."""
    conn = _get_conn()
    now = _now()
    with _lock:
        conn.execute(
            "UPDATE scheduled_job_history SET finished_at=?, status=?, result_summary=?, error_message=?, duration_seconds=? WHERE id=?",
            (now, status, result_summary, error_message, duration_seconds, history_id),
        )
        conn.commit()
    conn.close()


def get_job_history(job_id: str = "", limit: int = 50) -> List[Dict]:
    """Get scheduled job execution history."""
    conn = _get_conn()
    _init_db(conn)
    try:
        if job_id:
            rows = conn.execute(
                "SELECT * FROM scheduled_job_history WHERE job_id=? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scheduled_job_history ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════
# Post-Repair Snapshot
# ══════════════════════════════════════════════════════════════

def save_pre_repair_snapshot(machine_id: str, z_composite: float, z_voltage: float,
                              z_amperage: float, z_temperature: float, alert_level: str):
    """Save pre-repair Z-Score snapshot before repair begins."""
    conn = _get_conn()
    _init_db(conn)
    now = _now()
    with _lock:
        conn.execute(
            """INSERT OR REPLACE INTO post_repair_snapshot
               (machine_id, pre_z_composite, pre_z_voltage, pre_z_amperage, pre_z_temperature,
                pre_alert_level, snapshot_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (machine_id, z_composite, z_voltage, z_amperage, z_temperature, alert_level, now),
        )
        conn.commit()
    conn.close()


def save_post_repair_result(machine_id: str, z_composite: float, z_voltage: float,
                             z_amperage: float, z_temperature: float, alert_level: str,
                             verdict: str, confidence: str):
    """Save post-repair Z-Score and verdict."""
    conn = _get_conn()
    now = _now()
    with _lock:
        conn.execute(
            """UPDATE post_repair_snapshot SET
               post_z_composite=?, post_z_voltage=?, post_z_amperage=?, post_z_temperature=?,
               post_alert_level=?, verdict=?, confidence=?, validated_at=?
               WHERE machine_id=?""",
            (z_composite, z_voltage, z_amperage, z_temperature, alert_level,
             verdict, confidence, now, machine_id),
        )
        conn.commit()
    conn.close()


def get_repair_snapshot(machine_id: str) -> Optional[Dict]:
    """Get the pre/post repair snapshot for a machine."""
    conn = _get_conn()
    _init_db(conn)
    try:
        row = conn.execute(
            "SELECT * FROM post_repair_snapshot WHERE machine_id=?",
            (machine_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════
# Technician Management
# ══════════════════════════════════════════════════════════════

PRESET_TECHNICIANS = [
    ("李电压", "1970687947@qq.com", "13800001001", "electrical_specialist", "高电压,电路诊断"),
    ("周电流", "1970687947@qq.com", "13800001002", "electrical_specialist", "电流分析,谐波检测"),
    ("王热控", "1970687947@qq.com", "13800001003", "thermal_specialist", "热成像,散热系统"),
    ("赵温度", "1970687947@qq.com", "13800001004", "thermal_specialist", "温度传感,热漂移"),
    ("张师傅", "1970687947@qq.com", "13800001005", "senior_technician", "综合维修,故障诊断"),
    ("刘高级", "1970687947@qq.com", "13800001006", "senior_technician", "CNC维修,精密装配"),
    ("陈初级", "1970687947@qq.com", "13800001007", "junior_technician", "日常巡检,基础保养"),
    ("林助理", "1970687947@qq.com", "13800001008", "junior_technician", "协助维修,备件更换"),
    ("杨机械", "1970687947@qq.com", "13800001009", "mechanical_specialist", "机械传动,轴承维修"),
    ("黄维修", "1970687947@qq.com", "13800001010", "mechanical_specialist", "设备拆装,润滑系统"),
]


def init_technicians():
    """Seed preset technicians if table is empty."""
    conn = _get_conn()
    _init_db(conn)
    count = conn.execute("SELECT COUNT(*) FROM technicians").fetchone()[0]
    if count == 0:
        now = _now()
        for name, email, phone, ttype, skills in PRESET_TECHNICIANS:
            conn.execute(
                "INSERT INTO technicians (name, email, phone, technician_type, status, max_concurrent, skills, notes, created_at, updated_at) VALUES (?,?,?,?,'available',3,?,?,?,?)",
                (name, email, phone, ttype, skills, "", now, now),
            )
        conn.commit()
        print(f"[workflow_engine] Seeded {len(PRESET_TECHNICIANS)} technicians")
    conn.close()


def get_technicians(tech_type: str = "", status: str = "") -> List[Dict]:
    """List technicians with workload counts."""
    conn = _get_conn()
    _init_db(conn)
    try:
        query = """SELECT t.*, COUNT(ta.id) as current_workload
                   FROM technicians t
                   LEFT JOIN technician_assignments ta ON t.id = ta.technician_id AND ta.status = 'assigned'
                   WHERE 1=1"""
        params = []
        if tech_type:
            query += " AND t.technician_type = ?"
            params.append(tech_type)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        query += " GROUP BY t.id ORDER BY t.technician_type, t.name"
        rows = conn.execute(query, params).fetchall()
        results = [dict(r) for r in rows]

        # Fetch assigned machines for all returned technicians
        tech_ids = [r["id"] for r in results]
        if tech_ids:
            placeholders = ",".join("?" for _ in tech_ids)
            machine_rows = conn.execute(
                f"SELECT technician_id, machine_id FROM technician_assignments WHERE technician_id IN ({placeholders}) AND status = 'assigned'",
                tech_ids,
            ).fetchall()
            machine_map = {}
            for mr in machine_rows:
                tid = mr["technician_id"]
                if tid not in machine_map:
                    machine_map[tid] = []
                machine_map[tid].append({"machine_id": mr["machine_id"]})

            for r in results:
                r["assigned_machines"] = machine_map.get(r["id"], [])

        return results
    finally:
        conn.close()


def get_technician(tech_id: int) -> Optional[Dict]:
    """Get single technician with workload and assigned machines."""
    conn = _get_conn()
    _init_db(conn)
    try:
        row = conn.execute(
            """SELECT t.*, COUNT(ta.id) as current_workload
               FROM technicians t LEFT JOIN technician_assignments ta
               ON t.id = ta.technician_id AND ta.status = 'assigned'
               WHERE t.id = ? GROUP BY t.id""", (tech_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        # Get assigned machines
        machines = conn.execute(
            "SELECT machine_id, status, assigned_at FROM technician_assignments WHERE technician_id = ? AND status = 'assigned'",
            (tech_id,),
        ).fetchall()
        result["assigned_machines"] = [dict(m) for m in machines]
        return result
    finally:
        conn.close()


def add_technician(name: str, email: str, phone: str, tech_type: str,
                   max_concurrent: int = 3, skills: str = "", notes: str = "") -> int:
    """Add a new technician, returns ID."""
    conn = _get_conn()
    _init_db(conn)
    now = _now()
    with _lock:
        cur = conn.execute(
            "INSERT INTO technicians (name, email, phone, technician_type, status, max_concurrent, skills, notes, created_at, updated_at) VALUES (?,?,?,?,'available',?,?,?,?,?)",
            (name, email, phone, tech_type, max_concurrent, skills, notes, now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_technician(tech_id: int, **kwargs) -> bool:
    """Update technician fields."""
    allowed = {"name", "email", "phone", "technician_type", "status",
               "max_concurrent", "skills", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False
    updates["updated_at"] = _now()
    conn = _get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [tech_id]
    with _lock:
        conn.execute(f"UPDATE technicians SET {set_clause} WHERE id=?", vals)
        conn.commit()
    conn.close()
    return True


def delete_technician(tech_id: int) -> bool:
    """Delete a technician (only if no active assignments)."""
    conn = _get_conn()
    active = conn.execute(
        "SELECT COUNT(*) FROM technician_assignments WHERE technician_id=? AND status='assigned'",
        (tech_id,),
    ).fetchone()[0]
    if active > 0:
        conn.close()
        return False
    with _lock:
        conn.execute("DELETE FROM technicians WHERE id=?", (tech_id,))
        conn.commit()
    conn.close()
    return True


def assign_technicians_to_work_order(machine_id: str, tech_ids: List[int]) -> Dict:
    """Assign specific technicians to a work order."""
    conn = _get_conn()
    _init_db(conn)
    now = _now()
    assigned = []
    try:
        with _lock:
            for tid in tech_ids:
                # Check if already assigned to this WO
                existing = conn.execute(
                    "SELECT id FROM technician_assignments WHERE machine_id=? AND technician_id=? AND status='assigned'",
                    (machine_id, tid),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    "INSERT INTO technician_assignments (machine_id, technician_id, assigned_at, status) VALUES (?,?,?,'assigned')",
                    (machine_id, tid, now),
                )
                assigned.append(tid)

            # Update technician statuses
            for tid in tech_ids:
                workload = conn.execute(
                    "SELECT COUNT(*) FROM technician_assignments WHERE technician_id=? AND status='assigned'",
                    (tid,),
                ).fetchone()[0]
                max_load = conn.execute(
                    "SELECT max_concurrent FROM technicians WHERE id=?", (tid,)
                ).fetchone()[0]
                new_status = "busy" if workload >= max_load else "available"
                conn.execute(
                    "UPDATE technicians SET status=?, updated_at=? WHERE id=?",
                    (new_status, now, tid),
                )

        conn.commit()
        if assigned:
            print(f"[workflow_engine] Assigned technicians {assigned} to {machine_id}")
        return {"success": True, "assigned": assigned, "machine_id": machine_id}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_work_order_technicians(machine_id: str) -> List[Dict]:
    """Get assigned technicians for a work order."""
    conn = _get_conn()
    _init_db(conn)
    try:
        rows = conn.execute(
            """SELECT t.id, t.name, t.email, t.phone, t.technician_type, t.status as tech_status,
                      ta.status as assignment_status, ta.assigned_at
               FROM technician_assignments ta JOIN technicians t ON ta.technician_id = t.id
               WHERE ta.machine_id = ? AND ta.status = 'assigned'""",
            (machine_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def release_technician_from_work_order(machine_id: str, technician_id: int):
    """Mark a technician's assignment as completed for a work order."""
    conn = _get_conn()
    now = _now()
    with _lock:
        conn.execute(
            "UPDATE technician_assignments SET status='completed' WHERE machine_id=? AND technician_id=?",
            (machine_id, technician_id),
        )
        # Update technician status
        workload = conn.execute(
            "SELECT COUNT(*) FROM technician_assignments WHERE technician_id=? AND status='assigned'",
            (technician_id,),
        ).fetchone()[0]
        max_load = conn.execute(
            "SELECT max_concurrent FROM technicians WHERE id=?", (technician_id,)
        ).fetchone()[0]
        new_status = "busy" if workload >= max_load else "available"
        conn.execute("UPDATE technicians SET status=?, updated_at=? WHERE id=?", (new_status, now, technician_id))
        conn.commit()
    conn.close()


def create_work_order(machine_id: str, strategy: str, plan_data: dict = None) -> bool:
    """Manually create a work order from home page. Returns True if created, False if exists."""
    conn = _get_conn()
    _init_db(conn)
    existing = conn.execute("SELECT machine_id FROM work_order_state WHERE machine_id=?", (machine_id,)).fetchone()
    if existing:
        conn.close()
        return False  # Already exists
    now = _now()
    tech_type = (plan_data or {}).get("technician_type", "")
    tech_count = int((plan_data or {}).get("technician_count", 1) or 1)
    with _lock:
        conn.execute(
            "INSERT INTO work_order_state (machine_id, status, maintenance_strategy, technician_type, technician_count, created_at, updated_at) VALUES (?, 'pending', ?, ?, ?, ?, ?)",
            (machine_id, strategy, tech_type, tech_count, now, now),
        )
        conn.execute(
            "INSERT INTO work_order_state_history (machine_id, from_status, to_status, triggered_by, notes, created_at) VALUES (?, NULL, 'pending', 'user', ?, ?)",
            (machine_id, f"手动创建 - 策略: {strategy}", now),
        )
        conn.commit()
    conn.close()
    return True


def clear_all_work_orders() -> int:
    """Clear all work order tracking data. Returns count of deleted records."""
    conn = _get_conn()
    _init_db(conn)
    with _lock:
        count = conn.execute("SELECT COUNT(*) FROM work_order_state").fetchone()[0]
        conn.execute("DELETE FROM work_order_state_history")
        conn.execute("DELETE FROM technician_assignments")
        conn.execute("DELETE FROM work_order_state")
        # Reset all technician statuses
        conn.execute("UPDATE technicians SET status='available', updated_at=?", (_now(),))
        conn.commit()
    conn.close()
    print(f"[workflow_engine] Cleared {count} work orders")
    return count


def get_work_orders_by_strategy() -> dict:
    """Count work orders by strategy."""
    conn = _get_conn()
    _init_db(conn)
    rows = conn.execute(
        "SELECT maintenance_strategy, COUNT(*) as cnt FROM work_order_state GROUP BY maintenance_strategy"
    ).fetchall()
    conn.close()
    result = {"cost_efficiency": 0, "production_efficiency": 0, "quality_first": 0}
    for r in rows:
        key = r["maintenance_strategy"] or ""
        if key in result:
            result[key] = r["cnt"]
    return result


def initialize():
    """Call on app startup: init DB + seed technicians. No auto-sync from CSV."""
    conn = _get_conn()
    _init_db(conn)
    conn.close()
    init_technicians()
