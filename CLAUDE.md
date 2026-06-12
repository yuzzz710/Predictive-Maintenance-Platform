# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

智能设备预测性维护 — A predictive maintenance system for 100 CNC machines. Uses 4 sensor parameters (Voltage, Amperage, Temperature, Rotor Speed) to detect anomalies and generate prioritized maintenance work orders. The core finding across all analysis phases: 4 parameters are insufficient for pure ML predictive maintenance (max Youden's J = 0.075). The system therefore uses a **cost-risk-driven + statistical-baseline fusion** approach.

## Project Phases

The analysis follows a 4-phase pipeline, each in its own directory:

| Phase | Directory | Purpose |
|---|---|---|
| 1 | `数据探索分析/` | 14 statistical analyses + 17 visualizations of raw data |
| 2 | `基线分析和确定/` | 4 statistical baselines (z-score, cost-risk matrix, failure signatures, Hotelling T²) |
| 3 | `预测性维护模型/` + `预测性维护模型_v2/` | v1 XGBoost + v2 Multi-Task NN experiments |
| 4 | `预测性维护模型_v3/` | Decision engine + predictability analysis + system design doc |

## Architecture: Agent-MCP Framework

The production runtime is in `agent-mcp架构/`. It exposes 7 MCP Tools via FastMCP and runs a DAG pipeline via a Python orchestrator.

**Two execution paths:**

1. **Agent mode** — Claude calls individual MCP tools in any order:
   `explain_predictability_limit` → `prepare_data` → `run_stat_analysis` + `run_ml_analysis` (parallel) → `run_diagnosis` → `generate_decision`

2. **Full pipeline** — Single call to `run_predictive_maintenance()`, which imports `agent_orchestrator.PredictiveMaintenanceAgent` in-process and runs the fixed DAG.

**MCP server:** `agent-mcp架构/mcp_server.py` uses `FastMCP("predictive-maintenance")`. Tools 1-5 invoke skills via `subprocess.run()` (600s timeout per skill). Tool 0 (`explain_predictability_limit`) runs in-process reading precomputed CSVs from `预测性维护模型_v3/outputs/`. Tool 6 imports the orchestrator directly.

**Orchestrator:** `agent-mcp架构/agent_orchestrator.py` — `PredictiveMaintenanceAgent` class. DAG: `data_prep → stat+ml(ThreadPool parallel) → diagnosis → decision`. ML unavailable → auto-skip to stat-only degradation path. Skill invocation is always `subprocess.run()` targeting each skill's `scripts/run.py`.

**The `skills/` directory is intentionally separate from `agent-mcp架构/`** — 5 independent Python packages, each with `scripts/run.py` as CLI entry point and `SKILL.md` as documentation:

| Skill | Directory | CLI Args | Key Output |
|---|---|---|---|
| 1 data-prep | `skills/predictive-maintenance-data-prep/` | positional: `<data_dir> <output_dir>` | `z_scores.csv`, `cost_risk_matrix.csv` |
| 2 stat-inference | `skills/predictive-maintenance-stat-inference/` | `--data-dir --prep-dir --output-dir` | `alert_summary.csv`, `t2_results.csv` |
| 3 ml-inference | `skills/predictive-maintenance-ml-inference/` | `--data-dir --prep-dir --output-dir --model` | `prediction_report.csv` |
| 4 diagnosis | `skills/predictive-maintenance-diagnosis/` | `--data-dir --prep-dir --stat-dir [--ml-dir] --output-dir --skip-predictability` | `diagnosis_report.csv` |
| 5 decision | `skills/predictive-maintenance-decision/` | `--data-dir --prep-dir --stat-dir [--ml-dir --diag-dir] --output-dir --max-orders` | `maintenance_work_orders.csv` |

Skills share code via copy-paste (e.g., `maintenance_decision_engine.py` exists in both diagnosis and decision skills). Each skill's `run.py` does `sys.path.insert(0, os.path.dirname(__file__))` before importing its local modules.

## Common Commands

### Dashboard

```bash
cd web-dashboard
python server.py
# Open http://localhost:8765
```

Or double-click `web-dashboard/start.bat`. The server is a minimal stdlib HTTP server on port 8765 with CSV/JSON MIME types.

### Run Full Predictive Maintenance Pipeline

```bash
cd agent-mcp架构
python agent_orchestrator.py --data-dir ../原始数据集 --model v1
# With ML skip (fast stat-only path, ~5.7s):
python agent_orchestrator.py --data-dir ../原始数据集 --skip-ml --skip-diagnosis
```

### Run Individual Skills (from project root)

```bash
# Skill 1: Data preparation
python skills/predictive-maintenance-data-prep/scripts/run.py 原始数据集 outputs/data_prep

# Skill 2: Statistical inference
python skills/predictive-maintenance-stat-inference/scripts/run.py --data-dir 原始数据集 --prep-dir outputs/data_prep --output-dir outputs/stat

# Skill 3: ML inference (v1 XGBoost)
python skills/predictive-maintenance-ml-inference/scripts/run.py --data-dir 原始数据集 --prep-dir outputs/data_prep --output-dir outputs/ml --model v1

# Skill 5: Decision engine
python skills/predictive-maintenance-decision/scripts/run.py --data-dir 原始数据集 --prep-dir outputs/data_prep --stat-dir outputs/stat --output-dir outputs/decision --max-orders 20
```

### Test MCP Tool 0 (in-process, no skill invocation)

```bash
cd agent-mcp架构
python -c "from mcp_server import explain_predictability_limit; print(explain_predictability_limit()['conclusion'])"
```

### Start MCP Server (for Claude Desktop integration)

```bash
cd agent-mcp架构
python mcp_server.py
# Uses stdio transport — connect from Claude Desktop config
```

## Dashboard Architecture (`web-dashboard/`)

Single-page HTML application (~1244 lines). No build step, no framework — vanilla JS + ECharts 5.5.0 + PapaParse 5.4.1 from CDN.

**4 tabs, rendered lazily** (only sec1 at init; sec2/sec3/sec4 render on first navigation):

| Tab | Data Sources | Key Charts |
|---|---|---|
| 数据探索 | `summary.csv`, `fault_dist.csv`, `log.csv` | Daily output bar, fault stack, boxplots, scatter |
| 基线划定分析 | `variance_decomp.csv`, `z_scores.csv`, `failure_sig.csv`, `cost_risk.csv` | Variance bars, alert donut, radar, bubble, z-score timeseries |
| 预测性维护模型 | `eval_metrics.csv`, `variant_comp.csv`, `feature_imp.csv`, `robustness.csv`, `dim1.csv`, `dim4.csv` | Eval bars, variant bars, feat importance, robustness heatmap, ceiling bar |
| 预测性维护建议 | `work_orders.csv`, `diagnosis.csv`, `dim1.csv`, `dim5.csv` | Youden's J bars, anomaly donut, fault-overlap bars, work order cards, sensor cards |

**Image galleries:** 50 PNG images in `images/{eda,baseline,v1,v2}/`. Each section has a toggle gallery with Chinese captions + lightbox (keyboard: ← → Esc). The `GALLERY` JS object maps each section's images to figure names and descriptions.

**Key JS globals:** `DATA` (cached CSV data), `CHARTS` (ECharts instances), `_rendered` (lazy-render tracker). Data loading uses `loadCSV(path)` → PapaParse with `dynamicTyping:true`. CSV column names in JS use bracket notation (e.g., `r['f2_0.5']`) — dots in column headers from the CSV source require this.

## Key Technical Details

**Sensor limitation is the project's central finding:** All 4 parameters have Youden's J < 0.08. ~22% of fault samples fall within normal z-score range. ML models (XGBoost AUC≈0.48, MTNN AUC≈0.59) converge to trivial predictors because the information simply isn't in the 4 sensors. The decision engine compensates by weighting statistical anomaly (0.40) + cost risk (0.25) + ML density (0.25) + trend (0.10).

**Per-machine baselines are mandatory:** Inter-machine variance accounts for 61-73% of total variance — global thresholds are invalid. Every z-score, T² statistic, and alert is computed relative to each machine's own normal-operation distribution.

**Windows encoding on data files:** All CSV/JSON files are UTF-8. Python scripts that read from `原始数据集/` or `agent-mcp架构/` must specify `encoding='utf-8'` explicitly — Windows defaults to GBK.

**Data files:** 4 raw CSVs in `原始数据集/` (~254KB total). 100 machines, 2,999 observations, 9 fault types (Type 0 = normal, Types 1-9 = various faults). Key files for downstream use: `MACHINE_LOG_DATA._2025.csv` (time-series sensor readings with fault labels), `MACHINE_SUMMARY_DATA._2025.csv` (per-machine metadata with cost/output).
