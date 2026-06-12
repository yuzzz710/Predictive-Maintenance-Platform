# 智能设备预测性维护 — Agent-MCP 系统架构说明

> **项目**：苗圃杯·智能设备预测性维护  
> **赛题要求**：结合制造业产线维护测试日志、监控参数及设备成本要素，甄别未来可能存在异常的设备，提出预测性维护建议  
> **目标**：交付完整的设备预测性维护建议报告 + 预测性维护告警模型 + 可行的预测性维护建议

---

## 概述

本系统将 100 台 CNC 加工设备的原始监测数据（4 项参数：电压、电流、温度、转子转速），通过 **5 个推理技能** 转化为 **按优先级排序、有成本依据的维护工单**。

5 个技能通过 Model Context Protocol 协议封装为 7 个 MCP Tool，使 Claude 能够**自主规划调用顺序、动态编排推理流水线**。

```
用户: "分析这个工厂数据"
  → Claude 推理 → 调 prepare_data → 并行调 stat + ml → diagnosis → generate_decision
  → 输出: 20 张优先级维护工单 + 风险报告
```

---

## 1. 项目全景

### 1.1 赛题要求与技术路线

| 赛题要求 | 本项目实现 |
|---|---|
| **数据整合探索** | 数据探索分析目录：14 项统计分析 + 17 组可视化 |
| **基线分析和确定** | 4 个统计基线（z-score、成本风险矩阵、故障类型签名、Hotelling T²） |
| **预测性维护告警模型** | v1 XGBoost 双阶段 + v2 Multi-Task Neural Network（3 变体）|
| **测试和验证** | Youden's J 评估、5 维度可预测性根因分析、鲁棒性测试 |
| **预测性维护计划（附加）** | v3 决策引擎：4 层融合架构 → 6 种动作类型 → 优先级工单 + 成本节约估算 |

### 1.2 项目四阶段

```
数据探索分析 ──→ 基线分析和确定 ──→ 预测性维护模型(v1/v2) ──→ 预测性维护模型_v3
(14项分析)      (4个统计基线)        (XGBoost + MTNN)          (决策引擎 + 系统方案)
     │                │                      │                        │
     ▼                ▼                      ▼                        ▼
 数据理解         告警基线                ML实验验证              风险驱动决策
 方差分解         z-score 基线           v1 AUC≈0.50             4层: 融合→诊断
 参数独立性       cost-risk 矩阵          v2 AUC≈0.59              →决策→工单
 阈值识别         T² SPC控制             均达到理论上限
```

**核心发现贯穿四阶段：** 4 个监测参数信息量不足以支撑纯 ML 预测性维护（Youden's J max = 0.075）。所有 ML 模型（XGBoost、MTNN）均收敛到平凡预测器。因此系统采用 **成本风险驱动 + 统计基线融合** 的务实路线。

### 1.3 项目文件树

```
苗圃杯/git3/
│
├── 题目.txt                                 # 赛题说明
├── ARCHITECTURE.md                          # ★ 本文档
│
├── 原始数据集/                              # 4 个原始 CSV
│   ├── MACHINE_LOG_DATA._2025.csv           #   设备监控日志（2999行 × 100台）
│   ├── MACHINE_SUMMARY_DATA._2025.csv       #   设备元数据（100台，含成本/产量）
│   ├── PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv  # 产品组装测试
│   └── PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv  # 产品测试测量值
│
├── 数据探索分析/                            # 阶段一：14项统计分析
│   ├── figure_documentation_master.md       #   完整分析报告
│   ├── machine_failure_analysis（2、3、4）.py
│   ├── advanced_failure_analysis(5-14).py
│   └── figure*.png/pdf                      #   17 组可视化
│
├── 基线分析和确定/                          # 阶段二：4个统计基线
│   ├── BASELINE_DEVELOPMENT_DOC.md          #   基线开发文档
│   ├── baseline_analysis.py                 #   核心代码
│   └── figures_nature.py                    #   Nature 风格 6 图
│
├── 预测性维护模型/                          # 阶段三 v1：XGBoost 双阶段
│   ├── model_development_doc.md
│   ├── model_training.py
│   ├── model_outputs/
│   └── figures/
│
├── 预测性维护模型_v2/                       # 阶段三 v2：Multi-Task NN
│   ├── model_development_doc_v2.md
│   ├── model_training_v2.py
│   ├── model_outputs/
│   └── figures/
│
├── 预测性维护模型_v3/                       # 阶段四：系统方案 + 决策引擎
│   ├── predictive_maintenance_system_design.md  # 系统级方案设计文档
│   ├── maintenance_decision_engine.py           # 4层决策引擎
│   ├── predictability_analysis.py               # 5维度可预测性分析
│   └── outputs/
│       ├── dim1_single_param_discriminability.csv
│       ├── dim2_param_coupling_stability.csv
│       ├── dim3_fault_non_progressive.csv
│       ├── dim4_model_convergence.csv
│       ├── dim5_sensor_gap_analysis.csv
│       ├── maintenance_work_orders.csv
│       ├── maintenance_decision_report.csv
│       └── predictability_limitation_summary.txt
│
└── skills/                                  # ★ MCP Agent 工作目录
    ├── mcp_server.py                        # ★ MCP Server 主程序（7 个 Tool）
    ├── agent_orchestrator.py                # ★ 编排器（固定 DAG）
    ├── mcp-adapter-guide.md                 # MCP 适配开发指南
    ├── predictive-maintenance-skill-system-v2.md  # 技能系统指南
    │
    ├── predictive-maintenance-data-prep/    # Skill 1: 数据准备
    │   ├── SKILL.md
    │   └── scripts/baseline_analysis.py, run.py
    │
    ├── predictive-maintenance-stat-inference/  # Skill 2: 统计推理
    │   ├── SKILL.md
    │   └── scripts/baseline_analysis.py, run.py
    │
    ├── predictive-maintenance-ml-inference/    # Skill 3: ML 推理
    │   ├── SKILL.md
    │   └── scripts/model_training.py, model_training_v2.py, run.py
    │
    ├── predictive-maintenance-diagnosis/       # Skill 4: 异常诊断
    │   ├── SKILL.md
    │   └── scripts/maintenance_decision_engine.py, predictability_analysis.py, run.py
    │
    └── predictive-maintenance-decision/        # Skill 5: 决策引擎
        ├── SKILL.md
        └── scripts/maintenance_decision_engine.py, run.py
```

---

## 2. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                     Claude Desktop / Code                         │
│                                                                  │
│  用户: "分析这个工厂数据，生成维护工单"                               │
│       ↓                                                          │
│  Claude 自主推理:                                                  │
│    1. explain_predictability_limit()     → 了解传感器极限          │
│    2. prepare_data(data_dir)             → 数据准备               │
│    3. run_stat_analysis() + run_ml_analysis()  → 并行推理        │
│    4. run_diagnosis()                    → 异常模式诊断            │
│    5. generate_decision()                → 生成维护工单            │
│       ↓                                                          │
│  "CNC_085 电压漂移，紧急维修，日暴露成本 $6,441"                     │
└────────────────────────┬─────────────────────────────────────────┘
                         │  MCP Protocol (stdio, JSON-RPC)
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                     mcp_server.py                                 │
│                  FastMCP("predictive-maintenance")                │
│                                                                  │
│  ┌─────────────────── 7 个 MCP Tool ──────────────────────────┐  │
│  │                                                             │  │
│  │  explain_predictability_limit()  → 只读 v3/outputs 静态数据  │  │
│  │  prepare_data()        → subprocess → Skill 1 run.py        │  │
│  │  run_stat_analysis()   → subprocess → Skill 2 run.py        │  │
│  │  run_ml_analysis()     → subprocess → Skill 3 run.py        │  │
│  │  run_diagnosis()       → subprocess → Skill 4 run.py        │  │
│  │  generate_decision()   → subprocess → Skill 5 run.py        │  │
│  │  run_predictive_maintenance() → import → agent_orchestrator │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                    │
│       两种执行路径:                                                 │
│       ① 独立 Tool: subprocess → 各 Skill CLI 入口 (scripts/run.py) │
│       ② 全流程 Tool: Python import → 编排器 DAG                    │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│              agent_orchestrator.py                                │
│           PredictiveMaintenanceAgent                              │
│                                                                  │
│  固定 DAG:                                                        │
│  data_prep ──┬── stat_inference ──┬── diagnosis ── decision      │
│              └── ml_inference  ───┘                               │
│                                                                  │
│  特性: 输入4 CSV校验 → ThreadPool并行 → ML不可用降级 → 工单计数    │
└────────────────────────┬─────────────────────────────────────────┘
                         │  subprocess
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                  5 个 Skill（独立 Python 脚本）                     │
│                                                                  │
│  Skill 1: data-prep      产出: z_scores.csv, cost_risk_matrix    │
│  Skill 2: stat-inference 产出: alert_summary.csv, t2_results     │
│  Skill 3: ml-inference   产出: prediction_report.csv             │
│  Skill 4: diagnosis      产出: diagnosis_report.csv              │
│  Skill 5: decision       产出: maintenance_work_orders.csv ★     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 5 个 Skill 详解

### 3.1 Skill 1: data-prep（数据准备）

**赛题对应：** 数据整合探索 + 基线分析

```
输入: 4 个原始 CSV 文件
处理:
  - 加载 2999 条记录 × 100 台设备
  - 逐设备从正常样本计算 μ, σ（设备间方差占 61-73%，否决全局基线）
  - 计算逐设备 z-score（Voltage + Amperage + Temperature 欧几里得组合）
  - 构建成本风险矩阵：Risk = P(failure) × Unit Cost × Daily Output
  - 分析故障类型签名（3 组 × 9 类型）
  - Hotelling T² 多变量 SPC
  - K-Means 设备聚类（K=3，冷启动用）
输出: 10 个文件（z_scores, cost_risk_matrix, baseline_stats, failure_signatures 等）
```

### 3.2 Skill 2: stat-inference（统计推理）

**赛题对应：** 基线分析和确定

```
输入: data-prep 输出目录 + 原始数据
处理:
  - 评估 z-score 基线性能（P=84%, FPR=20% @ z>2.0）
  - 计算 Hotelling T² 统计量 + 卡方控制限 (α=0.01)
  - 分析故障类型参数签名（高电压型/热型/微弱型）
  - 汇总 100 台设备告警状态（NORMAL/WATCH/WARNING/ALARM）
输出: alert_summary.csv, t2_results.csv, failure_signature_analysis.csv
```

### 3.3 Skill 3: ml-inference（ML 推理）

**赛题对应：** 预测性维护告警模型设计

```
输入: data-prep 输出目录 + 原始数据
处理:
  v1 (XGBoost):
    - 双阶段预测: 14min + 28min 滑动窗口
    - 35 维特征（时序统计 + 设备静态 + 产品质量 + 当前状态）
    - 成本敏感训练 (sample_weight × cost × output)
    - AUC≈0.50, R²≈0 — 达到 4 参数信息理论上限
  v2 (MTNN):
    - 共享表征 + 双任务头（故障密度回归 + 质量预测回归）
    - 106 维特征（趋势/波动/状态/成本 四维体系）
    - 数据增强（噪声+掩码+Dropout）+ 设备级交叉验证
    - AUC≈0.59, R²≈0.02 — 接近理论边界，但不可工业部署
输出: prediction_report.csv, evaluation_metrics.csv
```

### 3.4 Skill 4: diagnosis（异常诊断）

**赛题对应：** 预测性维护建议（附加）

```
输入: stat + ml 输出（ml 可选）
处理:
  - 4 种异常模式识别:
      voltage_drift（PSU 退化）| thermal_buildup（冷却/轴承）
      power_anomaly（负载/绕组）| combined_degradation（系统性劣化）
  - 5 维度可预测性分析（可选跳过，提速）:
      D1 单参数判别力 | D2 参数耦合稳定性 | D3 故障非渐进性
      D4 模型收敛证据 | D5 传感器信息缺口
输出: diagnosis_report.csv
```

### 3.5 Skill 5: decision（决策引擎）★ 最终产出

**赛题对应：** 预测性维护计划

```
输入: data-prep + stat + ml(可选) + diagnosis(可选)
处理:
  Layer 1 — 输入融合:  stat_anomaly(0.40) + ml_density(0.25) + cost_risk(0.25) + trend(0.10)
  Layer 2 — 诊断:      4 种异常模式匹配 → 证据强度计算
  Layer 3 — 决策:      6 种动作类型 (immediate_shutdown → no_action)
  Layer 4 — 输出:      优先级排序 + 成本节约估算
输出:
  ★ maintenance_work_orders.csv（最终产物）
     maintenance_decision_report.csv
     maintenance_report.txt
     decision_summary.json
```

**6 种动作类型：**

| 动作 | 触发条件 | 时间窗口 | 示例 |
|---|---|---|---|
| immediate_shutdown | z_max ≥ 10.0 | 立即 | 停机检查 |
| preventive_repair | ALARM + 高成本风险 | 1-3 天 | 安排维修 |
| schedule_inspection | ALARM 标准 或 WARNING+模式 | 3-7 天 | 计划检查 |
| increase_monitoring | WARNING 无模式 | 7-14 天 | 加密监控 |
| routine_check | WATCH | 30 天 | 常规巡检 |
| no_action | NORMAL | 30 天 | 不操作 |

---

## 4. Skill 改编为 MCP Tool 的方法

### 4.1 改编三步法

每个 Skill 原本是独立 CLI 脚本：

```bash
python scripts/run.py --data-dir <raw> --prep-dir <prep> --output-dir <out>
```

改编为 MCP Tool：

| 步骤 | 代码 | 说明 |
|---|---|---|
| 1 | `@mcp.tool()` + docstring | 装饰器即注册，docstring 即 Tool description |
| 2 | 构建 args 列表 | 函数参数 → CLI 参数字符串 |
| 3 | `_run_script()` 调用 | subprocess 执行 Skill 的 run.py |

### 4.2 统一执行器

所有 5 个 Skill Tool 共用同一个 helper（`skills/mcp_server.py:189`）：

```python
def _run_script(skill_dir_name: str, args: list) -> dict:
    script = SKILLS_BASE / skill_dir_name / "scripts" / "run.py"
    cmd = [sys.executable, str(script)] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return {
        "success": proc.returncode == 0,
        "duration_seconds": duration,
        "stdout_tail": ...,
        "stderr_tail": ...,
    }
```

### 4.3 改编前后对比

```
改编前（Skill CLI — Workflow 模式）:
  $ cd skills/predictive-maintenance-stat-inference
  $ python scripts/run.py --data-dir /raw --prep-dir /prep --output-dir /out

改编后（MCP Tool — Agent 模式）:
  Claude 自主决定何时调用:
  run_stat_analysis(data_dir="/raw", prep_dir="/prep", output_dir="/out")
       ↓
  _run_script("predictive-maintenance-stat-inference", ["--data-dir", ...])
       ↓
  subprocess: python scripts/run.py --data-dir /raw --prep-dir /prep ...
       ↓
  返回结构化 JSON: {status, output_dir, alert_summary_preview, duration, ...}
```

### 4.4 设计决策

**为什么 Skill Tool 用 subprocess 而非 Python import？**
- 每个 Skill 有独立依赖（v1 用 xgboost，v2 用 torch）
- subprocess 隔离避免依赖冲突
- 独立超时控制（每个 600s）

**为什么全流程 Tool 用 Python import？**
- 编排器是纯 Python 逻辑，无特殊依赖
- 直接 import 更快，可访问完整 `PipelineResult` 数据结构

---

## 5. MCP 接口完整规范

### 5.0 `explain_predictability_limit` — 可预测性限制说明

```
位置: skills/mcp_server.py:43
类型: 纯读取（不运行任何 Skill）
数据源: 预测性维护模型_v3/outputs/ 下 5 个 CSV
```

此 Tool 回答：「当前传感器能支撑什么水平的预测性维护？为什么？该装什么新传感器？」

**无参数，直接返回** 5 维度分析 + 5 条根因 + 6 种传感器升级建议。

**返回值结构（关键字段）：**

```json
{
  "conclusion": "4 monitoring parameters DO NOT support effective predictive maintenance.",
  "performance_ceiling": 0.60,
  "current_max_youden_j": 0.0749,
  "youden_j": {
    "Voltage": {"youden_j": 0.075, "cohens_d": 0.11},
    "Rotor Speed": {"youden_j": 0.022, "cohens_d": 0.00}
  },
  "fault_overlap": {
    "Voltage": {"fault_in_normal_pct": 96.3}
  },
  "correlation_stability": {
    "V-A": {"normal_corr": -0.01, "fault_corr": 0.09, "significant_change": true}
  },
  "non_progressive_onset": {
    "Voltage": {"pre_fault_in_normal_pct": 79.2}
  },
  "model_convergence": [
    {"variant": "10in_5pred", "r2": 0.02, "auc": 0.59, "is_mean_predictor": true}
  ],
  "root_causes": [
    {"id": "R1", "cause": "insufficient_sensor_discriminability", "severity": "critical",
     "fix": "Add vibration and acoustic emission sensors"}
  ],
  "recommended_new_sensors": [
    {"sensor": "Vibration (accelerometer)", "expected_youden_j": "0.40-0.70", "cost": "$200-500"}
  ],
  "what_works_today": {
    "approach": "cost-risk-driven maintenance (statistical baseline)",
    "detection_rate": "P=84%, FPR=20% (z-score with threshold 2.0)"
  }
}
```

---

### 5.1 `prepare_data` — 数据准备

```
位置: skills/mcp_server.py:242
底层: subprocess → Skill 1
```

| 参数 | 类型 | 必填 | 默认值 |
|---|---|---|---|
| `data_dir` | str | 是 | — |
| `output_dir` | str | 否 | `./outputs/output_data_prep` |

**返回：** `{tool, status, output_dir, duration_seconds, summary: {report, z_scores_preview, cost_risk_preview, output_files}, next_step}`

---

### 5.2 `run_stat_analysis` — 统计推理

```
位置: skills/mcp_server.py:281
依赖: prepare_data 完成后调用
可并行: 与 run_ml_analysis 同时
```

| 参数 | 类型 | 必填 | 默认值 |
|---|---|---|---|
| `data_dir` | str | 是 | — |
| `prep_dir` | str | 是 | — |
| `output_dir` | str | 否 | `./outputs/output_stat_inference` |

---

### 5.3 `run_ml_analysis` — ML 推理

```
位置: skills/mcp_server.py:323
依赖: prepare_data 完成后调用
可并行: 与 run_stat_analysis 同时
```

| 参数 | 类型 | 必填 | 默认值 |
|---|---|---|---|
| `data_dir` | str | 是 | — |
| `prep_dir` | str | 是 | — |
| `output_dir` | str | 否 | `./outputs/output_ml_inference` |
| `model` | str | 否 | `"v1"` (v1=XGBoost, v2=PyTorch MTNN) |

---

### 5.4 `run_diagnosis` — 异常诊断

```
位置: skills/mcp_server.py:368
依赖: stat + ml 都完成后调用
```

| 参数 | 类型 | 必填 | 默认值 |
|---|---|---|---|
| `data_dir` | str | 是 | — |
| `prep_dir` | str | 是 | — |
| `stat_dir` | str | 是 | — |
| `ml_dir` | str\|null | 否 | `null` |
| `output_dir` | str | 否 | `./outputs/output_diagnosis` |
| `skip_predictability` | bool | 否 | `true` |

---

### 5.5 `generate_decision` — 工单生成 ★

```
位置: skills/mcp_server.py:418
依赖: 前序步骤全部完成后调用
```

| 参数 | 类型 | 必填 | 默认值 |
|---|---|---|---|
| `data_dir` | str | 是 | — |
| `prep_dir` | str | 是 | — |
| `stat_dir` | str | 是 | — |
| `ml_dir` | str\|null | 否 | `null` |
| `diag_dir` | str\|null | 否 | `null` |
| `output_dir` | str | 否 | `./outputs/output_decision` |
| `streaming` | bool | 否 | `false` |
| `max_orders` | int | 否 | `20` |

**返回：** `{tool, status, output_dir, duration_seconds, work_orders_count, work_orders: [...], report: "..."}`

---

### 5.6 `run_predictive_maintenance` — 一键全流程

```
位置: skills/mcp_server.py:477
底层: Python import → agent_orchestrator.PredictiveMaintenanceAgent
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `data_dir` | str | 是 | — | |
| `output_dir` | str | 否 | `"./outputs"` | |
| `skip_ml` | bool | 否 | `false` | 跳过 ML（降级到 stat-only） |
| `skip_diagnosis` | bool | 否 | `false` | |
| `model` | str | 否 | `"v1"` | |
| `streaming` | bool | 否 | `false` | |
| `max_orders` | int | 否 | `20` | |

**返回：** `{status: {...}, work_orders_count, work_orders_preview, output_dir, step_statuses, total_duration_seconds}`

---

## 6. 数据流

```
原始数据集 (4 CSV)
      │
      ▼
┌─────────────┐
│ prepare_data │──── z_scores.csv ────┐
│   (Skill 1)  │──── cost_risk.csv ───┤
└─────────────┘                       │
                                      ▼
               ┌─────────────────────────────────────┐
               │        Phase 2 (并行)                │
               │  run_stat_analysis (Skill 2)         │
               │  → alert_summary.csv, t2_results     │
               │                                     │
               │  run_ml_analysis (Skill 3)           │
               │  → prediction_report.csv             │
               └──────────────┬──────────────────────┘
                              │
                              ▼
                    ┌──────────────┐
                    │ run_diagnosis │
                    │   (Skill 4)   │
                    → diagnosis_report.csv
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   generate   │
                    │   _decision  │
                    │   (Skill 5)  │
                    └──────┬───────┘
                           │
                           ▼
             ★ maintenance_work_orders.csv
               maintenance_report.txt
               maintenance_decision_report.csv
```

---

## 7. 两种 Tool 执行路径对比

| | 独立 Tool（6 个） | 一键全流程 Tool（1 个） |
|---|---|---|
| 执行方式 | subprocess 调各 Skill 的 run.py | Python import 调 orchestrator |
| 编排者 | **Claude（动态推理）** | agent_orchestrator（固定 DAG） |
| 灵活性 | 可跳过、重试、替换任意步骤 | 固定顺序，仅可 skip_ml/skip_diag |
| 并行控制 | Claude 自主决定哪些并行 | ThreadPoolExecutor 硬编码 |
| 降级逻辑 | Claude 根据返回的 status 自主判断 | orchestrator 内置 try/except |
| 适用场景 | 需要理解每一步输出 | 快速跑通全流程 |

**两种路径可混用：** Claude 先调 `explain_predictability_limit` 了解传感器瓶颈，再决定走精细控制还是一键全流程。

---

## 8. MCP 注册配置

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "predictive-maintenance": {
      "command": "python",
      "args": [
        "C:/Users/yuzzz/Desktop/苗圃杯/git3/skills/mcp_server.py"
      ]
    }
  }
}
```

### 验证

```bash
cd skills
python -c "from mcp_server import explain_predictability_limit; print(explain_predictability_limit()['conclusion'])"
```

---

## 9. Workflow → Agent 的转变

```
┌─ Workflow 模式 ───────────────────────────────────┐
│                                                   │
│  用户: python agent_orchestrator.py               │
│         --data-dir ... --skip-ml --skip-diagnosis │
│                                                   │
│  参数由人决定，路径固定，无法动态调整                    │
└───────────────────────────────────────────────────┘

┌─ Agent 模式 ──────────────────────────────────────────────────┐
│                                                               │
│  用户: "分析这个工厂数据，给出维护建议"                           │
│                                                               │
│  Claude 推理过程:                                              │
│    "先看看当前传感器能做什么"                                    │
│    → explain_predictability_limit()                           │
│    "Youden J 才 0.075，ML 信号弱，但统计基线可用"                │
│    → prepare_data()                                           │
│    → run_stat_analysis() + run_ml_analysis() 并行             │
│    "stats 和 ML 都有了，诊断异常模式"                           │
│    → run_diagnosis()                                          │
│    "融合所有信号，生成工单"                                     │
│    → generate_decision()                                      │
│                                                               │
│  Claude 输出:                                                  │
│    "基于 4 参数系统，产出 20 张维护工单。                        │
│     Top 3 高风险: CNC_085 ($6,441/天), CNC_034, CNC_087。      │
│     当前传感器不足以支撑纯 ML 预测（Youden J=0.075），            │
│     建议优先安装振动传感器（$200-500/台，预期提升到 0.40+）。"     │
│                                                               │
│  每一步由 Claude 根据上下文和返回值自主决定                        │
└───────────────────────────────────────────────────────────────┘
```

---

## 10. 文件功能总表

| 文件 | 类型 | 作用 |
|---|---|---|
| `skills/mcp_server.py` | MCP Server | 7 个 Tool 定义 + FastMCP 入口 |
| `skills/agent_orchestrator.py` | 编排器 | 固定 DAG 调度 + 降级 + 工单计数 |
| `skills/mcp-adapter-guide.md` | 文档 | MCP 适配开发指南（含 Resource/Prompt 方案） |
| `skills/predictive-maintenance-skill-system-v2.md` | 文档 | 技能系统开发与使用指南 |
| `skills/predictive-maintenance-*/SKILL.md` | 文档 | 各 Skill 说明 |
| `skills/predictive-maintenance-*/scripts/run.py` | CLI 入口 | 各 Skill 独立运行脚本 |
| `skills/predictive-maintenance-*/scripts/*.py` | 核心代码 | baseline_analysis, model_training, decision_engine 等 |
| `基线分析和确定/BASELINE_DEVELOPMENT_DOC.md` | 文档 | 基线分析：4 基线 + 6 图 + 参数配置 |
| `预测性维护模型/model_development_doc.md` | 文档 | v1 XGBoost 双阶段模型 |
| `预测性维护模型_v2/model_development_doc_v2.md` | 文档 | v2 Multi-Task NN（3 变体） |
| `预测性维护模型_v3/predictive_maintenance_system_design.md` | 文档 | 系统级方案设计 |
| `预测性维护模型_v3/outputs/` | 数据 | 决策引擎输出 + 5 维度分析静态数据 |
| `数据探索分析/figure_documentation_master.md` | 文档 | 14 项统计分析报告 |
| `原始数据集/` | 数据 | 4 个原始 CSV |
