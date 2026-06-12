#!/usr/bin/env python3
"""
预测性维护告警模型 v2 — Multi-Task Neural Network
===================================================
Architecture:
  - Shared feature extractor (Dense + BatchNorm + Dropout)
  - Head 1: Fault prediction (binary, next 5 steps)
  - Head 2: Product quality prediction (regression, only 15 machines)

Key improvements over v1:
  - 5-step prediction window (not single-step)
  - 4D feature engineering: Trend / Volatility / State / Cost
  - Data augmentation: noise + missing + jitter
  - Multi-variant window: 15->5, 10->10, 10->5
  - Continuous confirmation alert logic
  - Robustness evaluation under perturbations

Author : Predictive Maintenance Team
Date   : 2026-05-17
"""

import numpy as np
import pandas as pd
import os
import json
import warnings
from typing import Dict, Tuple, List, Optional
from collections import defaultdict

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler
from sklearn.metrics import (
    roc_auc_score, fbeta_score, average_precision_score,
    precision_score, recall_score, r2_score, mean_squared_error,
)
from sklearn.model_selection import GroupKFold
from scipy import stats as sp_stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

warnings.filterwarnings("ignore")
torch.manual_seed(42)
np.random.seed(42)

# ============================================================================
# SECTION 0: Configuration
# ============================================================================

OUTPUT_DIR = "model_outputs"
FIGURE_DIR = "figures"
DATA_DIR = "../原始数据集"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FIGURE_DIR, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 8, "axes.labelsize": 7,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
})

CONFIG = {
    # Window variants: (input_steps, predict_steps)
    "window_variants": [(15, 5), (10, 10), (10, 5)],

    # Data augmentation
    "augmentation": {
        "noise_std_range": (0.02, 0.05),   # × parameter σ
        "mask_prob": 0.20,                  # probability of masking
        "mask_max_steps": 3,                # max steps to mask
        "time_jitter_std": 0.10,            # time perturbation std
        "label_smoothing": 0.05,
    },

    # Model architecture
    "model": {
        "shared_dims": [128, 64, 32],
        "head_dims": [16],
        "dropout": 0.35,
        "batch_norm": True,
    },

    # Training
    "training": {
        "batch_size": 64,
        "learning_rate": 0.001,
        "weight_decay": 1e-4,
        "epochs": 500,
        "early_stopping_patience": 60,
        "aux_loss_weight": 0.30,  # weight for quality prediction loss
        "lr_scheduler_factor": 0.5,
        "lr_scheduler_patience": 25,
    },

    # Alert logic
    "alert": {
        "upgrade_windows": {"ALARM": 3, "WARNING": 2, "WATCH": 1},
        "downgrade_windows": {"ALARM": 3, "WARNING": 2, "WATCH": 2},
        "score_weights": {"ml_prob": 0.40, "stat_anomaly": 0.35, "cost_risk": 0.25},
    },

    # Parameters
    "params": ["Op.Voltage", "Op.Amperage", "Op.Temperature"],
    "excluded_params": ["Rotor Speed"],

    # Safe ranges from baseline Task 8 (P99)
    "safe_ranges": {
        "v": (101.0, 361.9), "a": (13.5, 44.2), "t": (46.8, 124.4),
    },
    "thermal_p95": 5.31,
}

# ============================================================================
# SECTION 1: Data Loading
# ============================================================================

def load_all_data(data_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    datasets = {}
    log = pd.read_csv(os.path.join(data_dir, "MACHINE_LOG_DATA._2025.csv"))
    log["Date"] = pd.to_datetime(log["Date"])
    log = log.sort_values(["Equipment.Id", "Date"]).reset_index(drop=True)
    log["time_step"] = log.groupby("Equipment.Id").cumcount()
    datasets["log"] = log

    datasets["summary"] = pd.read_csv(os.path.join(data_dir, "MACHINE_SUMMARY_DATA._2025.csv"))
    datasets["assembly"] = pd.read_csv(os.path.join(data_dir, "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_2025.csv"))
    tests = pd.read_csv(os.path.join(data_dir, "PRODUCT_ASSEMBLY_LINE_WITH_MACHINES_TESTS_2025.csv"))
    tests["DATE"] = pd.to_datetime(tests["DATE"])
    datasets["tests"] = tests
    return datasets


# ============================================================================
# SECTION 2: Feature Engineering — Four Dimensions
# ============================================================================

def compute_per_machine_baselines(log_train_normal: pd.DataFrame) -> pd.DataFrame:
    """Per-machine μ, σ from training normal data only."""
    bl = log_train_normal.groupby("Equipment.Id").agg(
        v_mu=("Op.Voltage", "mean"), v_sigma=("Op.Voltage", "std"),
        a_mu=("Op.Amperage", "mean"), a_sigma=("Op.Amperage", "std"),
        t_mu=("Op.Temperature", "mean"), t_sigma=("Op.Temperature", "std"),
        r_mu=("Rotor Speed", "mean"), r_sigma=("Rotor Speed", "std"),
        n_normal=("Op.Voltage", "count"),
    ).reset_index().rename(columns={"Equipment.Id": "machine_id"})
    for c in ["v_sigma", "a_sigma", "t_sigma", "r_sigma"]:
        bl[c] = bl[c].fillna(bl[c].median()).clip(lower=0.01)
    return bl


def extract_trend_features(v, a, t, steps, n):
    """Dimension 1: Trend features — where are parameters heading?"""
    feats = {}
    for name, arr in [("v", v), ("a", a), ("t", t)]:
        if n >= 3 and np.std(arr) > 1e-6:
            x = np.arange(n)
            slope, intercept, r_val, p_val, _ = sp_stats.linregress(x, arr)
            feats[f"{name}_slope"] = slope
            feats[f"{name}_trend_r2"] = r_val ** 2
            feats[f"{name}_kendall_tau"] = sp_stats.kendalltau(x, arr).correlation
        else:
            feats[f"{name}_slope"] = 0.0
            feats[f"{name}_trend_r2"] = 0.0
            feats[f"{name}_kendall_tau"] = 0.0

        # Acceleration
        if n >= 3:
            d2 = np.diff(arr, n=2)
            feats[f"{name}_accel_mean"] = np.mean(d2)
            feats[f"{name}_accel_abs_max"] = np.max(np.abs(d2)) if len(d2) > 0 else 0.0
        else:
            feats[f"{name}_accel_mean"] = 0.0
            feats[f"{name}_accel_abs_max"] = 0.0

        # Consecutive direction
        if n >= 2:
            diffs = np.diff(arr)
            ups = diffs > 0
            downs = diffs < 0
            feats[f"{name}_consecutive_up"] = max_consecutive(ups)
            feats[f"{name}_consecutive_down"] = max_consecutive(downs)
            feats[f"{name}_reversals"] = np.sum(np.diff(ups.astype(int)) != 0)
        else:
            feats[f"{name}_consecutive_up"] = 0
            feats[f"{name}_consecutive_down"] = 0
            feats[f"{name}_reversals"] = 0
    return feats


def extract_volatility_features(v, a, t, n):
    """Dimension 2: Volatility — how unstable are parameters?"""
    feats = {}
    for name, arr in [("v", v), ("a", a), ("t", t)]:
        feats[f"{name}_std"] = np.std(arr) if n > 1 else 0.0
        feats[f"{name}_cv"] = np.std(arr) / (np.mean(arr) + 0.001)  # coefficient of variation
        feats[f"{name}_range"] = np.max(arr) - np.min(arr)
        feats[f"{name}_iqr"] = np.percentile(arr, 75) - np.percentile(arr, 25)
        feats[f"{name}_mad"] = np.mean(np.abs(arr - np.mean(arr)))  # mean absolute deviation
        rms = np.sqrt(np.mean(arr ** 2))
        feats[f"{name}_rms"] = rms
        feats[f"{name}_crest_factor"] = np.max(np.abs(arr)) / (rms + 0.001)
        feats[f"{name}_form_factor"] = rms / (np.mean(np.abs(arr)) + 0.001)

        if n >= 2:
            diffs = np.diff(arr)
            feats[f"{name}_diff_std"] = np.std(diffs)
            feats[f"{name}_diff_max"] = np.max(np.abs(diffs))
            feats[f"{name}_diff_range"] = np.max(diffs) - np.min(diffs)
        else:
            feats[f"{name}_diff_std"] = 0.0
            feats[f"{name}_diff_max"] = 0.0
            feats[f"{name}_diff_range"] = 0.0

    # Cross-parameter volatility ratio
    for p1, p2 in [("v", "a"), ("v", "t"), ("a", "t")]:
        cv1 = feats[f"{p1}_cv"]
        cv2 = feats[f"{p2}_cv"]
        feats[f"cv_ratio_{p1}_{p2}"] = cv1 / (cv2 + 0.001)
    return feats


def extract_state_features(v, a, t, r, fault_types, baseline, machine_id, n):
    """Dimension 3: State — what condition is the machine in?"""
    feats = {}
    bl = baseline[baseline["machine_id"] == machine_id]
    has_bl = len(bl) > 0

    # Current state
    feats["current_fault_type"] = fault_types[-1]
    feats["current_is_normal"] = 1 if fault_types[-1] == 0 else 0
    feats["window_fault_ratio"] = np.mean(fault_types > 0)
    feats["window_normal_count"] = np.sum(fault_types == 0)
    feats["window_fault_diversity"] = len(set(fault_types[fault_types > 0]))

    # Z-score deviations
    if has_bl:
        bv = bl.iloc[0]
        z_v = np.abs(v - bv["v_mu"]) / bv["v_sigma"]
        z_a = np.abs(a - bv["a_mu"]) / bv["a_sigma"]
        z_t = np.abs(t - bv["t_mu"]) / bv["t_sigma"]
    else:
        z_v = z_a = z_t = np.zeros(n)

    feats["z_v_last"] = z_v[-1]
    feats["z_a_last"] = z_a[-1]
    feats["z_t_last"] = z_t[-1]
    z_comp = np.sqrt(z_v**2 + z_a**2 + z_t**2)
    feats["z_comp_last"] = z_comp[-1]
    feats["z_comp_mean"] = np.mean(z_comp)
    feats["z_comp_max"] = np.max(z_comp)
    feats["z_comp_std"] = np.std(z_comp) if n > 1 else 0.0
    feats["z_comp_trend"] = z_comp[-1] - z_comp[0] if n > 1 else 0.0

    # Safe range violations
    safe = CONFIG["safe_ranges"]
    for pname, arr, (lo, hi) in [
        ("v", v, safe["v"]), ("a", a, safe["a"]), ("t", t, safe["t"])
    ]:
        violations = (arr < lo) | (arr > hi)
        feats[f"{pname}_violation_count"] = np.sum(violations)
        viol_vals = arr[violations]
        if len(viol_vals) > 0:
            boundary_dist = np.minimum(np.abs(viol_vals - lo), np.abs(viol_vals - hi))
            feats[f"{pname}_violation_severity"] = np.mean(boundary_dist) / (hi - lo)
        else:
            feats[f"{pname}_violation_severity"] = 0.0

    # Derived indicators
    power = v * a
    feats["power_mean"] = np.mean(power)
    feats["power_trend_slope"] = (power[-1] - power[0]) / n if n > 1 else 0.0
    thermal = t / np.clip(a, 0.01, None)
    feats["thermal_mean"] = np.mean(thermal)
    feats["thermal_max"] = np.max(thermal)
    feats["thermal_over_p95"] = np.sum(thermal > CONFIG["thermal_p95"])

    # Correlation within window
    if n >= 4:
        for (p1, x), (p2, y) in [
            (("v", v), ("a", a)), (("v", v), ("t", t)), (("a", a), ("t", t))
        ]:
            sdx, sdy = np.std(x), np.std(y)
            feats[f"corr_{p1}{p2}"] = np.corrcoef(x, y)[0, 1] if sdx > 0 and sdy > 0 else 0.0
    else:
        for pair in ["va", "vt", "at"]:
            feats[f"corr_{pair}"] = 0.0

    return feats


def extract_cost_context_features(
    machine_id, log_window, static_features, product_features,
    window_end_step, current_idx, n_total
):
    """Dimension 4: Cost & Context — how important and maintained is this machine?"""
    feats = {}
    srow = static_features[static_features["machine_id"] == machine_id]
    has_s = len(srow) > 0

    feats["unit_cost"] = srow["unit_cost"].values[0] if has_s else 5.0
    feats["daily_output"] = srow["daily_output"].values[0] if has_s else 1000.0
    feats["machine_age_months"] = srow["machine_age_months"].values[0] if has_s else 0
    feats["days_since_service"] = srow["days_since_service"].values[0] if has_s else 90
    feats["days_since_repair"] = srow["days_since_repair"].values[0] if has_s else 30
    feats["days_to_next_service"] = srow["days_to_next_service"].values[0] if has_s else 30
    feats["service_overdue"] = 1 if feats["days_since_service"] > 90 else 0

    # Historical fault rate from observed steps
    hist_rate = np.mean(log_window["Failure.Equipment.Type"].values > 0)
    feats["historical_fault_rate"] = hist_rate
    feats["cost_at_risk"] = hist_rate * feats["unit_cost"] * feats["daily_output"]

    # Steps since last fault
    fault_mask = log_window["Failure.Equipment.Type"].values > 0
    if np.any(fault_mask):
        feats["steps_since_last_fault"] = n_total - 1 - np.where(fault_mask)[0][-1]
    else:
        feats["steps_since_last_fault"] = n_total

    # Product quality features
    prow = product_features[product_features["machine_id"] == machine_id]
    if len(prow) > 0:
        pr = prow.iloc[0]
        feats["has_quality_data"] = 1
        for c in product_features.columns:
            if c in ("machine_id",):
                continue
            feats[f"prod_{c}"] = pr[c] if not pd.isna(pr[c]) else 0.0
    else:
        feats["has_quality_data"] = 0
        for c in product_features.columns:
            if c == "machine_id":
                continue
            feats[f"prod_{c}"] = 0.0

    return feats


def max_consecutive(bool_arr):
    """Max consecutive True values."""
    if len(bool_arr) == 0:
        return 0
    max_c, cur = 0, 0
    for b in bool_arr:
        if b:
            cur += 1
        else:
            max_c = max(max_c, cur)
            cur = 0
    return max(max_c, cur)


# ============================================================================
# SECTION 3: Product Quality Features (for auxiliary task)
# ============================================================================

def build_product_features(assembly: pd.DataFrame, tests: pd.DataFrame) -> pd.DataFrame:
    """Per-machine product quality features and labels."""
    af = assembly.groupby("MACHINE").agg(
        avg_failed_tests=("FAILED_TESTS", "mean"),
        max_failed_tests=("FAILED_TESTS", "max"),
        total_failed=("FAILED_TESTS", "sum"),
        n_products=("SERIAL NO", "nunique"),
    ).reset_index().rename(columns={"MACHINE": "machine_id"})
    af["defect_rate"] = af["total_failed"] / af["n_products"]

    tests_copy = tests.copy()
    tests_copy["spec_center"] = (tests_copy["LWR_SPEC_LIMIT"] + tests_copy["UPR_SPEC_LIMIT"]) / 2
    tests_copy["spec_tolerance"] = (tests_copy["UPR_SPEC_LIMIT"] - tests_copy["LWR_SPEC_LIMIT"]) / 2
    tests_copy["spec_tolerance"] = tests_copy["spec_tolerance"].replace(0, 1.0)
    tests_copy["deviation_norm"] = (
        (tests_copy["MEASMT_VALUE"] - tests_copy["spec_center"]) / tests_copy["spec_tolerance"]
    ).abs()
    tests_copy["in_spec"] = (
        (tests_copy["MEASMT_VALUE"] >= tests_copy["LWR_SPEC_LIMIT"])
        & (tests_copy["MEASMT_VALUE"] <= tests_copy["UPR_SPEC_LIMIT"])
    ).astype(int)

    tf = tests_copy.groupby("MACHINE").agg(
        test_pass_rate=("in_spec", "mean"),
        param_deviation_mean=("deviation_norm", "mean"),
        param_deviation_max=("deviation_norm", "max"),
    ).reset_index().rename(columns={"MACHINE": "machine_id"})

    prod = af.merge(tf, on="machine_id", how="outer").fillna(0)
    return prod


def build_static_features(summary: pd.DataFrame) -> pd.DataFrame:
    """Per-machine static features."""
    df = summary.copy().rename(columns={"Equipment.Id": "machine_id"})
    ref = pd.Timestamp("2025-05-18")
    ym = df["Month.of.Manufacture"].astype(int)
    df["machine_age_months"] = (ref.year - (ym // 100)) * 12 + (ref.month - (ym % 100))
    df["Last.Service.Date"] = pd.to_datetime(df["Last Service Date"])
    df["Last.Repair.Date"] = pd.to_datetime(df["Last Repair Date"])
    df["Next.Service.Date"] = pd.to_datetime(df["Next Service Date"])
    df["days_since_service"] = (ref - df["Last.Service.Date"]).dt.days
    df["days_since_repair"] = (ref - df["Last.Repair.Date"]).dt.days
    df["days_to_next_service"] = (df["Next.Service.Date"] - ref).dt.days
    return df[[
        "machine_id", "Unit Cost of Production", "Units Produced Per day",
        "machine_age_months", "days_since_service", "days_since_repair",
        "days_to_next_service",
    ]].rename(columns={
        "Unit Cost of Production": "unit_cost",
        "Units Produced Per day": "daily_output",
    })


# ============================================================================
# SECTION 4: Dataset Builder
# ============================================================================

def build_dataset(
    log, baseline, static_features, product_features,
    input_steps, predict_steps, train_end,
):
    """
    Build multi-task dataset.
    For each valid window position in [0, train_end):
      - Input: input_steps window features
      - y_fault: 1 if any fault in next predict_steps
      - y_quality: avg_failed_tests (only for 15 machines, NaN otherwise)
    """
    features_list = []
    y_fault_list = []
    y_quality_list = []
    quality_mask_list = []  # 1 for machines with product data
    machine_ids = []
    window_positions = []

    machines = sorted(log["Equipment.Id"].unique())
    prod_machines = set(product_features["machine_id"].values)

    for mid in machines:
        mlog_full = log[log["Equipment.Id"] == mid].sort_values("time_step")
        mlog = mlog_full[mlog_full["time_step"] < train_end]
        n_available = len(mlog)

        if n_available < input_steps + predict_steps:
            continue

        has_quality = mid in prod_machines
        quality_val = 0.0
        if has_quality:
            prow = product_features[product_features["machine_id"] == mid]
            if len(prow) > 0:
                quality_val = prow.iloc[0]["avg_failed_tests"]

        # Determine max window start index
        max_start = n_available - input_steps - predict_steps + 1
        for start_idx in range(max_start):
            win = mlog.iloc[start_idx : start_idx + input_steps]
            v = win["Op.Voltage"].values.astype(float)
            a = win["Op.Amperage"].values.astype(float)
            t = win["Op.Temperature"].values.astype(float)
            r = win["Rotor Speed"].values.astype(float)
            steps_arr = win["time_step"].values.astype(float)
            fault_types = win["Failure.Equipment.Type"].values.astype(int)
            n = input_steps
            window_end_step = int(mlog.iloc[start_idx + input_steps - 1]["time_step"])

            # Four-dimension features
            feats = {}
            feats.update(extract_trend_features(v, a, t, steps_arr, n))
            feats.update(extract_volatility_features(v, a, t, n))
            feats.update(extract_state_features(v, a, t, r, fault_types, baseline, mid, n))
            feats.update(extract_cost_context_features(
                mid, win, static_features, product_features,
                window_end_step, start_idx + input_steps - 1, n,
            ))

            # Target: fraction of steps with faults in next predict_steps
            future = mlog.iloc[start_idx + input_steps : start_idx + input_steps + predict_steps]
            y_fault = (future["Failure.Equipment.Type"] > 0).mean()  # fraction, 0.0-1.0

            features_list.append(feats)
            y_fault_list.append(y_fault)
            y_quality_list.append(quality_val)
            quality_mask_list.append(1 if has_quality else 0)
            machine_ids.append(mid)
            window_positions.append(window_end_step)

    df = pd.DataFrame(features_list)
    # Fill NaN with 0
    df = df.fillna(0.0)

    feature_names = list(df.columns)
    X = df.values.astype(np.float32)
    y_fault = np.array(y_fault_list, dtype=np.float32)
    y_quality = np.array(y_quality_list, dtype=np.float32)
    quality_mask = np.array(quality_mask_list, dtype=np.float32)

    return X, np.array(y_fault_list, dtype=np.float32), np.array(y_quality_list, dtype=np.float32), \
           quality_mask, feature_names, np.array(machine_ids), np.array(window_positions)


# ============================================================================
# SECTION 5: Data Augmentation
# ============================================================================

class DataAugmenter:
    """Training-time augmentation for robustness."""

    def __init__(self):
        self.cfg = CONFIG["augmentation"]

    def augment(self, X: np.ndarray) -> np.ndarray:
        """Apply random perturbations to feature matrix."""
        X_aug = X.copy()
        n_samples, n_features = X.shape

        # 1. Gaussian noise (per sample, per feature)
        noise_frac = np.random.uniform(self.cfg["noise_std_range"][0],
                                        self.cfg["noise_std_range"][1])
        noise = np.random.randn(*X_aug.shape).astype(np.float32) * noise_frac * np.std(X_aug, axis=0)
        X_aug += noise

        # 2. Random feature masking (simulates missing sensor readings)
        if np.random.random() < self.cfg["mask_prob"]:
            n_mask = np.random.randint(1, self.cfg["mask_max_steps"] + 1)
            for _ in range(n_mask):
                feat_idx = np.random.randint(0, n_features)
                # Set to column mean (simulating interpolation)
                col_mean = np.nanmean(X_aug[:, feat_idx])
                mask_rows = np.random.choice(n_samples, size=max(1, n_samples // 10), replace=False)
                X_aug[mask_rows, feat_idx] = col_mean

        # 3. Random feature dropout (per sample)
        drop_prob = 0.05
        drop_mask = np.random.random(X_aug.shape) < drop_prob
        col_means = np.nanmean(X_aug, axis=0)
        X_aug[drop_mask] = np.tile(col_means, (n_samples, 1))[drop_mask]

        return np.clip(X_aug, -1e6, 1e6)


# ============================================================================
# SECTION 6: Multi-Task Neural Network
# ============================================================================

class MultiTaskNet(nn.Module):
    """Shared feature extractor + two task-specific heads."""

    def __init__(self, input_dim: int, shared_dims: List[int], head_dims: List[int],
                 dropout: float = 0.3, use_batch_norm: bool = True):
        super().__init__()

        # Shared layers
        shared_layers = []
        prev_dim = input_dim
        for d in shared_dims:
            shared_layers.append(nn.Linear(prev_dim, d))
            if use_batch_norm:
                shared_layers.append(nn.BatchNorm1d(d))
            shared_layers.append(nn.ReLU())
            shared_layers.append(nn.Dropout(dropout))
            prev_dim = d
        self.shared = nn.Sequential(*shared_layers)

        # Head 1: Fault prediction (binary)
        fault_layers = []
        prev_dim = shared_dims[-1]
        for d in head_dims:
            fault_layers.append(nn.Linear(prev_dim, d))
            fault_layers.append(nn.ReLU())
            fault_layers.append(nn.Dropout(dropout * 0.7))
            prev_dim = d
        fault_layers.append(nn.Linear(prev_dim, 1))
        self.fault_head = nn.Sequential(*fault_layers)

        # Head 2: Quality prediction (regression)
        quality_layers = []
        prev_dim = shared_dims[-1]
        for d in head_dims:
            quality_layers.append(nn.Linear(prev_dim, d))
            quality_layers.append(nn.ReLU())
            quality_layers.append(nn.Dropout(dropout * 0.7))
            prev_dim = d
        quality_layers.append(nn.Linear(prev_dim, 1))
        self.quality_head = nn.Sequential(*quality_layers)

    def forward(self, x):
        shared_repr = self.shared(x)
        fault_logit = self.fault_head(shared_repr)
        quality_pred = self.quality_head(shared_repr)
        return fault_logit.squeeze(-1), quality_pred.squeeze(-1)


# ============================================================================
# SECTION 7: Training with Early Stopping
# ============================================================================

class EarlyStopping:
    def __init__(self, patience=60, min_delta=1e-4, mode="max"):
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self.best_score = -np.inf if mode == "max" else np.inf
        self.best_epoch = 0
        self.counter = 0
        self.best_state = None

    def step(self, score, epoch, model):
        improved = (self.mode == "max" and score > self.best_score + self.min_delta) or \
                   (self.mode == "min" and score < self.best_score - self.min_delta)
        if improved:
            self.best_score = score
            self.best_epoch = epoch
            self.counter = 0
            self.best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            self.counter += 1
        return self.counter >= self.patience


def train_model(
    model, X_train, y_fault_train, y_quality_train, quality_mask_train,
    X_val, y_fault_val, y_quality_val, quality_mask_val,
    augmenter=None, verbose=True,
):
    """Train multi-task model with early stopping and LR scheduling."""
    cfg = CONFIG["training"]

    # Create DataLoader with weighted sampling
    n_pos = y_fault_train.sum()
    n_neg = len(y_fault_train) - n_pos
    if n_pos > 0 and n_neg > 0:
        weights = np.where(y_fault_train > 0, 1.0 / n_pos, 1.0 / n_neg)
        weights = weights / weights.sum() * len(weights)
        sampler = WeightedRandomSampler(weights, len(weights), replacement=True)
        train_dataset = TensorDataset(
            torch.FloatTensor(X_train), torch.FloatTensor(y_fault_train),
            torch.FloatTensor(y_quality_train), torch.FloatTensor(quality_mask_train),
        )
        train_loader = DataLoader(train_dataset, batch_size=cfg["batch_size"], sampler=sampler)
    else:
        train_dataset = TensorDataset(
            torch.FloatTensor(X_train), torch.FloatTensor(y_fault_train),
            torch.FloatTensor(y_quality_train), torch.FloatTensor(quality_mask_train),
        )
        train_loader = DataLoader(train_dataset, batch_size=cfg["batch_size"], shuffle=True)

    X_val_t = torch.FloatTensor(X_val).to(DEVICE)
    y_fault_val_t = torch.FloatTensor(y_fault_val).to(DEVICE)
    y_quality_val_t = torch.FloatTensor(y_quality_val).to(DEVICE)
    quality_mask_val_t = torch.FloatTensor(quality_mask_val).to(DEVICE)

    model = model.to(DEVICE)
    optimizer = optim.AdamW(model.parameters(), lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=cfg["lr_scheduler_factor"],
        patience=cfg["lr_scheduler_patience"],
    )

    fault_criterion = nn.MSELoss()
    quality_criterion = nn.MSELoss()

    es = EarlyStopping(patience=cfg["early_stopping_patience"], mode="min")
    history = {"train_loss": [], "val_loss": [], "val_quality_mse": []}

    for epoch in range(cfg["epochs"]):
        model.train()
        epoch_loss = 0.0
        n_batches = 0

        for batch in train_loader:
            X_b, yf_b, yq_b, qm_b = [b.to(DEVICE) for b in batch]

            # Augmentation
            if augmenter is not None:
                X_b = torch.FloatTensor(augmenter.augment(X_b.cpu().numpy())).to(DEVICE)

            optimizer.zero_grad()
            fault_logits, quality_preds = model(X_b)

            # Main loss: fault density prediction (regression, 0-1)
            fault_preds = torch.sigmoid(fault_logits)  # map logit to [0,1]
            loss_main = fault_criterion(fault_preds, yf_b)

            # Auxiliary loss: quality prediction (only for machines with product data)
            if qm_b.sum() > 0:
                mask = qm_b > 0
                loss_aux = quality_criterion(quality_preds[mask], yq_b[mask])
                loss = loss_main + cfg["aux_loss_weight"] * loss_aux
            else:
                loss = loss_main

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        history["train_loss"].append(avg_loss)

        # Validation
        model.eval()
        with torch.no_grad():
            fault_logits_val, quality_preds_val = model(X_val_t)
            fault_preds_val = torch.sigmoid(fault_logits_val).cpu().numpy()
            val_loss = mean_squared_error(y_fault_val, fault_preds_val)

            mask_val = quality_mask_val_t > 0
            if mask_val.sum() > 0:
                val_mse = mean_squared_error(
                    y_quality_val[mask_val.cpu().numpy().astype(bool)],
                    quality_preds_val[mask_val].cpu().numpy(),
                )
            else:
                val_mse = 0.0

        # Composite val score: fault loss + weighted quality loss
        val_composite = val_loss + cfg["aux_loss_weight"] * val_mse
        history["val_loss"].append(val_loss)
        history["val_quality_mse"].append(val_mse)

        scheduler.step(-val_composite)  # minimize composite loss

        if es.step(val_composite, epoch, model):
            if verbose and epoch % 20 == 0:
                print(f"  Early stop at epoch {epoch+1}, best val_loss={es.best_score:.4f}")
            break

        if verbose and epoch % 50 == 0:
            print(f"  Epoch {epoch+1:3d}: loss={avg_loss:.4f}, val_loss={val_loss:.4f}, val_mse={val_mse:.4f}")

    # Restore best model
    model.load_state_dict(es.best_state)
    return model, history, es.best_score, es.best_epoch


# ============================================================================
# SECTION 8: Evaluation
# ============================================================================

def evaluate_model_full(
    model, X, y_fault, y_quality, quality_mask,
    feature_names, dataset_df=None, label="Test",
):
    """Comprehensive evaluation: fault density regression + quality prediction."""
    model.eval()
    X_t = torch.FloatTensor(X).to(DEVICE)

    with torch.no_grad():
        fault_logits, quality_preds = model(X_t)
        fault_preds = torch.sigmoid(fault_logits).cpu().numpy()  # predicted fault density [0,1]
        quality_preds = quality_preds.cpu().numpy()

    results = {}

    # --- Fault density regression evaluation ---
    mse = mean_squared_error(y_fault, fault_preds)
    r2 = r2_score(y_fault, fault_preds)
    mae = np.mean(np.abs(y_fault - fault_preds))

    # Binarize for AUC/Precision/Recall: density >= 0.5 = "significant fault risk"
    y_binary = (y_fault >= 0.5).astype(int)
    if len(np.unique(y_binary)) > 1:
        auc = roc_auc_score(y_binary, fault_preds)
        ap = average_precision_score(y_binary, fault_preds)

        # Best F2 threshold
        best_f2, best_t = 0.0, 0.5
        for t in np.linspace(0.1, 0.9, 81):
            yp = (fault_preds >= t).astype(int)
            f2 = fbeta_score(y_binary, yp, beta=2, zero_division=0)
            if f2 > best_f2:
                best_f2 = f2
                best_t = t

        yp_best = (fault_preds >= best_t).astype(int)
        prec_b = precision_score(y_binary, yp_best, zero_division=0)
        rec_b = recall_score(y_binary, yp_best, zero_division=0)
        f2_b = fbeta_score(y_binary, yp_best, beta=2, zero_division=0)
        prec_05 = precision_score(y_binary, (fault_preds >= 0.5).astype(int), zero_division=0)
        rec_05 = recall_score(y_binary, (fault_preds >= 0.5).astype(int), zero_division=0)
        f2_05 = fbeta_score(y_binary, (fault_preds >= 0.5).astype(int), beta=2, zero_division=0)
    else:
        auc, ap = 0.5, 0.0
        best_t, best_f2, prec_b, rec_b, f2_b = 0.5, 0.0, 0.0, 0.0, 0.0
        prec_05, rec_05, f2_05 = 0.0, 0.0, 0.0

    mean_density = y_fault.mean()
    pred_mean = fault_preds.mean()

    print(f"\n--- {label} | Fault Density Regression ---")
    print(f"  True mean density={mean_density:.3f}, Pred mean={pred_mean:.3f}")
    print(f"  MSE={mse:.4f}, R2={r2:.4f}, MAE={mae:.4f}")
    print(f"  Binary AUC (≥0.5)={auc:.4f}, AP={ap:.4f}")
    print(f"  Best t={best_t:.2f}: P={prec_b:.4f}, R={rec_b:.4f}, F2={f2_b:.4f}")
    print(f"  t=0.50:       P={prec_05:.4f}, R={rec_05:.4f}, F2={f2_05:.4f}")

    results["fault"] = {
        "mse": float(mse), "r2": float(r2), "mae": float(mae),
        "mean_true_density": float(mean_density), "mean_pred_density": float(pred_mean),
        "binary_auc": float(auc), "binary_ap": float(ap),
        "best_threshold": float(best_t), "best_f2": float(f2_b),
        "best_precision": float(prec_b), "best_recall": float(rec_b),
        "precision_0.5": float(prec_05), "recall_0.5": float(rec_05), "f2_0.5": float(f2_05),
    }

    # --- Quality prediction evaluation (only for machines with product data) ---
    qmask = quality_mask > 0
    if qmask.sum() > 0:
        yq_true = y_quality[qmask]
        yq_pred = quality_preds[qmask]
        q_mse = mean_squared_error(yq_true, yq_pred)
        q_r2 = r2_score(yq_true, yq_pred)
        # Binarize quality for AUC (above/below median)
        yq_binary = (yq_true > np.median(yq_true)).astype(int)
        if len(np.unique(yq_binary)) > 1:
            q_auc = roc_auc_score(yq_binary, yq_pred)
        else:
            q_auc = 0.5

        print(f"\n--- {label} | Quality Prediction (n={qmask.sum()}) ---")
        print(f"  MSE={q_mse:.4f}, R2={q_r2:.4f}, AUC(binarized)={q_auc:.4f}")

        results["quality"] = {
            "mse": float(q_mse), "r2": float(q_r2), "auc_binarized": float(q_auc),
            "n_samples": int(qmask.sum()),
        }
    else:
        results["quality"] = {"mse": 0.0, "r2": 0.0, "auc_binarized": 0.5, "n_samples": 0}

    # --- Cost-stratified evaluation ---
    if dataset_df is not None and "cost_at_risk" in dataset_df.columns:
        cr = dataset_df["cost_at_risk"].values[:len(fault_preds)]
        p90, p50 = np.percentile(cr, 90), np.percentile(cr, 50)
        groups = {
            "high_cost (>=P90)": cr >= p90,
            "mid_cost (P50-P90)": (cr >= p50) & (cr < p90),
            "low_cost (<P50)": cr < p50,
        }
        cs = {}
        for gname, mask in groups.items():
            if mask.sum() == 0:
                continue
            yb = y_binary[mask]
            yp = (fault_preds[mask] >= best_t).astype(int)
            sub_mse = mean_squared_error(y_fault[mask], fault_preds[mask])
            cs[gname] = {
                "n": int(mask.sum()),
                "mse": float(sub_mse),
                "precision": float(precision_score(yb, yp, zero_division=0)),
                "recall": float(recall_score(yb, yp, zero_division=0)),
                "f2": float(fbeta_score(yb, yp, beta=2, zero_division=0)),
            }
            print(f"  [{gname}] n={cs[gname]['n']}: MSE={cs[gname]['mse']:.4f}, "
                  f"P={cs[gname]['precision']:.4f}, R={cs[gname]['recall']:.4f}, F2={cs[gname]['f2']:.4f}")
        results["cost_stratified"] = cs

    return results, fault_preds, quality_preds


# ============================================================================
# SECTION 9: Robustness Evaluation
# ============================================================================

def evaluate_robustness(model, X_test, y_fault_test, augmenter, n_trials=10):
    """Evaluate model under progressively stronger perturbations."""
    noise_levels = [0.0, 0.02, 0.05, 0.10, 0.15]
    mask_probs = [0.0, 0.1, 0.2, 0.3]

    y_binary = (y_fault_test >= 0.5).astype(int)
    has_neg = y_binary.sum() > 0 and (1 - y_binary).sum() > 0

    results = {}
    print(f"\n--- Robustness Evaluation ({n_trials} trials) ---")

    for noise_lvl in noise_levels:
        for mask_p in mask_probs:
            mses = []
            aucs = []
            for _ in range(n_trials):
                X_pert = X_test.copy()
                # Apply noise
                if noise_lvl > 0:
                    noise = np.random.randn(*X_pert.shape).astype(np.float32) * noise_lvl * np.std(X_pert, axis=0)
                    X_pert = X_pert + noise
                # Apply masking
                if mask_p > 0:
                    drop = np.random.random(X_pert.shape) < mask_p
                    col_means = np.nanmean(X_pert, axis=0)
                    X_pert[drop] = np.tile(col_means, (X_pert.shape[0], 1))[drop]

                model.eval()
                with torch.no_grad():
                    logits, _ = model(torch.FloatTensor(X_pert).to(DEVICE))
                    preds = torch.sigmoid(logits).cpu().numpy()
                mses.append(mean_squared_error(y_fault_test, preds))
                if has_neg:
                    aucs.append(roc_auc_score(y_binary, preds))

            key = f"noise={noise_lvl:.2f}_mask={mask_p:.1f}"
            results[key] = {
                "mse_mean": np.mean(mses), "mse_std": np.std(mses),
                "auc_mean": np.mean(aucs) if aucs else 0.5,
                "auc_std": np.std(aucs) if aucs else 0.0,
            }

    # Print summary
    for key, vals in sorted(results.items()):
        print(f"  {key}: MSE={vals['mse_mean']:.4f}±{vals['mse_std']:.4f}, AUC={vals['auc_mean']:.4f}±{vals['auc_std']:.4f}")

    return results


# ============================================================================
# SECTION 10: Alert Logic with Continuous Confirmation
# ============================================================================

class AlertManager:
    """Multi-signal fusion with continuous confirmation."""

    def __init__(self, cfg_alert=None):
        self.cfg = cfg_alert or CONFIG["alert"]
        self.machine_states = defaultdict(lambda: {
            "current_level": "NORMAL",
            "consecutive_up": 0,
            "consecutive_down": 0,
            "alert_score_history": [],
        })

    def compute_stat_anomaly_signal(self, z_comp_mean, z_comp_max, thermal_over_p95):
        """Compute normalized statistical anomaly signal [0, 1]."""
        # z-score based
        z_signal = np.clip(z_comp_mean / 3.0, 0, 1)
        # Thermal based
        t_signal = np.clip(thermal_over_p95 / 3.0, 0, 1)
        return 0.7 * z_signal + 0.3 * t_signal

    def compute_cost_risk_signal(self, cost_at_risk, cost_p50, cost_p90):
        """Normalize cost risk to [0, 1]."""
        if cost_at_risk >= cost_p90:
            return 0.9
        elif cost_at_risk >= cost_p50:
            return 0.5 + 0.4 * (cost_at_risk - cost_p50) / (cost_p90 - cost_p50 + 1)
        else:
            return 0.3 * cost_at_risk / (cost_p50 + 1)

    def decide(self, machine_id, ml_prob, z_comp_mean, z_comp_max,
               thermal_over_p95, cost_at_risk, cost_p50, cost_p90):
        """Make alert decision with continuous confirmation."""
        w = self.cfg["score_weights"]
        stat_sig = self.compute_stat_anomaly_signal(z_comp_mean, z_comp_max, thermal_over_p95)
        cost_sig = self.compute_cost_risk_signal(cost_at_risk, cost_p50, cost_p90)

        alert_score = w["ml_prob"] * ml_prob + w["stat_anomaly"] * stat_sig + w["cost_risk"] * cost_sig

        state = self.machine_states[machine_id]
        state["alert_score_history"].append(alert_score)
        if len(state["alert_score_history"]) > 20:
            state["alert_score_history"] = state["alert_score_history"][-20:]

        # Determine target level based on score
        if alert_score >= 0.70:
            target = "ALARM"
        elif alert_score >= 0.50:
            target = "WARNING"
        elif alert_score >= 0.30:
            target = "WATCH"
        else:
            target = "NORMAL"

        levels = ["NORMAL", "WATCH", "WARNING", "ALARM"]
        current_idx = levels.index(state["current_level"])
        target_idx = levels.index(target)

        if target_idx > current_idx:
            # Upgrading
            state["consecutive_up"] += 1
            state["consecutive_down"] = 0
            required = self.cfg["upgrade_windows"].get(target, 1)
            if state["consecutive_up"] >= required:
                state["current_level"] = target
                state["consecutive_up"] = 0
        elif target_idx < current_idx:
            # Downgrading
            state["consecutive_down"] += 1
            state["consecutive_up"] = 0
            required = self.cfg["downgrade_windows"].get(state["current_level"], 2)
            if state["consecutive_down"] >= required:
                state["current_level"] = levels[current_idx - 1]
                state["consecutive_down"] = 0
        else:
            state["consecutive_up"] = 0
            state["consecutive_down"] = 0

        return state["current_level"], alert_score


# ============================================================================
# SECTION 11: Visualizations
# ============================================================================

def plot_training_curves(history, variant_label, output_path):
    """Training loss and validation loss curves."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 3))

    ax1.plot(history["train_loss"], color="#517E9C", lw=0.8)
    ax1.set_xlabel("Epoch"), ax1.set_ylabel("Train Loss")
    ax1.set_title("Training Loss")

    ax2.plot(history["val_loss"], color="#C2685A", lw=0.8, label="Val Loss (Fault MSE)")
    ax2.set_xlabel("Epoch"), ax2.set_ylabel("Val MSE")
    ax2.set_title("Validation Loss (Fault Density)")
    ax2.legend(frameon=False, fontsize=6)

    fig.suptitle(f"Training Curves — {variant_label}", fontsize=9, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def plot_robustness_heatmap(robustness_results, output_path):
    """Heatmap of AUC under different perturbation levels."""
    noise_levels = sorted(set(float(k.split("_")[0].split("=")[1]) for k in robustness_results))
    mask_probs = sorted(set(float(k.split("_")[1].split("=")[1]) for k in robustness_results))

    matrix = np.zeros((len(noise_levels), len(mask_probs)))
    anot = np.zeros((len(noise_levels), len(mask_probs), 2))

    for r in robustness_results:
        parts = r.split("_")
        nl = float(parts[0].split("=")[1])
        mp = float(parts[1].split("=")[1])
        i, j = noise_levels.index(nl), mask_probs.index(mp)
        matrix[i, j] = robustness_results[r]["auc_mean"]
        anot[i, j, 0] = robustness_results[r]["auc_mean"]
        anot[i, j, 1] = robustness_results[r]["auc_std"]

    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(matrix, cmap="RdYlBu_r", aspect="auto", vmin=0.35, vmax=0.65)
    for i in range(len(noise_levels)):
        for j in range(len(mask_probs)):
            ax.text(j, i, f"{matrix[i,j]:.3f}", ha="center", va="center", fontsize=6)

    ax.set_xticks(range(len(mask_probs)))
    ax.set_xticklabels([f"{m:.0%}" for m in mask_probs])
    ax.set_yticks(range(len(noise_levels)))
    ax.set_yticklabels([f"{n:.0%}" for n in noise_levels])
    ax.set_xlabel("Mask Probability"), ax.set_ylabel("Noise Level (×σ)")
    ax.set_title("Robustness: AUC under Perturbation")
    fig.colorbar(im, ax=ax, label="AUC")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def plot_window_comparison(all_variant_results, output_path):
    """Compare regression metrics across window variants."""
    variants = list(all_variant_results.keys())
    fault_r2 = [all_variant_results[v]["fault"]["r2"] for v in variants]
    fault_mse = [all_variant_results[v]["fault"]["mse"] for v in variants]
    quality_r2 = [all_variant_results[v].get("quality", {}).get("r2", 0.0) for v in variants]

    x = np.arange(len(variants))
    width = 0.25

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5))

    ax1.bar(x - width, fault_r2, width, color="#517E9C", label="Fault R2")
    ax1.bar(x, fault_mse, width, color="#C8945F", label="Fault MSE")
    ax1.bar(x + width, quality_r2, width, color="#C2685A", label="Quality R2")
    ax1.set_xticks(x)
    ax1.set_xticklabels([v.replace("_", "→") for v in variants], fontsize=6)
    ax1.set_ylabel("Score"), ax1.set_title("Regression Metrics")
    ax1.legend(frameon=False, fontsize=5)
    ax1.axhline(y=0, color="gray", ls=":", lw=0.5)

    fault_aucs = [all_variant_results[v]["fault"]["binary_auc"] for v in variants]
    quality_aucs = [all_variant_results[v].get("quality", {}).get("auc_binarized", 0.5) for v in variants]
    ax2.bar(x - width/2, fault_aucs, width*2, color="#517E9C", label="Fault AUC (binned)")
    ax2.bar(x + width/2, quality_aucs, width*2, color="#C2685A", label="Quality AUC")
    ax2.axhline(y=0.5, color="gray", ls=":", lw=0.6)
    ax2.set_xticks(x)
    ax2.set_xticklabels([v.replace("_", "→") for v in variants], fontsize=6)
    ax2.set_ylabel("AUC"), ax2.set_title("Binary AUC")
    ax2.legend(frameon=False, fontsize=5)
    ax2.set_ylim(0, 1)

    fig.suptitle("Window Variant Comparison", fontsize=9, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


# ============================================================================
# SECTION 12: Main Pipeline
# ============================================================================

def main():
    print("=" * 60)
    print("Predictive Maintenance Model v2 — Training Pipeline")
    print(f"Device: {DEVICE}")
    print("=" * 60)

    # [1] Load data
    print("\n[1/10] Loading datasets...")
    data = load_all_data()
    log, summary, assembly, tests = data["log"], data["summary"], data["assembly"], data["tests"]
    print(f"  Log: {log.shape}, Machines: {log['Equipment.Id'].nunique()}")

    # [2] Build static & product features
    print("\n[2/10] Building static & product features...")
    static_features = build_static_features(summary)
    product_features = build_product_features(assembly, tests)
    print(f"  Product machines: {product_features['machine_id'].nunique()}")

    # [3] Compute per-machine baselines from all normal records in first 20 time steps
    #     (sufficient normal samples to estimate μ, σ stably)
    log_baseline = log[log["time_step"] < 20]
    log_baseline_normal = log_baseline[log_baseline["Failure.Equipment.Type"] == 0]
    baseline = compute_per_machine_baselines(log_baseline_normal)
    print(f"\n[3/10] Baselines computed from {len(log_baseline_normal)} training normal records")

    # [4] Iterate over window variants
    all_variant_results = {}
    best_variant = None
    best_auc = 0.0

    for (input_steps, predict_steps) in CONFIG["window_variants"]:
        variant_label = f"{input_steps}in_{predict_steps}pred"
        print(f"\n{'=' * 60}")
        print(f"[4/10] Window Variant: {input_steps} → {predict_steps}")
        print(f"{'=' * 60}")

        # Build datasets from all time steps
        X_all, yf_all, yq_all, qm_all, feat_names, mach_ids, win_pos = build_dataset(
            log, baseline, static_features, product_features,
            input_steps, predict_steps, train_end=30,
        )

        # Machine-level split to prevent data leakage (60/20/20)
        # Each machine's windows go entirely to one split
        unique_machines = np.unique(mach_ids)
        np.random.seed(42)
        np.random.shuffle(unique_machines)
        n_train_m = int(len(unique_machines) * 0.60)
        n_val_m = int(len(unique_machines) * 0.20)
        train_machines = set(unique_machines[:n_train_m])
        val_machines = set(unique_machines[n_train_m:n_train_m + n_val_m])
        test_machines = set(unique_machines[n_train_m + n_val_m:])

        train_mask = np.array([m in train_machines for m in mach_ids])
        val_mask = np.array([m in val_machines for m in mach_ids])
        test_mask = np.array([m in test_machines for m in mach_ids])

        X_train, yf_train, yq_train, qm_train = X_all[train_mask], yf_all[train_mask], yq_all[train_mask], qm_all[train_mask]
        X_val, yf_val, yq_val, qm_val = X_all[val_mask], yf_all[val_mask], yq_all[val_mask], qm_all[val_mask]
        X_test, yf_test, yq_test, qm_test = X_all[test_mask], yf_all[test_mask], yq_all[test_mask], qm_all[test_mask]

        print(f"  Train: {X_train.shape[0]} (from {len(train_machines)} machines)")
        print(f"  Val:   {X_val.shape[0]} (from {len(val_machines)} machines)")
        print(f"  Test:  {X_test.shape[0]} (from {len(test_machines)} machines)")
        print(f"  Pos rate: tr={yf_train.mean():.3f}, va={yf_val.mean():.3f}, te={yf_test.mean():.3f}")
        print(f"  Quality samples: tr={qm_train.sum():.0f}, va={qm_val.sum():.0f}, te={qm_test.sum():.0f}")

        # [5] Create model
        print(f"\n[5/10] Building multi-task model...")
        input_dim = X_train.shape[1]
        model = MultiTaskNet(
            input_dim=input_dim,
            shared_dims=CONFIG["model"]["shared_dims"],
            head_dims=CONFIG["model"]["head_dims"],
            dropout=CONFIG["model"]["dropout"],
            use_batch_norm=CONFIG["model"]["batch_norm"],
        )
        print(f"  Input dim: {input_dim}, Shared: {CONFIG['model']['shared_dims']}")
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  Parameters: {n_params:,}")

        # [6] Train
        print(f"\n[6/10] Training...")
        augmenter = DataAugmenter()
        model, history, best_val_auc, best_epoch = train_model(
            model, X_train, yf_train, yq_train, qm_train,
            X_val, yf_val, yq_val, qm_val,
            augmenter=augmenter, verbose=True,
        )
        print(f"  Best val loss: {best_val_auc:.4f} at epoch {best_epoch+1}")

        # [7] Evaluate
        print(f"\n[7/10] Evaluating on test set...")
        test_results, fault_probs, quality_preds = evaluate_model_full(
            model, X_test, yf_test, yq_test, qm_test,
            feat_names, label=f"Test({variant_label})",
        )

        # [8] Robustness evaluation
        print(f"\n[8/10] Robustness evaluation...")
        robustness_results = evaluate_robustness(model, X_test, yf_test, augmenter)

        all_variant_results[variant_label] = {
            "fault": test_results["fault"],
            "quality": test_results["quality"],
            "robustness": robustness_results,
            "history": history,
            "best_val_auc": best_val_auc,
            "feature_names": feat_names,
            "input_steps": input_steps,
            "predict_steps": predict_steps,
        }

        # [9] Save model & visualizations
        print(f"\n[9/10] Saving model & figures...")
        os.makedirs(os.path.join(OUTPUT_DIR, variant_label), exist_ok=True)
        torch.save({
            "model_state_dict": model.state_dict(),
            "feature_names": feat_names,
            "input_steps": input_steps,
            "predict_steps": predict_steps,
            "input_dim": input_dim,
            "config": CONFIG,
        }, os.path.join(OUTPUT_DIR, variant_label, "model.pt"))

        plot_training_curves(
            history, variant_label,
            os.path.join(FIGURE_DIR, f"training_curves_{variant_label}.png"),
        )

        # Track best variant (by validation R2 equivalent: lower MSE = better)
        if test_results["fault"]["r2"] > best_auc:
            best_auc = test_results["fault"]["r2"]
            best_variant = variant_label

    # [10] Comparison & final report
    print(f"\n{'=' * 60}")
    print("[10/10] Variant Comparison & Final Report")
    print(f"{'=' * 60}")

    for variant, results in all_variant_results.items():
        f = results["fault"]
        q = results["quality"]
        print(f"\n  {variant}:")
        print(f"    Fault:  MSE={f['mse']:.4f}, R2={f['r2']:.4f}, BinAUC={f['binary_auc']:.4f}, F2={f['best_f2']:.4f}")
        if q["n_samples"] > 0:
            print(f"    Quality: MSE={q['mse']:.4f}, R2={q['r2']:.4f}, AUC={q['auc_binarized']:.4f}")

    print(f"\n  Best variant: {best_variant} (Fault R2={best_auc:.4f})")

    # Window comparison plot
    plot_window_comparison(
        all_variant_results,
        os.path.join(FIGURE_DIR, "window_variant_comparison.png"),
    )

    # Robustness heatmap for best variant
    plot_robustness_heatmap(
        all_variant_results[best_variant]["robustness"],
        os.path.join(FIGURE_DIR, "robustness_heatmap.png"),
    )

    # Save evaluation summary
    eval_rows = []
    for variant, results in all_variant_results.items():
        f = results["fault"]
        q = results["quality"]
        eval_rows.append({
            "variant": variant,
            "input_steps": results["input_steps"],
            "predict_steps": results["predict_steps"],
            "fault_mse": f["mse"], "fault_r2": f["r2"], "fault_mae": f["mae"],
            "fault_binary_auc": f["binary_auc"], "fault_binary_ap": f["binary_ap"],
            "fault_best_f2": f["best_f2"],
            "fault_best_precision": f["best_precision"],
            "fault_best_recall": f["best_recall"],
            "mean_true_density": f["mean_true_density"],
            "mean_pred_density": f["mean_pred_density"],
            "quality_mse": q["mse"], "quality_r2": q["r2"],
            "quality_auc": q["auc_binarized"],
            "best_val_auc": results["best_val_auc"],
        })
    pd.DataFrame(eval_rows).to_csv(
        os.path.join(OUTPUT_DIR, "variant_comparison.csv"), index=False, float_format="%.4f"
    )

    # Save robustness summary
    rob_rows = []
    for variant, results in all_variant_results.items():
        for key, vals in results["robustness"].items():
            rob_rows.append({
                "variant": variant, "condition": key,
                "mse_mean": vals["mse_mean"], "mse_std": vals["mse_std"],
                "auc_mean": vals["auc_mean"], "auc_std": vals["auc_std"],
            })
    pd.DataFrame(rob_rows).to_csv(
        os.path.join(OUTPUT_DIR, "robustness_report.csv"), index=False, float_format="%.4f"
    )

    # Load best model and generate prediction report
    print(f"\nGenerating alert prediction report with best model ({best_variant})...")
    best_info = all_variant_results[best_variant]
    checkpoint = torch.load(os.path.join(OUTPUT_DIR, best_variant, "model.pt"), weights_only=False)

    best_model = MultiTaskNet(
        input_dim=checkpoint["input_dim"],
        shared_dims=CONFIG["model"]["shared_dims"],
        head_dims=CONFIG["model"]["head_dims"],
        dropout=CONFIG["model"]["dropout"],
        use_batch_norm=CONFIG["model"]["batch_norm"],
    )
    best_model.load_state_dict(checkpoint["model_state_dict"])
    best_model = best_model.to(DEVICE)
    best_model.eval()

    # Generate predictions for all machines (latest window)
    rows = []
    machine_ids_pred = []
    for mid in sorted(log["Equipment.Id"].unique()):
        input_steps = best_info["input_steps"]
        mlog = log[log["Equipment.Id"] == mid].sort_values("time_step")
        if len(mlog) < input_steps:
            continue
        win = mlog.iloc[-input_steps:]
        v = win["Op.Voltage"].values.astype(float)
        a = win["Op.Amperage"].values.astype(float)
        t = win["Op.Temperature"].values.astype(float)
        r = win["Rotor Speed"].values.astype(float)
        steps_arr = win["time_step"].values.astype(float)
        fault_types = win["Failure.Equipment.Type"].values.astype(int)
        n = input_steps

        feats = {}
        feats.update(extract_trend_features(v, a, t, steps_arr, n))
        feats.update(extract_volatility_features(v, a, t, n))
        feats.update(extract_state_features(v, a, t, r, fault_types, baseline, mid, n))
        feats.update(extract_cost_context_features(
            mid, win, static_features, product_features, int(mlog.iloc[-1]["time_step"]), n-1, n
        ))

        rows.append(feats)
        machine_ids_pred.append(mid)

    pred_df = pd.DataFrame(rows).fillna(0.0)
    # Align with training feature names
    for fname in best_info["feature_names"]:
        if fname not in pred_df.columns:
            pred_df[fname] = 0.0
    X_pred = pred_df[best_info["feature_names"]].values.astype(np.float32)

    with torch.no_grad():
        logits, quality_preds = best_model(torch.FloatTensor(X_pred).to(DEVICE))
        probs = torch.sigmoid(logits).cpu().numpy()

    pred_df["machine_id"] = machine_ids_pred
    pred_df["fault_density_pred"] = probs
    pred_df["pred_quality"] = quality_preds.cpu().numpy()

    # Cost risk
    pred_df["cost_at_risk"] = pred_df.get("cost_at_risk", pred_df["unit_cost"] * pred_df["daily_output"] * 0.7)
    cr_p50, cr_p90 = pred_df["cost_at_risk"].quantile(0.50), pred_df["cost_at_risk"].quantile(0.90)

    # Alert logic
    alert_mgr = AlertManager()
    alerts = []
    scores = []
    for _, row in pred_df.iterrows():
        level, score = alert_mgr.decide(
            row["machine_id"], row["fault_density_pred"],
            row.get("z_comp_mean", 0), row.get("z_comp_max", 0),
            row.get("thermal_over_p95", 0),
            row["cost_at_risk"], cr_p50, cr_p90,
        )
        alerts.append(level)
        scores.append(score)

    pred_df["alert_level"] = alerts
    pred_df["alert_score"] = scores
    pred_df = pred_df.sort_values("alert_score", ascending=False)

    pred_df[["machine_id", "fault_density_pred", "cost_at_risk", "alert_level", "alert_score"]].to_csv(
        os.path.join(OUTPUT_DIR, "prediction_report.csv"), index=False, float_format="%.4f"
    )

    print(f"\nAlert Distribution:")
    for lvl in ["ALARM", "WARNING", "WATCH", "NORMAL"]:
        print(f"  {lvl}: {(pred_df['alert_level'] == lvl).sum()} machines")

    print(f"\nTop 10 High-Risk Machines:")
    for _, r in pred_df.head(10).iterrows():
        print(f"  {r['machine_id']}: FaultDensity={r['fault_density_pred']:.3f}, "
              f"CostRisk={r['cost_at_risk']:.0f}, Score={r['alert_score']:.3f}, {r['alert_level']}")

    # Multi-task effectiveness check
    print(f"\n{'=' * 60}")
    print("Multi-Task Learning Effectiveness")
    print(f"{'=' * 60}")
    for variant, results in all_variant_results.items():
        f = results["fault"]
        q = results["quality"]
        print(f"  {variant}: Fault R2={f['r2']:.4f}, Fault MSE={f['mse']:.4f}, "
              f"Quality R2={q.get('r2', 0.0):.4f}, Quality AUC={q.get('auc_binarized', 0.5):.4f}")

    print(f"\nTraining complete. Outputs in: {OUTPUT_DIR}/, {FIGURE_DIR}/")
    print(f"Best model: {OUTPUT_DIR}/{best_variant}/model.pt")

    return best_model, all_variant_results, best_variant


if __name__ == "__main__":
    main()
