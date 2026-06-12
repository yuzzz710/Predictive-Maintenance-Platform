---
name: predictive-maintenance-stat-inference
description: |
  Statistical inference for 100-CNC predictive maintenance: evaluate z-score baselines,
  Hotelling T2 multivariate SPC, failure-type signature analysis. Use when the user
  needs statistical alerts, threshold tuning, anomaly detection without ML, or when ML
  models are unavailable (fallback path). Second skill in the pipeline, runs in parallel
  with ml-inference after data-prep.
---

# Predictive Maintenance — Statistical Inference (Skill 2/5)

## Purpose

Run statistical anomaly detection using 4 complementary baselines. This skill
provides the strongest signal in the current system. It needs no trained model.

## Bundled scripts

```
scripts/
├── baseline_analysis.py    # Statistical functions (evaluate_z_baseline, compute_hotelling_t2, etc.)
└── run.py                  # Entry point
```

## Prerequisites

Skill 1 (data-prep) must have been run first. You need the output directory
from skill 1 (contains `z_scores.csv`, `baseline_stats.csv`, etc.) plus the
original raw data directory.

## How to run

```bash
python scripts/run.py \
  --data-dir <raw_csv_directory> \
  --prep-dir <data_prep_output_directory> \
  --output-dir <output_directory>
```

Example:
```bash
python scripts/run.py \
  --data-dir /path/to/raw_csvs/ \
  --prep-dir outputs_data_prep \
  --output-dir outputs_stat
```

## Output files

| File | Description |
|---|---|
| `z_threshold_sweep.csv` | Precision/recall/F1/FPR at thresholds [1.0, 1.5, 2.0, 2.5, 3.0, 3.5] |
| `t2_results.csv` | Per-row Hotelling T2 statistic + alert flags |
| `failure_signature_analysis.csv` | Per-failure-type parameter deviations from normal |
| `alert_summary.csv` | Per-machine: current level, z_max, z_mean, per-parameter z-scores |
| `stat_inference_summary.json` | Key metrics (best F1, T2 metrics, alert distribution) |
| `manifest.json` | Paths + metadata for downstream skills |

## What happens internally

1. **Z-score evaluation** — Sweeps thresholds, computes precision/recall/specificity/F1/FPR.
   Best F1 typically at z > 2.5: recall ≈ 84%, FPR ≈ 20%.
2. **Hotelling T2** — Multivariate SPC. Per-machine covariance, chi-square critical value
   at α = 0.01. Note: T2 adds limited value because parameter covariance is weak (r < 0.1).
3. **Failure signatures** — 3 groups:
   - High-Voltage (Types 4,5): Voltage +10.7V — most detectable
   - Thermal (Types 3,6–9): Temperature +1.5°C — moderate
   - Subtle (Types 1,2): Voltage +1.8V — very difficult
4. **Alert aggregation** — Per-machine: current alert_level, max z_composite, per-param z-scores

## Alert thresholds

| Level | Threshold | Meaning |
|---|---|---|
| Normal | z ≤ 1.5 | Routine monitoring |
| Watch | z > 1.5 | Increase monitoring frequency |
| Warning | z > 2.0 | Schedule inspection |
| Alarm | z > 2.5 | Preventive repair or immediate action |

## Fallback role

When skill 3 (ml-inference) is not available, this skill's `alert_summary.csv` feeds
directly into skill 4 (diagnosis) and skill 5 (decision). The decision engine's ML
weight (0.25) is low enough that decisions remain stable without ML.
