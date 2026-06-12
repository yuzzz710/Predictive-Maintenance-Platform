# 智能设备预测性维护 — 基线分析与确定：开发文档

> **项目**：苗圃杯·智能设备预测性维护  
> **阶段**：基线分析与确定（Baseline Analysis & Determination）  
> **日期**：2026-05-16  
> **数据**：出题单位提供的脱敏 Excel 数据（4 个 CSV 文件）  

---

## 1. 项目结构

```
原始数据集/
├── MACHINE_LOG_DATA._2025.csv                          # 设备监控日志（2999行 × 100台设备）
├── MACHINE_SUMMARY_DATA._2025.csv                      # 设备元数据（100台，含成本/产量）
├── PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv         # 产品组装测试（135行 × 15台设备）
├── PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv   # 产品测试测量值（420行）
├── baseline_analysis.py                                # [代码] 基线分析主程序
├── figures.py                                          # [代码] 初始7图可视化
├── figures_nature.py                                   # [代码] Nature风格精修6图（SVG+PDF+TIFF）
├── baseline_outputs/                                   # [输出] 所有中间数据和图表
│   ├── z_scores.csv                                    #   逐设备z-score计算结果
│   ├── cost_risk_matrix.csv                            #   成本风险矩阵
│   ├── failure_signatures.csv                          #   故障类型参数签名
│   ├── variance_decomposition.csv                      #   方差分解
│   ├── hotelling_t2.csv                                #   Hotelling T2统计量
│   ├── machine_clusters.csv                            #   设备聚类结果
│   ├── summary_report.txt                              #   文本报告
│   ├── figA_variance_decomposition.{svg,pdf,tiff}      #   图A：方差分解
│   ├── figB_threshold_performance.{svg,pdf,tiff}       #   图B：阈值性能曲线
│   ├── figC_zscore_distributions.{svg,pdf,tiff}        #   图C：z-score分布对比
│   ├── figD_clusters_signatures.{svg,pdf,tiff}         #   图D：聚类+故障签名（双面板）
│   ├── figE_cost_risk_bubble.{svg,pdf,tiff}            #   图E：成本风险气泡图
│   └── figF_machine_baseline_ranges.{svg,pdf,tiff}     #   图F：逐设备正常电压范围
└── BASELINE_DEVELOPMENT_DOC.md                         # [本文档]
```

---

## 2. 技术栈与依赖

### 2.1 编程语言与版本

| 项目 | 版本 |
|------|------|
| Python | 3.12+ |
| pandas | 2.x |
| numpy | 1.26+ |
| scipy | 1.12+ |
| scikit-learn | 1.4+ |
| matplotlib | 3.8+ |
| seaborn | 0.13+ |

### 2.2 库用途说明

| 库 | 用途 | 在代码中的位置 |
|----|------|---------------|
| `pandas` | 数据加载、清洗、分组聚合、合并连接 | `baseline_analysis.py` 全篇 |
| `numpy` | 数值计算、z-score、sqrt、linalg | `baseline_analysis.py` §2-6 |
| `scipy.stats` | 卡方分布临界值（Hotelling T2）、统计检验 | `baseline_analysis.py` §5 |
| `scipy.spatial.distance.mahalanobis` | 马氏距离（备选方案） | `baseline_analysis.py` §5 |
| `sklearn.cluster.KMeans` | 设备工况聚类（K=3） | `baseline_analysis.py` §6 |
| `sklearn.preprocessing.StandardScaler` | 聚类前标准化 | `baseline_analysis.py` §6 |
| `matplotlib` | 全部图表的底层绘制 | `figures_nature.py` 全篇 |
| `seaborn` | 样式辅助（`sns.despine()`） | `figures_nature.py` |

### 2.3 环境配置

```bash
pip install pandas numpy scipy scikit-learn matplotlib seaborn
```

---

## 3. 基线模型设计

### 3.1 基线模型总览

本项目的"基线"定义为：**在没有任何时序建模或机器学习的情况下，仅依赖统计分布和业务规则的最低可行告警模型**。任何后续 ML 模型的性能必须超越此基线才有工程价值。

共设计 **4 个基线模型**，分两个层级：

| 层级 | 基线 | 类型 | 优先级 |
|------|------|------|--------|
| 一级（必须） | 基线 1：逐设备复合 Z-Score 统计基线 | 统计异常检测 | P0 |
| 一级（必须） | 基线 2：成本加权风险矩阵 | 业务规则排序 | P0 |
| 二级（建议） | 基线 3：故障类型分层阈值 | 领域知识增强 | P1 |
| 二级（建议） | 基线 4：Hotelling T² 多变量 SPC | 多元统计过程控制 | P1 |

---

### 3.2 基线 1：逐设备复合 Z-Score 统计基线（P0）

#### 3.2.1 模型原理

对每台设备，从其历史正常（Failure.Equipment.Type = 0）样本中学习各参数的均值 μ 和标准差 σ，然后将任意观测 x 转换为 z-score：`z = |x - μ| / σ`。

复合 z-score 定义为三个监控参数的欧几里得组合：

```
z_composite = sqrt( z_Voltage² + z_Amperage² + z_Temperature² )
```

**为什么逐设备？** 方差分解证明设备间差异占 61-73%（见图 A）。若用全局均值，CNC_001（正常 289V）会被误判为高压故障，CNC_004（正常 156V）的故障会被漏报。

**为什么欧几里得组合而非加权？** 三个参数在全局和正常状态下几乎完全独立（|r| < 0.1），因此独立 z-score 的欧几里得组合等价于假设各向同性协方差矩阵的马氏距离。

#### 3.2.2 参数配置

```python
CONFIG = {
    "z_thresholds": {
        "watch": 1.5,    # 关注级（黄色）
        "warning": 2.0,  # 警告级（橙色）
        "alarm": 2.5,    # 告警级（红色）
    },
    "min_normal_samples": 6,   # 少于6条正常样本的设备用族群基线
    "params": ["Op.Voltage", "Op.Amperage", "Op.Temperature"],
    "excluded_params": ["Rotor Speed"],  # 已被验证无诊断价值
}
```

#### 3.2.3 阈值选择依据

| 阈值 | 精确率 | 召回率 | F1 | FPR | 使用场景 |
|------|--------|--------|-----|-----|---------|
| z > 1.0 | 73.5% | 85.6% | 79.0% | 80.5% | 最佳 F1（但 FPR 过高） |
| z > 1.5 | 76.0% | 62.2% | 68.4% | 51.2% | 初步筛查（Watch） |
| **z > 2.0** | **83.9%** | **39.4%** | **53.6%** | **19.7%** | **运维派单（Warning）** |
| z > 2.5 | 92.1% | 21.9% | 35.4% | 4.9% | 紧急干预（Alarm） |
| z > 3.0 | 97.5% | 12.8% | 22.6% | 0.8% | 高置信自动停机 |

最佳 F1 在 z > 1.0，但 FPR=80.5% 对运维不可接受。**推荐操作点：z > 2.0**（精确率 83.9%，FPR 19.7%，即每 5 次告警约 4 次正确）。

#### 3.2.4 稀疏数据冷启动策略

10 台设备仅有 3-5 条正常样本，μ 和 σ 的估计不稳定。应对策略：
- 将设备按正常工况聚类为 3 个族群（K-Means, K=3）
- 稀疏设备使用所属族群的 μ 和 σ 作为初始基线
- 随着正常样本积累（≥6 条），切换回自基线

---

### 3.3 基线 2：成本加权风险矩阵（P0）

#### 3.3.1 模型原理

```
Risk Score = P(failure) × Unit Cost × Daily Output
```

其中 `P(failure)` 为设备历史故障率（Type > 0 的比例）。

#### 3.3.2 参数配置

```python
CONFIG = {
    "cost_risk": {
        "high": 5300,    # ≥ P90 分位数 → 高风险
        "medium": 4500,  # ≥ P75 分位数 → 中风险
    },
}
```

阈值基于 100 台设备的 cost_at_risk 分布自适应确定（P75 和 P90）。

#### 3.3.3 关键发现

- **CNC_095**：单位成本 114（全局最高），虽故障率仅 67%，每次故障经济损失极高
- **CNC_036**：单位成本 32，故障率 83%，综合风险排名前 5
- **CNC_085**：成本仅 4 但日产量 1,858 + 故障率 87%，因产量大而成为 volume-driven risk

---

### 3.4 基线 3：故障类型分层阈值（P1）

#### 3.4.1 模型原理

将 9 种故障类型按参数偏差签名分为 3 组：

| 故障组 | 包含类型 | 电压偏移 | 温度偏移 | 特征 |
|--------|---------|---------|---------|------|
| High-Voltage | Type 4, 5 | +10.7V | +1.2°C | 电压主导 |
| Thermal | Type 3, 6, 7, 8, 9 | +5.6V | +1.5°C | 温度主导 |
| Subtle | Type 1, 2 | +1.8V | ±0.1°C | 极微弱 |

对每组使用不同参数权重：

```python
CONFIG = {
    "failure_groups": {
        "High-Voltage": [4, 5],    # z权重: V=0.7, T=0.2, A=0.1
        "Thermal": [3, 6, 7, 8, 9], # z权重: V=0.3, T=0.6, A=0.1
        "Subtle": [1, 2],          # z权重: V=0.4, T=0.3, A=0.3
    },
}
```

---

### 3.5 基线 4：Hotelling T² 多变量 SPC（P1）

#### 3.5.1 模型原理

Hotelling T² 统计量是多变量统计过程控制（MSPC）的标准方法：

```
T² = (x - μ)' Σ⁻¹ (x - μ)
```

其中 x 是观测向量 [Voltage, Amperage, Temperature]，μ 是设备正常状态的均值向量，Σ 是协方差矩阵。

控制限：T² > χ²(p, α)，其中 p=3（参数个数），α=0.01。

#### 3.5.2 参数配置

```python
CONFIG = {
    "t2_alpha": 0.01,  # 显著性水平（99%置信）
}
```

#### 3.5.3 性能

- 精确率：100%（无误报）  
- 召回率：22.0%（仅检出最强偏差的故障）
- F1：36.1%

T² 作为补充验证——当 T² + z-score 同时告警时置信度极高。

---

## 4. 基线分析流程（How Baseline Analysis Was Conducted）

### 4.1 分析管线

```
数据加载 → 数据探索 → 方差分解 → 逐设备基线构建 → z-score计算 → 阈值评估
                ↓                           ↓
         成本风险矩阵               Hotelling T² 计算
                ↓                           ↓
         故障类型签名分析 ← → 设备聚类 → 产品质量关联
                ↓
         基线报告 + 可视化输出
```

### 4.2 关键决策点

1. **全局基线 vs 逐设备基线**：方差分解确认设备间方差占 61-73%，否决全局基线方案
2. **参数选择**：Rotor Speed 在正常/故障间无显著差异（-0.05%, KS p=0.46），排除
3. **正常样本阈值**：≥6 条设为自己的基线；<6 条使用族群基线（10 台设备）
4. **阈值选择**：z > 2.0 为运维推荐阈值，平衡精确率（83.9%）和 FPR（19.7%）
5. **成本整合**：风险排序不是单维度故障率，而是故障率 × 成本 × 产量的三维乘积

### 4.3 基线局限（记录在案，供后续建模参考）

| 局限 | 影响 | 后续方向 |
|------|------|---------|
| 静态基线无时序信息 | 无法捕捉参数漂移趋势 | 滑动窗口 + 时序模型（LSTM/Transformer） |
| 正常样本仅 3-15 条/台 | 基线估计方差大 | 贝叶斯分层模型（pool strength across machines） |
| 7 小时窗口无长期退化 | 无法建立寿命曲线 | 引入维修记录时间维度和设备服役年龄 |
| 4 参数与产品质量弱相关（r=0.075） | 仅靠监控参数无法预测产品缺陷 | 引入产品测试特征作为多任务学习目标 |
| 未建模故障类型间关系 | 无法区分"哪种故障即将发生" | 多分类模型 + 故障类型概率输出 |
| 无外部因素（批次、操作员、环境） | 可能遗漏系统性偏差来源 | 引入 LINE、WRKSTN_NM 作为随机效应 |

---

## 5. 图表说明

### 图 A：方差分解

- **展示内容**：三个参数的设备间方差 vs 设备内方差占比
- **结论**：61-73% 的方差来自设备间差异 → 逐设备基线是必须的
- **数据**：832 条正常观测，100 台设备

### 图 B：阈值性能曲线

- **展示内容**：精确率、召回率、F1、FPR 随 z-score 阈值变化的四线图
- **结论**：z > 2.0 为运维最佳操作点（P=84%, FPR=20%）
- **数据**：2,999 条观测，100 台设备

### 图 C：z-score 分布对比

- **展示内容**：正常态与故障态的复合 z-score 密度直方图，含三级阈值线
- **结论**：约 22% 的故障在 z < 2.5 区间与正常态重叠，需要时序特征增强
- **数据**：832 正常 + 2,167 故障观测

### 图 D：设备聚类 + 故障签名（双面板）

- **左面板**：设备在正常态电压-温度空间的 K-Means 聚类（K=3）
- **右面板**：9 种故障类型的参数偏移热力图
- **结论**：3 个工况族群 + 3 组故障签名 → 可设计分族群的分层检测策略

### 图 E：成本风险气泡图

- **展示内容**：100 台设备的故障率 × 单位成本散点图，气泡大小 = 综合成本风险
- **结论**：高成本设备（CNC_095 成本=114）与高产量设备（CNC_085 日产=1,858）均需优先维护

### 图 F：逐设备正常电压范围

- **展示内容**：15 台代表性设备的正常态电压 μ ± 2σ 范围
- **结论**：电压设定点跨 130V 以上 → 任何全局阈值均不可用
- **数据**：仅正常态（Type 0），15 台代表性设备

---

## 6. 文件对照表

| 文件 | 功能 | 入口 |
|------|------|------|
| `baseline_analysis.py` | 全部基线计算 + CSV 输出 | `python baseline_analysis.py` |
| `figures.py` | 初始 7 图（PNG only） | `python figures.py` |
| `figures_nature.py` | Nature风格精修 6 图（SVG+PDF+TIFF） | `python figures_nature.py` |
| `baseline_outputs/` | 所有中间数据和图表输出 | 自动生成 |

---

## 7. 引用说明

- 统计方法：z-score 标准化、方差分解、K-Means 聚类、Hotelling T² MSPC
- 可视化：Nature-journal 标准（Arial, 7pt, 600dpi, SVG editable text, LZW-compressed TIFF）
- 调色板：低饱和度 muted family（Steel Blue #517E9C / Brick Red #C2685A / Sage #5F8B6F / Amber #C8945F）
- 数据来源：出题单位提供的脱敏 Excel 数据，4 个 CSV 文件

---

*文档版本：v1.0 | 2026-05-16*
