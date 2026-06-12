---
name: predictive-maintenance-diagnosis
description: |
  Anomaly pattern diagnosis for 100-CNC predictive maintenance: identify voltage drift,
  thermal buildup, power anomaly, combined degradation patterns from parameter signatures.
  Also covers root-cause predictability analysis across 5 evidence dimensions. Use when
  the user needs to understand WHAT is happening (not just that something is wrong),
  wants a predictability limitation assessment, or needs pattern-specific diagnostic
  reports. Fourth skill in the pipeline, fuses stat-inference and ml-inference outputs.
---

# Predictive Maintenance — Diagnosis (Skill 4/5)

## Purpose

Translate raw alerts into specific, actionable diagnoses. Instead of "Machine X
at WARNING," this skill says "Machine X shows voltage drift consistent with PSU
degradation — inspect voltage regulator within 3 days."

Also provides the 5-dimension predictability limitation analysis that defines
what the current sensor suite can and cannot detect.

## Bundled scripts

```
scripts/
├── maintenance_decision_engine.py  # Diagnostic rules (diagnose method)
├── predictability_analysis.py      # 5-dimension root cause analysis
└── run.py                          # Entry point
```

## Prerequisites

- Skill 1 (data-prep) output directory
- Skill 2 (stat-inference) output directory (for alert summary)
- Skill 3 (ml-inference) output directory (optional — for ML predictions)
- Raw data directory

## How to run

```bash
python scripts/run.py \
  --data-dir <raw_csv_directory> \
  --prep-dir <data_prep_output_directory> \
  --stat-dir <stat_inference_output_directory> \
  --ml-dir <ml_inference_output_directory> \
  --output-dir <output_directory>
```

Without ML:
```bash
python scripts/run.py \
  --data-dir /path/to/raw_csvs/ \
  --prep-dir outputs_data_prep \
  --stat-dir outputs_stat \
  --output-dir outputs_diagnosis
```

Add `--skip-predictability` to skip the long-running 5-dimension analysis
(useful for quick diagnosis-only runs).

## Output files

| File | Description |
|---|---|
| `diagnosis_report.csv` | Per-machine: primary_pattern, patterns_detected, confidence, evidence scores |
| `predictability_limitation_summary.txt` | Executive summary of predictability ceiling |
| `manifest.json` | Paths + pattern distribution |

## 4 anomaly patterns

| Pattern | Physical meaning | Detection rule |
|---|---|---|
| `voltage_drift` | PSU degradation, bus instability | \|z_V\| > 2.0 AND \|voltage_trend\| > 0.02 |
| `thermal_buildup` | Cooling issue, bearing friction | \|z_T\| > 2.0 AND thermal_over_p95 ≥ 2 |
| `power_anomaly` | Load mismatch, winding degradation | \|z_V\| > 1.5 AND \|z_A\| > 1.5 |
| `combined_degradation` | Systemic deterioration | ≥ 2 params with \|z\| > 2.0 |

When multiple patterns match, `combined_degradation` takes precedence (most severe).
Otherwise, the pattern with highest evidence score is primary.

## 5-dimension predictability analysis

| Dimension | Finding |
|---|---|
| 1. Single-parameter discriminability | Max Youden's J = 0.075 (need > 0.30) |
| 2. Parameter coupling | Correlations unchanged normal vs fault |
| 3. Fault progression | 70% faults within normal parameter ranges |
| 4. Model convergence | All models → trivial mean predictor (R² ≈ 0) |
| 5. Sensor gaps | Missing vibration/acoustic/current-signature (80%+ of diagnostic info) |

**Recommendation**: Add vibration sensors (highest-impact single improvement).
Expected to increase Youden's J from 0.075 to 0.40+.

## What happens internally

1. **Pattern diagnosis** — For each machine, apply 4 diagnostic rule sets using
   per-parameter z-scores, trend slopes, and thermal exceedance counts.
2. **Predictability analysis** (optional) — 5-dimension systematic evidence
   collection proving sensor insufficiency. Generates summary figure and text.

Diagnosis results feed into skill 5 (decision) as the `primary_pattern` and
`diagnosis_confidence` fields used for action determination.
