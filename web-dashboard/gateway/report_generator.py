"""
Report Generator — HTML Template (Jinja2) + best-effort PDF conversion.

Primary output: Industrial dark-themed HTML report (Jinja2 + matplotlib charts).
Secondary output: PDF via WeasyPrint (if GTK3 available) or wkhtmltopdf.

Architecture:
  HTML Report is the CORE — preserves full industrial styling, charts, tables, AI summary.
  PDF is just an export format — gracefully degrades if no backend available.
"""
import os
import io
import sys
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_TEMPLATES = BASE_DIR / "report_templates"
REPORTS_OUTPUT = BASE_DIR / "reports" / "generated"

# ── Dark theme matplotlib style ──
BG_COLOR = "#0e1117"
CARD_COLOR = "#141820"
TEXT_COLOR = "#e6ebf2"
ACCENT_CYAN = "#00c9a0"
ACCENT_ORANGE = "#f0a030"
ACCENT_RED = "#f04040"
ACCENT_BLUE = "#4d94ff"
GRID_COLOR = "#1c2230"

plt.rcParams.update({
    "figure.facecolor": BG_COLOR,
    "axes.facecolor": CARD_COLOR,
    "axes.edgecolor": GRID_COLOR,
    "axes.labelcolor": TEXT_COLOR,
    "text.color": TEXT_COLOR,
    "xtick.color": TEXT_COLOR,
    "ytick.color": TEXT_COLOR,
    "grid.color": GRID_COLOR,
    "grid.alpha": 0.5,
    "figure.dpi": 150,
})


def _find_chinese_font():
    candidates = [
        "Microsoft YaHei", "PingFang SC", "SimHei", "Noto Sans CJK SC",
        "WenQuanYi Micro Hei", "Source Han Sans SC", "sans-serif",
    ]
    available = [f.name for f in font_manager.fontManager.ttflist]
    for name in candidates:
        if name in available:
            return name
    return "sans-serif"


CN_FONT = _find_chinese_font()
plt.rcParams["font.family"] = CN_FONT


# ══════════════════════════════════════════════════════════════════════════
# Chart Generators (matplotlib → base64 PNG for embedding in HTML)
# ══════════════════════════════════════════════════════════════════════════

def _chart_sensor_trend(chart_data: dict, title: str = "") -> str:
    """Generate a sensor trend line chart → base64 PNG."""
    fig, ax = plt.subplots(figsize=(8, 3))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(CARD_COLOR)

    x = chart_data.get("x_axis", chart_data.get("xAxis", []))
    for s in chart_data.get("series", []):
        data = s.get("data", [])
        label = s.get("name", "")
        color = s.get("lineStyle", {}).get("color", ACCENT_CYAN)
        ls = s.get("lineStyle", {}).get("type", "solid")
        ax.plot(range(len(data)), data, color=color, linewidth=1.5,
                linestyle="--" if ls == "dashed" else "-", label=label, alpha=0.9)

    thresholds = chart_data.get("thresholds", {})
    if thresholds:
        for key, val in thresholds.items():
            if val is not None:
                style = "--" if "warning" in key else ":"
                alpha_val = 0.4 if "warning" in key else 0.6
                ax.axhline(y=val, color=ACCENT_RED, linestyle=style,
                          linewidth=0.8, alpha=alpha_val)

    anomalies = chart_data.get("anomalies", [])
    if anomalies:
        idxs, vals = [], []
        for a in anomalies:
            d = a.get("date", "")
            v = a.get("value_raw", a.get("value", 0))
            if d in x:
                idxs.append(x.index(d))
                vals.append(v)
        if idxs:
            ax.scatter(idxs, vals, c=ACCENT_RED, s=30, zorder=5, marker='x', label='异常点')

    ax.set_title(title or chart_data.get("title", ""), fontsize=10, color=TEXT_COLOR, pad=8)
    ax.legend(fontsize=7, loc='upper right', framealpha=0.3, facecolor=BG_COLOR,
             edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=7)
    if len(x) > 20:
        step = len(x) // 10
        ax.set_xticks(range(0, len(x), step))
        ax.set_xticklabels([x[i] for i in range(0, len(x), step)], rotation=30, ha='right', fontsize=6)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _chart_risk_distribution(report_data: dict) -> str:
    """Horizontal bar chart of top risk devices → base64 PNG."""
    devices = report_data.get("device_details", [])
    if not devices:
        return ""

    fig, ax = plt.subplots(figsize=(8, 3))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(CARD_COLOR)

    def _get_wo(d):
        return d.get("industrial_plan") or d.get("work_order") or {}
    sorted_devs = sorted(devices,
                        key=lambda d: _get_wo(d).get("urgency_score", 0) or 0,
                        reverse=True)[:10]
    names = [d["machine_id"] for d in sorted_devs]
    scores = [_get_wo(d).get("urgency_score", 0) or 0 for d in sorted_devs]
    colors = [ACCENT_RED if s > 70 else ACCENT_ORANGE if s > 40 else ACCENT_CYAN for s in scores]

    ax.barh(range(len(names)), scores, color=colors, height=0.6, alpha=0.85)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("紧急度评分", fontsize=8)
    ax.set_title("高风险设备 — 紧急度评分", fontsize=10, color=TEXT_COLOR, pad=8)
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.3)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _chart_fault_distribution(report_data: dict) -> str:
    """Donut chart of fault group distribution → base64 PNG."""
    fault_stats = report_data.get("fault_statistics", {})
    dist = fault_stats.get("fault_group_distribution", {})
    if not dist:
        return ""

    fig, ax = plt.subplots(figsize=(5, 3.5))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    labels = list(dist.keys())
    sizes = list(dist.values())
    pie_colors = {"Normal": "#3fb950", "Subtle": ACCENT_CYAN, "Thermal": ACCENT_ORANGE,
                  "High-Voltage": ACCENT_RED}
    colors = [pie_colors.get(l, ACCENT_BLUE) for l in labels]

    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, colors=colors, autopct='%1.1f%%',
        startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.4, edgecolor=BG_COLOR, linewidth=1),
    )
    for t in autotexts:
        t.set_color(TEXT_COLOR)
        t.set_fontsize(8)

    ax.set_title("故障分组分布", fontsize=10, color=TEXT_COLOR, pad=8)
    ax.legend(wedges, [f"{l} ({s})" for l, s in zip(labels, sizes)],
             fontsize=7, loc='lower center', ncol=2, framealpha=0.3,
             facecolor=BG_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _chart_cost_breakdown(report_data: dict) -> str:
    """Cost risk bar chart → base64 PNG."""
    cost_data = report_data.get("cost_analysis", {})
    by_action = cost_data.get("cost_by_action", {})
    if not by_action:
        return ""

    fig, ax = plt.subplots(figsize=(7, 2.8))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(CARD_COLOR)

    actions = list(by_action.keys())
    costs = list(by_action.values())
    action_labels = {
        "immediate_shutdown": "立即\n停机",
        "preventive_repair": "预防性\n维修",
        "schedule_inspection": "安排\n检查",
    }
    labels = [action_labels.get(a, a.replace("_", "\n").title()) for a in actions]

    ax.bar(range(len(actions)), costs, color=ACCENT_CYAN, alpha=0.8, width=0.5)
    ax.set_xticks(range(len(actions)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("风险成本 ($)", fontsize=8)
    ax.set_title("按措施类型划分的成本风险", fontsize=10, color=TEXT_COLOR, pad=8)
    ax.grid(axis='y', alpha=0.3)
    ax.tick_params(labelsize=8)
    for i, c in enumerate(costs):
        ax.text(i, c + max(costs) * 0.02, f"${c:,.0f}", ha='center', fontsize=7, color=TEXT_COLOR)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ══════════════════════════════════════════════════════════════════════════
# HTML Report Generator (PRIMARY)
# ══════════════════════════════════════════════════════════════════════════

def _render_html(report_data: dict, template_name: str) -> str:
    """Render Jinja2 template with report_data + embedded charts → HTML string."""
    # Generate charts
    charts = {
        "risk_distribution": _chart_risk_distribution(report_data),
        "fault_distribution": _chart_fault_distribution(report_data),
        "cost_breakdown": _chart_cost_breakdown(report_data),
    }

    sensor_charts = report_data.get("sensor_charts", [])
    for i, sc in enumerate(sensor_charts[:6]):
        if sc.get("chart_data"):
            chart_b64 = _chart_sensor_trend(
                sc["chart_data"],
                f"{sc['machine_id']} {sc['sensor_label']} 趋势"
            )
            charts[f"sensor_trend_{i}"] = chart_b64

    # Jinja2 with custom filters
    env = Environment(loader=FileSystemLoader(str(REPORT_TEMPLATES)))
    env.filters['money'] = lambda v: f"${v:,.0f}" if v else "$0"
    env.filters['r0'] = lambda v: f"{v:.0f}" if v is not None else "-"
    env.filters['r1'] = lambda v: f"{v:.1f}" if v is not None else "-"
    env.filters['pct'] = lambda v: f"{v:.0%}" if v is not None else "N/A"
    template = env.get_template(template_name)

    return template.render(
        report=report_data,
        charts=charts,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _try_convert_pdf(html: str) -> Optional[bytes]:
    """Try converting HTML to PDF. Returns PDF bytes or None if all backends fail."""
    # Backend 1: WeasyPrint (best quality, needs GTK3 on Windows)
    try:
        from weasyprint import HTML as WHTML
        return WHTML(string=html).write_pdf()
    except Exception:
        pass

    # Backend 2: wkhtmltopdf via pdfkit
    try:
        import pdfkit
        return pdfkit.from_string(html, False)
    except Exception:
        pass

    # Backend 3: xhtml2pdf (limited CSS but sometimes works)
    try:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        pisa.CreatePDF(html, dest=buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        pass

    return None


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def generate_report(report_data: dict, report_type: str = "weekly",
                    machine_id: Optional[str] = None) -> dict:
    """
    Generate an industrial AI maintenance report.

    Primary output: HTML file (full styling, charts, AI summary).
    Secondary output: PDF (best-effort, depends on system backends).

    Returns:
        {"success": bool, "html_url": str, "pdf_url": str|None, ...}
    """
    os.makedirs(REPORTS_OUTPUT, exist_ok=True)

    template_map = {
        "device": "device_report.html",
        "weekly": "weekly_report.html",
        "risk": "weekly_report.html",
        "thermal": "weekly_report.html",
        "health_critical": "weekly_report.html",
        "parts_summary": "weekly_report.html",
    }
    template = template_map.get(report_type, "weekly_report.html")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cn_names = {
        "weekly": "周度系统报告",
        "device": "单设备报告",
        "risk": "高风险设备报告",
        "thermal": "热漂移分析报告",
        "health_critical": "低健康分报告",
        "parts_summary": "备件需求汇总",
        "work_order": "工单执行报告",
    }
    cn = cn_names.get(report_type, report_type)
    if report_type == "device" and machine_id:
        base_name = f"{cn}_{machine_id}_{ts}"
    else:
        base_name = f"{cn}_{ts}"

    try:
        # ── PRIMARY: HTML Report ──
        html = _render_html(report_data, template)

        html_path = REPORTS_OUTPUT / f"{base_name}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        html_url = f"/reports/generated/{base_name}.html"
        html_size_kb = round(len(html.encode("utf-8")) / 1024, 1)

        # ── SECONDARY: Best-effort PDF ──
        pdf_url = None
        pdf_size_kb = 0

        pdf_bytes = _try_convert_pdf(html)
        if pdf_bytes:
            pdf_path = REPORTS_OUTPUT / f"{base_name}.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            pdf_url = f"/reports/generated/{base_name}.pdf"
            pdf_size_kb = round(len(pdf_bytes) / 1024, 1)

        text_summary = report_data.get("summary", "Report generated successfully.")

        return {
            "success": True,
            "html_url": html_url,
            "html_size_kb": html_size_kb,
            "pdf_url": pdf_url,
            "pdf_size_kb": pdf_size_kb,
            "base_name": base_name,
            "report_type": report_type,
            "text_summary": text_summary,
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:1000],
            "text_summary": f"Report generation failed: {str(e)}",
        }
