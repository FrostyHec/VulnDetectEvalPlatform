import os
import sys
import json
import csv

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
sys.path.insert(0, project_root)

from src.common.config.envs import DATASET_DIR

PRIMEVUL_DIR = os.path.join(DATASET_DIR, "dataset_patch", "primevul_format")
os.makedirs(PRIMEVUL_DIR, exist_ok=True)
INPUT_JSONL = os.path.join(PRIMEVUL_DIR, "ds.jsonl")
OUTPUT_INDEX = os.path.join(PRIMEVUL_DIR, "index_split.csv")

def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"Error: {INPUT_JSONL} not found.")
        return

    data = []
    with open(INPUT_JSONL, 'r') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    
    print(f"Loaded {len(data)} samples.")
    
    # Group by CVE ID to keep pairs together
    # Use the latest commit time in the group (usually the fix) as the sort key
    groups = {}
    for item in data:
        cve = item['cve_id']
        if cve not in groups:
            groups[cve] = []
        groups[cve].append(item)
    
    # Sort groups by time
    # We use the maximum commit time in the group (the fix time)
    sorted_cves = sorted(groups.keys(), key=lambda k: max(x['commit_time'] for x in groups[k]))
    
    total_cves = len(sorted_cves)
    n_train = int(total_cves * 0.8)
    n_val = int(total_cves * 0.1)
    
    train_cves = set(sorted_cves[:n_train])
    val_cves = set(sorted_cves[n_train:n_train+n_val])
    test_cves = set(sorted_cves[n_train+n_val:])
    
    print(f"Split: Train={len(train_cves)}, Val={len(val_cves)}, Test={len(test_cves)}")
    
    # Generate Index
    index_rows = []
    for item in data:
        cve = item['cve_id']
        split = "train"
        if cve in val_cves: split = "val"
        elif cve in test_cves: split = "test"
        
        index_rows.append({
            "id": item['id'],
            "split": split
        })
    
    with open(OUTPUT_INDEX, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=["id", "split"])
        writer.writeheader()
        writer.writerows(index_rows)
        
    print(f"Generated split index at {OUTPUT_INDEX}")

if __name__ == "__main__":
    main()
