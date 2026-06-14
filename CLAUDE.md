# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

> 苗圃杯·半决赛作品 v2.3 | 最后更新：2026-06-14
>
> 参考文档（按需 Read 加载）：
> `CLAUDE_REF_架构.md`（项目概述·目录·前端·CSS·JS） |
> `CLAUDE_REF_后端.md`（Gateway·Skills·数据文件） |
> `CLAUDE_REF_算法.md`（算法·角色·降级·RAG·业务）
>
> **注意**：参考文档版本为 v2.1（2026-06-04），部分最新功能（如评委讲解助手、3D球体演示）仅在本文档中描述。

---

## 项目定位

工业智能运维解决方案 — 100台 CNC 数控机床（CNC_001~100），4传感器参数（V/A/T/Rotor），9种故障类型。
3个系统角色（运维/管理/开发），3种维护策略（成本效率/生产效率/质量优先）。

技术栈：Python 3.10+ + FastAPI后端（8765端口）+ Vanilla JS/ECharts前端 + DeepSeek API。

---

## 核心约定（必须遵守）

1. **Windows 环境** — PowerShell 优先，文件路径用正斜杠或反斜杠，UTF-8 编码（所有CSV/JSON/Python读取需显式 `encoding='utf-8'`）
2. **逐设备基线是强制性的** — 设备间方差占 61-73%，不可用全局阈值（≥3样本才能建基线，三层回退策略）
3. **纯ML预测不可行** — 4参数 Youden's J≤0.075，AUC上限≈0.537，必须用多信号融合补偿（统计+ML+成本+趋势）
4. **角色分版用 CSS `:not()` 过滤** — `html[data-role]` + CSS类名（role-operator/role-manager/role-developer），不是简单高亮，不同角色看到不同页面子集
5. **策略切换需重新生成CSV** — `POST /api/maintenance/strategy` 后端重新计算工单，不是纯前端切换
6. **降级保障是工业级要求** — 四级降级（FULL→STAT_ONLY→RULE_ONLY→EMERGENCY），任何条件下都能产出可执行维护方案
7. **SHAP可解释性是核心竞争力** — 每个告警必须可追溯到具体参数和工业根因（RiskDecomposer + StatLayerSHAP → LocalExplainer）
8. **故障注入纯内存计算** — `POST /api/fault-injection` 不修改任何数据文件，演示完成后前端自动回滚
9. **算法对比用实际训练数据** — `benchmark_algorithms.py` 在真实2999行数据上训练，不使用虚拟/合成数据
10. **数据天花板可视化** — `kde_params.json` 提供4参数×200点KDE分布，前端交互式演示 Youden's J 从 0.075→0.90
11. **评委讲解助手** — `shared/assistant.js` + `shared/assistant.css` 在5个核心页面注入3D球体入口。话术库优先命中（40+板块预生成话术），未命中则调用 `/api/assistant/explain` SSE流式AI生成。球体可拖拽移动，位置记忆到 localStorage。弹窗白磨砂玻璃风格。

---

## 关键路径

| 用途 | 路径 |
|------|------|
| Web入口 | `web-dashboard/app.py` → http://localhost:8765 |
| 流水线调度 | `agent-mcp架构/agent_orchestrator.py`（DAG + ThreadPool） |
| 原始数据 | `原始数据集/`（4个脱敏CSV：LOG/SUMMARY/ASSEMBLY/TESTS） |
| 仪表盘数据 | `web-dashboard/data/`（60+CSV/JSON，从Pipeline同步） |
| 环境变量 | `.env`（DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL；SMTP_HOST/PORT/USER/PASSWORD/FROM/NOTIFY_ESCALATION_EMAIL） |
| 前端页面 | `web-dashboard/*.html`（home/index/chat/technical-overview/reports/role-gate/knowledge-base/work-order-tracking/workflows/inventory/technicians/device-grid/sphere-demo 共13个页面） |
| 共享模块 | `web-dashboard/shared/`（navbar/role-check/theme-init/role-switcher/demo-mode/assistant/design-tokens/sidebar/device-grid-component 共10个） |
| Gateway后端 | `web-dashboard/gateway/`（tools/prompts/deepseek_client/routes/kb_routes 等） |
| Skills | `skills/`（5个技能包：data_prep→stat_inference/ml_inference→diagnosis→decision） |

---

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt              # 完整生产环境
pip install -r requirements-dev.txt          # + pytest/jupyter（开发用）
pip install -r requirements-minimal.txt      # 无torch/xgboost/fastapi

# 启动Web平台
cd web-dashboard; python app.py

# 运行完整流水线
cd agent-mcp架构; python agent_orchestrator.py --data-dir ../原始数据集 --model v1

# 仅统计（快速，~9s）
cd agent-mcp架构; python agent_orchestrator.py --data-dir ../原始数据集 --skip-ml --skip-diagnosis

# 含策略+仪表盘同步
cd agent-mcp架构; python agent_orchestrator.py --data-dir ../原始数据集 --skip-ml --skip-diagnosis --shap --strategy production_efficiency --dashboard-data ../web-dashboard/data

# 算法对比实验（~2分钟）
cd web-dashboard; python scripts/benchmark_algorithms.py

# KDE分布参数计算（~2秒）
cd web-dashboard; python scripts/compute_kde_params.py

# 运行测试（需先运行流水线到 outputs_test/）
pytest tests/ -v
pytest tests/test_data_integrity.py -v       # 单文件
pytest tests/ -k "shap" -v                   # 按关键词筛选

# 独立报告流测试（无需pytest）
python test_report_pipeline.py
```

---

## 按需索引

需要了解架构/前端/后端/算法等详细信息时，Read 对应的参考文件：

| 需要了解的内容 | 文件 | 涵盖 |
|---------------|------|------|
| 项目概述、目录结构 | `CLAUDE_REF_架构.md` §一~二 | 定位、数据、技术栈、完整目录树 |
| Web前端页面与组件 | `CLAUDE_REF_架构.md` §三 | 角色门/首页双视图/仪表盘8Tab/Copilot/技术架构/报告中心 |
| CSS设计系统 | `CLAUDE_REF_架构.md` §四 | 设计令牌/深色主题/页面级变量/视觉模式 |
| JavaScript模块 | `CLAUDE_REF_架构.md` §五 | role-check/role-switcher/theme-init/navbar |
| Gateway后端架构 | `CLAUDE_REF_后端.md` §六 | app.py/config/routes/DeepSeek客户端/25个Tools/故障注入/提示词/报告系统 |
| Skills技能架构 | `CLAUDE_REF_后端.md` §七 | DAG流水线/5个技能包详解/Phase A/B/C决策体系 |
| 数据文件详解 | `CLAUDE_REF_后端.md` §八 | 原始数据/仪表盘数据/知识库JSON |
| 核心算法详解 | `CLAUDE_REF_算法.md` §九 | Z-Score基线/T²/成本风险/健康评分/决策融合/Youden's J/方差分解/算法对比/KDE |
| 角色权限体系 | `CLAUDE_REF_算法.md` §十 | 三角色定义/CSS过滤机制/类名语义/执行流程 |
| 降级架构 | `CLAUDE_REF_算法.md` §十一 | 四级降级/状态指示器 |
| RAG智能客服 | `CLAUDE_REF_算法.md` §十二 | 三层知识库/技术选型/文档分块/问题分类 |
| 业务流程自动化 | `CLAUDE_REF_算法.md` §十三 | 工单6状态机/定时任务/库存管理/员工管理 |
| 评委讲解助手 | `shared/assistant.js` | 话术库结构/上下文提取/匹配引擎/SSE AI回退/快捷操作 |
