#!/usr/bin/env python3
"""
Skill 1: predictive-maintenance-data-prep — Runner Script
==========================================================
Load raw CNC machine data, build per-machine statistical baselines,
compute z-scores, construct cost-risk matrix.

Usage:
    python run.py --data-dir <path_to_4_csv_files> --output-dir <output_path>
    python run.py <data_dir> <output_dir>
"""

import sys, os, argparse, json

# Ensure local scripts/ is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_analysis import run_baseline_pipeline, CONFIG


def main():
    parser = argparse.ArgumentParser(
        description="Predictive Maintenance — Data Preparation"
    )
    parser.add_argument("data_dir", nargs="?", default=".",
                        help="Directory containing the 4 raw CSV files")
    parser.add_argument("output_dir", nargs="?", default="outputs",
                        help="Directory for output CSV files")
    parser.add_argument("--data-dir", dest="data_dir_long", default=None)
    parser.add_argument("--output-dir", dest="output_dir_long", default=None)
    args = parser.parse_args()

    data_dir = args.data_dir_long or args.data_dir
    output_dir = args.output_dir_long or args.output_dir

    data_dir = os.path.abspath(data_dir)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Data directory : {data_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Config thresholds: Watch={CONFIG['z_thresholds']['watch']}, "
          f"Warning={CONFIG['z_thresholds']['warning']}, "
          f"Alarm={CONFIG['z_thresholds']['alarm']}")

    # Run the full baseline pipeline
    results = run_baseline_pipeline(data_dir)

    # Save all outputs to the specified output directory
    results["df_z"].to_csv(os.path.join(output_dir, "z_scores.csv"), index=False)
    results["cost_risk"].to_csv(os.path.join(output_dir, "cost_risk_matrix.csv"), index=False)
    results["sig_df"].to_csv(os.path.join(output_dir, "failure_signatures.csv"), index=False)
    results["var_decomp"].to_csv(os.path.join(output_dir, "variance_decomposition.csv"), index=False)
    results["t2_df"].to_csv(os.path.join(output_dir, "hotelling_t2.csv"), index=False)
    results["clusters"].to_csv(os.path.join(output_dir, "machine_clusters.csv"), index=False)
    results["baseline"].to_csv(os.path.join(output_dir, "baseline_stats.csv"), index=True)

    # Save z-eval summary as JSON
    z_eval_summary = {
        "best_f1_threshold": results["z_eval"]["best_f1"]["threshold"],
        "best_f1": results["z_eval"]["best_f1"]["f1"],
        "best_precision": results["z_eval"]["best_f1"]["precision"],
        "best_recall": results["z_eval"]["best_f1"]["recall"],
        "best_fpr": results["z_eval"]["best_f1"]["fpr"],
    }
    with open(os.path.join(output_dir, "z_eval_summary.json"), "w") as f:
        json.dump(z_eval_summary, f, indent=2)

    # Save the text report
    with open(os.path.join(output_dir, "summary_report.txt"), "w", encoding="utf-8") as f:
        f.write(results["report"])

    # Write a manifest so downstream skills know where to find things
    manifest = {
        "data_dir": data_dir,
        "output_dir": output_dir,
        "files": {
            "z_scores": "z_scores.csv",
            "cost_risk_matrix": "cost_risk_matrix.csv",
            "failure_signatures": "failure_signatures.csv",
            "variance_decomposition": "variance_decomposition.csv",
            "hotelling_t2": "hotelling_t2.csv",
            "machine_clusters": "machine_clusters.csv",
            "baseline_stats": "baseline_stats.csv",
            "z_eval_summary": "z_eval_summary.json",
            "summary_report": "summary_report.txt",
        },
        "n_machines": len(results["cost_risk"]),
        "n_stable_baselines": int((results["baseline"]["baseline_quality"] == "stable").sum()),
        "n_sparse_baselines": int((results["baseline"]["baseline_quality"] == "sparse").sum()),
    }
    with open(os.path.join(output_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    print(f"\nOutput files written to: {output_dir}/")
    for fname in manifest["files"].values():
        fpath = os.path.join(output_dir, fname)
        size_kb = os.path.getsize(fpath) / 1024 if os.path.exists(fpath) else 0
        print(f"  {fname} ({size_kb:.1f} KB)")

    print(f"\nMachines: {manifest['n_machines']}")
    print(f"Stable baselines: {manifest['n_stable_baselines']}")
    print(f"Sparse baselines: {manifest['n_sparse_baselines']}")
    return results


if __name__ == "__main__":
    main()
