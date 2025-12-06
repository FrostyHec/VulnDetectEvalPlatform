import os
import sys
import subprocess
import json
import csv

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
sys.path.insert(0, project_root)

from src.common.config.envs import DATASET_DIR

def run_test():
    print("Step 1: Running dataset extraction (max_samples=5)...")
    script_path = os.path.join(current_dir, "dataset_patch_to_primevul_format.py")
    cmd = [sys.executable, script_path, "--max_samples", "5"]
    
    ret = subprocess.run(cmd, capture_output=True, text=True)
    print(ret.stdout)
    if ret.returncode != 0:
        print("Error running extraction:")
        print(ret.stderr)
        sys.exit(1)
        
    # Verify ds.jsonl
    jsonl_path = os.path.join(DATASET_DIR, "dataset_patch", "primevul_format", "ds.jsonl")
    if not os.path.exists(jsonl_path):
        print("Error: ds.jsonl not created")
        sys.exit(1)
        
    with open(jsonl_path, 'r') as f:
        lines = f.readlines()
        print(f"Generated {len(lines)} samples in ds.jsonl")
        if len(lines) == 0:
            print("Warning: No samples generated. Check case_summary.csv")
            
    # Verify summary
    summary_path = os.path.join(DATASET_DIR, "dataset_patch", "primevul_format", "case_summary.csv")
    if os.path.exists(summary_path):
        with open(summary_path, 'r') as f:
            print("Summary content:")
            print(f.read())
            
    print("\nStep 2: Running dataset splitting...")
    split_script = os.path.join(current_dir, "split_dataset.py")
    cmd = [sys.executable, split_script]
    
    ret = subprocess.run(cmd, capture_output=True, text=True)
    print(ret.stdout)
    if ret.returncode != 0:
        print("Error running splitting:")
        print(ret.stderr)
        sys.exit(1)
        
    # Verify index_split.csv
    split_index = os.path.join(DATASET_DIR, "dataset_patch", "primevul_format", "index_split.csv")
    if os.path.exists(split_index):
        with open(split_index, 'r') as f:
            lines = f.readlines()
            print(f"Generated {len(lines)-1} entries in index_split.csv")
            
    print("\nTest Completed Successfully.")

if __name__ == "__main__":
    run_test()
