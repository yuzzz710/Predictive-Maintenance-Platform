# CLAUDE_REF_后端 — Gateway后端 · Skills技能 · 数据文件详解

> 从 CLAUDE.md 拆分 | 苗圃杯·半决赛 v2.1 | 2026-06-04

---

## 六、Gateway 后端架构

### 6.1 入口（app.py, 423行）

**框架**: FastAPI + uvicorn（端口 8765，reload=True）
**静态挂载**: `/data`, `/images`, `/shared`, `/reports/generated`, `/reports/pdfs`
**定时任务**: APScheduler（启动时注册3个定时任务，关闭时停止）

**路由表**（8个Router注册）:

| Router来源 | 前缀 | 主要端点 |
|------|------|------|
| `gateway.routes` | — | `POST /api/chat`, `POST /api/maintenance/strategy`, `GET /api/tools`, `GET /health` |
| `gateway.tracking_routes` | — | 工单跟踪CRUD + 技师管理API |
| `gateway.tracking_routes.router2` | — | 工单操作API |
| `gateway.tracking_routes.router3` | — | 工作流管理API |
| `gateway.tracking_routes.router4` | — | 库存管理API |
| `gateway.tracking_routes.router5` | — | 技师管理API |
| `gateway.kb_routes` | — | 知识库管理8端点（上传/索引/检索/删除/日志） |
| `gateway.fault_injection` | `/api` | `POST /api/fault-injection`（NEW） |

**页面路由**:

| 方法 | 路由 | 响应 |
|------|------|------|
| GET | `/` | home.html |
| GET | `/role-gate` | role-gate.html |
| GET | `/dashboard` | index.html |
| GET | `/chat` | chat.html |
| GET | `/technical-overview` | technical-overview.html |
| GET | `/knowledge-base` | knowledge-base.html |
| GET | `/work-order-tracking` | work-order-tracking.html |
| GET | `/workflows` | workflows.html |
| GET | `/inventory` | inventory.html |
| GET | `/technicians` | technicians.html |
| GET | `/reports` | reports.html（no-cache） |
| GET | `/api/reports` | JSON报告列表 |
| POST | `/api/reports/generate-pdf` | Playwright PDF生成 |
| POST | `/api/reports/delete` | 删除报告（HTML+PDF） |
| POST | `/api/reports/open-pdfs-folder` | 打开PDF文件夹 |

### 6.2 配置（config.py, 39行）

- 加载 `.env` 文件
- 读取 `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- 路径常量: `BASE_DIR`, `PROJECT_ROOT`, `MCP_DIR`, `DATA_DIR`, `V3_OUTPUTS`, `DASHBOARD_DATA`
- 服务器绑定: `HOST`（默认0.0.0.0）, `PORT`（默认8765）

### 6.3 路由（routes.py, 324行）

| 端点 | 功能 |
|------|------|
| `POST /api/chat` | SSE流式对话，调用 `chat_stream()` |
| `POST /api/maintenance/strategy` | 策略切换：重新生成工业维护计划CSV + 返回内联JSON数据 |
| `POST /api/work-order/generate` | LLM生成维护执行单（调用 `work_order_report_generator`） |
| `GET /api/tools` | 返回可用工具列表 |
| `GET /health` | 健康检查 |

### 6.4 DeepSeek客户端（deepseek_client.py, 235行）

**核心函数**: `chat_stream(messages)` — 异步生成器

**流程**:
1. 构建 OpenAI 兼容请求体（model, messages, tools, temperature=0.3, max_tokens=4096）
2. 发送 POST → 读取 SSE 流（`text/event-stream`）
3. 实时 yield `text_delta` 事件 → 前端逐字显示
4. 检测 `tool_calls` → 累积参数 → yield `tool_call` 事件
5. 执行工具 → 收集结果 → yield `tool_result` 事件
6. 将工具结果注入 messages → 重新调用（最多5轮）
7. 特殊事件：`chart`（ECharts图表数据）、`report`（报告链接）

**辅助函数**:
- `_trim_history()`: 保留最近3轮用户对话
- `_execute_tool_round()`: 执行一批工具调用

### 6.5 工具定义（tools.py, 2500+行）

**25个 Gateway Tools**（OpenAI function-calling 格式），其中 3 个为 RAG 文档检索工具:

| # | 工具名 | 类型 | 功能 |
|---|--------|------|------|
| 1 | `query_device_status` | 只读 | 单设备完整状态（告警/z-score/异常模式/维护建议/技师/备件/成本/SLA/健康分） |
| 2 | `list_alarm_devices` | 只读 | 所有告警/警告设备，按优先级排序 |
| 3 | `get_fault_history` | 只读 | 设备历史故障记录（时间/类型/分组/严重度） |
| 4 | `get_sensor_trend` | 只读 | 传感器时序趋势（含ECharts图表数据） |
| 5 | `compare_machines` | 只读 | 两台设备横向对比（含图表） |
| 6 | `get_root_cause_analysis` | 只读 | 多源根因分析（诊断/z-score/故障链） |
| 7 | `get_work_order_history` | 只读 | 维护工单历史（含成本/技师/备件/SLA） |
| 8 | `explain_predictability_limit` | 只读 | 5维度可预测性分析 + 传感器升级建议 |
| 9 | `get_backtest_results` | 只读 | 三层时序回测结果（点级+事件级+步进） |
| 10 | `get_rul_prediction` | 只读 | RUL预测（含置信区间，三轨并行架构） |
| 11 | `generate_maintenance_report` | 流水线 | AI生成HTML/PDF报告（8种类型） |
| 12 | `run_pipeline` | 流水线 | 一键运行完整DAG流水线（3种策略） |
| 13 | `list_work_order_status` | 只读 | 工单跟踪状态列表（状态机+分配+超时） |
| 14 | `assign_and_notify_work_order` | 流水线 | 自动匹配技师+发送邮件通知 |
| 15 | `update_work_order_status` | 流水线 | 工单状态流转+通知（6状态机） |
| 16 | `get_work_order_tracking_detail` | 只读 | 单工单完整审计轨迹 |
| 17 | `get_post_repair_validation` | 只读 | 修后Z-Score自动验收（3规则） |
| 18 | `run_health_check` | 流水线 | 手动触发每日健康巡检+邮件 |
| 19 | `check_spare_parts_inventory` | 只读 | 备件库存状态检查 |
| 20 | `generate_procurement_order` | 流水线 | 自动生成采购申请单 |
| 21 | `list_technicians` | 只读 | 员工/技师列表（姓名/负载/状态） |
| 22 | `assign_technician_to_work_order` | 流水线 | 技师分配到工单+通知 |
| 23 | `search_system_docs` | RAG检索 | 检索系统使用文档（CLAUDE.md等） |
| 24 | `search_maintenance_kb` | RAG检索 | 检索运维知识库（维护手册等） |
| 25 | `search_fault_cases` | RAG检索 | 检索历史故障案例（log.csv自动生成） |

### 6.6 故障注入API（fault_injection.py, 537行）（NEW）

**端点**: `POST /api/fault-injection`
**请求体**: `{"machine_id": "CNC_042", "fault_type": 3, "severity": "medium"}`

**处理流程**（全内存计算，不修改任何数据文件）:
1. 读取 `failure_sig.csv` 获取故障类型签名（参数偏离模式）
2. 读取 `equipment_health_score.csv` 获取当前健康分
3. 根据故障分组（High-Voltage/Thermal/Subtle）和严重度（mild/medium/severe）计算合成Z-Score
   - 故障分组Z-profile：High-Voltage→V主导，Thermal→T主导，Subtle→A主导
   - 严重度倍率：mild(1.8×/1.2×/0.5×), medium(2.8×/1.8×/0.8×), severe(4.2×/2.5×/1.2×)
4. 生成SHAP归因数据（异常信号 + Top贡献特征 + 排查清单 + 自然语言摘要）
5. 构建工单（优先级P1/P2/P3 + 动作类型 + 技师分配 + 备件清单 + 验收标准）
6. 构建6步前端动画描述符（每步含图标/标题/描述/grid_class）
7. 返回完整JSON：`{success, machine_id, injection: {fault_type, synthetic_z, shap, work_order, steps}}`

**关键设计**:
- 严重度影响：健康分惩罚（mild=-10hs, medium=-25hs, severe=-45hs）+ 成本风险倍率
- 技师匹配：voltage_drift→电气专家, thermal_buildup→热控专家, combined→高级技师
- 备件映射：voltage_drift→供电模块/稳压器/电容, thermal_buildup→散热风扇/导热硅脂/PT100
- 验收标准：Z-Score回归正常(z<1.5) + 24h无告警复现 + 温度稳定在基线±2σ

### 6.7 系统提示词（prompts.py, 200+行）

**提示词内容**:
- 三角色服务对象定义（运维+管理+开发）
- 10个工具的使用说明和触发条件
- 3种维护策略速览（成本效率/生产效率/质量优先）
- 策略选择规范（必须先展示三种选项，等用户选择后才能执行）
- 工单数据字段说明（成本/技师/备件/调度/质量）
- 9种故障类型参考
- 回答规范（先结论后细节、角色感知、价值先行、引用数据）
- 35条常见问题处理映射
- 传感器升级三阶段ROI数据
- RUL预测回答规范（含数据限制声明）

### 6.8 报告系统

**report_orchestrator.py（426行）**: 多步MCP工具协调，聚合数据构建报告上下文
**report_generator.py（320行）**: Jinja2模板渲染 + matplotlib暗色图表（传感器趋势/风险分布/故障饼图/成本柱状图）+ 三后端PDF转换
**work_order_report_generator.py（572行）**: LLM生成7章节维护执行单（问题摘要→可能原因→检查步骤→备件工具→安全提醒→验证方法→执行时段），注入专家规则知识库

---

## 七、Skills 技能架构

### 7.1 流水线 DAG

```
data_prep (Skill 1) ──required──┐
                                 ├── stat_inference (Skill 2) ──required── diagnosis (Skill 4) ──optional── decision (Skill 5)
                                 └── ml_inference (Skill 3) ──optional──┘
```

stat_inference 和 ml_inference 在 data_prep 后并行执行（ThreadPool）。

### 7.2 技能1：数据准备（predictive-maintenance-data-prep）

**入口**: `scripts/run.py <data_dir> <output_dir>`
**核心逻辑**: `baseline_analysis.py`（651行）

**输出文件**（7个）:
1. `z_scores.csv` — 逐设备复合Z-Score + 告警等级
2. `cost_risk_matrix.csv` — 故障率×单件成本×日产量
3. `baseline_stats.csv` — 每设备μ/σ/Q1/Q3/n + 基线质量/来源/集群
4. `failure_signatures.csv` — 故障类型参数偏离模式
5. `variance_decomposition.csv` — 设备间 vs 设备内方差占比
6. `machine_clusters.csv` — K-Means 3集群分配
7. `hotelling_t2.csv` — Hotelling T² 多变量统计量

**算法步骤**:
1. 加载 MACHINE_LOG → 筛选正常运行时段的样本（Failure.Type=0）
2. 每设备计算 μ/σ/Q1/Q3（至少3个样本，不足则用集群回退）
3. 三层回退策略：≥6样本→自身基线；3-5→60%自身+40%集群；<3→K-Means集群均值
4. 基于基线计算每个时间点的 z-score = (x-μ)/σ
5. 复合Z-Score = √(ZV² + ZA² + ZT²)
6. 故障签名：按故障类型分组统计参数偏离Δ和Δ%
7. 方差分解：ANOVA框架计算设备间/设备内方差占比
8. 成本风险矩阵：Risk = P(fault) × UnitCost × DailyOutput

### 7.3 技能2：统计推理（predictive-maintenance-stat-inference）

**入口**: `scripts/run.py --data-dir --prep-dir --output-dir`
**核心文件**: baseline_analysis.py + health_score.py + quality_cost_chain.py + backtest_validator.py

**输出文件**（4个）:
1. `alert_summary.csv` — 告警摘要统计
2. `t2_results.csv` — T²统计 + 控制限
3. `equipment_health_score.csv` — 8维度健康评分
4. `quality_cost_chain.csv` — 质量-成本因果链

**健康评分算法（health_score.py, 595行）**:

| 维度 | 权重 | 数据来源 |
|------|:--:|------|
| failure_rate（故障率） | 0.20 | 历史故障计数/总记录数 |
| zscore_risk（Z-Score异常） | 0.20 | z_composite 最大值 |
| temperature_trend（温度趋势） | 0.15 | 温度时序斜率 |
| voltage_instability（电压不稳定度） | 0.15 | 电压标准差/均值 |
| maintenance_overdue（维护超期） | 0.10 | 距保养到期天数 |
| cost_at_risk（成本风险） | 0.10 | 日成本风险值 |
| quality_failure_rate（质量缺陷率） | 0.05 | 产品测试缺陷率 |
| spec_violation_rate（超规格率） | 0.05 | 超出规格范围比例 |

健康分 = 100 - Σ(维度值 × 权重 × 缩放因子)
等级: Healthy(≥80) / Warning(≥60) / Degrading(≥40) / Critical(<40)

**时序回测（backtest_validator.py, 811行）**:

三层验证架构:
- **Layer 1 点级回测**: 逐时间步的混淆矩阵（TP/FP/TN/FN），计算Precision/Recall/F1/FPR
- **Layer 2 事件级回测**: 以故障发作点为锚点，计算预警提前量（lead time），统计检出率/漏报率
- **Layer 3 步进回测**: 30步 expanding window，验证基线收敛性（14-18步收敛）

### 7.4 技能3：ML推理（predictive-maintenance-ml-inference）

**入口**: `scripts/run.py --data-dir --prep-dir --output-dir --model v1|v2`

**v1 XGBoost（model_training.py, 1102行）**:
- 35维特征：A组17维滑动窗口统计量 + B组8维设备静态特征 + C组4维产品质量 + D组6维当前状态
- 双独立分类器：分别预测14分钟和28分钟后故障
- 成本敏感样本权重：weight ∝ UnitCost × DailyOutput
- 阈值优化：最大化 F2-score
- 窗口大小对比：win5/win8/win10

**v2 Multi-Task NN（model_training_v2.py, 1199行）**:
- 106维四维度特征体系：趋势(24维) + 波动率(36维) + 状态(26维) + 成本上下文(20维)
- 共享特征提取器：128→64→32（BatchNorm+ReLU+Dropout 0.35）
- 双任务头：故障密度回归（主任务）+ 产品质量预测（辅助任务）
- 数据增强：高斯噪声 + 随机掩码 + 特征Dropout
- 三变体对比：10in_5pred / 10in_10pred / 15in_5pred

**RUL估算（rul_estimator.py, 590行）**:
- 三轨并行架构：Track A 退化速率法（当前实现）+ Track B 生存分析 + Track C LSTM
- Track A：回溯健康分时序→拟合退化曲线→RUL=(当前健康分-40)/退化速率
- 输出：rul_steps, rul_hours, 置信区间, health_score_projected_7d/14d

### 7.5 技能4：诊断分析（predictive-maintenance-diagnosis）

**入口**: `scripts/run.py --data-dir --prep-dir --stat-dir [--ml-dir] --output-dir`

**诊断引擎（maintenance_decision_engine.py, 1050行）**:
- 4种异常模式识别：voltage_drift（电压漂移）/ thermal_buildup（热积聚）/ power_anomaly（功率异常）/ combined_degradation（复合退化）

**5维度可预测性分析（predictability_analysis.py, 536行）**:

| 维度 | 分析内容 | 核心指标 | 结论 |
|------|---------|---------|------|
| D1 单参数区分力 | 4参数分别的Youden's J、Cohen's d、KS检验 | J≤0.075 | 无参数能区分正常/故障 |
| D2 参数耦合 | 故障前后参数相关性变化 | ρ变化<0.1 | 耦合未显著改变 |
| D3 故障渐进性 | 故障前参数轨迹分析 | 无渐变趋势 | 故障非渐进式 |
| D4 模型收敛 | ML模型AUC vs 随机猜测 | AUC≈0.54 | 模型收敛到平凡解 |
| D5 传感器缺口 | 现有 vs 所需传感器对比 | 缺口=振动/频谱/热成像 | 需要传感器升级 |

**SHAP可解释性管线**:
1. `shap_explainer.py`（379行）: RiskDecomposer（公式直接分解）+ StatLayerSHAP（TreeSHAP）
2. `local_explainer.py`（420行）: 数学特征→5类工业根因（电气/热控/机械/维护/过程质量）
3. `shap_visualizer.py`（154行）: 导出 `shap_dashboard.json`（618KB, 100台）
4. `shap_postprocess.py`（176行）: 后处理入口，在决策完成后调用

### 7.6 技能5：决策工单（predictive-maintenance-decision）

**入口**: `scripts/run.py --data-dir --prep-dir --stat-dir [--ml-dir --diag-dir] --output-dir --max-orders --strategy`

**Phase A — 基础4层决策（maintenance_decision_engine.py, 1140行）**:

| 层 | 功能 | 方法 |
|----|------|------|
| L1 融合 | 多信号加权融合 | stat_anomaly=0.40 + ml_density=0.25 + cost_risk=0.25 + trend=0.10 |
| L2 诊断 | 异常模式识别 | 4种模式（voltage_drift/thermal_buildup/power_anomaly/combined_degradation） |
| L3 决策 | 动作分级 | 6级（immediate_shutdown→preventive_repair→schedule_inspection→increase_monitoring→routine_check→no_action） |
| L4 输出 | 工单生成 | 优先级排序 + 建议时间窗 + 预期成本/节约 + 根因标注 |

**Phase B — 工业扩展5模块**:

| 层 | 模块 | 文件 | 功能 |
|----|------|------|------|
| L5 | 策略选择器 | strategy_selector.py（224行） | 3种策略（cost_efficiency/production_efficiency/quality_first）不同阈值/权重/SLA |
| L6 | 技师分配器 | technician_assigner.py（212行） | 12条规则匹配技师类型，成本感知降级 |
| L7 | 备件规划器 | spare_parts_planner.py（183行） | 故障→备件目录，自动生成清单 |
| L8 | 停机优化器 | downtime_optimizer.py（167行） | 6规则决策树（立即/夜间/周末/间隙/计划） |
| L9 | 验收验证器 | acceptance_validator.py（202行） | 维修后逐项验收标准 |

**Phase C — 传感器升级路线图（sensor_upgrade_roadmap.py, 611行）**:

| 阶段 | 传感器 | Youden's J | 投资 | 预期5年ROI | 回本 |
|------|--------|:--:|------|:--:|:--:|
| Phase 1 | 振动加速度计+FFT分析仪 | 0.075→0.525 | $402k | 994% | 6月 |
| Phase 2 | 电流频谱+谐波分析 | 0.525→0.805 | $237k | 1136% | 5月 |
| Phase 3 | 红外热成像+趋势软件 | 0.805→0.90 | $393k | 723% | 8月 |

ROI模型：三场景概率估算（保守0.294× / 预期0.578× / 乐观0.812×）

---

## 八、数据文件详解

### 8.1 原始数据（4个CSV）

| 文件 | 大小 | 行数 | 列数 | 内容 |
|------|------|------|------|------|
| MACHINE_LOG | ~254KB | 2999 | 7 | 传感器日志（Date, Equipment.Id, Failure.Type, Amperage, Temperature, Voltage, Rotor Speed） |
| MACHINE_SUMMARY | ~9KB | 100 | 多列 | 设备元数据（型号/制造月份/保养日期/日产量/单件成本） |
| PRODUCT_ASSEMBLY | ~6KB | 135 | 多列 | 产品组装记录 |
| PRODUCT_TESTS | ~13KB | 420 | 多列 | 产品测试测量记录 |

### 8.2 仪表盘数据（web-dashboard/data/）

**脚本生成数据**（2个，NEW）:
- `algorithm_comparison.csv`（0.5KB）— 7种算法对比实验数据（AUC/F2/精确率/召回率/训练时间/推理时间）
- `kde_params.json`（47KB）— 4参数×200点KDE分布数据（正常/故障μ-σ-PDF + overlap + Youden's J + 三阶段传感器升级）

**核心流水线输出**（22个文件同步自Pipeline）:
- `z_scores.csv`（899KB）— 逐时间点Z-Score + 告警等级
- `baseline_stats.csv`（32KB）— 逐设备基线统计
- `cost_risk.csv`（10KB）— 成本风险矩阵
- `failure_sig.csv`（2KB）— 故障类型签名
- `variance_decomp.csv`（0.4KB）— 方差分解
- `machine_clusters.csv`（7KB）— 设备集群
- `t2_results.csv`（203KB）— Hotelling T²
- `log.csv`（197KB）— 运行日志
- `summary.csv`（6KB）— 设备摘要
- `alert_summary.csv`（18KB）— 告警摘要
- `equipment_health_score.csv`（11KB）— 健康评分
- `industrial_maintenance_plan.csv`（27KB）— 工业维护计划（30+列，含SHAP归因）
- `work_orders.csv` / `maintenance_work_orders.csv`（4-5KB）— 维护工单
- `strategy_comparison.csv`（0.4KB）— 策略对比
- `technician_schedule.csv`（2KB）— 技师排班
- `spare_parts_plan.csv`（5KB）— 备件规划
- `downtime_schedule.csv`（2KB）— 停机调度
- `diagnosis.csv`（5KB）— 诊断结果
- `rul_degradation.csv`（15KB）— RUL退化数据
- `sensor_phase_summary.csv`（1.4KB）— 传感器阶段摘要
- `backtest_*.csv`（多个）— 回测结果

**JSON文件**:
- `shap_dashboard.json` — SHAP归因仪表盘
- `degradation_status.json` — 系统降级状态（`{"mode":"FULL","components":{"ml_available":true,...}}`）
- `chain_analysis_summary.json` — 因果链分析汇总
- `quality_cost_chain_summary.json` — 质量成本链汇总
- `methodology_roadmap.json` — 方法论路线图
- `rul_summary.json` — RUL预测汇总
- `stat_inference_summary.json` — 统计推理汇总
- `backtest_summary.json` — 回测结果汇总
- `maintenance_acceptance_rules.json` — 维护验收规则
- `association_rules_summary.csv` — 关联规则汇总

### 8.3 知识库JSON（skills/decision/scripts/data/）

| 文件 | 内容 | 用途 |
|------|------|------|
| `technician_rules.json` | 12条技师分配规则 | 故障模式→技师类型/人数/工时 |
| `spare_parts_catalog.json` | 备件目录+单价 | 故障→备件推荐 |
| `acceptance_rules.json` | 验收标准 | 维修后逐项检查 |
| `sensor_roi_factors.json` | ROI计算因子 | 传感器投资回报模型 |
| `maintenance_expert_rules.json` | 诊断知识+检查步骤+安全提醒 | LLM提示词注入 |
| `industrial_sensor_knowledge.json` | 7种传感器规格/成本/ROI | AI投资顾问 |
