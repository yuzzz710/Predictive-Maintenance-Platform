"""
Report Charts — matplotlib chart generators extracted from report_generator.py.

All charts render to base64 PNG for embedding in HTML reports.
Dark industrial theme preserved from original code.
"""

import io
import base64

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ══════════════════════════════════════════════════════════════════════════
# Matplotlib dark theme
# ══════════════════════════════════════════════════════════════════════════

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


def _find_chinese_font() -> str:
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
# Public API
# ══════════════════════════════════════════════════════════════════════════

def generate_all_charts(spec) -> dict[str, str]:
    """Generate all needed charts from a ReportSpec → {chart_key: base64_png}."""
    charts = {}
    if not spec or not spec.context:
        return charts

    ctx = spec.context

    # Static charts
    if ctx.device_details:
        charts["risk_distribution"] = chart_risk_distribution(ctx)
    if ctx.fault_statistics:
        charts["fault_distribution"] = chart_fault_distribution(ctx)
    if ctx.cost_analysis:
        charts["cost_breakdown"] = chart_cost_breakdown(ctx)

    # Sensor trend charts (up to 6)
    for i, sc in enumerate(ctx.sensor_charts[:6]):
        if sc.get("chart_data"):
            charts[f"sensor_trend_{i}"] = chart_sensor_trend(
                sc["chart_data"],
                f"{sc['machine_id']} {sc['sensor_label']} 趋势"
            )

    return charts


# ══════════════════════════════════════════════════════════════════════════
# Individual chart functions
# ══════════════════════════════════════════════════════════════════════════

def chart_sensor_trend(chart_data: dict, title: str = "") -> str:
    """Sensor trend line chart → base64 PNG."""
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
                ax.axhline(y=val, color=ACCENT_RED, linestyle=style, linewidth=0.8, alpha=alpha_val)

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


def chart_risk_distribution(ctx) -> str:
    """Horizontal bar chart of top risk devices → base64 PNG."""
    devices = ctx.device_details
    if not devices:
        return ""

    fig, ax = plt.subplots(figsize=(8, 3))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(CARD_COLOR)

    def _get_wo(d):
        return d.get("industrial_plan") or d.get("work_order") or {}

    sorted_devs = sorted(devices, key=lambda d: _get_wo(d).get("urgency_score", 0) or 0, reverse=True)[:10]
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


def chart_fault_distribution(ctx) -> str:
    """Donut chart of fault group distribution → base64 PNG."""
    fault_stats = ctx.fault_statistics or {}
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


def chart_cost_breakdown(ctx) -> str:
    """Cost risk bar chart → base64 PNG."""
    cost_data = ctx.cost_analysis or {}
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
