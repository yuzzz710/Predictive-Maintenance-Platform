"""
Report Orchestrator — Layer 2 of the report system (refactored).

Config-driven report generation pipeline:
  1. Load report_config.json for the requested report_type
  2. Collect data via Layer 1 (report_data_collector)
  3. Assemble ReportSpec with sections, evidence chain, summary
  4. Render via Layer 3 (report_renderer)
  5. Deliver via Layer 4 (report_delivery)

Backward-compatible: function signature and return dict unchanged.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from gateway.report_models import (
    ReportSpec, SectionSpec, ChartSpec, TableSpec, ExportMeta,
)
from gateway.report_data_collector import collect_all_context
from gateway.report_renderer import render_report, render_email, CN_NAMES
from gateway.report_delivery import deliver_report
from gateway.report_pdf import try_convert_pdf, simple_markdown_to_html

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "report_config.json"


# ══════════════════════════════════════════════════════════════════════════
# Config loading
# ══════════════════════════════════════════════════════════════════════════

def _load_config(report_type: str) -> dict:
    """Load report type config from report_config.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        full_cfg = json.load(f)

    rt_config = full_cfg.get("report_types", {}).get(report_type)
    if not rt_config:
        raise ValueError(f"Unknown report type: {report_type}")

    # Inject LLM system prompt if applicable
    if rt_config.get("llm_enabled"):
        prompt_key = rt_config.get("llm_system_prompt_key", "work_order")
        rt_config["_system_prompt"] = full_cfg.get("llm_system_prompts", {}).get(prompt_key, "")
        rt_config["_llm_prompts"] = full_cfg.get("llm_system_prompts", {})

    return rt_config


# ══════════════════════════════════════════════════════════════════════════
# ReportSpec assembly
# ══════════════════════════════════════════════════════════════════════════

def _build_spec(ctx, config: dict, machine_id: str | None) -> ReportSpec:
    """Assemble ReportSpec from collected context + config sections."""
    report_type = ctx.report_type

    # ── Sections ──
    sections = []
    for sec_cfg in config.get("sections", []):
        sec = SectionSpec(
            key=sec_cfg["key"],
            title=sec_cfg["title"],
            order=sec_cfg["order"],
            enabled=True,
            template_block=sec_cfg.get("template_block", ""),
        )
        sections.append(sec)

    # ── Evidence chain ──
    evidence = {
        "conclusion": "",
        "indicators": {},
        "data_sources": list(config.get("data_sources", [])),
        "source_status": ctx.source_status,
        "failed_sources": ctx.failed_sources,
    }
    if ctx.root_cause:
        evidence["root_cause_confidence"] = ctx.root_cause.get("overall_confidence", 0)
        evidence["root_causes"] = ctx.root_cause.get("root_causes", [])
    if ctx.health_analysis:
        evidence["health_scores"] = ctx.health_analysis.get("scores", [])[:5]

    # ── Scope ──
    scope_parts = []
    if ctx.alerts_summary:
        scope_parts.append(f"告警设备 {ctx.alerts_summary.get('total', 0)} 台")
    if ctx.device_details:
        scope_parts.append(f"详细分析 {len(ctx.device_details)} 台")
    scope = "，".join(scope_parts) if scope_parts else f"报告类型: {report_type}"

    # ── Charts ──
    charts = []
    if ctx.device_details:
        charts.append(ChartSpec(chart_type="risk_distribution", title="高风险设备 — 紧急度评分", data={}))
    if ctx.fault_statistics and ctx.fault_statistics.get("fault_group_distribution"):
        charts.append(ChartSpec(chart_type="fault_distribution", title="故障分组分布", data={}))
    if ctx.cost_analysis and ctx.cost_analysis.get("cost_by_action"):
        charts.append(ChartSpec(chart_type="cost_breakdown", title="按措施类型划分的成本风险", data={}))
    for i, sc in enumerate(ctx.sensor_charts[:6]):
        charts.append(ChartSpec(
            chart_type="sensor_trend",
            title=f"{sc['machine_id']} {sc['sensor_label']} 趋势",
            data=sc.get("chart_data", {}),
        ))

    # ── Tables ──
    tables = []
    if ctx.health_analysis and ctx.health_analysis.get("scores"):
        rows = [[s["machine_id"], f"{s['health_score']:.1f}", s["trend"], s["top_risk"]]
                for s in ctx.health_analysis["scores"][:10]]
        tables.append(TableSpec(key="health_ranking", title="健康分排名", headers=["设备", "健康分", "趋势", "风险因子"], rows=rows))
    if ctx.parts_summary and ctx.parts_summary.get("top_parts"):
        rows = [[p["name"], str(p["count"])] for p in ctx.parts_summary["top_parts"]]
        tables.append(TableSpec(key="parts_top", title="备件需求 Top 10", headers=["备件名称", "需求数量"], rows=rows))

    # ── Summary ──
    summary = _build_summary(ctx, config)

    spec = ReportSpec(
        report_type=report_type,
        title=config.get("title", CN_NAMES.get(report_type, report_type)),
        scope=scope,
        summary=summary,
        sections=sections,
        charts=charts,
        tables=tables,
        recommendations=ctx.recommendations,
        cost_analysis=ctx.cost_analysis or {},
        evidence=evidence,
        export_meta=ExportMeta(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        context=ctx,
    )
    return spec


def _build_summary(ctx, config: dict) -> str:
    """Build executive summary from collected data."""
    alerts = ctx.alerts_summary or {}
    costs = ctx.cost_analysis or {}
    faults = ctx.fault_statistics or {}
    rca = ctx.root_cause or {}

    total_alarms = alerts.get("total", 0)
    thermal_count = alerts.get("thermal_drift_count", 0)
    shutdown_count = alerts.get("immediate_shutdown_count", 0)
    total_cost = costs.get("total_cost_at_risk", 0)

    lines = [
        f"## 执行摘要",
        f"",
        f"报告生成时间：{ctx.generated_at}",
        f"报告类型：{ctx.report_type}",
        f"",
        f"### 关键指标",
        f"- 当前需要关注的设备总数：{total_alarms} 台",
        f"- 热漂移设备：{thermal_count} 台",
        f"- 需要立即停机设备：{shutdown_count} 台",
        f"- 总成本风险：${total_cost:,.2f}",
    ]
    if faults.get("highest_fault_rate", {}).get("rate", 0) > 0:
        lines.append(
            f"- 最高故障率设备：{faults['highest_fault_rate']['machine_id']} "
            f"({faults['highest_fault_rate']['rate']}% 故障率)"
        )

    if shutdown_count > 0:
        lines.append(f"\n### ⚠ 紧急关注")
        lines.append(f"以下设备需要立即停机检查：{', '.join(alerts.get('immediate_shutdown_devices', [])[:5])}")

    if thermal_count > 0:
        lines.append(f"\n### 🔥 热漂移风险")
        lines.append(f"以下设备存在持续热积聚趋势：{', '.join(alerts.get('thermal_drift_devices', [])[:10])}")

    rca_causes = rca.get("root_causes", [])
    if rca_causes:
        lines.append(f"\n### 主要故障模式")
        for c in rca_causes[:3]:
            lines.append(f"- {c.get('cause', 'Unknown')}（置信度 {c.get('confidence', 0):.0%}）")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Public API — backward-compatible
# ══════════════════════════════════════════════════════════════════════════

def generate_maintenance_report(
    report_type: str = "weekly",
    machine_id: Optional[str] = None,
    top_n: int = 5,
    health_threshold: int = 30,
) -> dict:
    """
    Generate a maintenance report via the 4-layer pipeline.

    Args (unchanged from original):
        report_type: "weekly" | "device" | "risk" | "thermal" |
                     "health_critical" | "parts_summary" | "work_order"
        machine_id: Required for "device" and "work_order"
        top_n: Max devices for detailed analysis
        health_threshold: Health score cutoff for health_critical reports

    Returns (backward-compatible dict):
        {success, html_url, pdf_url, html_size_kb, pdf_size_kb,
         report_type, text_summary, machine_id, base_name, validated}
    """
    try:
        # ── 1. Load config ──
        config = _load_config(report_type)

        # ── 2. Collect data (Layer 1) ──
        ctx = collect_all_context(
            report_type=report_type,
            config=config,
            machine_id=machine_id,
            top_n=top_n,
            health_threshold=health_threshold,
        )

        # ── 3. Build ReportSpec ──
        spec = _build_spec(ctx, config, machine_id)

        # ── 4. LLM generation (if enabled) ──
        validated = True
        if config.get("llm_enabled") and machine_id:
            try:
                from gateway.report_llm import generate_work_order_from_spec
                markdown, validated = generate_work_order_from_spec(spec, machine_id, config)
                spec.llm_markdown = simple_markdown_to_html(markdown)
                spec.export_meta.validated = validated
            except Exception as e:
                spec.export_meta.validated = False
                spec.llm_markdown = (
                    f"> ⚠ LLM 生成失败: {e}\n\n"
                    + "本报告由系统降级模板自动生成，请人工审核后执行。"
                )

        # ── 5. Render (Layer 3) ──
        rendered = render_report(spec, fmt="html")

        # PDF if enabled
        if config.get("pdf_enabled") and rendered.html:
            try:
                rendered.pdf_bytes = try_convert_pdf(rendered.html)
            except Exception:
                pass

        # ── 6. Deliver (Layer 4) ──
        delivery = deliver_report(
            spec=spec,
            rendered=rendered,
            report_type=report_type,
            machine_id=machine_id,
            send_email=config.get("email_enabled", False),
        )

        return {
            "success": delivery.success,
            "html_url": delivery.html_url,
            "html_size_kb": delivery.html_size_kb,
            "pdf_url": delivery.pdf_url,
            "pdf_size_kb": delivery.pdf_size_kb,
            "base_name": delivery.base_name,
            "report_type": report_type,
            "text_summary": delivery.text_summary,
            "machine_id": machine_id,
            "validated": validated,
        }

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:2000],
            "report_type": report_type,
            "machine_id": machine_id,
            "text_summary": f"Report generation failed: {str(e)}",
        }
