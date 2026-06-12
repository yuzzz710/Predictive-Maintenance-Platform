"""
Work Order Report Generator — 生成式维护执行单
================================================
Aggregates multi-source context, constructs LLM prompts with embedded
expert maintenance rules, calls DeepSeek API to generate natural-language
work order execution sheets, renders HTML, and converts to PDF.

Architecture:
  1. Context Aggregation — collects all available data for a work order
  2. Prompt Construction  — embeds expert rules + context into system/user prompt
  3. DeepSeek API Call    — synchronous, non-streaming for complete output
  4. Section Validation   — ensures all 7 required sections are present
  5. HTML Rendering       — wraps generated Markdown in a print-friendly template
  6. PDF Conversion       — reuses existing _try_convert_pdf() pipeline

Usage:
    from gateway.work_order_report_generator import generate_work_order_report
    result = generate_work_order_report(machine_id="CNC_036", context=ctx)
    # result = {"success": True, "html_url": "...", "pdf_url": "...", ...}
"""
import os
import io
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import httpx

# ── Paths ──
BASE_DIR = Path(__file__).resolve().parent.parent  # web-dashboard/
REPORTS_OUTPUT = BASE_DIR / "reports" / "generated"
SKILLS_DECISION = (
    BASE_DIR.parent / "skills" / "predictive-maintenance-decision" / "scripts"
)

# ── DeepSeek API config (same as gateway/config.py) ──
def _load_api_config():
    """Load API key from environment or .env, matching gateway/config.py pattern."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        try:
            from dotenv import load_dotenv
            for p in [BASE_DIR / ".env", BASE_DIR.parent / ".env"]:
                if p.exists():
                    load_dotenv(p)
                    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
                    if api_key:
                        break
        except ImportError:
            pass
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    return api_key, base_url, model

DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL = _load_api_config()

# ── Expert Rules ──
def _load_expert_rules() -> dict:
    """Load the maintenance expert rules database."""
    rules_path = SKILLS_DECISION / "data" / "maintenance_expert_rules.json"
    if rules_path.exists():
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

EXPERT_RULES = _load_expert_rules()


# ══════════════════════════════════════════════════════════════════════════
# System Prompt
# ══════════════════════════════════════════════════════════════════════════

WORK_ORDER_SYSTEM_PROMPT = """你是工业CNC设备预测性维护高级专家，拥有20年现场维修经验。
你的任务是根据提供的设备多源监测数据，生成一份专业、可执行的现场维护执行单。

## 输出格式要求（必须严格包含以下全部7个章节，使用Markdown格式）

### 1. 问题摘要
用2-3句话概括设备当前状态：告警等级、核心异常参数、诊断模式、紧急程度。
必须引用具体数据（z-score值、成本风险金额、健康评分）。

### 2. 可能原因（按概率从高到低排列）
列出3-4个可能原因，每条包含：
- 原因描述
- 概率评估（高/中/低）
- 支撑证据（引用提供的上下文数据）
- 排除方法简述

### 3. 检查步骤（每步标注优先级、预计耗时、所需工具、判定标准）
至少5个步骤，按优先级P0→P1→P2→P3排列。P0为安全准备步骤（必须执行）。
每步格式：
- **P{N} [{耗时}min]** {步骤描述}
  - 🔧 工具：{所需工具}
  - ✅ 标准：{判定标准}

### 4. 备件与工具清单
分两部分：
- 可能需要更换的备件（名称、型号、数量、参考单价）
- 所需检测工具（逐项列出）
引用数据源中的实际备件编号和型号。

### 5. 安全注意事项
至少列出4条安全提醒，按严重程度排列。必须包含：
- 断电/锁定/挂牌(LOTO)要求
- 个人防护装备(PPE)要求
- 特殊危险源警示
- 作业制度要求

### 6. 修复后验证方法
列出至少3项验证测试，每项包含：
- 测试方法描述
- 量化判定标准
- 预计验证时长
引用提供的验收标准数据。

### 7. 建议执行时段
基于紧急度分数和SLA目标，给出：
- 推荐执行时间窗口（立即/本班次/24h内/本周）
- 预计总工时
- 对生产的影响评估
- 是否需要协调停机窗口

## 质量标准
- 语言：中文，专业术语可保留英文
- 数据引用：所有数字必须来自提供的上下文数据，不得编造
- 可操作性：每一条检查步骤现场人员拿到就能执行
- 安全性：安全提醒完整覆盖电气/热/机械三类风险
- 篇幅：总长度控制在1500-3000字"""


# ══════════════════════════════════════════════════════════════════════════
# HTML Template (print-friendly industrial dark theme)
# ══════════════════════════════════════════════════════════════════════════

def _build_html(machine_id: str, markdown_content: str, context: dict) -> str:
    """Wrap LLM-generated Markdown into a complete HTML report page."""
    priority = context.get("priority", "?")
    alert_level = context.get("alert_level", "?")
    action_type = context.get("action_type", "?")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    health_score = context.get("health_score", "N/A")
    cost_at_risk = context.get("cost_at_risk", 0)

    # Convert Markdown→HTML (simple approach: basic markdown parsing)
    html_body = _simple_markdown_to_html(markdown_content)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>维护执行单 — {machine_id}</title>
<style>
  :root {{
    --bg: #0e1117; --card: #141820; --card-alt: #181d26;
    --border: #1c2230; --text: #e6ebf2; --text2: #8e9aab; --text3: #5a6474;
    --cyan: #00c9a0; --amber: #f0a030; --red: #f04444; --blue: #4d94ff; --green: #3fb950;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'PingFang SC','Microsoft YaHei','Segoe UI',system-ui,sans-serif;
    line-height: 1.8; max-width: 960px; margin: 0 auto; padding: 40px 32px;
  }}
  .report-header {{
    border-bottom: 2px solid var(--cyan); padding-bottom: 20px; margin-bottom: 32px;
  }}
  .report-header h1 {{ font-size: 22px; color: var(--cyan); margin-bottom: 4px; }}
  .report-header .meta {{
    display: flex; gap: 24px; flex-wrap: wrap; font-size: 12px; color: var(--text2);
    font-family: 'Cascadia Code','Fira Code','Consolas',monospace;
  }}
  .report-header .meta span {{ color: var(--text); font-weight: 600; }}
  .meta-tags {{ display: flex; gap: 8px; margin-top: 8px; }}
  .meta-tag {{
    font-size: 10px; padding: 2px 10px; border-radius: 12px;
    font-family: 'Cascadia Code','Fira Code','Consolas',monospace;
    font-weight: 600;
  }}
  .tag-alarm {{ background: rgba(240,68,68,0.12); color: var(--red); border: 1px solid rgba(240,68,68,0.2); }}
  .tag-warning {{ background: rgba(240,160,48,0.12); color: var(--amber); border: 1px solid rgba(240,160,48,0.2); }}
  .tag-action {{ background: rgba(0,201,160,0.08); color: var(--cyan); border: 1px solid rgba(0,201,160,0.15); }}

  h2 {{
    font-size: 17px; color: var(--cyan); margin: 32px 0 14px;
    padding-bottom: 8px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 8px;
  }}
  h2 .sec-num {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 4px;
    background: rgba(0,201,160,0.08); color: var(--cyan);
    font-size: 13px; font-weight: 700; flex-shrink: 0;
  }}
  h3 {{ font-size: 14px; color: var(--text); margin: 16px 0 8px; }}
  p {{ font-size: 13px; color: var(--text2); margin-bottom: 8px; }}
  ul, ol {{ padding-left: 22px; margin-bottom: 12px; }}
  li {{ font-size: 13px; color: var(--text2); margin-bottom: 6px; }}
  strong {{ color: var(--text); }}
  code {{
    background: var(--card-alt); color: var(--cyan);
    padding: 1px 6px; border-radius: 3px; font-size: 12px;
    font-family: 'Cascadia Code','Fira Code','Consolas',monospace;
  }}
  blockquote {{
    border-left: 3px solid var(--amber); margin: 12px 0; padding: 10px 16px;
    background: rgba(240,160,48,0.04); border-radius: 0 4px 4px 0;
    font-size: 12px; color: var(--amber);
  }}
  table {{
    width: 100%; border-collapse: collapse; margin: 12px 0;
    font-size: 12px;
  }}
  th {{
    background: var(--card-alt); text-align: left; padding: 8px 12px;
    font-weight: 600; color: var(--text3); text-transform: uppercase;
    font-size: 10px; letter-spacing: 0.5px; border-bottom: 2px solid var(--border);
  }}
  td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border);
    color: var(--text2);
  }}
  .report-footer {{
    margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border);
    font-size: 11px; color: var(--text3); text-align: center;
  }}
  .disclaimer {{
    background: rgba(240,160,48,0.05); border: 1px dashed rgba(240,160,48,0.2);
    border-radius: 4px; padding: 12px 16px; margin-top: 24px;
    font-size: 11px; color: var(--amber);
  }}
  @media print {{
    body {{ background: #fff; color: #000; padding: 20px; }}
    h2 {{ color: #006b5e; border-bottom-color: #ccc; }}
    .report-header {{ border-bottom-color: #006b5e; }}
    .report-header h1 {{ color: #006b5e; }}
    .meta-tag {{ border-color: #999 !important; }}
    .disclaimer {{ background: #fff8e1; border-color: #ffc107; }}
  }}
</style>
</head>
<body>

<div class="report-header">
  <h1>🔧 设备维护执行单</h1>
  <div class="meta">
    <div>设备: <span>{machine_id}</span></div>
    <div>优先级: <span>P{priority}</span></div>
    <div>健康评分: <span>{health_score}/100</span></div>
    <div>风险成本: <span>${cost_at_risk:,.0f}</span></div>
    <div>生成时间: <span>{ts}</span></div>
  </div>
  <div class="meta-tags">
    <span class="meta-tag tag-alarm">{alert_level}</span>
    <span class="meta-tag tag-action">{action_type}</span>
  </div>
</div>

{html_body}

<div class="disclaimer">
  ⚠ <strong>重要提示：</strong>本执行单由 Industrial AI Copilot 基于设备实时监测数据自动生成。
  执行前请由维护班长审核确认。维修过程中如发现与执行单描述不符的情况，请以现场实际情况为准
  并及时更新维护记录。本执行单已存档至报告系统，可在「报告」页面查看历史版本。
</div>

<div class="report-footer">
  Industrial Predictive Maintenance System — AI-Generated Work Order Execution Sheet<br>
  生成时间: {ts} &nbsp;|&nbsp; 设备: {machine_id} &nbsp;|&nbsp; 由 DeepSeek 大模型辅助生成
</div>

</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════
# Simple Markdown→HTML converter (no external dependency)
# ══════════════════════════════════════════════════════════════════════════

def _simple_markdown_to_html(md: str) -> str:
    """Convert basic Markdown to HTML. Handles h2, h3, bold, code, lists, tables, blockquotes."""
    lines = md.split("\n")
    out = []
    in_list = False
    list_type = None
    in_table = False
    in_blockquote = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blockquote
        if stripped.startswith("> "):
            if not in_blockquote:
                out.append("<blockquote>")
                in_blockquote = True
            out.append(stripped[2:] + "<br>")
            i += 1
            continue
        elif in_blockquote and not stripped.startswith("> "):
            out.append("</blockquote>")
            in_blockquote = False

        # Code blocks (```)
        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            out.append(f"<pre><code>{_escape_html('\n'.join(code_lines))}</code></pre>")
            continue

        # Tables
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                out.append('<table>')
                in_table = True
            is_header = (i + 1 < len(lines) and
                        lines[i + 1].strip().startswith("|") and
                        "---" in lines[i + 1])
            tag = "th" if is_header else "td"
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            out.append("<tr>" + "".join(f"<{tag}>{_escape_html(c)}</{tag}>" for c in cells) + "</tr>")
            if is_header:
                i += 2  # skip separator row
                continue
            i += 1
            continue
        elif in_table:
            out.append("</table>")
            in_table = False

        # Headers
        if stripped.startswith("### "):
            out.append(f"<h3>{_inline_format(stripped[4:])}</h3>")
            i += 1; continue
        if stripped.startswith("## "):
            out.append(f"<h2><span class=\"sec-num\">§</span>{_inline_format(stripped[3:])}</h2>")
            i += 1; continue

        # Lists
        is_ul = stripped.startswith("- ") or stripped.startswith("* ")
        is_ol = len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] == ". "
        if is_ul or is_ol:
            if not in_list:
                list_type = "ul" if is_ul else "ol"
                out.append(f"<{list_type}>")
                in_list = True
            elif (is_ul and list_type == "ol") or (is_ol and list_type == "ul"):
                out.append(f"</{list_type}><{('ul' if is_ul else 'ol')}>")
                list_type = "ul" if is_ul else "ol"
            content = stripped[2:] if is_ul else stripped[stripped.index(". ") + 2:]
            out.append(f"<li>{_inline_format(content)}</li>")
            i += 1; continue
        elif in_list:
            out.append(f"</{list_type}>")
            in_list = False

        # Empty lines
        if not stripped:
            i += 1; continue

        # Paragraphs
        out.append(f"<p>{_inline_format(stripped)}</p>")
        i += 1

    # Close open blocks
    if in_list:
        out.append(f"</{list_type}>")
    if in_table:
        out.append("</table>")
    if in_blockquote:
        out.append("</blockquote>")

    return "\n".join(out)


def _inline_format(text: str) -> str:
    """Handle inline formatting: bold (**), code (`), italic (*)."""
    import re
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════════════════════════════════════════
# PDF Conversion (reuses existing _try_convert_pdf pattern)
# ══════════════════════════════════════════════════════════════════════════

def _try_convert_pdf(html: str):
    """Try converting HTML to PDF. Returns PDF bytes or None if all backends fail."""
    # Backend 1: WeasyPrint
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

    # Backend 3: xhtml2pdf
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
# Context Aggregation & Prompt Construction
# ══════════════════════════════════════════════════════════════════════════

def _build_user_prompt(machine_id: str, context: dict) -> str:
    """Construct the user prompt by embedding expert rules and multi-source context."""

    # ── Determine primary diagnostic pattern ──
    pattern = context.get("primary_pattern", "combined_degradation")
    if pattern not in EXPERT_RULES:
        pattern = "combined_degradation"
    rules = EXPERT_RULES.get(pattern, {})

    # ── Serialize expert rules for the pattern ──
    rules_text = ""
    if rules:
        causes = rules.get("common_causes", [])
        if causes:
            rules_text += "## 参考知识：该故障模式的常见原因\n"
            for c in causes:
                rules_text += f"- [{c.get('probability', '?')}概率] {c.get('cause', '')} — {c.get('evidence', '')}\n"

        steps = rules.get("inspection_steps", [])
        if steps:
            rules_text += "\n## 参考知识：该故障模式的标准检查步骤\n"
            for s in steps:
                rules_text += (f"- **{s.get('priority', '?')} [{s.get('duration', '?')}]** {s.get('step', '')}\n"
                             f"  - 🔧 工具：{s.get('tool', '')}\n"
                             f"  - ✅ 标准：{s.get('criterion', '')}\n")

        safety = rules.get("safety_notes", [])
        if safety:
            rules_text += "\n## 参考知识：安全注意事项\n"
            for s in safety:
                rules_text += f"- {s}\n"

        verify = rules.get("verification_after_repair", [])
        if verify:
            rules_text += "\n## 参考知识：修复后验证标准\n"
            for v in verify:
                rules_text += (f"- **{v.get('id', '')}**: {v.get('method', '')}\n"
                             f"  - 判定标准：{v.get('criterion', '')}\n"
                             f"  - 预计时长：{v.get('duration', '')}\n")

        parts = rules.get("parts_and_tools", {})
        if parts:
            likely = parts.get("likely_parts", [])
            if likely:
                rules_text += "\n## 参考知识：可能需要更换的备件\n"
                for p in likely:
                    rules_text += (f"- {p.get('name', '')} ({p.get('part_number', 'N/A')}) "
                                 f"×{p.get('qty', 1)} 单价${p.get('unit_cost', 0)}\n")

    # ── Serialize machine context ──
    ctx_json = json.dumps(context, ensure_ascii=False, indent=2, default=str)

    prompt = f"""请为以下设备生成完整的维护执行单。

## 设备上下文数据
```json
{ctx_json}
```

## 故障诊断模式专业知识
{rules_text if rules_text else "（该诊断模式暂无预置专家规则，请基于通用CNC维护经验生成）"}

## 生成要求
请严格按照系统提示词中的7章节格式输出。确保：
1. 引用上下文中的具体数据（z-score值、成本金额、备件编号）
2. 检查步骤融合上述参考知识，并可根据设备实际情况调整
3. 安全注意事项必须包含电气安全（断电/LOTO/验电）和热安全（烫伤防护）
4. 验证标准必须量化，不可模糊（如"电压<±5%"而非"电压正常"）
5. 输出为Markdown格式，不要用代码块包裹"""
    return prompt


# ══════════════════════════════════════════════════════════════════════════
# Section Validation
# ══════════════════════════════════════════════════════════════════════════

REQUIRED_SECTIONS = [
    "问题摘要", "可能原因", "检查步骤", "备件", "工具",
    "安全注意", "验证方法", "建议执行", "执行时段",
]


def validate_output(text: str) -> bool:
    """
    Check that the generated text contains all required sections.
    Uses fuzzy matching — at least 5 of the 7 core sections must be present.
    """
    required_keywords = [
        ["问题摘要", "设备状态", "当前状态"],
        ["可能原因", "原因分析", "故障原因"],
        ["检查步骤", "排查步骤", "诊断步骤"],
        ["备件", "工具清单", "备件与工具"],
        ["安全注意", "安全提醒", "安全"],
        ["验证方法", "修复后验证", "验证"],
        ["执行时段", "建议执行", "时间窗口", "执行时间"],
    ]

    matched = 0
    for keywords in required_keywords:
        if any(kw in text for kw in keywords):
            matched += 1

    return matched >= 5  # At least 5 of 7 sections present


# ══════════════════════════════════════════════════════════════════════════
# DeepSeek API Call
# ══════════════════════════════════════════════════════════════════════════

def _call_deepseek(system_prompt: str, user_prompt: str) -> str:
    """
    Call DeepSeek API synchronously (non-streaming) to generate the work order.
    Returns the generated Markdown text.
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not configured. Set DEEPSEEK_API_KEY env var "
            "or create a .env file in project root."
        )

    url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=httpx.Timeout(120.0))
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return content


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def generate_work_order_report(
    machine_id: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a natural-language work order execution sheet for a machine.

    Args:
        machine_id: Device ID, e.g. "CNC_036"
        context: Aggregated multi-source context dict with keys:
            - alert_level, action_type, priority, urgency_score
            - primary_pattern, cost_at_risk, health_score
            - z_scores (z_v, z_a, z_t, z_composite)
            - top_risk_factors, shap_summary
            - technician_type, spare_parts
            - suggested_window_days, sla_target_hours
            - fault_history_summary, acceptance_standards

    Returns:
        {"success": bool, "html_url": str, "pdf_url": str|None,
         "html_size_kb": float, "pdf_size_kb": float,
         "machine_id": str, "generated_at": str}
    """
    os.makedirs(REPORTS_OUTPUT, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"work_order_{machine_id}_{ts}"

    try:
        # ── Step 1: Build prompt ──
        user_prompt = _build_user_prompt(machine_id, context)

        # ── Step 2: Call DeepSeek ──
        raw_output = _call_deepseek(WORK_ORDER_SYSTEM_PROMPT, user_prompt)

        # ── Step 3: Validate ──
        is_valid = validate_output(raw_output)
        if not is_valid:
            # If validation fails, still proceed but flag it
            raw_output = (
                "> ⚠ 自动校验未通过——部分章节可能不完整，请人工审核后执行。\n\n"
                + raw_output
            )

        # ── Step 4: Render HTML ──
        html = _build_html(machine_id, raw_output, context)

        html_path = REPORTS_OUTPUT / f"{base_name}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        html_url = f"/reports/generated/{base_name}.html"
        html_size_kb = round(len(html.encode("utf-8")) / 1024, 1)

        # ── Step 5: Best-effort PDF ──
        pdf_url = None
        pdf_size_kb = 0

        pdf_bytes = _try_convert_pdf(html)
        if pdf_bytes:
            pdf_path = REPORTS_OUTPUT / f"{base_name}.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            pdf_url = f"/reports/generated/{base_name}.pdf"
            pdf_size_kb = round(len(pdf_bytes) / 1024, 1)

        return {
            "success": True,
            "html_url": html_url,
            "html_size_kb": html_size_kb,
            "pdf_url": pdf_url,
            "pdf_size_kb": pdf_size_kb,
            "machine_id": machine_id,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "validated": is_valid,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "machine_id": machine_id,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


# ══════════════════════════════════════════════════════════════════════════
# Batch generation (for pipeline integration)
# ══════════════════════════════════════════════════════════════════════════

def generate_work_orders_batch(
    work_orders: list,  # List of (machine_id, context) tuples
    max_orders: int = 5,
) -> list:
    """
    Generate execution sheets for multiple work orders.
    Processes sequentially to avoid rate-limiting the API.

    Args:
        work_orders: List of dicts with machine_id and context
        max_orders: Maximum number to generate (default 5 for API cost control)

    Returns:
        List of result dicts
    """
    results = []
    for i, wo in enumerate(work_orders[:max_orders]):
        mid = wo.get("machine_id", f"unknown_{i}")
        ctx = wo.get("context", wo)
        result = generate_work_order_report(mid, ctx)
        results.append(result)
    return results
