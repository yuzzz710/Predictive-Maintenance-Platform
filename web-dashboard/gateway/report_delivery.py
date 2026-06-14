"""
Report Delivery — Layer 4 of the report system.

Handles file save, URL generation, email sending, and result assembly.
Does NOT render content — it receives already-rendered output from Layer 3.

Usage:
    from gateway.report_delivery import deliver_report, DeliveryResult
    result = deliver_report(spec, rendered, report_type, machine_id)
"""

import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from gateway.report_models import ReportSpec, ExportMeta, REPORT_CN_NAMES
from gateway.report_renderer import RenderedReport

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_OUTPUT = BASE_DIR / "reports" / "generated"
PDF_OUTPUT = BASE_DIR / "reports" / "pdfs"


@dataclass
class DeliveryResult:
    """Returned by deliver_report() — consumed by API routes and scheduled jobs."""
    success: bool
    html_url: str | None = None
    pdf_url: str | None = None
    html_size_kb: float = 0.0
    pdf_size_kb: float = 0.0
    base_name: str | None = None
    report_type: str = ""
    text_summary: str = ""
    machine_id: str | None = None
    errors: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def deliver_report(
    spec: ReportSpec,
    rendered: RenderedReport,
    report_type: str,
    machine_id: str | None = None,
    send_email: bool = False,
) -> DeliveryResult:
    """
    Save rendered report to disk, generate URLs, optionally send email.

    Args:
        spec: The ReportSpec that was rendered
        rendered: Output from report_renderer.render_report()
        report_type: "weekly" | "device" | "risk" | ...
        machine_id: Target machine (for device/work_order reports)
        send_email: Whether to send via SMTP

    Returns:
        DeliveryResult with URLs and metadata
    """
    os.makedirs(REPORTS_OUTPUT, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cn = REPORT_CN_NAMES.get(report_type, report_type)

    if report_type == "device" and machine_id:
        base_name = f"{cn}_{machine_id}_{ts}"
    else:
        base_name = f"{cn}_{ts}"

    errors = list(rendered.errors)

    # ── Save HTML ──
    html_url = None
    html_size_kb = 0.0
    if rendered.html:
        try:
            html_path = REPORTS_OUTPUT / f"{base_name}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(rendered.html)
            html_url = f"/reports/generated/{base_name}.html"
            html_size_kb = round(len(rendered.html.encode("utf-8")) / 1024, 1)
        except Exception as e:
            errors.append(f"html_save: {e}")

    # ── Save PDF ──
    pdf_url = None
    pdf_size_kb = 0.0
    if rendered.pdf_bytes:
        try:
            os.makedirs(PDF_OUTPUT, exist_ok=True)
            pdf_path = PDF_OUTPUT / f"{base_name}.pdf"
            with open(pdf_path, "wb") as f:
                f.write(rendered.pdf_bytes)
            pdf_url = f"/reports/pdfs/{base_name}.pdf"
            pdf_size_kb = round(len(rendered.pdf_bytes) / 1024, 1)
        except Exception as e:
            errors.append(f"pdf_save: {e}")

    # ── Email ──
    email_sent = False
    if send_email:
        try:
            _send_report_email(spec, html_url, pdf_url)
            email_sent = True
        except Exception as e:
            errors.append(f"email: {e}")

    # ── Update export meta ──
    spec.export_meta = ExportMeta(
        html_url=html_url,
        pdf_url=pdf_url,
        email_sent=email_sent,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        file_size_kb=html_size_kb,
        validated=getattr(spec.export_meta, 'validated', True),
    )

    summary = spec.summary or "Report generated successfully."

    return DeliveryResult(
        success=len(errors) == 0 or html_url is not None,
        html_url=html_url,
        pdf_url=pdf_url,
        html_size_kb=html_size_kb,
        pdf_size_kb=pdf_size_kb,
        base_name=base_name,
        report_type=report_type,
        text_summary=summary,
        machine_id=machine_id,
        errors=errors,
    )


def _send_report_email(spec: ReportSpec, html_url: str | None, pdf_url: str | None) -> None:
    """Send report notification email. Thin wrapper over notification_service."""
    try:
        from gateway.notification_service import _send_email, _is_configured
        from gateway.config import SMTP_USER
        if _is_configured() and html_url:
            summary_text = _strip_markdown(spec.summary[:300])
            subject = f"[{spec.title}] 报告已生成"
            body = (
                f"<p style='color:#e6ebf2;'>{summary_text}</p>"
                f"<p><a href='{html_url}' style='color:#4d94ff;'>查看HTML报告</a></p>"
            )
            if pdf_url:
                body += f"<p><a href='{pdf_url}' style='color:#4d94ff;'>下载PDF</a></p>"
            _send_email(SMTP_USER, subject, body)
    except Exception:
        pass  # Email is best-effort


def _strip_markdown(text: str) -> str:
    """Remove basic Markdown formatting for plain-text display."""
    import re
    text = re.sub(r'#{1,6}\s*', '', text)      # headings
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)  # bold/italic
    text = re.sub(r'`([^`]+)`', r'\1', text)   # inline code
    text = text.replace('###', '').replace('**', '').replace('*', '')
    text = text.replace('\n', '<br>')
    return text
