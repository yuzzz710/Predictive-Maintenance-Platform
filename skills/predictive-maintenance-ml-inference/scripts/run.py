#!/usr/bin/env python3
"""
Skill 3: predictive-maintenance-ml-inference — Runner Script
=============================================================
Train ML models (XGBoost v1 or MTNN v2) and generate fault-density predictions.

Usage:
    # XGBoost (v1, fast):
    python run.py --data-dir <raw_data> --prep-dir <data_prep_output> --output-dir <output> --model v1

    # Multi-Task Neural Network (v2, PyTorch):
    python run.py --data-dir <raw_data> --prep-dir <data_prep_output> --output-dir <output> --model v2
"""

import sys, os, argparse, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_v1(data_dir, prep_dir, output_dir):
    """XGBoost dual-model pipeline."""
    import model_training as mt

    # Override paths
    mt.DATA_DIR = data_dir
    mt.OUTPUT_DIR = output_dir
    mt.FIGURE_DIR = os.path.join(output_dir, "figures")
    os.makedirs(mt.OUTPUT_DIR, exist_ok=True)
    os.makedirs(mt.FIGURE_DIR, exist_ok=True)

    print("Running XGBoost v1 pipeline...")
    mt.main()

    # mt.main() saves to OUTPUT_DIR; return paths
    pred_path = os.path.join(output_dir, "prediction_report.csv")
    model_path = os.path.join(output_dir, "model.json")
    return pred_path, model_path


def run_v2(data_dir, prep_dir, output_dir):
    """Multi-Task Neural Network pipeline."""
    import model_training_v2 as mt2

    mt2.DATA_DIR = data_dir
    mt2.OUTPUT_DIR = os.path.join(output_dir, "model_outputs")
    mt2.FIGURE_DIR = os.path.join(output_dir, "figures")
    os.makedirs(mt2.OUTPUT_DIR, exist_ok=True)
    os.makedirs(mt2.FIGURE_DIR, exist_ok=True)

    print("Running MTNN v2 pipeline...")
    mt2.main()

    pred_path = os.path.join(mt2.OUTPUT_DIR, "prediction_report.csv")
    return pred_path, None


def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance — ML Inference"
    )
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing raw CSV files")
    parser.add_argument("--prep-dir", required=True,
                        help="Directory containing data-prep outputs")
    parser.add_argument("--output-dir", default="outputs_ml",
                        help="Directory for output files")
    parser.add_argument("--model", choices=["v1", "v2"], default="v1",
                        help="Model version: v1 (XGBoost) or v2 (MTNN)")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    prep_dir = os.path.abspath(args.prep_dir)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Data directory    : {data_dir}")
    print(f"Data-prep outputs : {prep_dir}")
    print(f"Output directory  : {output_dir}")
    print(f"Model version     : {args.model}")

    if args.model == "v1":
        pred_path, model_path = run_v1(data_dir, prep_dir, output_dir)
    else:
        pred_path, model_path = run_v2(data_dir, prep_dir, output_dir)

    # Write manifest
    manifest = {
        "model_version": args.model,
        "data_dir": data_dir,
        "prep_dir": prep_dir,
        "output_dir": output_dir,
        "prediction_report": os.path.relpath(pred_path, output_dir) if pred_path and os.path.exists(pred_path) else None,
        "model_file": os.path.relpath(model_path, output_dir) if model_path and os.path.exists(model_path) else None,
    }
    with open(os.path.join(output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    if pred_path and os.path.exists(pred_path):
        pred_df = pd.read_csv(pred_path)
        print(f"\nPrediction report: {pred_df.shape[0]} machines")
        print(f"Columns: {list(pred_df.columns)}")
        print(f"\nOutput files written to: {output_dir}/")
    else:
        # Try alternate filename
        alt_path = os.path.join(output_dir, "prediction_report_all_machines.csv")
        if os.path.exists(alt_path):
            print(f"\nPrediction report: {alt_path}")
            print(f"\nOutput files written to: {output_dir}/")
        else:
            print("\nWarning: prediction report not found. Check training logs.")

    print("\nML inference complete.")


if __name__ == "__main__":
    main()
