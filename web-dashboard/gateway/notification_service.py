"""
Email Notification Service — SMTP-based work order notifications.
==================================================================
Sends HTML-formatted emails for work order assignment, status changes,
and escalations. Supports QQ Mail, 163, Gmail, and custom SMTP servers.

Configuration from .env / config.py:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
  NOTIFY_ESCALATION_EMAIL
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Optional, Dict

from gateway.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
    NOTIFY_ESCALATION_EMAIL,
)

logger = logging.getLogger(__name__)

# ── Chinese label mappings (shared with frontend) ──
STATUS_LABELS_CN = {
    "pending":             "待分配",
    "assigned":            "已分配",
    "escalated":           "已升级",
    "in_progress":         "执行中",
    "pending_acceptance":  "待验收",
    "rejected":            "验收不通过",
    "completed":           "已完成",
    "archived":            "已归档",
}

PATTERN_LABELS_CN = {
    "voltage_drift":       "电压漂移",
    "thermal_buildup":     "热积聚",
    "power_anomaly":       "功率异常",
    "combined_degradation": "复合退化",
    "normal":              "正常运行",
}

ACTION_LABELS_CN = {
    "immediate_shutdown":   "紧急停机",
    "preventive_repair":    "预防性维修",
    "schedule_inspection":  "计划检查",
    "increase_monitoring":  "加强监控",
    "routine_check":        "常规检查",
    "no_action":            "无需操作",
}

WINDOW_LABELS_CN = {
    "immediate": "立即（1小时内）",
    "night":     "夜间（22:00-06:00）",
    "weekend":   "下个周末",
    "next_gap":  "下个生产间隙",
    "scheduled": "下个计划维护窗口",
}

TECH_LABELS_CN = {
    "junior_technician":      "初级技师",
    "senior_technician":      "高级技师",
    "electrical_specialist":  "电气专家",
    "thermal_specialist":     "热控专家",
    "mechanical_specialist":  "机械专家",
}

PRIORITY_COLORS = {"P1": "#f04444", "P2": "#f0a030", "P3": "#4d94ff"}


def _t(raw: Optional[str], mapping: Dict[str, str]) -> str:
    """Translate a value using a mapping, return raw if not found."""
    if not raw:
        return "?"
    return mapping.get(raw, raw.replace("_", " ").title())


def _is_configured() -> bool:
    """Check if SMTP is configured."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def _strip_html(text: str) -> str:
    """Strip HTML tags to produce a plain-text fallback for email clients."""
    import re
    # Remove style blocks entirely
    text = re.sub(r'<style[^<]*</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level tags with newlines
    text = re.sub(r'</?(?:div|p|table|tr|h[1-6]|br|hr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse whitespace
    text = re.sub(r'\n\s*\n', '\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def _build_work_order_html(machine_id: str, detail: Dict, title: str,
                           extra_sections: Optional[str] = None) -> str:
    """Build a consistent HTML email template for work order notifications."""
    plan = detail.get("plan_data", {}) or {}

    priority = plan.get("maintenance_priority", plan.get("priority", "P2"))
    priority_color = PRIORITY_COLORS.get(priority, "#4d94ff")
    pattern = _t(plan.get("primary_pattern", ""), PATTERN_LABELS_CN)
    action = _t(plan.get("recommended_action", plan.get("action_type", "")), ACTION_LABELS_CN)
    tech_type = _t(plan.get("technician_type", ""), TECH_LABELS_CN)
    tech_count = plan.get("technician_count", 1)
    window = _t(plan.get("recommended_downtime_window", ""), WINDOW_LABELS_CN)
    cost_risk = plan.get("cost_at_risk", "N/A")
    health_score = plan.get("health_score", "N/A")
    reasoning = plan.get("reasoning", "")[:300]
    spare_parts = plan.get("spare_parts", "[]")
    acceptance = plan.get("acceptance_standard", "")
    sla = plan.get("sla_target_hours", "")

    # Parse spare_parts JSON string
    try:
        import json
        parts_list = json.loads(spare_parts) if isinstance(spare_parts, str) else spare_parts
        parts_str = ", ".join(parts_list) if isinstance(parts_list, list) else str(spare_parts)
    except (json.JSONDecodeError, TypeError):
        parts_str = str(spare_parts) if spare_parts else "无"

    # Current status
    current_status = detail.get("status", "pending")
    status_label = STATUS_LABELS_CN.get(current_status, current_status)

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#2c3e50;padding:20px;margin:0;">
<div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e8ecf1;border-radius:8px;overflow:hidden;">

  <!-- Header -->
  <div style="background:#2c3e50;padding:18px 24px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <span style="color:#66d9c8;font-size:15px;font-weight:700;">&#9670; {title}</span>
      </td>
      <td align="right">
        <span style="display:inline-block;padding:4px 12px;border-radius:3px;font-size:12px;font-weight:600;color:#ffffff;background:{priority_color};">{priority}</span>
        <span style="display:inline-block;margin-left:6px;padding:4px 10px;border-radius:3px;font-size:11px;color:#7f8c9b;background:#f0f2f5;">{status_label}</span>
      </td>
    </tr></table>
  </div>

  <!-- Body -->
  <div style="padding:24px;">

    <!-- Key Info Grid -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
      <tr>
        <td style="padding:10px 14px;width:50%;background:#fafbfc;border:1px solid #e8ecf1;">
          <div style="font-size:10px;color:#7f8c9b;margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px;">设备编号</div>
          <div style="font-size:16px;font-weight:600;color:#2c3e50;font-family:'Courier New',monospace;">{machine_id}</div>
        </td>
        <td style="padding:10px 14px;background:#fafbfc;border:1px solid #e8ecf1;">
          <div style="font-size:10px;color:#7f8c9b;margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px;">健康评分</div>
          <div style="font-size:16px;font-weight:600;color:#e67e22;">{health_score}</div>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 14px;background:#fafbfc;border:1px solid #e8ecf1;">
          <div style="font-size:10px;color:#7f8c9b;margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px;">故障模式</div>
          <div style="font-size:14px;color:#2c3e50;">{pattern}</div>
        </td>
        <td style="padding:10px 14px;background:#fafbfc;border:1px solid #e8ecf1;">
          <div style="font-size:10px;color:#7f8c9b;margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px;">日成本风险</div>
          <div style="font-size:14px;color:#e74c3c;font-weight:600;">${cost_risk}</div>
        </td>
      </tr>
    </table>

    <!-- Details -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
      <tr><td colspan="2" style="padding:8px 0 10px;font-size:13px;font-weight:600;color:#2c3e50;border-bottom:2px solid #e8ecf1;">&#128203; 工单详情</td></tr>
      <tr>
        <td style="padding:7px 10px;font-size:12px;color:#7f8c9b;width:95px;">维护动作</td>
        <td style="padding:7px 10px;font-size:13px;color:#2c3e50;">{action}</td>
      </tr>
      <tr>
        <td style="padding:7px 10px;font-size:12px;color:#7f8c9b;">分配技师</td>
        <td style="padding:7px 10px;font-size:13px;color:#2c3e50;">{tech_type} &times; {tech_count}&#20154;</td>
      </tr>
      <tr>
        <td style="padding:7px 10px;font-size:12px;color:#7f8c9b;">停机窗口</td>
        <td style="padding:7px 10px;font-size:13px;color:#2c3e50;">{window}</td>
      </tr>
      <tr>
        <td style="padding:7px 10px;font-size:12px;color:#7f8c9b;">备件清单</td>
        <td style="padding:7px 10px;font-size:13px;color:#2c3e50;">{parts_str}</td>
      </tr>
      <tr>
        <td style="padding:7px 10px;font-size:12px;color:#7f8c9b;">SLA目标</td>
        <td style="padding:7px 10px;font-size:13px;color:#2c3e50;">{sla}h &#20869;完成</td>
      </tr>
    </table>

    <!-- Root Cause -->
    <div style="margin-bottom:20px;padding:14px 16px;background:#fef9f0;border-left:3px solid #e67e22;">
      <div style="font-size:13px;color:#e67e22;font-weight:600;margin-bottom:6px;">&#128269; 根因分析</div>
      <div style="font-size:12px;color:#5a6474;line-height:1.7;">{reasoning}</div>
    </div>

    <!-- Acceptance Criteria -->
    <div style="margin-bottom:20px;padding:14px 16px;background:#f0faf6;border-left:3px solid #27ae60;">
      <div style="font-size:13px;color:#27ae60;font-weight:600;margin-bottom:6px;">&#10004; 验收标准</div>
      <div style="font-size:11px;color:#5a6474;line-height:1.6;">{acceptance}</div>
    </div>
"""

    if extra_sections:
        html += extra_sections

    html += """
    <!-- Footer -->
    <div style="margin-top:20px;padding-top:16px;border-top:1px solid #e8ecf1;font-size:11px;color:#7f8c9b;text-align:center;">
      <p style="margin:0 0 6px;">此邮件由预测性维护系统自动生成 &middot; 请勿直接回复</p>
      <p style="margin:0;">登录 <a href="http://localhost:8765/work-order-tracking" style="color:#2980b9;text-decoration:none;">工单跟踪看板</a> 查看详情</p>
    </div>

  </div>
</div>
</body>
</html>"""
    return html


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    if not _is_configured():
        logger.warning(f"[notification] SMTP not configured — skipping email to {to_email}, subject: {subject}")
        print(f"[notification] WARN SMTP not configured — would have sent: {subject} -> {to_email}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        # Plain-text fallback first (RFC: multipart/alternative lists least-preferred first)
        text_body = _strip_html(html_body)
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
        server.quit()

        logger.info(f"[notification] Email sent: {subject} -> {to_email}")
        print(f"[notification] OK Email sent: {subject} -> {to_email}")
        return True

    except Exception as e:
        logger.error(f"[notification] Failed to send email: {e}")
        print(f"[notification] FAIL Failed to send email: {e}")
        return False


def send_work_order_assignment(machine_id: str, detail: Dict,
                               to_email: Optional[str] = None) -> bool:
    """
    Send work order assignment notification.
    Called when a work order transitions to 'assigned'.
    """
    if not to_email:
        to_email = SMTP_USER  # Default: send to self for demo

    plan = detail.get("plan_data", {}) or {}
    pattern = _t(plan.get("primary_pattern", ""), PATTERN_LABELS_CN)

    extra = ""
    state_history = detail.get("state_history", [])
    if state_history:
        extra = """
    <!-- Timeline -->
    <div style="margin-bottom:20px;">
      <div style="font-size:13px;color:#2c3e50;font-weight:600;margin-bottom:8px;">&#128197; 状态时间线</div>
      <table width="100%" cellspacing="0" cellpadding="0">"""
        for h in state_history[-5:]:
            from_s = STATUS_LABELS_CN.get(h.get("from_status"), h.get("from_status", "—"))
            to_s = STATUS_LABELS_CN.get(h.get("to_status", ""), h.get("to_status", ""))
            t = h.get("created_at", "")[:19]
            extra += f"""
        <tr>
          <td style="padding:4px 8px;font-size:11px;color:#7f8c9b;width:130px;">{t}</td>
          <td style="padding:4px 8px;font-size:11px;color:#2c3e50;">{from_s} &#8594; {to_s}</td>
        </tr>"""
        extra += """
      </table>
    </div>"""

    html = _build_work_order_html(
        machine_id, detail,
        title=f"🔧 工单分配通知 — {machine_id}",
        extra_sections=extra,
    )

    subject = f"[工单分配] {machine_id} — {pattern} — 请确认接单"
    return _send_email(to_email, subject, html)


def send_status_change(machine_id: str, old_status: str, new_status: str,
                       detail: Dict, notes: str = "",
                       to_email: Optional[str] = None) -> bool:
    """Send status change notification."""
    if not to_email:
        to_email = SMTP_USER

    old_label = STATUS_LABELS_CN.get(old_status, old_status)
    new_label = STATUS_LABELS_CN.get(new_status, new_status)

    extra = f"""
    <!-- Status Change Highlight -->
    <div style="margin-bottom:20px;padding:14px 16px;background:#eef4ff;border-left:3px solid #2980b9;">
      <div style="font-size:13px;color:#2980b9;font-weight:600;margin-bottom:6px;">&#128260; 状态变更</div>
      <div style="font-size:14px;color:#2c3e50;font-weight:600;">{old_label} &#8594; {new_label}</div>"""
    if notes:
        extra += f"""
      <div style="font-size:11px;color:#7f8c9b;margin-top:4px;">备注: {notes}</div>"""
    extra += """
    </div>"""

    html = _build_work_order_html(
        machine_id, detail,
        title=f"📋 工单状态更新 — {machine_id}",
        extra_sections=extra,
    )

    subject = f"[工单更新] {machine_id}: {old_label} → {new_label}"
    return _send_email(to_email, subject, html)


def send_escalation(machine_id: str, assigned_at: str,
                    detail: Optional[Dict] = None) -> bool:
    """Send escalation notification to supervisor."""
    extra = f"""
    <div style="margin-bottom:20px;padding:14px 16px;background:#fef5f5;border-left:3px solid #e74c3c;">
      <div style="font-size:13px;color:#e74c3c;font-weight:600;margin-bottom:6px;">&#128680; 超时升级告警</div>
      <div style="font-size:13px;color:#2c3e50;">工单 <b>{machine_id}</b> 分配已超过 <b>24小时</b> 未响应</div>
      <div style="font-size:11px;color:#7f8c9b;margin-top:4px;">分配时间: {assigned_at}</div>
      <div style="font-size:11px;color:#7f8c9b;">当前时间: {__import__('datetime').datetime.now().isoformat()}</div>
    </div>
    <div style="margin-bottom:20px;padding:14px 16px;background:#fef9f0;border-left:3px solid #e67e22;">
      <div style="font-size:13px;color:#e67e22;font-weight:600;margin-bottom:6px;">&#9888; 需要立即处理</div>
      <div style="font-size:12px;color:#5a6474;">请登录工单跟踪看板确认技师状态，必要时重新分配或升级处理。</div>
    </div>"""

    html = ""
    if detail:
        html = _build_work_order_html(
            machine_id, detail,
            title=f"🚨 工单超时升级 — {machine_id}",
            extra_sections=extra,
        )
    else:
        html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#2c3e50;padding:20px;margin:0;">
<div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e8ecf1;border-radius:8px;overflow:hidden;">
  <div style="background:#2c3e50;padding:18px 24px;">
    <span style="color:#e74c3c;font-size:15px;font-weight:700;">&#128680; 工单超时升级 — {machine_id}</span>
  </div>
  <div style="padding:24px;">
    {extra}
    <p style="font-size:11px;color:#7f8c9b;margin-top:20px;padding-top:16px;border-top:1px solid #e8ecf1;text-align:center;">
      此邮件由预测性维护系统自动生成 &middot; 请勿直接回复
    </p>
  </div>
</div>
</body>
</html>"""

    subject = f"[超时升级] {machine_id} — 分配超24h未响应"
    return _send_email(NOTIFY_ESCALATION_EMAIL, subject, html)
