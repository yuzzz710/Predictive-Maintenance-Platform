"""
Scheduled Background Jobs — Daily health check, weekly reports, timeout detection.
====================================================================================
All background jobs managed by APScheduler. Each job logs its execution to SQLite
for visibility via the /workflows management page.

Jobs:
  - wo_timeout_check (every 15 min): Escalate overdue work orders
  - daily_health_check (daily 06:00): Run pipeline, notify critical devices
  - weekly_report (Monday 07:00): Generate + distribute weekly reports

Usage:
  from gateway.scheduled_jobs import register_all_jobs
  register_all_jobs(scheduler)  # called from app.py startup
"""

import csv
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from gateway.config import DASHBOARD_DATA, PROJECT_ROOT, DATA_DIR, SMTP_USER


def _get_current_strategy() -> str:
    """Read current strategy from industrial_maintenance_plan.csv or default."""
    plan_path = DASHBOARD_DATA / "industrial_maintenance_plan.csv"
    if plan_path.exists():
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    s = row.get("maintenance_strategy", "").strip()
                    if s:
                        return s
        except Exception:
            pass
    return "production_efficiency"


# ══════════════════════════════════════════════════════════════
# Job: Work Order Timeout Check (Phase A — migrated)
# ══════════════════════════════════════════════════════════════

def wo_timeout_check():
    """Check for overdue work orders and escalate them."""
    from gateway.workflow_engine import (
        check_timeouts, sync_from_plan_csv, get_work_order_detail, log_job_start, log_job_end,
    )
    from gateway.notification_service import send_escalation

    hid = log_job_start("wo_timeout_check", "工单超时检测")
    t0 = time.time()

    try:
        sync_from_plan_csv()
        escalated = check_timeouts()

        for item in escalated:
            try:
                detail = get_work_order_detail(item["machine_id"])
                send_escalation(
                    item["machine_id"],
                    item.get("assigned_at", ""),
                    detail=detail,
                )
            except Exception as e:
                print(f"[scheduler] Escalation email error for {item['machine_id']}: {e}")

        if escalated:
            ids = ", ".join(e["machine_id"] for e in escalated)
            summary = f"{len(escalated)} 个工单超时升级: {ids}"
        else:
            summary = "无超时工单"

        duration = time.time() - t0
        log_job_end(hid, "completed", summary, "", duration)
        print(f"[scheduler] wo_timeout_check: {summary} ({duration:.1f}s)")

    except Exception as e:
        duration = time.time() - t0
        log_job_end(hid, "failed", "", str(e), duration)
        print(f"[scheduler] wo_timeout_check FAILED: {e}")


# ══════════════════════════════════════════════════════════════
# Job: Daily Health Check
# ══════════════════════════════════════════════════════════════

def daily_health_check():
    """
    Daily pipeline run + critical device notification.
    1. Run DAG pipeline (skip ML for speed)
    2. Read equipment_health_score.csv, filter health_score < 40
    3. Read alert_summary.csv for alarm counts
    4. Send HTML email with critical device list
    """
    from gateway.workflow_engine import log_job_start, log_job_end
    from gateway.notification_service import _send_email, _is_configured

    hid = log_job_start("daily_health_check", "每日健康巡检")
    t0 = time.time()
    print("[scheduler] Starting daily health check...")

    try:
        # Step 1: Run pipeline
        strategy = _get_current_strategy()
        print(f"[scheduler] Running pipeline (strategy={strategy})...")
        from gateway.tools import _run_pipeline
        pipe_result = _run_pipeline(
            data_dir=str(DATA_DIR),
            skip_ml=True,
            max_orders=20,
            strategy=strategy,
        )

        if not pipe_result.get("success"):
            raise RuntimeError(f"Pipeline failed: {pipe_result.get('error', 'unknown')}")

        print(f"[scheduler] Pipeline done: {pipe_result.get('work_orders_count', 0)} work orders")

        # Step 2: Read health scores
        health_path = DASHBOARD_DATA / "equipment_health_score.csv"
        critical_devices = []
        if health_path.exists():
            with open(health_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    hs = float(row.get("health_score", 100) or 100)
                    if hs < 40:
                        critical_devices.append({
                            "machine_id": row.get("Equipment.Id", ""),
                            "health_score": hs,
                            "health_level": row.get("health_level", ""),
                            "trend": row.get("trend", ""),
                            "top_risk_factor": row.get("top_risk_factor_label", ""),
                            "zscore_risk": float(row.get("zscore_risk", 0) or 0),
                            "cost_at_risk": float(row.get("cost_at_risk", 0) or 0),
                        })

        # Step 3: Alert summary
        alert_path = DASHBOARD_DATA / "alert_summary.csv"
        alert_stats = {"Alarm": 0, "Warning": 0, "Watch": 0, "Normal": 0}
        if alert_path.exists():
            with open(alert_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    level = row.get("current_alert_level", "Normal")
                    alert_stats[level] = alert_stats.get(level, 0) + 1

        # Step 4: Build email using Jinja2 template
        critical_devices.sort(key=lambda x: x["health_score"])
        from gateway.report_renderer import render_email
        html = render_email("email_daily_health.html", {
            "critical_devices": critical_devices,
            "alert_stats": alert_stats,
            "work_orders_count": pipe_result.get("work_orders_count", 0),
            "strategy": strategy,
            "pipe_duration": pipe_result.get("total_duration_seconds", "?"),
        })

        # Send email
        if _is_configured():
            _send_email(SMTP_USER, f"[每日巡检] {datetime.now().strftime('%Y-%m-%d')} — {len(critical_devices)}台高危设备", html)
            print(f"[scheduler] Daily health email sent to {SMTP_USER}")

        # Re-sync workflow states with new plan
        from gateway.workflow_engine import sync_from_plan_csv
        sync_from_plan_csv()

        summary = (f"流水线完成: {pipe_result.get('work_orders_count', 0)} 张工单, "
                   f"{len(critical_devices)} 台高危设备, "
                   f"告警: Alarm={alert_stats.get('Alarm',0)} Warning={alert_stats.get('Warning',0)}")
        duration = time.time() - t0
        log_job_end(hid, "completed", summary, "", duration)
        print(f"[scheduler] daily_health_check: {summary} ({duration:.1f}s)")

    except Exception as e:
        duration = time.time() - t0
        log_job_end(hid, "failed", "", str(e), duration)
        print(f"[scheduler] daily_health_check FAILED: {e}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# Job: Weekly Report Generation
# ══════════════════════════════════════════════════════════════

def weekly_report_job():
    """Generate weekly report, risk report, and health_critical report, then email."""
    from gateway.workflow_engine import log_job_start, log_job_end
    from gateway.notification_service import _send_email, _is_configured
    from gateway.tools import _generate_maintenance_report

    hid = log_job_start("weekly_report", "周报生成与分发")
    t0 = time.time()
    print("[scheduler] Starting weekly report generation...")

    reports_ok = []
    reports_fail = []

    try:
        # Generate 3 reports
        for rtype, rname in [("weekly", "周度系统报告"), ("risk", "高风险设备报告"), ("health_critical", "低健康分报告")]:
            try:
                result = _generate_maintenance_report(report_type=rtype, health_threshold=30)
                if result.get("success"):
                    reports_ok.append({"type": rname, "url": result.get("html_url", ""), "size": result.get("html_size_kb", 0)})
                    print(f"[scheduler]   {rname}: OK ({result.get('html_url')})")
                else:
                    reports_fail.append({"type": rname, "error": result.get("error", "unknown")})
                    print(f"[scheduler]   {rname}: FAIL ({result.get('error')})")
            except Exception as e:
                reports_fail.append({"type": rname, "error": str(e)})
                print(f"[scheduler]   {rname}: EXCEPTION ({e})")

        # Build email using Jinja2 template
        from gateway.report_renderer import render_email
        html = render_email("email_weekly_report.html", {
            "reports_ok": reports_ok,
            "reports_fail": reports_fail,
        })

        if _is_configured():
            _send_email(SMTP_USER, f"[周报] {datetime.now().strftime('%Y-W%W')} 运维周报", html)

        summary = f"报告生成: {len(reports_ok)} 份成功, {len(reports_fail)} 份失败"
        duration = time.time() - t0
        log_job_end(hid, "completed" if not reports_fail else "completed_with_errors", summary, "", duration)
        print(f"[scheduler] weekly_report: {summary} ({duration:.1f}s)")

    except Exception as e:
        duration = time.time() - t0
        log_job_end(hid, "failed", "", str(e), duration)
        print(f"[scheduler] weekly_report FAILED: {e}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════

def register_all_jobs(scheduler):
    """Register all background jobs with the APScheduler instance."""
    from apscheduler.triggers.cron import CronTrigger

    # wo_timeout_check: every 15 minutes (migrated from app.py)
    scheduler.add_job(
        wo_timeout_check,
        'interval',
        minutes=15,
        id='wo_timeout_check',
        next_run_time=None,
        replace_existing=True,
    )

    # daily_health_check: every day at 06:00
    scheduler.add_job(
        daily_health_check,
        CronTrigger(hour=6, minute=0),
        id='daily_health_check',
        replace_existing=True,
    )

    # weekly_report: every Monday at 07:00
    scheduler.add_job(
        weekly_report_job,
        CronTrigger(day_of_week='mon', hour=7, minute=0),
        id='weekly_report',
        replace_existing=True,
    )

    print("[scheduler] Registered 3 jobs: wo_timeout_check, daily_health_check, weekly_report")
