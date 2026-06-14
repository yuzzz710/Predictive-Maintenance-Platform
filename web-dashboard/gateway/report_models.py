"""
Report Unified Data Models — 报告系统统一数据结构

All report generation flows MUST construct these objects first,
then pass them to the renderer. No business logic in templates.

Usage:
    from gateway.report_models import (
        ReportContext, ReportSpec, SectionSpec,
        ChartSpec, TableSpec, ExportMeta,
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ══════════════════════════════════════════════════════════════════════════
# Section specification
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SectionSpec:
    """One report section — title, order, and whether it's enabled."""
    key: str
    title: str
    order: float
    enabled: bool = True
    template_block: str = ""
    degradation_reason: str | None = None  # set when disabled due to data failure

    def disable(self, reason: str) -> None:
        self.enabled = False
        self.degradation_reason = reason


# ══════════════════════════════════════════════════════════════════════════
# Chart specification
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class ChartSpec:
    """One chart — type identifier + data + optional pre-rendered base64 PNG."""
    chart_type: str  # "risk_distribution" | "fault_distribution" | "cost_breakdown" | "sensor_trend"
    title: str
    data: dict = field(default_factory=dict)
    base64_png: str | None = None
    enabled: bool = True


# ══════════════════════════════════════════════════════════════════════════
# Table specification
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class TableSpec:
    """One data table — key, title, column headers, rows."""
    key: str
    title: str
    headers: list[str] = field(default_factory=list)
    rows: list[list[str | float]] = field(default_factory=list)
    sort_by: str | None = None


# ══════════════════════════════════════════════════════════════════════════
# Export metadata
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class ExportMeta:
    """Export tracking — URLs, sizes, validation status."""
    html_url: str | None = None
    pdf_url: str | None = None
    email_sent: bool = False
    generated_at: str = ""
    file_size_kb: float = 0.0
    validated: bool = True  # for LLM output validation


# ══════════════════════════════════════════════════════════════════════════
# Report context — all raw data collected from sources
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class ReportContext:
    """Container for ALL raw data collected by the data-collection layer.

    Each field corresponds to one data source.  Fields are None when
    the source is not applicable or when it failed (degradation).
    """
    report_type: str
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # ── Alert overview ──
    alerts_summary: dict | None = None

    # ── Per-device status (list of query_device_status results) ──
    device_details: list[dict] = field(default_factory=list)

    # ── Sensor trend chart data ──
    sensor_charts: list[dict] = field(default_factory=list)

    # ── Fault statistics across target devices ──
    fault_statistics: dict | None = None

    # ── Root cause analysis for primary device ──
    root_cause: dict | None = None

    # ── Cost risk aggregation ──
    cost_analysis: dict | None = None

    # ── Health score ranking ──
    health_analysis: dict | None = None

    # ── Spare parts demand aggregation ──
    parts_summary: dict | None = None

    # ── Predictability limit explanation ──
    predictability_context: dict | None = None

    # ── Maintenance recommendations (sorted by priority) ──
    recommendations: list[dict] = field(default_factory=list)

    # ── Work-order-specific aggregated context ──
    work_order_context: dict | None = None

    # ── Source traceability — which data sources succeeded / failed ──
    source_status: dict[str, bool] = field(default_factory=dict)

    def mark_source_ok(self, name: str) -> None:
        self.source_status[name] = True

    def mark_source_fail(self, name: str) -> None:
        self.source_status[name] = False

    @property
    def failed_sources(self) -> list[str]:
        return [k for k, v in self.source_status.items() if not v]


# ══════════════════════════════════════════════════════════════════════════
# Report spec — the single object passed to renderers
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class ReportSpec:
    """Fully assembled report — ready for rendering.

    This is the ONLY object renderers receive.  Templates access
    everything through this spec; no separate dict arguments.
    """
    report_type: str
    title: str
    scope: str = ""
    summary: str = ""

    # ── Structure ──
    sections: list[SectionSpec] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)
    tables: list[TableSpec] = field(default_factory=list)

    # ── Content ──
    recommendations: list[dict] = field(default_factory=list)
    cost_analysis: dict = field(default_factory=dict)

    # ── Evidence chain ──
    evidence: dict = field(default_factory=dict)

    # ── Export ──
    export_meta: ExportMeta = field(default_factory=ExportMeta)

    # ── Raw data (for deep access in templates that need it) ──
    context: ReportContext | None = None

    # ── LLM output (populated for work_order type after LLM generation) ──
    llm_markdown: str | None = None

    @property
    def enabled_sections(self) -> list[SectionSpec]:
        return [s for s in self.sections if s.enabled]

    @property
    def disabled_sections(self) -> list[SectionSpec]:
        return [s for s in self.sections if not s.enabled]

    @property
    def enabled_charts(self) -> list[ChartSpec]:
        return [c for c in self.charts if c.enabled]

    def to_summary_dict(self) -> dict[str, Any]:
        """Minimal serialization for LLM prompts — facts only, no rendering noise."""
        return {
            "report_type": self.report_type,
            "title": self.title,
            "scope": self.scope,
            "summary": self.summary,
            "sections": [
                {"key": s.key, "title": s.title, "enabled": s.enabled}
                for s in self.sections
            ],
            "cost_analysis": self.cost_analysis,
            "recommendations": self.recommendations,
            "evidence": self.evidence,
        }
