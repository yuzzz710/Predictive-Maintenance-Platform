---
name: predictive-maintenance-ml-inference
description: |
  ML inference for 100-CNC predictive maintenance: feature engineering, XGBoost dual-model
  training, Multi-Task Neural Network training, prediction generation. Use when the user
  wants to train models, generate fault-density predictions, or evaluate ML performance.
  Third skill in the pipeline, runs in parallel with stat-inference after data-prep.
---

# Predictive Maintenance — ML Inference (Skill 3/5)

## Purpose

Train and evaluate machine learning models for fault prediction. Two model versions
are available: v1 (XGBoost, fast) and v2 (Multi-Task Neural Network, PyTorch).
Both converge to the same performance ceiling (AUC ≈ 0.59) because the limitation
is in the 4 sensors, not the model architecture.

## Bundled scripts

```
scripts/
├── model_training.py       # v1: XGBoost dual-model (~60 features, sliding window)
├── model_training_v2.py    # v2: Multi-Task Neural Network (~100 features, 4D engineering)
└── run.py                  # Entry point
```

## Prerequisites

- Skill 1 (data-prep) output directory (contains `z_scores.csv`, `cost_risk_matrix.csv`)
- Raw data directory (for loading log + summary + assembly + tests CSVs)
- For v1: `xgboost`, `scikit-learn` installed
- For v2: `torch`, `scikit-learn` installed

## How to run

```bash
# XGBoost v1 (fast, recommended):
python scripts/run.py \
  --data-dir <raw_csv_directory> \
  --prep-dir <data_prep_output_directory> \
  --output-dir <output_directory> \
  --model v1

# Multi-Task Neural Network v2 (PyTorch):
python scripts/run.py \
  --data-dir <raw_csv_directory> \
  --prep-dir <data_prep_output_directory> \
  --output-dir <output_directory> \
  --model v2
```

Example:
```bash
python scripts/run.py \
  --data-dir /path/to/raw_csvs/ \
  --prep-dir outputs_data_prep \
  --output-dir outputs_ml \
  --model v1
```

## Choosing v1 vs v2

| Criterion | v1 (XGBoost) | v2 (MTNN) |
|---|---|---|
| Training speed | Seconds | Minutes |
| GPU needed | No | Optional |
| Feature set | ~60 features | ~100 features (4D) |
| Interpretability | Feature importance | Gradient sensitivity |
| Performance ceiling | AUC ≈ 0.59 | AUC ≈ 0.59 |

Both are limited by sensor information, not model capacity. Use v1 unless
the user specifically wants neural network results.

## Output files

| File | Description |
|---|---|
| `prediction_report.csv` | Per-machine: machine_id, fault_density_pred, cost_at_risk, alert_level, alert_score |
| `model.json` or `model.pth` | Trained model (v1 JSON, v2 PyTorch state dict) |
| `manifest.json` | Paths + metadata |

For v2, additional files are saved in `model_outputs/` subdirectory:
- `variant_comparison.csv` — input_window × prediction_horizon comparison
- `evaluation_metrics.csv` — AUC, R², precision, recall per variant

## What happens internally

**v1 (XGBoost)**:
1. Extract ~60 window features (moments, trends, autocorrelation, z-score interactions)
2. Train two XGBoost classifiers: fault occurrence + fault type
3. Blend predictions with z-score baseline (α ≈ 0.7, favoring z-score)
4. Generate per-machine prediction report

**v2 (MTNN)**:
1. Extract 4D features: Trend (24d) + Volatility (36d) + State (33d) + Cost (~15d)
2. Train shared-trunk [128,64,32] → FaultHead + QualityHead
3. Data augmentation: noise + masking + jitter
4. Compare 3 window variants: 15in_5pred, 10in_10pred, 10in_5pred
5. Best variant (10in_5pred): AUC = 0.589

## Critical caveat — always communicate

The 4 monitoring parameters have a fundamental information ceiling:
- Single-parameter max Youden's J = 0.075 (usable threshold = 0.30)
- 70% of fault samples fall within normal parameter ranges
- All models converge to trivial mean predictor (R² ≈ 0)
- The ML signal weight in decision fusion is only 0.25

Frame ML results as "what the sensors can see" rather than "how good the model is."
