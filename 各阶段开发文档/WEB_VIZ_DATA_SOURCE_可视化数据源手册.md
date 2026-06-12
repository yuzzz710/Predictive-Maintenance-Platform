# 智能设备预测性维护 — Web 可视化数据源手册

> **用途**：为 Web 前端页面提供完整的数据文件清单、字段说明、可视化方案
> **项目根路径**：`C:\Users\yuzzz\Desktop\苗圃杯\git5`

---

## 页面结构总览

```
┌─────────────────────────────────────────────────────────┐
│  Nav: 数据探索 │ 基线分析 │ 模型构建 │ 预测性维护建议      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Section 1 — 数据探索（4 个面板）                         │
│    设备概览统计 / 参数分布 / 故障分析 / 相关性热力图       │
│                                                         │
│  Section 2 — 基线划定分析（5 个面板）                      │
│    方差分解 / 设备基线范围 / z-score 阈值 / 故障签名雷达图 │
│    / 成本风险气泡图                                       │
│                                                         │
│  Section 3 — 模型构建（4 个面板）                          │
│    模型对比 / 特征重要性 / 训练曲线 / 鲁棒性测试           │
│                                                         │
│  Section 4 — 预测性维护建议（4 个面板）                    │
│    可预测性限制 / 诊断结果 / 工单看板 / 传感器升级方案      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Section 1：数据探索

> 回答"数据长什么样"，面向数据概览，所有图表**纯前端渲染**。

### 1.1 设备概览统计卡片

**数据文件**：`原始数据集/MACHINE_SUMMARY_DATA._2025.csv`（6.4KB）

| 字段                    | 类型   | 可视化用途                                 |
| ----------------------- | ------ | ------------------------------------------ |
| Equipment.Id            | string | 设备 ID                                    |
| Equipment.Type          | string | 设备类型                                   |
| Month.of.Manufacture    | date   | 制造月份，计算**设备年龄**           |
| Last Service Date       | date   | 上次保养日期，计算**距上次保养天数** |
| Next Service Date       | date   | 下次保养日期，计算**距下次保养天数** |
| Last Repair Date        | date   | 上次维修日期，计算**距上次维修天数** |
| Units Produced Per day  | int    | 日产量，**设备产能对比柱状图**       |
| Unit Cost of Production | float  | 单位生产成本，**成本分布直方图**     |

**可视化方案**：

- 顶部 **4 张数字卡片**：100 台设备 | X 种设备类型 | 平均日产量 | 平均单位成本
- **日产量排名柱状图**：Top 20 设备（横轴设备ID，纵轴日产量）
- **设备年龄分布直方图**：计算 `(2026 - Month.of.Manufacture)` 分组
- **保养状态仪表盘**：`days_since_service` vs `days_to_next_service` 对比

---

### 1.2 参数时序分布

**数据文件**：`原始数据集/MACHINE_LOG_DATA._2025.csv`（196.8KB，2999行 × 100台）

| 字段                   | 类型      | 可视化用途         |
| ---------------------- | --------- | ------------------ |
| Date                   | datetime  | X 轴时间           |
| Equipment.Id           | string    | 设备筛选器         |
| Failure.Equipment.Type | int (0-9) | 故障类型，颜色编码 |
| Op.Amperage            | float     | 电流               |
| Op.Temperature         | float     | 温度               |
| Op.Voltage             | float     | 电压               |
| Rotor Speed            | float     | 转速               |

**可视化方案**：

- **4 参数联动时序折线图**：选一台设备，展示 Voltage/Amperage/Temperature/Rotor Speed 四条曲线，故障区间用红色背景高亮
- **4 参数箱线图**（正常 vs 故障分组）：每种故障类型一个箱线图子图
- **4 参数小提琴图**：展示正常/故障分布形态差异

---

### 1.3 故障分析

**数据文件**：`数据探索分析/per_device_fault_distribution.csv`（4.0KB）

| 字段               | 类型   | 可视化用途             |
| ------------------ | ------ | ---------------------- |
| Equipment_Id       | string | 设备 ID                |
| Type_0 ~ Type_9    | int    | 每种故障类型的出现次数 |
| Total              | int    | 总记录数（30）         |
| Fault_Count        | int    | 故障窗口数             |
| Normal_Count       | int    | 正常窗口数             |
| Unique_Fault_Types | int    | 故障多样性             |

**可视化方案**：

- **100 台设备堆叠柱状图**：每台设备一条柱子，颜色分层 = 9 种故障类型 + 正常（Type_0）
- **故障类型饼图**：9 种故障类型的总占比
- **故障多样性散点图**：X=Fault_Count, Y=Unique_Fault_Types，点大小=Total，标识高故障+高多样性设备

---

### 1.4 参数相关性

**数据文件**：`数据探索分析/Unified_Machine_WideTable_2025.csv`（247KB）
— 或直接在前端用原始 MACHINE_LOG_DATA 计算相关系数矩阵

**可视化方案**：

- **正常状态相关性热力图**：V-A, V-T, V-RPM, A-T, A-RPM, T-RPM 6 对
- **故障状态相关性热力图**：同上，左右对比布局
- **相关性变化箭头图**：展示正常→故障相关系数的变化方向和幅度

---

## Section 2：基线划定分析

> 回答"什么算异常"，面向统计基线的建立与验证。

### 2.1 方差分解 — 为什么逐设备基线？

**数据文件**：`基线分析和确定/variance_decomposition.csv`（0.4KB）

| 字段          | 类型   | 可视化用途                       |
| ------------- | ------ | -------------------------------- |
| parameter     | string | Voltage / Amperage / Temperature |
| total         | float  | 总方差                           |
| inter_machine | float  | 设备间方差                       |
| intra_machine | float  | 设备内方差                       |
| inter_pct     | float  | 设备间方差占比（61-73%）         |
| intra_pct     | float  | 设备内方差占比                   |

**可视化方案**：

- **百分比堆叠柱状图**：3 个参数各一根柱子，inter_machine（蓝色）vs intra_machine（灰色）分层
- 标注关键结论："设备间方差占 61-73%，否决全局基线"

---

### 2.2 设备基线范围

**数据文件**：`基线分析和确定/baseline_stats.csv`（或从 `z_scores.csv` 中提取每设备的 μ 和 σ）
— **注意**：此文件需从 MCP data-prep 输出中获取，路径为 `agent-mcp架构/outputs_test_mcp/output_data_prep/baseline_stats.csv`

**可视化方案**：

- **设备基线范围横向柱状图**：选 Top 20 设备，横轴 μ±3σ 范围线；每条线用设备自身的正常样本建立
- **设备集群散点图**：X=Voltage_mean, Y=Temperature_mean，颜色=cluster（来自 `machine_clusters.csv`）

---

### 2.3 z-score 阈值与告警分布

**数据文件**：`基线分析和确定/z_scores.csv`（744.7KB，或 MCP 输出中同路径）

| 关键字段                               | 类型     | 可视化用途                       |
| -------------------------------------- | -------- | -------------------------------- |
| Equipment.Id                           | string   | 设备 ID                          |
| Date                                   | datetime | 时间                             |
| z_Voltage / z_Amperage / z_Temperature | float    | 单参数 z-score                   |
| z_composite                            | float    | 综合 z-score（欧几里得）         |
| alert_level                            | string   | Normal / Watch / Warning / Alarm |

**可视化方案**：

- **z-score 阈值线图**：选一台设备，画出 z_composite 时序曲线，叠加 3 条阈值线（Watch=1.5, Warning=2.0, Alarm=2.5）
- **告警等级分布环形图**：4 种 alert_level 的设备占比
- **告警设备表格**：z_composite 最高的 Top 10 设备，带排序和筛选

---

### 2.4 故障类型参数签名（雷达图）

**数据文件**：`基线分析和确定/failure_signatures.csv`（1.9KB）

| 字段                     | 类型      | 可视化用途                               |
| ------------------------ | --------- | ---------------------------------------- |
| failure_type             | int (0-9) | 故障类型                                 |
| failure_group            | string    | Normal / Subtle / Thermal / High-Voltage |
| Op.Voltage_delta_pct     | float     | 电压偏移 %                               |
| Op.Amperage_delta_pct    | float     | 电流偏移 %                               |
| Op.Temperature_delta_pct | float     | 温度偏移 %                               |
| n                        | int       | 样本数                                   |

**可视化方案**：

- **9 型故障雷达图**（3×3 小多图）：每张雷达图 3 轴（V/A/T 偏移%），按 failure_group 颜色分组
- 选中某型时弹出详细卡片：样本数、偏移量、归属组别

---

### 2.5 成本风险矩阵

**数据文件**：`基线分析和确定/cost_risk_matrix.csv`（9.9KB）

| 字段         | 类型   | 可视化用途                              |
| ------------ | ------ | --------------------------------------- |
| Equipment.Id | string | 设备 ID                                 |
| failure_rate | float  | 历史故障率                              |
| cost_at_risk | float  | 日暴露成本（Unit Cost × Daily Output） |
| risk_tier    | string | High / Medium / Low                     |

**可视化方案**：

- **成本风险气泡图**：X=failure_rate, Y=cost_at_risk, 气泡大小=Unit Cost, 颜色=risk_tier
- **风险等级饼图**：High / Medium / Low 占比
- **Top 10 高风险设备横向柱状图**：按 cost_at_risk 降序

---

## Section 3：模型构建

> 回答"模型怎么做、效果如何"，面向 ML 实验验证。

### 3.1 模型评估对比

**数据文件 A**：`预测性维护模型/model_outputs/evaluation_metrics.csv`（0.6KB）— XGBoost v1

| 字段                       | 类型   | 可视化用途        |
| -------------------------- | ------ | ----------------- |
| window_size                | int    | 5 / 8 / 10        |
| target                     | string | 14min / 28min     |
| auc                        | float  | AUC 值            |
| ap                         | float  | Average Precision |
| brier                      | float  | Brier Score       |
| f2_0.5                     | float  | F2@t=0.5          |
| precision_0.5 / recall_0.5 | float  | P/R@t=0.5         |

**数据文件 B**：`预测性维护模型_v2/model_outputs/variant_comparison.csv`（0.6KB）— MTNN v2

| 字段                                   | 类型   | 可视化用途                            |
| -------------------------------------- | ------ | ------------------------------------- |
| variant                                | string | 15in_5pred / 10in_10pred / 10in_5pred |
| fault_r2                               | float  | 故障密度 R²                          |
| fault_binary_auc                       | float  | 二分类 AUC                            |
| fault_best_f2                          | float  | 最佳 F2                               |
| mean_true_density vs mean_pred_density | float  | 真实 vs 预测均值对比                  |

**可视化方案**：

- **双模型对比仪表盘**（XGBoost vs MTNN）：AUC、R²、F2 四宫格数字卡片
- **窗口大小对比分组柱状图**：win=5/8/10 的 AUC/AP/Brier 对比
- **模型性能上限标注线**：在 AUC 图上标注理论天花板（AUC=0.60），解释为什么模型无法超过此线
- **"均值预测器"证据图**：mean_true_density vs mean_pred_density 散点图，展示所有模型变体坍缩到对角线

---

### 3.2 特征重要性

**数据文件**：`预测性维护模型/model_outputs/feature_importance_win5.csv`（3.9KB）

| 字段             | 类型   | 可视化用途       |
| ---------------- | ------ | ---------------- |
| feature          | string | 特征名           |
| importance_14min | float  | 14min 模型重要性 |
| importance_28min | float  | 28min 模型重要性 |
| importance_avg   | float  | 平均重要性       |

**可视化方案**：

- **Top 20 特征重要性横向柱状图**：按 importance_avg 降序，14min/28min 双色叠柱
- **特征分类分组**：趋势特征 / 波动特征 / 状态特征 / 成本特征 用不同颜色

---

### 3.3 训练曲线

**数据文件**：无 CSV — 使用现有的 PNG 图像

`预测性维护模型_v2/figures/training_curves_10in_5pred.png`
`预测性维护模型_v2/figures/training_curves_10in_10pred.png`
`预测性维护模型_v2/figures/training_curves_15in_5pred.png`
`预测性维护模型/figures/win5/model_14min_roc_pr.png`（及 win5/win8/win10 各窗口）

**可视化方案**：

- **ROC/PR 曲线**：从已有 PNG 加载，或从 `evaluation_metrics.csv` 重建简版
- **训练曲线交互画廊**：缩略图+点击放大
- **多窗口 ROC 对比**：win=5/8/10 三条 ROC 曲线叠加

---

### 3.4 鲁棒性测试

**数据文件**：`预测性维护模型_v2/model_outputs/robustness_report.csv`（3.6KB）

| 字段               | 类型   | 可视化用途                                  |
| ------------------ | ------ | ------------------------------------------- |
| variant            | string | 模型变体                                    |
| condition          | string | clean / noise_0.01 / mask_0.1 / dropout_0.1 |
| mse_mean / mse_std | float  | MSE 均值/标准差                             |
| auc_mean / auc_std | float  | AUC 均值/标准差                             |

**可视化方案**：

- **鲁棒性热力图**：行=variant, 列=condition, 颜色深度=auc_mean
- **扰动前后对比**：clean vs 各扰动条件的 AUC 变化柱状图

---

## Section 4：可行的预测性维护建议

> 回答"现在该做什么"，面向最终决策和行动计划。**这是赛题附加部分的核心产出**。

### 4.1 可预测性限制仪表盘（传感器瓶颈分析）

**数据文件**：`预测性维护模型_v3/outputs/dim1_single_param_discriminability.csv`

| 字段                | 类型   | 可视化用途                                     |
| ------------------- | ------ | ---------------------------------------------- |
| parameter           | string | Voltage / Amperage / Temperature / Rotor Speed |
| cohens_d            | float  | Cohen's d 效应量                               |
| youden_j            | float  | Youden's J 指数                                |
| fault_in_normal_pct | float  | 故障样本落入正常范围的 %                       |
| normal_p99_range    | string | 正常值 P99 范围                                |

**数据文件**：`预测性维护模型_v3/outputs/dim5_sensor_gap_analysis.csv`

| 字段              | 类型   | 可视化用途           |
| ----------------- | ------ | -------------------- |
| sensor            | string | 传感器名称           |
| expected_youden_j | string | 预期 Youden's J 范围 |
| expected_auc_gain | string | 预期 AUC 增益        |
| mechanism         | string | 检测机理说明         |
| cost_per_machine  | string | 每台成本             |
| feasibility       | string | 可行性等级           |

**可视化方案**：

- **Youden's J 仪表盘**：4 张迷你仪表盘（每参数一张），指针指向 Youden's J，红色区域标注"<0.30 不可用"
- **故障重叠率柱状图**：4 根柱子（fault_in_normal_pct），高度 96-98%，标题"96%+ 故障落在正常参数范围内"
- **传感器升级对比卡片**（6 张）：每张卡片展示传感器名 + 预期增益 + 成本 + 可行性徽章
- **5 大根因折叠面板**：R1-R5，点击展开 evidence + fix 建议

**辅助数据源**：`预测性维护模型_v3/outputs/dim2_param_coupling_stability.csv`、`dim3_fault_non_progressive.csv`、`dim4_model_convergence.csv`
— 用于补充根因分析的证据数据

---

### 4.2 异常诊断面板

**数据文件**：`agent-mcp架构/outputs_test_mcp/output_diagnosis/diagnosis_report.csv`（4.9KB）

| 字段                          | 类型   | 可视化用途                                                                                    |
| ----------------------------- | ------ | --------------------------------------------------------------------------------------------- |
| machine_id                    | string | 设备 ID                                                                                       |
| primary_pattern               | string | 主异常模式（normal / voltage_drift / thermal_buildup / power_anomaly / combined_degradation） |
| patterns_detected             | string | 检测到的全部模式（\|分隔）                                                                    |
| diagnosis_confidence          | float  | 诊断置信度                                                                                    |
| evidence_voltage_drift        | float  | 电压漂移证据强度                                                                              |
| evidence_thermal_buildup      | float  | 热积聚证据强度                                                                                |
| evidence_power_anomaly        | float  | 功率异常证据强度                                                                              |
| evidence_combined_degradation | float  | 综合退化证据强度                                                                              |

**可视化方案**：

- **异常模式分布环形图**：5 种模式的设备数量占比
- **100 台设备异常热力图**：X=4 种 evidence，Y=100 台设备，颜色深度=证据强度
- **设备详情卡片**：点击某台设备展示 4 条 evidence 柱状图 + 主模式标签

---

### 4.3 维护工单看板 ★（核心最终产出）

**数据文件**：`agent-mcp架构/outputs_test_mcp/output_decision/maintenance_work_orders.csv`（5.6KB）

| 字段             | 类型   | 可视化用途                                                                                                                     |
| ---------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------ |
| priority         | int    | 优先级序号 1-20                                                                                                                |
| machine_id       | string | 设备 ID                                                                                                                        |
| alert_level      | string | ALARM / WARNING / WATCH / NORMAL                                                                                               |
| action_type      | string | 6 种动作类型（immediate_shutdown / preventive_repair / schedule_inspection / increase_monitoring / routine_check / no_action） |
| cost_at_risk     | float  | 日暴露成本 $                                                                                                                   |
| urgency_score    | float  | 紧急度 0-100                                                                                                                   |
| window_days      | int    | 建议执行窗口（天）                                                                                                             |
| expected_savings | float  | 预期成本节约 $                                                                                                                 |
| suggestion       | string | 中文维护建议文本                                                                                                               |

**可视化方案**：

- **工单卡片流**：按 priority 排列，每张卡片含：
  - 优先级徽章（红=1-4紧急 / 橙=5-11 / 黄=12-20）
  - 设备 ID + 动作类型标签
  - urgency_score 进度条
  - cost_at_risk / expected_savings 金额对比（cost vs save）
  - suggestion 摘要（前 80 字）
- **动作类型分布柱状图**：6 种 action_type 的设备计数
- **成本节约汇总卡片**：总 cost_at_risk vs 总 expected_savings 对比数字
- **时间窗口甘特图**：20 台设备 × window_days 的横道图，颜色=action_type

**辅助文件**：`agent-mcp架构/outputs_test_mcp/output_decision/maintenance_decision_report.csv`（25.3KB）
— 100 台设备的完整评估（含 risk_score、所有模式的详细信息），用于工单看板中点击设备弹出详情

---

### 4.4 综合决策报告

**数据文件**：`agent-mcp架构/outputs_test_mcp/output_decision/maintenance_report.txt`（4.5KB）
— 结构化文本报告，包含告警分布、异常模式分布、Top 10 高风险设备、工单摘要

**数据文件**：`agent-mcp架构/outputs_test_mcp/output_decision/decision_summary.json`（1.0KB）
— JSON 格式的统计汇总

| JSON 字段            | 可视化用途               |
| -------------------- | ------------------------ |
| n_machines_evaluated | 总评估设备数             |
| alert_distribution   | 告警等级分布（数字卡片） |
| action_distribution  | 动作类型分布             |
| n_work_orders        | 工单总数                 |
| top_5_urgent         | Top 5 紧急设备列表       |

**可视化方案**：

- **报告摘要卡片**：总设备数 | 告警数 | 工单数 | 总成本风险
- **可导出 PDF 按钮**：将全文渲染为可下载的 PDF 报告

---

## 附录 A：文件清单与引用路径

以下为 Web 前端需要加载的**核心数据文件**（去重后的权威来源）：

### 原始数据（前端直接加载）

```
原始数据集/MACHINE_LOG_DATA._2025.csv                    → Section 1.2
原始数据集/MACHINE_SUMMARY_DATA._2025.csv                 → Section 1.1
原始数据集/PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv   → Section 1（产品质量关联）
原始数据集/PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv → Section 1（测试测量值）
```

### 探索分析输出

```
数据探索分析/per_device_fault_distribution.csv            → Section 1.3
```

### 基线分析输出

```
基线分析和确定/variance_decomposition.csv                 → Section 2.1
基线分析和确定/z_scores.csv                               → Section 2.3
基线分析和确定/cost_risk_matrix.csv                       → Section 2.5
基线分析和确定/failure_signatures.csv                     → Section 2.4
基线分析和确定/hotelling_t2.csv                           → Section 2.3（T² 补充）
基线分析和确定/machine_clusters.csv                       → Section 2.2
```

### 模型构建输出

```
预测性维护模型/model_outputs/evaluation_metrics.csv        → Section 3.1
预测性维护模型/model_outputs/feature_importance_win5.csv   → Section 3.2
预测性维护模型_v2/model_outputs/variant_comparison.csv     → Section 3.1
预测性维护模型_v2/model_outputs/robustness_report.csv      → Section 3.4
```

### 预测性维护建议输出

```
预测性维护模型_v3/outputs/dim1_single_param_discriminability.csv  → Section 4.1
预测性维护模型_v3/outputs/dim2_param_coupling_stability.csv       → Section 4.1
预测性维护模型_v3/outputs/dim3_fault_non_progressive.csv          → Section 4.1
预测性维护模型_v3/outputs/dim4_model_convergence.csv              → Section 4.1
预测性维护模型_v3/outputs/dim5_sensor_gap_analysis.csv            → Section 4.1
agent-mcp架构/outputs_test_mcp/output_diagnosis/diagnosis_report.csv       → Section 4.2
agent-mcp架构/outputs_test_mcp/output_decision/maintenance_work_orders.csv → Section 4.3 ★
agent-mcp架构/outputs_test_mcp/output_decision/maintenance_decision_report.csv → Section 4.3
agent-mcp架构/outputs_test_mcp/output_decision/maintenance_report.txt       → Section 4.4
agent-mcp架构/outputs_test_mcp/output_decision/decision_summary.json        → Section 4.4
```

### 现有可视化图片（直接嵌入或参考）

```
数据探索分析/figures/           → 17 张 PNG（已有 EDA 图表，可直接展示）
基线分析和确定/figures/          →  7 张 PNG（基线分析 6 图）
预测性维护模型/figures/          → 18 张 PNG（模型评估图）
预测性维护模型_v2/figures/       →  5 张 PNG（训练曲线+对比）
```

---

## 附录 B：前端技术栈建议

| 层面     | 推荐方案                                  | 说明                                 |
| -------- | ----------------------------------------- | ------------------------------------ |
| 框架     | React + Vite 或 Vue 3 + Vite              | SPA 单页应用                         |
| 图表库   | ECharts 或 Recharts                       | 支持箱线图、小提琴图、热力图、雷达图 |
| 数据加载 | PapaParse（CSV 解析）                     | 前端直接解析 CSV，无需后端           |
| UI 组件  | Ant Design 或 Tailwind CSS                | 卡片、表格、标签、徽章               |
| 布局     | CSS Grid + Flexbox                        | 响应式仪表盘布局                     |
| 部署     | 纯静态站点（Vercel/Netlify/GitHub Pages） | 所有数据为静态 CSV，无需后端服务器   |

---

## 附录 C：数据加载优先级

按用户最关心的内容排序，建议分三批加载：

**第一批（首屏，< 300KB）**：

1. `per_device_fault_distribution.csv`（4KB）→ 故障概览
2. `variance_decomposition.csv`（0.4KB）→ 方差分解
3. `failure_signatures.csv`（1.9KB）→ 故障签名
4. `evaluation_metrics.csv`（0.6KB）→ 模型对比
5. `variant_comparison.csv`（0.6KB）→ 模型对比
6. `dim1 ~ dim5`（共 2.5KB）→ 传感器瓶颈
7. `maintenance_work_orders.csv`（5.6KB）→ **工单看板** ★
8. `decision_summary.json`（1.0KB）→ 摘要
9. `diagnosis_report.csv`（4.9KB）→ 诊断
10. `cost_risk_matrix.csv`（9.9KB）→ 成本风险

**第二批（按需，< 1MB）**：
11. `MACHINE_SUMMARY_DATA._2025.csv`（6.4KB）→ 设备概览
12. `feature_importance_win5.csv`（3.9KB）→ 特征重要性
13. `robustness_report.csv`（3.6KB）→ 鲁棒性
14. `maintenance_decision_report.csv`（25.3KB）→ 设备详情
15. `machine_clusters.csv`（7.3KB）→ 集群
16. `hotelling_t2.csv`（203KB）→ T² 统计

**第三批（大文件，延迟加载）**：
17. `MACHINE_LOG_DATA._2025.csv`（197KB）→ 时序图（选单台设备时按需加载）
18. `z_scores.csv`（745KB）→ z-score 时序（同上）
19. `Unified_Machine_WideTable_2025.csv`（247KB）→ 宽表（高级分析用）
