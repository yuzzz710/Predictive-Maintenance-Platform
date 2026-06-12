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

        # Step 4: Build email
        critical_devices.sort(key=lambda x: x["health_score"])
        critical_html_rows = ""
        for d in critical_devices[:15]:
            hs_color = "#f04444" if d["health_score"] < 25 else "#f0a030"
            critical_html_rows += f"""
            <tr>
              <td style="padding:6px 10px;border:1px solid #1c2230;font-family:monospace;">{d['machine_id']}</td>
              <td style="padding:6px 10px;border:1px solid #1c2230;color:{hs_color};font-weight:600;">{d['health_score']:.1f}</td>
              <td style="padding:6px 10px;border:1px solid #1c2230;">{d['health_level']}</td>
              <td style="padding:6px 10px;border:1px solid #1c2230;">{d['top_risk_factor']}</td>
              <td style="padding:6px 10px;border:1px solid #1c2230;color:#f04444;">${d['cost_at_risk']:.0f}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Microsoft YaHei',sans-serif;background:#0e1117;color:#e6ebf2;padding:24px;">
<div style="max-width:650px;margin:0 auto;background:#141820;border:1px solid #1c2230;border-radius:6px;overflow:hidden;">
<div style="background:#1a1f2b;padding:20px 24px;border-bottom:1px solid #1c2230;">
  <span style="color:#00c9a0;font-size:16px;font-weight:bold;">◆ 每日健康巡检报告</span>
  <span style="float:right;font-size:12px;color:#5a6474;">{datetime.now().strftime('%Y-%m-%d')}</span>
</div>
<div style="padding:24px;">
  <div style="display:flex;gap:12px;margin-bottom:20px;">
    <div style="flex:1;background:rgba(255,255,255,0.02);border:1px solid #1c2230;border-radius:4px;padding:12px;text-align:center;">
      <div style="font-size:22px;font-weight:700;color:#f04444;">{len(critical_devices)}</div>
      <div style="font-size:11px;color:#5a6474;">高危设备 (健康分&lt;40)</div>
    </div>
    <div style="flex:1;background:rgba(255,255,255,0.02);border:1px solid #1c2230;border-radius:4px;padding:12px;text-align:center;">
      <div style="font-size:22px;font-weight:700;color:#f0a030;">{alert_stats.get('Alarm',0)+alert_stats.get('Warning',0)}</div>
      <div style="font-size:11px;color:#5a6474;">告警/警告设备</div>
    </div>
    <div style="flex:1;background:rgba(255,255,255,0.02);border:1px solid #1c2230;border-radius:4px;padding:12px;text-align:center;">
      <div style="font-size:22px;font-weight:700;color:#3fb950;">{pipe_result.get('work_orders_count', 0)}</div>
      <div style="font-size:11px;color:#5a6474;">今日工单</div>
    </div>
  </div>
  <div style="font-size:13px;color:#8e9aab;margin-bottom:12px;">高危设备列表 (Top {min(15, len(critical_devices))})</div>
  <table width="100%" style="border-collapse:collapse;margin-bottom:16px;">
    <tr style="background:rgba(255,255,255,0.02);">
      <td style="padding:6px 10px;border:1px solid #1c2230;color:#5a6474;font-size:11px;">设备</td>
      <td style="padding:6px 10px;border:1px solid #1c2230;color:#5a6474;font-size:11px;">健康分</td>
      <td style="padding:6px 10px;border:1px solid #1c2230;color:#5a6474;font-size:11px;">等级</td>
      <td style="padding:6px 10px;border:1px solid #1c2230;color:#5a6474;font-size:11px;">风险因子</td>
      <td style="padding:6px 10px;border:1px solid #1c2230;color:#5a6474;font-size:11px;">日成本风险</td>
    </tr>{critical_html_rows}
  </table>
  <p style="font-size:11px;color:#5a6474;">策略: {strategy} | 流水线耗时: {pipe_result.get('total_duration_seconds', '?')}s</p>
  <p style="font-size:11px;color:#5a6474;">查看详情: <a href="http://localhost:8765/dashboard" style="color:#4d94ff;">仪表盘</a> | <a href="http://localhost:8765/work-order-tracking" style="color:#4d94ff;">工单跟踪</a></p>
</div></div></body></html>"""

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

        # Build email
        report_rows = ""
        for r in reports_ok:
            report_rows += f"""<tr><td style="padding:8px 12px;border:1px solid #1c2230;">{r['type']}</td>
            <td style="padding:8px 12px;border:1px solid #1c2230;color:#3fb950;">OK</td>
            <td style="padding:8px 12px;border:1px solid #1c2230;">{r['size']} KB</td>
            <td style="padding:8px 12px;border:1px solid #1c2230;"><a href="{r['url']}" style="color:#4d94ff;">查看</a></td></tr>"""
        for r in reports_fail:
            report_rows += f"""<tr><td style="padding:8px 12px;border:1px solid #1c2230;">{r['type']}</td>
            <td style="padding:8px 12px;border:1px solid #1c2230;color:#f04444;">FAIL</td>
            <td style="padding:8px 12px;border:1px solid #1c2230;" colspan="2">{r['error']}</td></tr>"""

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Microsoft YaHei',sans-serif;background:#0e1117;color:#e6ebf2;padding:24px;">
<div style="max-width:600px;margin:0 auto;background:#141820;border:1px solid #1c2230;border-radius:6px;overflow:hidden;">
<div style="background:#1a1f2b;padding:20px 24px;border-bottom:1px solid #1c2230;">
  <span style="color:#00c9a0;font-size:16px;font-weight:bold;">◆ 周度运维报告</span>
  <span style="float:right;font-size:12px;color:#5a6474;">{datetime.now().strftime('%Y-%m-%d')}</span>
</div>
<div style="padding:24px;">
  <p style="font-size:13px;color:#8e9aab;margin-bottom:16px;">本周度报告已自动生成，共 {len(reports_ok)}/{len(reports_ok)+len(reports_fail)} 份成功。</p>
  <table width="100%" style="border-collapse:collapse;margin-bottom:20px;">
    <tr style="background:rgba(255,255,255,0.02);">
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">报告类型</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">状态</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">大小</td>
      <td style="padding:8px 12px;border:1px solid #1c2230;color:#5a6474;">链接</td>
    </tr>{report_rows}
  </table>
  <p style="font-size:11px;color:#5a6474;">查看所有报告: <a href="http://localhost:8765/reports" style="color:#4d94ff;">报告管理中心</a></p>
</div></div></body></html>"""

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
