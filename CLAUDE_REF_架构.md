# CLAUDE_REF_架构 — 项目概述 · 目录结构 · Web前端 · CSS · JS

> 从 CLAUDE.md 拆分 | 苗圃杯·半决赛 v2.3 | 2026-06-16

---

## 一、项目概述

### 1.1 项目定位

工业智能运维解决方案 —— 为工厂运维工程师（执行层）和生产管理负责人（决策层）提供从异常发现到工单执行的全链路系统。

### 1.2 核心数据

| 指标 | 数值 | 说明 |
|------|------|------|
| 监控设备 | 100台 CNC 数控机床 | CNC_001 ~ CNC_100 |
| 传感器参数 | 4个 | Voltage（电压）、Amperage（电流）、Temperature（温度）、Rotor Speed（转速） |
| 故障类型 | 9种 | Type 1-9，分为4组（Subtle/Thermal/High-Voltage/Normal） |
| 当前 Youden's J | ≤ 0.075 | 4参数传感器信息上限（可用阈值 > 0.30） |
| Z-Score 告警精确率 | 83.9% | z>2.0，每5次告警约4次正确 |
| 设备健康分布 | 危险10台 / 劣化88台 / 健康2台 | 8维度加权评分 |
| 系统角色 | 3个 | 运维工程师 / 生产管理负责人 / 平台开发人员 |
| 维护策略 | 3种 | 成本效率 / 生产效率 / 质量优先 |

### 1.3 技术栈

| 层级 | 技术 |
|------|------|
| 数据分析 | Python (pandas, numpy, scipy), KDE, Cohen's d, KS-test, Youden's J, Bootstrap BCa |
| 统计基线 | 逐设备Z-Score, Hotelling T², K-Means聚类, Spearman ρ, Wilson CI, Baron-Kenny中介 |
| 机器学习 | XGBoost, PyTorch Multi-Task NN, TreeSHAP, 滑动窗口特征工程 |
| 后端 | FastAPI, FastMCP, DeepSeek API, SSE Streaming, subprocess DAG调度 |
| 前端 | Vanilla JS, ECharts 5.5, PapaParse 5.4, 深色工业主题, 懒加载渲染 |
| RAG 智能客服 | BGE-small-zh-v1.5 嵌入模型, Chroma 向量数据库, LangChain 风格分块, 问题分类器 |
| 业务流程 | SQLite 状态机, APScheduler 定时任务, SMTP 邮件通知, CSV 库存模拟 |
| 报告 | Jinja2, matplotlib, WeasyPrint/Playwright PDF |

---

## 二、目录结构

```
半决赛v1/
├── .env                               # DeepSeek API Key（不提交Git）
├── .gitignore
├── CLAUDE.md                          # 核心指令+索引（本文件的主入口）
├── CLAUDE_REF_架构.md                 # 本文件
├── CLAUDE_REF_后端.md                 # Gateway + Skills + 数据文件
├── CLAUDE_REF_算法.md                 # 算法 + 角色 + 降级 + RAG + 业务
├── requirements.txt                   # Python依赖
├── 项目介绍.md                         # 面向评委的项目全景文档
│
├── 原始数据集/                         # 4个脱敏CSV
│   ├── MACHINE_LOG_DATA._2025.csv     # 传感器日志（2999条×100台）
│   ├── MACHINE_SUMMARY_DATA._2025.csv # 设备元数据
│   ├── PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv  # 产品组装
│   └── PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv # 产品测试
│
├── 数据探索分析/                       # Phase 1: EDA
│   ├── analysis_fault_types.py        # 故障类型分布分析
│   ├── machine_failure_analysis.py    # 参数级故障分析
│   ├── advanced_failure_analysis.py   # 高级故障分析（Youden's J等）
│   ├── task1_per_device_analysis.py   # 逐设备统计画像
│   ├── cross_table_analysis.py        # 四表联合挖掘
│   ├── chain_analysis.py              # 因果链+Bootstrap中介
│   ├── fix_figure14.py                # 热负荷图修复
│   └── outputs_cross_table/           # 跨表分析输出
│
├── 基线分析和确定/                     # Phase 2: 统计基线
│   ├── baseline_analysis.py           # 4基线模型
│   ├── figures.py                     # 标准图表
│   └── figures_nature.py              # Nature风格图表
│
├── 预测性维护模型/                     # Phase 3: ML v1
│   ├── model_training.py              # XGBoost双时间窗口
│   ├── figures/                       # 模型评估图表
│   └── model_outputs/                 # 训练好的模型
│
├── 预测性维护模型_v2/                  # Phase 3: ML v2
│   ├── model_training_v2.py           # Multi-Task NN
│   ├── figures/                       # 对比图表
│   └── model_outputs/                 # 3种变体输出
│
├── 预测性维护模型_v3/                  # Phase 4: 可预测性分析
│   ├── predictability_analysis.py     # 5维度天花板分析
│   └── outputs/                       # 分析输出
│
├── agent-mcp架构/                     # Phase 5: MCP + 流水线
│   ├── agent_orchestrator.py          # DAG调度器（743行）
│   ├── mcp_server.py                  # FastMCP服务器（576行）
│   └── outputs/                       # 生产输出
│
├── skills/                            # 5个技能包
│   ├── predictive-maintenance-data-prep/       # 技能1：数据准备
│   ├── predictive-maintenance-stat-inference/   # 技能2：统计推理
│   ├── predictive-maintenance-ml-inference/     # 技能3：ML推理
│   ├── predictive-maintenance-diagnosis/        # 技能4：诊断分析
│   └── predictive-maintenance-decision/         # 技能5：决策工单
│
├── web-dashboard/                     # Phase 6: Web平台
│   ├── app.py                         # FastAPI入口（420+行）
│   ├── home.html                      # 首页（运维+管理双视图）
│   ├── index.html                     # 仪表盘（8个Tab）
│   ├── chat.html                      # AI Copilot对话（含RAG检索增强）
│   ├── technical-overview.html        # 技术架构文档
│   ├── reports.html                   # 报告管理中心
│   ├── role-gate.html                 # 角色选择门
│   ├── knowledge-base.html            # 知识库管理页面
│   ├── work-order-tracking.html       # 工单跟踪看板
│   ├── workflows.html                 # 工作流管理
│   ├── inventory.html                 # 库存管理
│   ├── technicians.html               # 员工管理
│   ├── device-grid.html               # 独立设备健康矩阵（10×10）
│   ├── sphere-demo.html               # 鹰眼3D球体数字孪生（NEW）
│   ├── gateway/                       # 后端模块（20文件）
│   │   ├── tools.py                   # 25个Gateway Tools（含3个RAG工具）
│   │   ├── prompts.py                 # 系统提示词（含RAG FAQ映射）
│   │   ├── deepseek_client.py         # DeepSeek SSE流式客户端（支持RAG上下文注入）
│   │   ├── routes.py                  # 核心路由（chat + 策略切换 + assistant/explain RAG增强）
│   │   ├── kb_routes.py               # 知识库管理API（9端点，含chart_docs索引）
│   │   ├── rag_engine.py              # RAG核心引擎（BGE+Chroma，4集合含chart_docs）
│   │   ├── question_classifier.py     # 问题分类器（中英文）
│   │   ├── fault_injection.py         # 故障注入演示API（6步闭环模拟）（NEW）
│   │   ├── workflow_engine.py         # 工作流状态机（SQLite）
│   │   ├── notification_service.py    # 邮件通知服务（SMTP）
│   │   ├── work_order_builder.py      # 工单上下文动态构建
│   │   ├── tracking_routes.py         # 工单跟踪/工作流/库存/技师API（550行）
│   │   ├── scheduled_jobs.py          # APScheduler定时任务
│   │   ├── post_repair_checker.py     # 修后Z-Score自动验收
│   │   ├── inventory_connector.py     # CSV库存管理
│   │   ├── report_orchestrator.py     # 报告数据聚合协调器
│   │   ├── report_generator.py        # Jinja2报告生成 + matplotlib图表
│   │   ├── work_order_report_generator.py  # LLM维护执行单生成
│   │   ├── config.py                  # 配置管理
│   │   └── __init__.py
│   ├── scripts/                       # 数据生成脚本（2个）（NEW）
│   │   ├── benchmark_algorithms.py    # 7种算法对比训练脚本
│   │   └── compute_kde_params.py      # KDE分布参数计算脚本
│   ├── shared/                        # 前端共享模块（7 JS + 3 CSS = 10个）
│   ├── data/                          # 仪表盘数据（60+CSV）+ 知识库存储
│   │   ├── algorithm_comparison.csv   # 7种算法对比实验数据
│   │   ├── kde_params.json            # KDE分布参数（4参数×200点）
│   │   └── knowledge_base/            # 知识库文档+Chroma向量DB
│   ├── 参考手册_提取文本.txt             # 完整参考手册文本（RAG chart_docs索引源）
│   ├── images/                        # ECharts导出图片
│   ├── report_templates/              # Jinja2报告模板
│   └── reports/                       # 生成的报告
│
├── 虚拟数据集/                         # 合成数据生成器
├── tests/                             # Pytest测试套件（6个测试文件）
└── 多个 outputs_*/ 目录                # 各类测试/验证输出
```

---

## 三、Web 前端平台详解

### 3.1 角色选择门（role-gate.html）

**路由**: `/role-gate`
**大小**: 17KB
**用途**: 用户首次访问时的角色选择入口

**设计特色**:
- 工业控制室美学：深色背景 + 微妙网格线 + 扫描线叠加效果
- 三张角色卡片水平排列，分别使用青/琥珀/紫三色系统
- 卡片顶部色条 + hover升起8px + 内发光动画
- 交错入场动画（50ms/150ms/250ms延迟）
- 860px以下三列变单列堆叠

**三角色卡片**:
| 角色 | 颜色 | 图标 | 标题 | 功能描述 |
|------|------|------|------|---------|
| 运维工程师 | 青 #00c9a0 | ⚙ | Operator · 执行层 | 设备健康监控、异常告警处理、工单执行跟踪、根因归因分析 |
| 生产管理负责人 | 琥珀 #f0a030 | 📊 | Manager · 决策层 | 业务指标总览、成本效益分析、策略对比选择、传感器投资ROI |
| 平台开发人员 | 紫 #a371f7 | 🔧 | Developer · 全量视图 | 完整数据探索、预测模型评估、系统架构文档、全部页面可见 |

**交互逻辑**:
1. `selectRole(role)` → `sessionStorage.setItem('user_role', role)`
2. 读取 URL 参数 `?redirect=` 回到用户原本想访问的页面
3. Manager 默认跳转 `/dashboard`，Operator/Developer 跳转 `/`

### 3.2 首页（home.html）— 双视图

**路由**: `/`
**大小**: 72KB
**用途**: 运维工程师的设备监控主页 / 生产管理负责人的业务总览主页

#### 3.2.1 运维工程师视图（role-operator）

**页面布局**（从上到下）:

**A. Header 区域**
- 标题：`◆ 设备健康状态总览`
- 右上角徽章：`执行视图`（青色系）
- 4个统计数字：健康/退化/高危设备数 + 活跃工单数

**B. 统计卡片行**（4列）
- 设备健康率（百分比 + 健康/退化/高危分布）
- 高危设备数（红色数值）
- 告警精确率：83.9%（Z-Score z>2.0）
- 今日待维护数（活跃工单数）

**C. 2×5 紧急维护设备网格**
- 从 `industrial_maintenance_plan.csv` 取 Top 10（按优先级排序）
- 每张卡片显示：设备ID、健康分进度条（颜色：绿>80/黄>60/琥珀>40/红<40）、维护动作（中文映射）、停机窗口（中文映射）、故障原因（取自 plan.reasoning，超过50字截断）
- 卡片点击 → 调用 `openPanel()` 弹出SHAP归因详情面板
- 数据右键 → 弹出基线溯源面板（健康分溯源）

**D. 10×10 设备健康网格**
- 100台 CNC 设备（CNC_001 ~ CNC_100）
- Keycap 3D 风格：立体按键效果（border-bottom阴影 + inset高光）
- 三种颜色：绿色（健康/Warning）、金色（退化）、红色（危险）
- 活跃工单脉冲动画（ALARM红色光晕 / WARNING橙色光晕）
- 优先级角标（#1, #2, ...）
- 点击格子 → 右侧滑出详情面板（SHAP归因 + 维护工单）
- 右键格子 → 弹出基线溯源面板

**E. 设备详情侧滑面板**（detail-panel）
- 420px宽，从右侧滑入，overlay遮罩
- 关键指标：健康评分、故障率、维护超期天数、成本风险($k)
- 关键异常信号：severity徽章（🔴🟡🟢）+ 特征标签 + 数值 + 解释
- SHAP归因分析：Top 5贡献特征 + 方向箭头 + 自然语言摘要
- 维护工单：优先级、动作类型、紧急度、建议窗口、预期节省、根因
- 建议排查清单：编号列表
- 按 Esc / 点击遮罩 / 点击× 关闭

**F. 工单卡片区**（wo-card-grid，2列）
- 数据来源：`industrial_maintenance_plan.csv`
- 策略标签：从 `sessionStorage.current_strategy` 读取当前策略
- 每张卡片显示：设备ID、优先级徽章（P1红/P2琥珀/P3蓝）、动作类型、技师（中文映射）、备件（JSON解析截取40字）、停机窗口（中文映射）、期限天数、预期节约($)
- 卡片左侧色条：P1红色 / P2琥珀色 / P3蓝色
- hover效果：右移2px + 边框高亮
- 点击 → 弹出SHAP详情面板
- 右键 → 弹出 Z-Score 溯源面板

**G. 零件采购清单**
- 数据来源：`spare_parts_plan.csv`
- 按 `part_name` 聚合去重
- 英→中映射：rotor_assembly→转子总成, bearing_kit→轴承套件, seal_kit→密封套件, lubrication_kit→润滑套件, o-ring_set→O型密封圈组, cooling_fan_assembly→散热风扇总成, thermal_paste→导热硅脂, temperature_sensor_pt100→PT100温度传感器, heat_sink_assembly→散热器总成
- 表格列：零件名称、关联设备数、预估总成本、关联设备（最多显示5个）

**H. AI 快捷提问条**
- 链接到 `/chat?prompt=...` 预设问题
- 问题：当前哪些设备风险最高？为什么？

**I. 故障注入演示**（Developer专属，NEW）
- Header右侧 `⚡ 故障注入演示` 按钮（`role-developer` CSS类控制可见性）
- 弹出配置面板：选择目标设备（CNC_001~100）、故障类型（1-9）、严重度（轻微/中等/严重）
- 点击"注入并演示" → 6步自动推进动画（每步1.5s间隔）：
  1. **故障信号注入** — 传感器数据按故障签名偏移
  2. **Z-Score 异常检测** — 显示电压/电流/温度三参数Z值 + 综合Z + 告警等级
  3. **SHAP 根因分析** — 自然语言摘要 + Top 3贡献特征
  4. **自动生成维护工单** — 优先级/动作/停机窗口/SLA/备件/预期节省
  5. **技师分配 & 邮件通知** — 技师类型+人数+工单号（演示模式未实际发送）
  6. **修复后验收通过** — Z-Score回归正常 + 健康分恢复 + 验收标准全部通过
- 后端API：`POST /api/fault-injection`（`gateway/fault_injection.py`，~320行）
- 纯内存计算，不修改任何数据文件
- 演示期间：10×10网格中目标设备格红色高亮 + 脉冲动画 + 优先级角标
- 关闭步骤面板后自动回滚：移除高亮、角标，恢复原始健康分显示

#### 3.2.2 生产管理负责人视图（role-manager）

**页面布局**:

**A. Header 区域**
- 标题：`◆ 运维业务总览`（琥珀色菱形）
- 右上角徽章：`决策视图`（琥珀色系）
- 当前角色 + 监控设备数

**B. KPI 卡片行**（4列）
- 高危设备数（红色顶部色条）
- 活跃工单数（蓝色顶部色条）+ 当前策略标签
- 预期月度节省（青色顶部色条）
- 告警精确率：83.9%（紫色顶部色条）

**C. 设备健康分布 + 日成本风险 Top 5**（2列）
- 健康分布：水平堆叠条（红/琥珀/绿）+ 图例
- Top 5 风险表格：设备ID、日成本风险($k/天)、故障率(%)、健康分

**D. 当前维护策略**
- 三个策略标签（成本效率/生产效率/质量优先），当前策略高亮
- 策略标签在仪表盘切换后通过 `sessionStorage.current_strategy` 同步

**E. 快捷入口**
- 📊 业务总览仪表盘 → `/dashboard#sec0`
- ⚙️ 维护决策中心 → `/dashboard#sec6`
- 📈 传感器升级ROI → `/dashboard#sec7`
- 🤖 AI Copilot → `/chat`
- 📋 生成周报 → `/reports`

**F. AI 快捷提问条**
- 问题：当前维护投入产出比？传感器升级ROI分析？

#### 3.2.3 平台开发人员视图（developer）

同时看到运维+管理全部内容（双视图并存）。

#### 3.2.4 基线溯源面板（trace-panel）

**触发方式**: 右键点击任意带 `data-trace` 属性的元素
**位置**: 页面中央弹出，560px宽，overlay遮罩
**关闭方式**: 点击× / 点击遮罩 / 按Esc

**三种溯源类型**:

| 类型 | data-trace值 | 触发元素 | 内容 |
|------|-------------|---------|------|
| 健康分溯源 | `health` | 10×10网格、2×5卡片、统计卡片 | 8维度加权明细（含贡献度进度条）、基线说明（来源/质量/样本数）、自然语言解读 |
| Z-Score溯源 | `zscore` | 工单卡片 | 电压/电流/温度三参数Z值vs基线μ±σ、综合判定、阈值扫参表（z>1.0~2.5，含P/R/F1/FPR）、基线来源说明 |
| 成本风险溯源 | `risk` | 成本风险值 | 公式分解（故障概率×单件成本×日产量）、风险档位建议 |

### 3.3 仪表盘（index.html）— 8个Tab

**路由**: `/dashboard`
**大小**: 324KB

#### Tab 角色可见性矩阵

| Tab | ID | 内容 | 运维 | 管理 | 开发 |
|-----|------|------|:--:|:--:|:--:|
| 业务总览 | sec0 | KPI + 业务价值卡片 + 角色导航 | ❌ | ✅ | ✅ |
| 运行日志 | sec1 | 实时日志表 + 传感器时序 + 故障分布 | ✅ | ❌ | ✅ |
| 数据探索 | sec2 | EDA图库 + 跨表分析 + 因果链 | ❌ | ❌ | ✅ |
| 基线划定分析 | sec3 | 方差分解 + Z-Score + 成本风险气泡 | ❌ | ❌ | ✅ |
| 预测性维护模型 | sec4 | XGBoost/MTNN + 鲁棒性 + SHAP | ❌ | ❌ | ✅ |
| 方案有效性验证 | sec5 | 三层时序回测 | ✅ | ✅ | ✅ |
| 智能维护决策中心 | sec6 | 策略选择器 + 工单 + SHAP瀑布 | ❌ | ✅ | ✅ |
| 设备健康与感知升级 | sec7 | 健康分 + RUL + 传感器ROI | ❌ | ✅ | ✅ |

#### sec0: 业务总览（Manager专属）
- 5个统计卡片（高危/工单/月度节省/精确率/ROI）
- 4个业务价值卡片（故障预警/维护推荐/成本优化/风险规避）
- 角色快速导航链接（运维侧3个 + 管理侧3个 + Copilot + 报告）

#### sec1: 运行日志（Operator专属）
- 实时日志数据表（分页、筛选、排序）
- 参数时序图（温度/电压/电流/转速）
- 故障类型分布图

#### sec2: 数据探索（Developer专属）
- 17张EDA图库（可折叠展开）
- 四表联合关联分析（Spearman ρ矩阵 + Pearson r + Kruskal-Wallis H）
- 因果链分析（条件概率链 + Bootstrap中介 + 交叉特征）
- 方法论路线图

#### sec3: 基线划定分析（Developer专属）
- 方差分解图（设备间 vs 设备内）
- Z-Score时序图 + 阈值线
- 告警分布饼图
- 四基线架构图
- 成本风险气泡图

#### sec4: 预测性维护模型（Developer专属）
- XGBoost v1 ROC/PR曲线 + 特征重要性
- MTNN v2 三变体对比 + 鲁棒性热力图
- Youden's J 天花板分析图
- SHAP 全局特征重要性 + 根因类别占比
- **🔬 算法对比实验墙**（NEW）：7种主流算法在4参数数据上的对比
  - 分组柱状图（AUC + 训练时间双Y轴），标注随机线(0.5)和可用线(0.70)
  - 7种算法：逻辑回归(LR)、支持向量机(SVM)、随机森林(RF)、XGBoost、LightGBM、CNN(1D-Conv)、Multi-Task NN
  - 数据类型标签：classical（蓝）/ ensemble（青）/ deep（紫）
  - 所有指标来自实际训练（`scripts/benchmark_algorithms.py`），含3次重复的mean±std
  - 5种sklearn模型在2999行数据上实际训练，CNN/MTNN复用已有`variant_comp.csv`
  - 预测目标：`next_is_fault`（预测性任务，非检测任务），31维特征工程
  - 结论卡片：所有算法AUC在0.517-0.589之间，均未突破可用阈值0.70
  - 详细对比表：算法/类型/AUC/F2/精确率/召回率/训练时间/推理时间

#### sec5: 方案有效性验证（全员可见）
- 三层时序回测：点级混淆矩阵 + 事件级提前量 + 步进Expanding Window
- 按故障组分层漏报率
- 灵敏度-提前量Tradeoff分析

#### sec6: 智能维护决策中心（Manager+Developer）

**策略选择器**（role-manager包裹，Operator不可见）:
- 三种维护策略卡片（成本效率/生产效率/质量优先）
- 每张卡片显示：阈值(ALARM/WARNING/WATCH)、融合权重、最大工单数、SLA目标
- 点击切换 → API调用 → CSV重新生成 → 页面重新渲染
- 策略持久化到 `sessionStorage.current_strategy`

**工单队列**（role-manager包裹）:
- P1 紧急工单卡片（红色左边框，2列网格）
- P2 计划工单卡片（琥珀色左边框）
- 每张工单卡片：优先级、设备ID、动作类型、成本风险、紧急度、期限、预期节约

**SHAP Waterfall 单设备告警归因**（全员可见）:
- 设备选择器下拉框（按风险排序）
- 风险贡献分解瀑布图（ECharts）
- 根因类别占比柱状图
- 关键异常信号详情列表

#### sec7: 设备健康与感知升级（Manager专属）
- 三级结构：实时监控 → 退化诊断 → 长期规划
- 健康分-RUL象限散点图
- 8维度加权健康评分模型（可展开详情）
- 传感器升级三阶段ROI（保守/预期/乐观三场景）
- Youden's J累积曲线 + CAPEX/OPEX堆叠图
- 部署清单表格

#### 全局功能
- **主题切换**: 暗色/浅色，localStorage持久化
- **Hash导航**: `/dashboard#sec6` 自动切换到对应Tab
- **策略恢复**: 页面加载时从 sessionStorage 恢复策略状态
- **懒加载**: 仅在首次点击Tab时渲染内容（`_rendered` 标记）
- **Pipeline状态栏**: 显示各数据阶段就绪状态

### 3.4 AI Copilot（chat.html）

**路由**: `/chat`
**大小**: 58KB

**布局**:
- 左侧可折叠侧边栏（260px宽）+ 右侧对话区
- 顶部 Header：Logo + 状态指示器 + 返回仪表盘链接
- 底部输入区：textarea + 发送按钮 + 提示文字

**侧边栏推荐问题**（11条，按角色过滤）:

| # | 问题 | 角色 |
|---|------|:--:|
| 1 | 当前哪些设备风险最高？ | 运维 |
| 2 | 为什么4个传感器参数不够用？ | 开发 |
| 3 | 帮我分析 CNC_042 的根因 | 运维 |
| 4 | 展示 CNC_036 温度变化趋势 | 运维 |
| 5 | 对比 CNC_001 和 CNC_036 | 运维 |
| 6 | 加装振动传感器投资回报率？ | 管理 |
| 7 | 帮我生成高风险设备报告 | 管理 |
| 8 | 系统预测能力如何验证？ | 全员 |
| 9 | 三种维护策略怎么选？ | 管理 |
| 10 | 健康分最低的设备有哪些？ | 运维 |
| 11 | RUL预测：设备还能用多久？ | 全员 |

**角色过滤**: JS动态过滤 + 重新编号 + 分区标签（🔧运维工程师常用 / 📊生产管理者常用）

**欢迎消息**: 根据角色动态切换图标（⚙/📊）和文案

**对话功能**:
- SSE 流式响应（DeepSeek API）
- Markdown 渲染（marked.js）
- ECharts 图表即时生成（tool_call → chart_data → 内联渲染）
- 多轮工具调用（最多5轮）
- 12个 Gateway Tools 覆盖完整运维流程

### 3.5 技术架构（technical-overview.html）

**路由**: `/technical-overview`
**大小**: 120KB

**11个板块**（全员可见，无角色过滤）:

| # | 板块 | 内容 |
|---|------|------|
| 00 | 系统全景鸟瞰 | 四层架构：角色门→数据层→智能层→应用层（ECharts架构图） |
| 01 | 三角色权限与首页双视图 | 三角色卡片（青/琥珀/紫）+ 权限控制机制 + CSS :not()过滤核心逻辑代码块 |
| 02 | 核心算法体系 | 6个算法卡片：Z-Score/T²/成本风险/故障签名/健康评分/决策融合 |
| 02.5 | **数据天花板·交互式演示**（NEW） | 4参数KDE分布重叠图 + Youden's J滑块 + 传感器升级三阶段 |
| 03 | DAG流水线与降级架构 | 5技能DAG + ThreadPool并行 + 四级自动降级状态机图 |
| 04 | 决策引擎·三层架构 | Phase A基础→Phase B工业扩展→Phase C传感器路线图 |
| 05 | AI Copilot·MCP+Gateway | 10 Gateway Tools + MCP协议 + SSE流式架构 |
| 06 | SHAP可解释性管线 | 双路径归因：RiskDecomposer + StatLayerSHAP → LocalExplainer |
| 07 | Dashboard数据同步架构 | 22文件同步 + 8标签页 + 角色可见性矩阵 |
| 08 | 数据流转与技术演进 | 5阶段技术演进时间线 + 每阶段核心发现 |
| 09 | 技术栈全景 | 分层技术栈卡片：分析层/统计层/ML层/后端/前端/报告 |

**板块 02.5 — 数据天花板·交互式演示**（NEW，~430行代码）:
- 数据来源：`data/kde_params.json`（`scripts/compute_kde_params.py` 从 `log.csv` + `dim1.csv` 计算）
- 2×2 KDE分布重叠图网格（电压/电流/温度/转速），每张图含正常(青)和故障(红)两条PDF曲线
- 重叠区域半透明红色填充 + 百分比标注（如"重叠 96.3%"）
- 底部滑块：拖动切换传感器升级阶段（Phase 0→1→2→3），Youden's J值动态变化（0.075→0.525→0.805→0.90）
- 阶段卡片：显示新增传感器、投资额、5年ROI、回本周期
- 结论卡片：4参数信息瓶颈 → 纯ML不可行（AUC≤0.537） → 必须传感器升级 + 多信号融合
- JS函数：`renderKdeChart()`, `animateYoudenJ()`, `updatePhaseDisplay()`, `initDataCeiling()`

**Hero区域**: 6个指标徽章（Youden's J、决策权重、告警精确率、角色体系、标签页数、MCP工具）

### 3.6 报告中心（reports.html）

**路由**: `/reports`
**大小**: 31KB

**功能**:
- 报告列表（搜索/筛选/排序）
- 报告类型自动识别（从文件名前缀）
- PDF生成（Playwright Chromium headless）
- 角色过滤：运维看设备/热漂移/备件/工单报告，管理看周报/风险/健康/投资报告

**8种报告类型**:

| 类型 | 用途 | 可见角色 |
|------|------|:--:|
| weekly | 周度系统报告 | 管理 |
| device | 单设备深度报告 | 运维 |
| risk | 高风险设备报告 | 管理 |
| thermal | 热漂移分析报告 | 运维 |
| health_critical | 低健康分集体报告 | 管理 |
| parts_summary | 备件需求汇总 | 运维 |
| work_order | 工单执行单 | 运维 |
| sensor_advisory | 传感器投资建议 | 管理 |

### 3.6 设备健康矩阵（device-grid.html）

**路由**: `/device-grid`
**用途**: 独立的10×10设备健康矩阵视图，与首页共享 device-grid-component.js 组件。去掉管理层KPI卡片和策略选择器，聚焦运维工程师的设备状态监控。支持缩放、排序、筛选，适合大屏投屏监控。

### 3.7 鹰眼3D球体（sphere-demo.html）

**路由**: `/sphere-demo`
**用途**: 基于Three.js的交互式3D数字孪生演示。100台CNC设备以节点分布在3D球体表面，健康评分映射为颜色和大小。支持MediaPipe手势识别（握拳旋转/张手缩放/双指平移）和鼠标回退方案。60fps渲染管线，适合展厅大屏和路演演示。

---

## 四、CSS 设计系统

### 4.1 设计令牌（Design Tokens）

所有页面共用一套 CSS 自定义属性，定义在 `:root` 中。

**深色主题（默认）**:

```css
:root {
  --bg-root: #080a0d;          /* 最深背景 */
  --bg-surface: #0e1117;       /* 表面/Header背景 */
  --bg-card: #141820;           /* 卡片背景 */
  --bg-card-alt: #181d26;       /* 交替卡片背景 */
  --bg-input: #0c0f15;          /* 输入框背景 */
  --border: #1c2230;             /* 默认边框 */
  --border-light: #242b38;      /* 浅边框 */
  --border-accent: #2a3a50;     /* 强调边框 */
  --text-primary: #e6ebf2;      /* 主文字 */
  --text-secondary: #8e9aab;    /* 次要文字 */
  --text-muted: #5a6474;        /* 弱化文字 */
  --accent-cyan: #00c9a0;       /* 主强调色（健康/告警） */
  --accent-amber: #f0a030;      /* 警告色 */
  --accent-red: #f04444;         /* 危险色 */
  --accent-blue: #4d94ff;       /* 信息色 */
  --accent-green: #3fb950;      /* 成功色 */
  --accent-purple: #a371f7;     /* 紫色（SHAP） */
  --accent-pink: #db61a2;       /* 粉色 */
  --shadow-card: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 30px rgba(0,0,0,0.5);
  --radius: 3px;                /* 工业锐角 */
  --radius-md: 6px;
  --font-mono: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
  --font-sans: 'PingFang SC', 'Microsoft YaHei', 'Hiragino Sans GB', 'Segoe UI', system-ui, sans-serif;
  --transition: 0.2s cubic-bezier(0.33, 1, 0.68, 1);
}
```

**浅色主题（`[data-theme="light"]`）**:
- 所有背景色反转为白/浅灰系列
- 所有文字色反转为深色系列
- 强调色（accent-*）保持不变
- body::before 大气背景改为浅色渐变
- 阴影减弱

### 4.2 页面级 CSS 变量差异

| 页面 | 变量前缀 | 特殊变量 |
|------|---------|---------|
| home.html | `--bg`, `--bg-card`, `--text` (简化版) | `--green`, `--yellow`, `--orange`, `--red`, `--blue`, `--purple`, `--teal` |
| index.html | `--bg-root`, `--bg-surface`, `--bg-card` (完整版) | 40+变量 |
| chat.html | 同 index.html | 同 index.html |
| technical-overview.html | 同 index.html | `--accent-pink`, `--radius-lg` |
| reports.html | 同 index.html | 同 index.html |
| role-gate.html | `--bg-root`, `--bg-card`, `--border` | `--cyan`, `--amber`, `--purple`, `--cyan-dim`, `--amber-dim`, `--purple-dim` |

### 4.3 导航栏 CSS 变量（navbar.js 注入）

```css
--gn-bg: rgba(14, 17, 23, 0.92);       /* 毛玻璃背景 */
--gn-border: rgba(28, 34, 48, 0.8);
--gn-text: #e6ebf2;
--gn-text-secondary: #8e9aab;
--gn-text-muted: #5a6474;
--gn-hover-bg: rgba(255,255,255,0.03);
```

### 4.4 关键视觉模式

1. **大气背景**: `body::before` 固定定位径向渐变（多色环境光晕）
2. **扫描线叠加**: `body::after` 半透明水平条纹（仅 role-gate）
3. **3D Keycap 效果**: 底部阴影 + 多层 box-shadow + inset 高光
4. **脉冲动画**: logo-dot / 工单光晕（`@keyframes pulse/keycapPulse/keycapAlarm/keycapWarn`）
5. **毛玻璃导航**: `backdrop-filter: blur(16px) saturate(180%)`
6. **交错入场**: `stagger-in` + `animation-delay`（index.html）
7. **左侧色条**: 卡片 `border-left: 3px solid`（chart-card, info-card, wo-card）

---

## 五、JavaScript 模块

### 5.1 role-check.js（41行）

**加载时机**: `<head>` 第一个 `<script>`，同步执行，首帧前完成
**职责**:
1. 从 `sessionStorage` 读取 `user_role`
2. 无角色 → `window.location.replace('/role-gate?redirect=...')`
3. 有角色 → `document.documentElement.setAttribute('data-role', role)`
4. 无效角色 → 清除并重定向
5. try-catch 保护（sessionStorage 不可用时静默降级）
6. `console.log('[role-check] data-role set to:', role)`

### 5.2 role-switcher.js（78行）

**全局 API**: `window.RoleSwitcher`
- `RoleSwitcher.get()` → 返回当前角色标识
- `RoleSwitcher.set(role)` → 设置角色 + 清除 role_context_sent + 刷新页面
- `RoleSwitcher.label(role)` → 返回中文标签
- `RoleSwitcher.meta(role)` → 返回完整元数据（label, subtitle, icon, color）

### 5.3 theme-init.js（16行）

**加载时机**: `<head>` 第二个 `<script>`，同步执行
**职责**: 从 `localStorage` 读取 `dashboard-theme`，若为 `light` 则设置 `data-theme="light"` 属性

### 5.4 navbar.js（424行）

**注入方式**: IIFE自执行，创建 `<style>` + `<nav id="global-nav">` 插入 `<body>` 最前面

**导航链接**（6个）:
| 链接 | 路由 | 图标 |
|------|------|------|
| 首页 | `/` | ● |
| 仪表盘 | `/dashboard` | ■ |
| AI Copilot | `/chat` | ⚙ |
| 知识库 | `/knowledge-base` | 📚 |
| 技术架构 | `/technical-overview` | ☰ |
| 报告 | `/reports` | 📄 |

**右侧组件**（从左到右）:
1. **角色切换按钮**（gn-role-toggle）: 胶囊形，显示彩色圆点+角色名，点击循环切换 operator→manager→developer→operator，切换后 `window.location.reload()`
2. **主题切换按钮**（gn-theme-btn）: 胶囊形，显示 ☀浅色/☾深色，点击切换 `data-theme` + localStorage + 刷新页面
3. **降级状态指示器**（gn-status）: 彩色圆点+模式文字，每60秒轮询 `degradation_status.json`，点击弹出详情面板
4. **版本徽章**: `v2.0 · 半决赛版`

**降级状态详情面板**:
- 弹出层（420px宽，居中定位，毛玻璃背景）
- 显示：ML推理/统计推理/规则引擎 三组件状态（✅/❌）
- 影响范围说明（4种模式各有不同描述）
- 恢复建议（含具体命令行）
- 点击遮罩或×关闭

**响应式断点**: 768px（隐藏右侧区域）、520px（隐藏Logo文字）
