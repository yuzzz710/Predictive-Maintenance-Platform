"""
Question Classifier — Route user questions to the right handler.
================================================================
Non-LLM, zero-latency classification using keyword + pattern matching.
Determines whether a question should trigger RAG retrieval or go
directly to the existing tool-calling data pipeline.

Categories:
  - data_query:      Device-specific data (CNC_042 status, sensor trends, alarms)
  - system_doc:      System usage / documentation (how to switch strategy, what's Z-Score)
  - maintenance_kb:  Maintenance knowledge (bearing replacement steps, safety procedures)
  - fault_case:      Historical fault case lookup (similar faults, Type 4 troubleshooting)
"""

import re
from typing import Dict, List


# ═══════════════════════════════════════════════════════════════════════════
# Keyword Sets (simpler and more robust than regex patterns)
# ═══════════════════════════════════════════════════════════════════════════

# Strong data query signals
DATA_QUERY_KEYWORDS = [
    # Device IDs (strongest signal)
    r'CNC[_\s]?\d{3}',
    # Pipeline/report generation actions
    r'(生成|跑|执行|运行|重新|generate|run|execute).*(报告|流水线|工单|维护计划|report|pipeline|work.order)',
    r'(报告|流水线|工单|维护计划|report|pipeline|work.order).*(生成|跑|执行|运行|generate|run|execute)',
    # Work order operations
    r'(告警|工单|分配|验收|派工|维修完成|归档|alarm|work.order|assign|dispatch|acceptance)',
    # Sensor data queries with device context
    r'(温度|电压|电流|转速|振动|temp|voltage|current|speed|vibration).*(趋势|曲线|变化|监控|走势|图表|trend|chart|monitor)',
    r'(趋势|曲线|变化|监控|走势|图表|trend).*(温度|电压|电流|转速|temp|voltage|current)',
    # Status checks with machine context
    r'(当前|现在|current|status).*(状态|情况|风险|告警|健康|risk|alarm|health)',
    r'(哪些|哪个|什么|which|what).*(设备|机器|machine).*(风险|告警|最高|最低|维护|risk|alarm|maintenance)',
    # Backtest / validation
    r'(回测|验证|漏报|检出|提前量|backtest|validation|lead.time)',
    # Inventory
    r'(库存|备件|采购|下单|inventory|stock|procurement|order)',
    # Technician
    r'(技师|员工|负载|排班|technician|staff|workload)',
    # RUL
    r'(RUL|剩余.*寿命|remaining.*life)',
    # Work order tracking
    r'(工单.*跟踪|工单.*状态|工单.*进度|work.order.*track|tracking)',
]

# System documentation keywords
SYSTEM_DOC_KEYWORDS = [
    # Chinese: how-to + system term
    r'(怎么|如何|怎样|怎么用).*(计算|切换|配置|选择|操作|使用|查看|设定|设置|确定)',
    r'(什么是|是什么|什么叫).*(健康分|基线|策略|Z.Score|角色|权限|降级|SHAP|RUL|T²|Hotelling)',
    r'(健康分|基线|策略|Z.Score|角色|权限|降级|SHAP|RUL|T²).*(是什么|什么意思|含义|定义|怎么|如何)',
    r'(区别|对比|差异|不同|哪个好).*(策略|角色|方案|模型|算法|架构)',
    r'(三种|三个|几种).*(策略|角色|方案|模型)',
    r'(公式|算法|原理|架构|设计|流程|步骤).*(怎么|如何|什么是|是什么)',
    r'(为什么).*(参数|传感器|预测|Youden|不够|不准|有限)',
    r'(基线.*溯源|溯源.*类型|方差.*分解|成本.*风险).*(是什么|有哪些|怎么)',
    r'(仪表盘|Dashboard|Tab|标签页).*(有哪些|怎么|功能)',
    r'(阈值|门限|Youden|Cohen|KS).*(怎么|如何|设定|确定|选择|计算)',
    r'(DAG|流水线|技能|skill|MCP|pipeline).*(怎么|如何|是什么|架构)',
    # English: how-to + system terms
    r'\bhow\b.*\b(calculat|comput|switch|config|select|us(?:e|ing)|view|access|chang|set|determin|choos)',
    r'\bwhat\s+(is|are)\b.*\b(health.score|baseline|strateg|role|permission|degradation|SHAP|RUL|Z.Score|algorithm|formula|architecture|Youden|threshold)',
    r'\bdifferen|compar|which\s+is\s+better|which\s+strateg|which\s+role|which\s+model',
    r'\bwhy\b.*\b(sensor|prediction|parameter|limited|Youden|not.enough)',
    r'\b(threshold|Z.Score|Youden|Cohen|baseline|strateg|role|algorithm|formula|architecture|pipeline|methodology)\b.*\b(how|what|explain|describ|defin|set|select|determin|calculat|config)',
]

# Maintenance knowledge base keywords
MAINT_KB_KEYWORDS = [
    # Chinese: repair/maintenance operations
    r'(更换|维修|拆卸|安装|替换|修复|修理).*(步骤|方法|流程|过程|指南|手册)',
    r'(步骤|方法|流程|过程|指南|手册).*(更换|维修|拆卸|安装|替换|修复|修理)',
    r'(怎么|如何|怎样).*(换|修|拆|装|更换|维修|拆卸|安装)',
    r'(需要什么|用什么|需要哪些).*(工具|备件|零件|材料|设备)',
    r'(工具|备件|零件|材料).*(需要|清单|列表)',
    r'(安全|紧急|停机|断电|防护|危险).*(操作|流程|步骤|措施|规范|规程)',
    r'(操作|流程|步骤|措施|规范|规程).*(安全|紧急|停机|断电|防护)',
    r'(轴承|转子|密封|润滑|散热|主轴|电机|冷却|传感器|变频).*(怎么|如何|维护|保养|检查|更换|维修)',
    r'(怎么|如何|维护|保养|检查|更换|维修).*(轴承|转子|密封|润滑|散热|主轴|电机|冷却|传感器|变频)',
    r'(日常|每日|每周|每月|定期).*(点检|巡检|检查|维护|保养)',
    r'(点检|巡检|检查|维护|保养).*(日常|每日|每周|每月|定期|标准|项目|内容)',
    r'(排查|诊断|判断|分析|定位).*(故障|异常|问题|原因)',
    r'(电压漂移|热积聚|功率异常|复合退化).*(怎么|如何|排查|处理|解决)',
    # English: maintenance/repair operations
    r'(?i)\b(replac|repair|install|remov|fix|chang).*\b(bearing|rotor|seal|lubric|cool(?:ing)?|spindl|motor|sensor)',
    r'\b(bearing|rotor|seal|lubric|cool|spindl|motor)\b.*\b(replac|repair|install|maintain|inspect|fix)',
    r'\bhow\b.*\b(replac|repair|install|remov|fix|maintain|inspect)\b.*\b(bearing|rotor|seal|motor|spindl|part|component)',
    r'\b(safety|emergency|shutdown|lockout|PPE|protection)\b.*\b(procedur|step|guide|protocol|rule|standard)',
    r'\bwhat\s+(tools|parts|equipment|materials)\b.*\b(need|required|necessary)',
    r'\b(daily|weekly|monthly|routine|regular)\b.*\b(inspection|maintenance|check|checklist)',
    r'\b(diagnos|troubleshoot|identify|find)\b.*\b(fault|failure|problem|issue|abnormal)',
    r'\b(overheat|hot\s+spindle|thermal\s+drift)',
    r'\b(voltage\s+drift|thermal\s+buildup|power\s+anomaly|combined\s+degradation)',
]

# Fault case keywords
FAULT_CASE_KEYWORDS = [
    # Chinese: historical fault/case lookups
    r'(历史|过去|以前|曾经|之前).*(故障|异常|案例|记录)',
    r'(故障|异常).*(历史|案例|记录|发生过|出现过)',
    r'(有没有|是否有|查找|搜索).*(类似|相似|相同|相关).*(故障|案例)',
    r'(类似|相似|相同).*(故障|案例|情况|问题)',
    r'Type\s*[0-9].*(怎么|如何|处理|修复|解决|排查)',
    r'(怎么|如何|处理|修复|解决|排查).*Type\s*[0-9]',
    r'(微弱|热异常|高压|High.Voltage|Thermal|Subtle).*(故障|怎么|如何|处理)',
    r'(故障.*原因|故障.*分析|故障.*复盘|故障.*总结)',
    # English: fault case queries
    r'\b(history|past|previous|historical)\b.*\b(fault|failure|case|incident|record)',
    r'\b(fault|failure)\b.*\b(history|case|record|incident|occurred|happened)',
    r'\b(find|search|lookup|any|are there)\b.*\b(similar|related|comparable)\b.*\b(fault|failure|case)',
    r'(?i)type\s*[0-9]\b.*\b(how|handl|fix|resolv|troubleshoot|deal)',
    r'\b(how|handl|fix|resolv|troubleshoot)\b.*(?i)type\s*[0-9]',
    r'\b(High.Voltage|Thermal|Subtle)\b.*\b(fault|failure|case|how|handl|fix)',
    r'\b(root.cause|post.mortem|failure.analysis)\b',
]


# ═══════════════════════════════════════════════════════════════════════════
# Classification Logic
# ═══════════════════════════════════════════════════════════════════════════

def _count_matches(text: str, patterns: List[str]) -> int:
    """Count how many patterns match the text."""
    count = 0
    for pat in patterns:
        try:
            if re.search(pat, text, re.IGNORECASE):
                count += 1
        except re.error:
            continue
    return count


def classify_question(text: str) -> Dict:
    """
    Classify a user question into one of four types.

    Returns:
        {
            "type": "system_doc" | "maintenance_kb" | "fault_case" | "data_query",
            "confidence": float (0.0 - 1.0),
            "matched_patterns": [...],
            "should_rag": bool,
            "rag_collections": [...],
        }
    """
    if not text or not text.strip():
        return {
            "type": "data_query", "confidence": 1.0,
            "matched_patterns": [], "should_rag": False, "rag_collections": [],
        }

    # Count matches for each category
    data_score = _count_matches(text, DATA_QUERY_KEYWORDS)
    sys_score = _count_matches(text, SYSTEM_DOC_KEYWORDS)
    maint_score = _count_matches(text, MAINT_KB_KEYWORDS)
    fault_score = _count_matches(text, FAULT_CASE_KEYWORDS)

    # Device ID is a very strong data query signal
    has_device_id = bool(re.search(r'CNC[_\s]?\d{3}', text, re.IGNORECASE))
    if has_device_id:
        data_score += 3  # strong boost

    # If no matches at all, try broader heuristics
    total = data_score + sys_score + maint_score + fault_score

    if total == 0:
        # No patterns matched — use broader heuristics
        # If it contains question words (how/what/why/怎么/如何/什么是) without CNC IDs,
        # lean toward system_doc
        question_markers = [r'\bhow\b', r'\bwhat\b', r'\bwhy\b', r'\bexplain\b', r'\bdefine\b',
                           r'怎么', r'如何', r'怎样', r'什么是', r'是什么', r'为什么']
        has_question = any(re.search(m, text, re.IGNORECASE) for m in question_markers)
        if has_question and not has_device_id:
            return {
                "type": "system_doc", "confidence": 0.5,
                "matched_patterns": ["heuristic: question without device ID"],
                "should_rag": True, "rag_collections": ["sys_docs"],
            }
        return {
            "type": "data_query", "confidence": 0.5,
            "matched_patterns": ["heuristic: no patterns matched"],
            "should_rag": False, "rag_collections": [],
        }

    # Determine the best category
    scores = {
        "data_query": data_score,
        "system_doc": sys_score,
        "maintenance_kb": maint_score,
        "fault_case": fault_score,
    }

    best_type = max(scores, key=scores.get)
    best_count = scores[best_type]

    # Confidence
    confidence = best_count / total if total > 0 else 0.5

    # Should RAG?
    should_rag = best_type in ("system_doc", "maintenance_kb", "fault_case")

    # RAG collections
    rag_collections = []
    if best_type == "system_doc":
        rag_collections = ["sys_docs"]
    elif best_type == "maintenance_kb":
        rag_collections = ["maint_kb"]
    elif best_type == "fault_case":
        rag_collections = ["fault_cases"]
    elif best_type == "data_query" and (sys_score > 0 or maint_score > 0):
        # Mixed signals: user might be asking a doc question with data context
        should_rag = True
        if sys_score > 0:
            rag_collections.append("sys_docs")
        if maint_score > 0:
            rag_collections.append("maint_kb")

    # If any RAG category has matches, also search those
    if should_rag and sys_score > 0 and "sys_docs" not in rag_collections:
        rag_collections.append("sys_docs")
    if should_rag and maint_score > 0 and "maint_kb" not in rag_collections:
        rag_collections.append("maint_kb")
    if should_rag and fault_score > 0 and "fault_cases" not in rag_collections:
        rag_collections.append("fault_cases")

    return {
        "type": best_type,
        "confidence": round(min(confidence, 1.0), 3),
        "matched_patterns": [],  # simplified — don't enumerate
        "should_rag": should_rag,
        "rag_collections": rag_collections,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Quick API
# ═══════════════════════════════════════════════════════════════════════════

def is_rag_question(text: str) -> bool:
    """Quick check: does this question need RAG retrieval?"""
    result = classify_question(text)
    return result["should_rag"]


def get_rag_collections(text: str) -> List[str]:
    """Get which RAG collections to search for this question."""
    result = classify_question(text)
    return result.get("rag_collections", [])
