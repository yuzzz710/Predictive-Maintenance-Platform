# CLAUDE_REF_算法 — 核心算法 · 角色权限 · 降级 · RAG · 业务流程

> 从 CLAUDE.md 拆分 | 苗圃杯·半决赛 v2.1 | 2026-06-04

---

## 九、核心算法详解

### 9.1 逐设备 Z-Score 基线

**公式**: Z = (x - μ) / σ
**复合**: Z_composite = √(ZV² + ZA² + ZT²)

**三层回退**:
- L1 集群回退：≥6正常样本→自身μ/σ；3-5→60%自身+40%集群；<3→K-Means均值
- L2 故障分组权重：高压型(V=0.50 A=0.25 T=0.25) / 热控型(V=0.25 A=0.25 T=0.50) / 微弱型(均匀)
- L3 产能分层阈值：核心(Watch=1.3 Alarm=2.3) / 标准(1.5/2.5) / 辅助(1.6/2.6)

**阈值扫参**:

| z阈值 | 精确率 | 召回率 | F1 | FPR | 运维场景 |
|-------|--------|--------|-----|-----|---------|
| z>1.0 | 73.5% | 85.6% | 79.0% | 80.5% | FPR过高不可用 |
| z>1.5 | 76.0% | 62.2% | 68.4% | 51.2% | 初步筛查(Watch) |
| z>2.0 | **83.9%** | 39.4% | 53.6% | **19.7%** | **运维派单(推荐)** |
| z>2.5 | 92.1% | 21.9% | 35.4% | 4.9% | 紧急干预(Alarm) |

### 9.2 Hotelling T² 多变量控制

**公式**: T² = (x - μ)ᵀ Σ⁻¹ (x - μ)
**控制限**: χ²(α=0.01, df=3)
**性能**: P=100%, R=22%（高置信度验证器）

### 9.3 成本风险矩阵

**公式**: Risk = P(fault) × UnitCost × DailyOutput
**阈值**: P90/P75分位数自适应
**技师降级**: 低于P50成本风险的设备自动降级技师配置（节省$15-40/h）

### 9.4 8维度健康评分

**公式**: HealthScore = 100 - Σ(维度值 × 权重 × 缩放因子)
**等级**: Healthy(≥80) / Warning(≥60) / Degrading(≥40) / Critical(<40)
**趋势分类**: Stable / Degrading / Critical（基于健康分时序斜率）

### 9.5 多信号决策融合

**融合公式**: Risk = 0.40×stat_anomaly + 0.25×ml_density + 0.25×cost_risk + 0.10×trend
**ML不可用时**: stat_anomaly权重提升至0.65，自动降级为纯统计路径

### 9.6 Youden's J 性能天花板

| 参数 | Youden's J | 诊断价值 | 故障在正常范围占比 |
|------|:--:|------|:--:|
| Voltage | 0.075 | 无（可用>0.30） | 96.3% |
| Temperature | 0.067 | 无 | 97.4% |
| Amperage | 0.057 | 无 | 97.9% |
| Rotor Speed | 0.022 | 完全无（Cohen's d=-0.002, KS p=0.458） | 98.0% |

理论AUC上限 = 0.5 + J_max/2 ≈ 0.537

### 9.7 方差分解

| 参数 | 设备间方差占比 | 设备内方差占比 |
|------|:--:|:--:|
| Voltage | 60.6% | 43.5% |
| Amperage | 72.7% | 33.5% |
| Temperature | 63.9% | 43.0% |

结论：61-73%的方差来自设备间差异，必须逐设备建立基线。

### 9.8 算法对比实验（benchmark_algorithms.py, 324行）（NEW）

在4参数传感器数据上对比7种主流算法的预测性能，以实验数据证明"纯ML预测不可行"。

**数据来源**: 100%实际训练，无虚拟/合成数据
- 5种sklearn模型在2999行MACHINE_LOG数据上实际训练
- CNN/MTNN结果复用已有 `variant_comp.csv`（实际训练产出）

**特征工程**（31维）:
- 逐设备Z-Score（zv/za/zt/zc）+ 比率（v_ratio/a_ratio/t_ratio）+ 衍生（power/thermal）
- 滚动窗口统计量（rolling mean/std × 9参数 + rolling max × 4参数）
- 预测目标：`next_is_fault`（预测下一时间步的故障，非当前状态检测）

**7种算法对比结果**:

| 算法 | 类型 | AUC | F2 | 训练时间 | 推理时间 |
|------|------|:--:|:--:|------|------|
| 逻辑回归(LR) | classical | 0.523 | 0.520 | 0.014s | 0.0004ms |
| 支持向量机(SVM) | classical | 0.517 | 0.928 | 0.646s | 0.10ms |
| 随机森林(RF) | ensemble | 0.517 | 0.835 | 1.25s | 0.015ms |
| XGBoost | ensemble | 0.520 | 0.769 | 0.291s | 0.001ms |
| LightGBM | ensemble | 0.538 | 0.776 | 0.141s | 0.003ms |
| CNN (1D-Conv) | deep | 0.547 | 0.973 | 680s | 12.5ms |
| Multi-Task NN | deep | 0.589 | 0.976 | 920s | 18.3ms |

**结论**: 所有7种算法AUC在0.517-0.589之间，均未突破可用阈值0.70。深度方法略优于经典ML，但最高仅超出随机猜测0.09。证明瓶颈在数据（4传感器信息上限），不在模型。

### 9.9 KDE分布参数计算（compute_kde_params.py, 165行）（NEW）

**输入**: `log.csv`（正常/故障样本分离）+ `dim1.csv`（overlap/Cohen's d/Youden's J）+ `sensor_phase_summary.csv`（传感器升级三阶段）
**输出**: `kde_params.json`（47KB）

**计算逻辑**:
1. 从log.csv分离正常样本（Failure.Type=0）和故障样本（Failure.Type>0）
2. 每参数计算 μ/σ → scipy.stats.norm.pdf 生成200点PDF曲线（X轴范围 μ±4σ）
3. 从dim1.csv读取overlap_pct, cohens_d, youden_j 标注
4. 从sensor_phase_summary.csv读取三阶段传感器升级数据
5. 输出baseline_youden_j=0.075 + baseline_summary自然语言结论

---

## 十、角色权限体系

### 10.1 三角色定义

| 角色 | 标识 | 颜色 | 定位 |
|------|------|------|------|
| operator | 运维工程师 | 青 #00c9a0 | 执行层：日常监控、异常处理、工单执行 |
| manager | 生产管理负责人 | 琥珀 #f0a030 | 决策层：预算管控、策略选择、投资决策 |
| developer | 平台开发人员 | 紫 #a371f7 | 全量视图：技术细节审查、模型评估 |

### 10.2 CSS 过滤机制

```css
/* Operator: 隐藏纯Manager和纯Developer内容 */
html[data-role="operator"] .role-manager:not(.role-operator) { display: none !important; }
html[data-role="operator"] .role-developer:not(.role-operator) { display: none !important; }

/* Manager: 隐藏纯Operator和纯Developer内容 */
html[data-role="manager"] .role-operator:not(.role-manager) { display: none !important; }
html[data-role="manager"] .role-developer:not(.role-manager) { display: none !important; }

/* Developer: 无隐藏规则 → 全量可见 */
```

**关键设计**: `:not()` 伪类确保同时拥有多个角色类的元素不被误杀。`class="role-operator role-manager"` 对 operator 和 manager 均可见。

### 10.3 类名语义

| 类名 | Operator看到 | Manager看到 | Developer看到 |
|------|:--:|:--:|:--:|
| `role-operator` | ✅ | ❌ | ✅ |
| `role-manager` | ❌ | ✅ | ✅ |
| `role-developer` | ❌ | ❌ | ✅ |
| `role-operator.role-manager` | ✅ | ✅ | ✅ |
| （无角色类） | ✅ | ✅ | ✅ |

### 10.4 执行流程

1. `role-check.js`（同步，首帧前）→ 读取 `sessionStorage.user_role`
2. 无角色 → 跳转 `/role-gate` 选择门
3. 有角色 → `document.documentElement.setAttribute('data-role', role)`
4. CSS 规则立即生效（零闪烁）
5. 导航栏右侧胶囊按钮 → 点击循环切换 → `window.location.reload()`

---

## 十一、降级架构

### 11.1 四级降级

```
FULL（全功能, 22文件）→ STAT_ONLY（ML跳过, ~9s）→ RULE_ONLY（纯规则, ~3s）→ EMERGENCY（应急工单, <1s）
```

| 级别 | 触发条件 | 可用组件 | 工单质量 |
|------|---------|---------|---------|
| FULL | 所有组件就绪 | stat + ML + SHAP + 决策 | 最高（含SHAP归因） |
| STAT_ONLY | ML不可用 / --skip-ml | stat + 决策 | 高（统计基线+规则） |
| RULE_ONLY | 统计不可用 | 纯规则引擎 | 中（硬阈值） |
| EMERGENCY | data_prep失败 | 原始传感器波动 | 低（仅参数超限告警） |

### 11.2 降级状态指示器

- 位置：导航栏右侧（gn-status）
- 颜色：🟢绿色FULL / 🟡黄色STAT_ONLY / 🟠橙色RULE_ONLY / 🔴红色EMERGENCY
- 点击弹出：组件状态 + 影响范围 + 恢复建议（含具体命令行）
- 自动刷新：每60秒轮询 `degradation_status.json`

---

## 十二、RAG 智能客服与文档问答

### 12.1 系统概述

在 AI Copilot 基础上搭建 RAG（检索增强生成）系统，让 LLM 能够检索并引用项目文档和运维知识库回答问题，补齐了纯数据查询的短板。

### 12.2 架构流程

```
用户提问 → 问题分类器（系统文档/运维知识/故障案例/数据查询）
  → 数据查询类 → 走现有 Gateway Tools（不变）
  → 文档知识类 → BGE嵌入 → Chroma向量检索 → Top-K片段注入系统提示词 → LLM基于文档回答
```

### 12.3 三层知识库

| 知识库 | 文档来源 | 块数 | 内容 |
|--------|------|:--:|------|
| sys_docs（系统文档） | CLAUDE.md + 15个技术文档 | 494 | 系统操作、算法原理、功能说明 |
| maint_kb（运维知识） | CNC维护手册、安全规程、排查指南 | 28 | 设备维护、故障排查、安全操作 |
| fault_cases（故障案例） | log.csv 自动生成 | 833 | 历史故障案例+处理经验 |

### 12.4 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 嵌入模型 | BAAI/bge-small-zh-v1.5 | 中文优化，本地运行，~100MB |
| 向量数据库 | Chroma | 本地文件存储，零配置 |
| 文档分块 | 按标题边界，800字/块，100字重叠 | 保持语义完整 |
| 问题分类 | 关键词+模式匹配（非LLM） | 零延迟，中英文双语 |
| 降级策略 | BGE → DeepSeek API → TF-IDF | 任何网络条件下可用 |

### 12.5 新增 Gateway Tools（3个）

| 工具名 | 功能 | 检索目标 |
|--------|------|---------|
| `search_system_docs` | 检索系统使用文档 | CLAUDE.md, SKILL.md, 技术文档 |
| `search_maintenance_kb` | 检索运维知识库 | 维护手册, 安全规程, 排查指南 |
| `search_fault_cases` | 检索历史故障案例 | log.csv 自动生成的故障案例 |

### 12.6 前端增强

- **Chat 侧边栏**：新增"📚 系统使用 & 知识问答"分区（6 个推荐问题）
- **RAG 工具卡片**：紫色主题区分数据查询，展示来源文档+相关度+内容摘要
- **知识库管理页面**：`/knowledge-base`（Developer 角色），上传/索引/检索测试/日志

---

## 十三、业务流程自动化

### 13.1 工单全流程跟踪（Phase A）

基于 SQLite 的 6 状态机：
```
pending（待分配）→ assigned（已分配）→ in_progress（执行中）→ pending_acceptance（待验收）→ completed（已完成）→ archived（已归档）
```

- **Kanban 看板**：`/work-order-tracking`，6 列状态，策略标签切换
- **邮件通知**：QQ 邮箱 SMTP，HTML 工业主题模板，状态变更 + 超时升级
- **技师分配**：12 条规则匹配技师类型 + 成本感知降级
- **动态上下文构建**：任意 100 台设备的工单可通过 `work_order_builder.py` 动态生成

### 13.2 定时任务（Phase B）

| 任务 | 频率 | 功能 |
|------|------|------|
| 每日健康巡检 | 每天 06:00 | 运行 DAG 流水线 → 筛选健康分<40 → 邮件通知 |
| 周度报告 | 每周一 07:00 | 生成 3 份报告 → 邮件发送 |
| 工单超时检查 | 每 15 分钟 | 超时工单自动升级 → 邮件通知 |

### 13.3 备件库存管理（Phase C）

- CSV 文件模拟 ERP 系统
- 采购申请状态流：申请中 → 已下单 → 运输中 → 已到货 → 已入库
- 入库自动触发库存更新
- 库存缺口自动计算 + 采购订单生成

### 13.4 员工管理体系（Phase D）

- 10 名预设员工（中文名 + 真实联系方式）
- 技师类型：junior_technician / electrical_specialist / thermal_specialist / senior_technician
- 工单分配 + 负载跟踪 + 状态管理

### 13.5 新增页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 工单跟踪看板 | `/work-order-tracking` | Kanban 状态机 + 策略标签 |
| 工作流管理 | `/workflows` | 定时任务状态 + 手动触发 |
| 库存管理 | `/inventory` | 备件库存 + 采购订单 |
| 员工管理 | `/technicians` | 技师花名册 + 负载仪表盘 |
