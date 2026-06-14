"""
Report Renderer — Layer 3 of the report system.

Single entry point: render_report(spec, format).
All templates receive ONLY the ReportSpec object — no scattered arguments.

Usage:
    from gateway.report_renderer import render_report, RenderedReport
    result = render_report(spec, format="html")
"""

import json
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from gateway.report_models import ReportSpec
from gateway.report_charts import generate_all_charts
from gateway.report_pdf import try_convert_pdf, simple_markdown_to_html

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_TEMPLATES = BASE_DIR / "report_templates"
REPORTS_OUTPUT = BASE_DIR / "reports" / "generated"


@dataclass
class RenderedReport:
    """Output of the rendering layer — ready for delivery."""
    html: str | None = None
    markdown: str | None = None
    pdf_bytes: bytes | None = None
    chart_base64s: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def render_report(spec: ReportSpec, fmt: str = "html") -> RenderedReport:
    """Render a ReportSpec into the requested format.

    Args:
        spec: Fully assembled ReportSpec
        fmt: "html" | "markdown" | "pdf" | "email"

    Returns:
        RenderedReport with populated html/markdown/pdf_bytes fields
    """
    result = RenderedReport()

    # Generate charts (used by HTML)
    try:
        result.chart_base64s = generate_all_charts(spec)
    except Exception as e:
        result.errors.append(f"charts: {e}")

    if fmt in ("html", "pdf"):
        try:
            result.html = _render_html(spec, result.chart_base64s)
        except Exception as e:
            result.errors.append(f"html: {e}")

    if fmt == "markdown":
        try:
            result.markdown = _render_markdown(spec)
        except Exception as e:
            result.errors.append(f"markdown: {e}")

    if fmt == "pdf" and result.html:
        try:
            result.pdf_bytes = try_convert_pdf(result.html)
        except Exception as e:
            result.errors.append(f"pdf: {e}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# HTML rendering
# ══════════════════════════════════════════════════════════════════════════

CN_NAMES = {
    "weekly": "周度系统报告",
    "device": "单设备报告",
    "risk": "高风险设备报告",
    "thermal": "热漂移分析报告",
    "health_critical": "低健康分报告",
    "parts_summary": "备件需求汇总",
    "work_order": "工单执行报告",
}


def _render_html(spec: ReportSpec, chart_base64s: dict[str, str]) -> str:
    """Render ReportSpec to full HTML using Jinja2 template."""
    template_name = _get_template_name(spec.report_type)

    env = Environment(loader=FileSystemLoader(str(REPORT_TEMPLATES)))
    env.filters['money'] = lambda v: f"${v:,.0f}" if v else "$0"
    env.filters['r0'] = lambda v: f"{v:.0f}" if v is not None else "-"
    env.filters['r1'] = lambda v: f"{v:.1f}" if v is not None else "-"
    env.filters['pct'] = lambda v: f"{v:.0%}" if v is not None else "N/A"

    template = env.get_template(template_name)

    return template.render(
        spec=spec,
        charts=chart_base64s,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _get_template_name(report_type: str) -> str:
    """Map report type to Jinja2 template filename."""
    mapping = {
        "device": "device_report.html",
        "weekly": "weekly_report.html",
        "risk": "weekly_report.html",
        "thermal": "weekly_report.html",
        "health_critical": "weekly_report.html",
        "parts_summary": "weekly_report.html",
        "work_order": "work_order_report.html",
    }
    return mapping.get(report_type, "weekly_report.html")


# ══════════════════════════════════════════════════════════════════════════
# Markdown rendering (for LLM input / work order output)
# ══════════════════════════════════════════════════════════════════════════

def _render_markdown(spec: ReportSpec) -> str:
    """Render ReportSpec as structured Markdown.

    This produces clean Markdown that serves as LLM input context
    or as a human-readable text fallback when HTML/PDF fail.
    """
    lines = [f"# {spec.title}", "", f"> {spec.scope}", "", spec.summary, ""]

    for section in spec.enabled_sections:
        lines.append(f"## {section.title}")
        lines.append("")
        if section.degradation_reason:
            lines.append(f"> ⚠ 此章节数据缺失: {section.degradation_reason}")
            lines.append("")

    if spec.recommendations:
        lines.append("## 维护建议")
        lines.append("")
        for r in spec.recommendations[:10]:
            lines.append(f"- **{r.get('machine_id', '')}** (P{r.get('priority', '?')}): {r.get('suggestion', '')[:200]}")
        lines.append("")

    if spec.cost_analysis:
        lines.append(f"## 成本风险: ${spec.cost_analysis.get('total_cost_at_risk', 0):,.0f}")
        lines.append("")

    if spec.disabled_sections:
        lines.append("## 降级说明")
        for s in spec.disabled_sections:
            lines.append(f"- {s.title}: {s.degradation_reason or '数据不可用'}")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Email rendering
# ══════════════════════════════════════════════════════════════════════════

def render_email(template_name: str, context: dict) -> str:
    """Render a Jinja2 email template with the given context dict.

    Used by report_delivery.py and scheduled_jobs.py instead of
    building inline HTML.
    """
    env = Environment(loader=FileSystemLoader(str(REPORT_TEMPLATES)))
    template = env.get_template(template_name)
    return template.render(**context, generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
