---
name: predictive-maintenance-decision
description: |
  Maintenance decision engine for 100-CNC predictive maintenance: multi-signal fusion,
  action recommendation, work order prioritization, cost-savings estimation. Use when
  the user needs actionable maintenance work orders, wants to know "what should we do
  and when?", or needs cost-justified maintenance scheduling. Final skill in the
  5-skill pipeline, consumes all upstream outputs.
---

# Predictive Maintenance — Decision Engine (Skill 5/5)

## Purpose

Convert all upstream signals into prioritized, cost-justified maintenance work
orders. This is where business value is realized: operators don't see risk scores —
they see "Shut down CNC_067 immediately — critical deviation, daily exposure $7,455."

## Bundled scripts

```
scripts/
├── maintenance_decision_engine.py  # Full 4-layer decision engine
└── run.py                          # Entry point
```

## Prerequisites

- Skill 1 (data-prep) output directory (cost_risk_matrix.csv, z_scores.csv)
- Skill 2 (stat-inference) output directory (alert_summary.csv)
- Skill 3 (ml-inference) output directory (optional)
- Skill 4 (diagnosis) output directory (optional)
- Raw data directory

## How to run

```bash
python scripts/run.py \
  --data-dir <raw_csv_directory> \
  --prep-dir <data_prep_output_directory> \
  --stat-dir <stat_inference_output_directory> \
  --ml-dir <ml_inference_output_directory> \
  --diag-dir <diagnosis_output_directory> \
  --output-dir <output_directory>
```

Minimal (stat-inference only, no ML):
```bash
python scripts/run.py \
  --data-dir /path/to/raw_csvs/ \
  --prep-dir outputs_data_prep \
  --stat-dir outputs_stat \
  --output-dir outputs_decision
```

Options:
- `--streaming` — Enable continuous confirmation (requires 2–3 consecutive observations
  before alert level changes; use for live monitoring)
- `--max-orders N` — Cap work orders per cycle (default: 20)

## Output files

| File | Audience | Description |
|---|---|---|
| `maintenance_work_orders.csv` | **Operators** | Prioritized work orders with cost estimates |
| `maintenance_decision_report.csv` | Engineers | Full evaluation results for all 100 machines |
| `maintenance_report.txt` | Supervisors | Formatted text report |
| `decision_summary.json` | Dashboards | Summary stats (alert distribution, top urgent) |
| `manifest.json` | Automation | Paths + metadata |

## The 4-layer decision architecture

### Layer 1 — Multi-signal fusion

| Signal | Weight | Source |
|---|---|---|
| Statistical anomaly (z-score + thermal) | 0.40 | stat-inference |
| ML fault density | 0.25 | ml-inference (default 0.7 if unavailable) |
| Cost risk | 0.25 | data-prep (percentile-binned) |
| Trend (parameter drift) | 0.10 | stat-inference |

Output: risk_score [0, 1]

### Layer 2 — Diagnosis

Delegates to skill 4. Identifies which of 4 anomaly patterns is present.

### Layer 3 — Action determination (6 types)

| Action | Trigger | Time window |
|---|---|---|
| `immediate_shutdown` | z_max ≥ 10.0 | 0 days |
| `preventive_repair` | ALARM + (z_max ≥ 8.0 or high-cost) | 1–3 days |
| `schedule_inspection` | ALARM (standard) or WARNING with pattern | 3–7 days |
| `increase_monitoring` | WARNING (no pattern) or WATCH with pattern | 7–14 days |
| `routine_check` | WATCH (normal pattern) | 30 days |
| `no_action` | NORMAL | 30 days |

Cost multiplier: +40% urgency for critical-cost machines (≥ $10K), +20% for high-cost (≥ $5K).

### Layer 4 — Work order generation

- Filters: NORMAL/ROUTINE_CHECK/NO_ACTION excluded
- Deduplicates: one order per machine (highest urgency)
- Ranks by: urgency desc, then cost_at_risk desc
- Caps at: 20 orders per cycle (configurable)
- Savings: `expected_savings = cost_at_risk × 2.70` (emergency 3× vs preventive 0.3×)

## Example output

```
======================================================================
PRIORITIZED MAINTENANCE WORK ORDERS
======================================================================

[1] CNC_036 | ALARM | preventive_repair
    Urgency: 100/100 | Cost at risk: $18,080
    Window: 3 day(s) | Savings: $12,656
    [High Risk Tier] Preventive repair within 3 day(s)...

[2] CNC_025 | ALARM | preventive_repair
    Urgency: 100/100 | Cost at risk: $17,043
    Window: 1 day(s) | Savings: $11,930
    Severe deviation (z_max=8.3) — urgent inspection needed...
```

## Design rationale

- **ML weight 0.25**: ML signal is weak (AUC ≈ 0.59); z-score baseline is stronger
- **6 action types**: Maps directly to maintenance workflow stages
- **Work order cap**: Prevents alert fatigue
- **Cost-savings estimates**: Justifies maintenance spend with dollar figures
- **Human-readable suggestions**: Operators get specific instructions, not scores
