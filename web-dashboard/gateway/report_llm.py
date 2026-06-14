"""
Report LLM — strict LLM boundary for work order report generation.

LLM is ONLY used for:
- Converting structured data → natural-language work order narratives
- Generating human-readable explanations from data

LLM NEVER generates numbers, chart conclusions, or factual claims.
All facts MUST come from the ReportSpec + expert rules JSON.

Usage:
    from gateway.report_llm import generate_work_order_from_spec
    markdown, is_valid = generate_work_order_from_spec(spec)
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Expert rules path ──
SKILLS_DECISION = (
    BASE_DIR.parent / "skills" / "predictive-maintenance-decision" / "scripts"
)
EXPERT_RULES_PATH = SKILLS_DECISION / "data" / "maintenance_expert_rules.json"


# ══════════════════════════════════════════════════════════════════════════
# DeepSeek API config
# ══════════════════════════════════════════════════════════════════════════

def _load_api_config():
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


def _load_system_prompt(config: dict) -> str:
    """Get the LLM system prompt from report config."""
    prompt_key = config.get("llm_system_prompt_key", "work_order")
    prompts = config.get("_llm_prompts", {})
    return prompts.get(prompt_key, "")


def _load_expert_rules() -> dict:
    """Load maintenance expert rules database for prompt injection."""
    if EXPERT_RULES_PATH.exists():
        with open(EXPERT_RULES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ══════════════════════════════════════════════════════════════════════════
# Section validation
# ══════════════════════════════════════════════════════════════════════════

REQUIRED_SECTION_KEYWORDS = [
    ["问题摘要", "设备状态", "当前状态"],
    ["可能原因", "原因分析", "故障原因"],
    ["检查步骤", "排查步骤", "诊断步骤"],
    ["备件", "工具清单", "备件与工具"],
    ["安全注意", "安全提醒", "安全"],
    ["验证方法", "修复后验证", "验证"],
    ["执行时段", "建议执行", "时间窗口", "执行时间"],
]


def validate_work_order_output(text: str) -> bool:
    """Check that LLM output contains at least 5 of 7 required sections."""
    matched = 0
    for keywords in REQUIRED_SECTION_KEYWORDS:
        if any(kw in text for kw in keywords):
            matched += 1
    return matched >= 5


# ══════════════════════════════════════════════════════════════════════════
# Prompt construction
# ══════════════════════════════════════════════════════════════════════════

def _build_work_order_prompt(spec, machine_id: str) -> str:
    """Build the LLM user prompt from structured ReportSpec + expert rules.

    Strict rule: input is ONLY spec.to_summary_dict() + expert_rules JSON.
    No raw context dict is passed — the LLM only sees curated structured data.
    """
    expert_rules = _load_expert_rules()
    ctx = spec.context
    wc = ctx.work_order_context if ctx else {}

    # Determine primary pattern
    pattern = wc.get("primary_pattern", "combined_degradation") if wc else "combined_degradation"
    if pattern not in expert_rules:
        pattern = "combined_degradation"
    rules = expert_rules.get(pattern, {})

    # Serialize expert rules for this pattern
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
                rules_text += (
                    f"- **{s.get('priority', '?')} [{s.get('duration', '?')}]** {s.get('step', '')}\n"
                    f"  - 🔧 工具：{s.get('tool', '')}\n"
                    f"  - ✅ 标准：{s.get('criterion', '')}\n"
                )

        safety = rules.get("safety_notes", [])
        if safety:
            rules_text += "\n## 参考知识：安全注意事项\n"
            for s in safety:
                rules_text += f"- {s}\n"

        verify = rules.get("verification_after_repair", [])
        if verify:
            rules_text += "\n## 参考知识：修复后验证标准\n"
            for v in verify:
                rules_text += (
                    f"- **{v.get('id', '')}**: {v.get('method', '')}\n"
                    f"  - 判定标准：{v.get('criterion', '')}\n"
                    f"  - 预计时长：{v.get('duration', '')}\n"
                )

        parts = rules.get("parts_and_tools", {})
        if parts:
            likely = parts.get("likely_parts", [])
            if likely:
                rules_text += "\n## 参考知识：可能需要更换的备件\n"
                for p in likely:
                    rules_text += (
                        f"- {p.get('name', '')} ({p.get('part_number', 'N/A')}) "
                        f"×{p.get('qty', 1)} 单价${p.get('unit_cost', 0)}\n"
                    )

    # Build structured prompt — spec summary (facts only) + expert rules
    spec_summary = json.dumps(spec.to_summary_dict(), ensure_ascii=False, indent=2)

    # Device context as structured JSON (not raw text dump)
    device_ctx = json.dumps(wc, ensure_ascii=False, indent=2, default=str) if wc else "{}"

    return f"""请为以下设备生成完整的维护执行单。

## 设备结构化数据（全部来自系统采集，不得编造额外数据）
```json
{device_ctx}
```

## 报告摘要（系统计算得出，可引用但不可篡改）
```json
{spec_summary}
```

## 故障诊断模式专业知识
{rules_text if rules_text else "（该诊断模式暂无预置专家规则，请基于通用CNC维护经验生成，但必须在证据中标注为"通用经验"而非"系统数据"）"}

## 生成要求
请严格按照系统提示词中的7章节格式输出。确保：
1. 所有数值必须来自上述结构化数据，不得编造任何数字
2. 检查步骤融合参考知识，可根据设备实际情况调整
3. 安全注意事项必须包含电气安全（断电/LOTO/验电）和热安全（烫伤防护）
4. 验证标准必须量化，不可模糊（如"电压<±5%"而非"电压正常"）
5. 输出为Markdown格式，不要用代码块包裹"""


# ══════════════════════════════════════════════════════════════════════════
# DeepSeek API call
# ══════════════════════════════════════════════════════════════════════════

def _call_deepseek(system_prompt: str, user_prompt: str) -> str:
    """Call DeepSeek API synchronously. Raises RuntimeError on failure."""
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

    return resp.json()["choices"][0]["message"]["content"]


# ══════════════════════════════════════════════════════════════════════════
# Fallback — static Markdown when LLM is unavailable
# ══════════════════════════════════════════════════════════════════════════

def _build_fallback_markdown(spec, machine_id: str) -> str:
    """Generate minimal static Markdown work order when LLM is not available."""
    ctx = spec.context
    wc = ctx.work_order_context if ctx else {}
    z = wc.get("z_scores", {}) if wc else {}
    health = wc.get("health_score", "N/A") if wc else "N/A"
    priority = wc.get("priority", "?") if wc else "?"
    cost = wc.get("cost_at_risk", 0) if wc else 0
    pattern = wc.get("primary_pattern", "unknown") if wc else "unknown"

    return f"""## 1. 问题摘要
设备 **{machine_id}** 当前告警等级 **P{priority}**，健康评分 {health}/100。
诊断模式：{pattern}。
Z-Score: V={z.get('z_voltage', 'N/A')} A={z.get('z_amperage', 'N/A')} T={z.get('z_temperature', 'N/A')} C={z.get('z_composite', 'N/A')}。
成本风险：${cost:,.0f}。

> ⚠ 本报告由系统自动生成（LLM不可用，退回静态模板）。请维护班长人工审核。

## 2. 可能原因
1. 传感器信号漂移（概率：中，基于z-score异常）
2. 电气连接不良（概率：中，基于电压波动）
3. 机械部件磨损（概率：低，基于运行时长）
4. 热积聚（概率：低，基于温度趋势）

## 3. 检查步骤
- **P0 [15min]** 执行LOTO安全锁定程序
- **P1 [30min]** 检查传感器连接与校准状态
- **P2 [45min]** 检查电气接线端子紧固情况
- **P3 [60min]** 执行预防性维护手册标准检查

## 4. 备件与工具清单
请参照标准维护手册和设备BOM清单。

## 5. 安全注意事项
1. 必须执行LOTO（锁定/挂牌/验电）
2. 佩戴防护手套和护目镜
3. 注意高温部件烫伤风险
4. 双人作业，一人操作一人监护

## 6. 修复后验证方法
1. 运行设备30分钟，监测参数是否恢复正常
2. 对比修复前后z-score值
3. 记录修复过程和更换件信息

## 7. 建议执行时段
建议在本班次内安排检查，预计总工时 2-3 小时。
"""


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def generate_work_order_from_spec(spec, machine_id: str, config: dict) -> tuple[str, bool]:
    """
    Generate work order Markdown from structured ReportSpec.

    Args:
        spec: ReportSpec with populated context.work_order_context
        machine_id: Target machine ID
        config: Report type config dict (containing llm_system_prompt_key)

    Returns:
        (markdown_text, is_valid)
        - Normal path: LLM-generated Markdown, validated
        - Fallback path: static template Markdown, is_valid=False
    """
    # System prompt is injected by _load_config() in orchestrator.
    # If missing, go straight to fallback — no on-disk re-read here.
    system_prompt = config.get("_system_prompt", "")

    if not system_prompt:
        return _build_fallback_markdown(spec, machine_id), False

    try:
        user_prompt = _build_work_order_prompt(spec, machine_id)
        raw_output = _call_deepseek(system_prompt, user_prompt)
        is_valid = validate_work_order_output(raw_output)

        if not is_valid:
            raw_output = (
                "> ⚠ 自动校验未通过——部分章节可能不完整，请人工审核后执行。\n\n"
                + raw_output
            )

        return raw_output, is_valid
    except Exception:
        return _build_fallback_markdown(spec, machine_id), False
