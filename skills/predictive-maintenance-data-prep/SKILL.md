---
name: predictive-maintenance-data-prep
description: |
  Data preparation for 100-CNC-machine predictive maintenance: load 4 raw CSV datasets,
  build per-machine statistical baselines, compute z-scores, construct cost-risk matrix.
  Use when the user needs to ingest machine-log data, establish baselines, or prepare
  features before running any inference (statistical or ML). This is the first skill in
  the 5-skill predictive maintenance pipeline.
---

# Predictive Maintenance — Data Preparation (Skill 1/5)

## Purpose

Load raw CNC machine monitoring data (4 CSV files) and produce structured,
machine-aware inputs for all downstream skills. This is the mandatory first step.

## Bundled scripts

```
scripts/
├── baseline_analysis.py    # Core module: load, baseline, z-score, cost-risk
└── run.py                  # Entry point
```

## How to run

```bash
python scripts/run.py <data_directory> <output_directory>
```

Example:
```bash
python scripts/run.py /path/to/raw_csvs/ outputs_data_prep
```

The data directory must contain these 4 files:
- `MACHINE_LOG_DATA._2025.csv`
- `MACHINE_SUMMARY_DATA._2025.csv`
- `PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv`
- `PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv`

If assembly or test files are missing, the pipeline degrades gracefully —
z-score and cost-risk outputs are still produced.

## Output files (in the output directory)

| File | Consumed by |
|---|---|
| `z_scores.csv` | stat-inference, ml-inference, decision |
| `cost_risk_matrix.csv` | stat-inference, decision |
| `baseline_stats.csv` | stat-inference (reference) |
| `failure_signatures.csv` | diagnosis |
| `variance_decomposition.csv` | diagnosis |
| `machine_clusters.csv` | stat-inference (cold-start fallback) |
| `manifest.json` | All downstream skills (paths + metadata) |

## Key configuration

Thresholds (hardcoded in `baseline_analysis.py` CONFIG dict):
- Z-score: Watch > 1.5, Warning > 2.0, Alarm > 2.5
- Cost risk: Medium > 4500, High > 5300
- Min normal samples per machine: 6
- Monitored parameters: Voltage, Amperage, Temperature (Rotor Speed excluded)

## What happens internally

1. **Load** — 4 CSV files into DataFrames
2. **Baseline** — μ, σ, Q1, Q3, IQR per machine from Type-0 (normal) samples only
3. **Z-scores** — per-row z_Voltage, z_Amperage, z_Temperature + composite `z_composite = sqrt(z_V² + z_A² + z_T²)`
4. **Cost-risk** — `cost_at_risk = failure_rate × unit_cost × daily_output / 100`
5. **Clusters** — 3-cluster KMeans for sparse-machine fallback
6. **Variance decomposition** — inter-machine vs intra-machine variance per parameter

## Known limitations (communicate to user)

- Rotor Speed excluded — >99.9% intra-machine variance, zero diagnostic value
- 4 parameters max Youden's J = 0.075 (need > 0.30 for reliability)
- Machines with < 6 normal samples are "sparse" — downstream skills use cluster fallback
- All 100 machines in "High" risk tier under default cost thresholds (tight cost distribution)
