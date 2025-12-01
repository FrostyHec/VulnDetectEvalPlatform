import os
import csv
import sys
import subprocess
import concurrent.futures
import threading
from collections import defaultdict

# Add the src directory to sys.path to allow imports from common
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.common.config.envs import DATASET_DIR
except ImportError:
    src_path = os.path.join(project_root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from common.config.envs import DATASET_DIR

def get_repo_name_from_url(url):
    if not url: return None
    parts = url.strip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}_{parts[-1]}"
    return "unknown_repo"

def log_failure(entry, error_msg, log_dir):
    # entry: dict with keys project_type, vuln_type, cve_id, etc.
    # Log to dataset/dataset_patch/check/index_failure/...
    
    failure_root = os.path.join(DATASET_DIR, "dataset_patch", "check", "index_failure")
    
    # 1. Append to index.csv
    index_file = os.path.join(failure_root, "index.csv")
    os.makedirs(failure_root, exist_ok=True)
    
    file_exists = os.path.exists(index_file)
    
    # Use a lock for file writing if we were parallelizing this part, 
    # but we will collect failures and write them, or write atomically.
    # For simplicity in this script, we'll assume single-threaded writing or use a lock.
    
    with open(index_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["project_type", "vuln_type", "cve_id"])
        writer.writerow([entry["project_type"], entry["vuln_type"], entry["cve_id"]])
        
    # 2. Create detailed log file
    # Structure: failure_root / project_type / vuln_type / cve_id / failure.log
    log_path = os.path.join(failure_root, entry["project_type"], entry["vuln_type"], entry["cve_id"])
    os.makedirs(log_path, exist_ok=True)
    
    with open(os.path.join(log_path, "failure.log"), "w", encoding="utf-8") as f:
        f.write(error_msg)

def check_patch_application(repo_path, last_vuln_commit, patch_commits):
    # Returns (Success: bool, Message: str)
    
    if not os.path.exists(repo_path):
        return False, f"Repository not found at {repo_path}"
        
    if last_vuln_commit == "unknown":
        return False, "last_vuln_commit is unknown"
        
    # We need to be careful about modifying the repo state if other threads are using it.
    # Strategy: Since we are grouping by repo, we can assume exclusive access to this repo object 
    # (if we implement the grouping correctly in the main loop).
    
    try:
        # 1. Reset to last_vuln_commit
        # -f to force discard changes
        subprocess.run(["git", "checkout", "-f", last_vuln_commit], cwd=repo_path, check=True, capture_output=True)
        
        # 2. Apply patches
        # We use cherry-pick. If it's a merge commit, it might fail or need -m 1.
        # Assuming standard commits for now.
        
        for commit in patch_commits:
            # Try cherry-pick
            # -n: no commit, just apply changes to index/worktree (optional, but we want to see if it applies)
            # Actually, if we want to verify we can reach the fixed state, we should let it commit.
            # But we don't want to pollute the reflog too much? It's a detached HEAD, so it's fine.
            
            # Check if commit exists first?
            # git cat-file -t commit
            
            proc = subprocess.run(["git", "cherry-pick", commit], cwd=repo_path, capture_output=True, text=True)
            
            if proc.returncode != 0:
                # Cherry-pick failed.
                # Check if it might be a merge commit issue
                # Try with -m 1 (mainline parent)
                proc_merge = subprocess.run(["git", "cherry-pick", "-m", "1", commit], cwd=repo_path, capture_output=True, text=True)
                
                if proc_merge.returncode != 0:
                    # Both failed
                    subprocess.run(["git", "cherry-pick", "--abort"], cwd=repo_path, capture_output=True)
                    return False, f"Failed to cherry-pick {commit} on top of {last_vuln_commit}.\nStandard: {proc.stderr}\nMerge (-m 1): {proc_merge.stderr}"
                
        return True, "Success"
        
    except subprocess.CalledProcessError as e:
        return False, f"Git command failed: {e}"
    except Exception as e:
        return False, f"Exception: {e}"

def process_repo_group(repo_url, entries, repos_dir):
    # Process all entries belonging to a single repository serially
    repo_name = get_repo_name_from_url(repo_url)
    repo_path = os.path.join(repos_dir, repo_name)
    
    results = []
    
    for entry in entries:
        cve_id = entry["cve_id"]
        last_vuln = entry["last_vuln_commit"]
        patch_str = entry["patch_commit"]
        patch_commits = patch_str.split(";") if patch_str else []
        
        print(f"Checking {cve_id} ({repo_name})...")
        
        success, msg = check_patch_application(repo_path, last_vuln, patch_commits)
        
        if not success:
            print(f"  [FAILED] {cve_id}")
            log_failure(entry, msg, repos_dir) # Pass repos_dir just to have context if needed, but log_failure uses global path
        else:
            print(f"  [PASSED] {cve_id}")
            
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run on first 5 entries only")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel workers (repos)")
    args = parser.parse_args()
    
    index_csv = os.path.join(DATASET_DIR, "dataset_patch", "index.csv")
    repos_dir = os.path.join(DATASET_DIR, "dataset_patch", "repos")
    
    if not os.path.exists(index_csv):
        print(f"Index file not found: {index_csv}")
        return

    # Read Index
    entries = []
    with open(index_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)
            
    if args.test:
        entries = entries[:5]
        
    # Group by Repo
    repo_groups = defaultdict(list)
    for entry in entries:
        repo_url = entry["github_base_repo_url"]
        if repo_url:
            # Handle multiple URLs if present (take first)
            if ";" in repo_url:
                repo_url = repo_url.split(";")[0]
            repo_groups[repo_url].append(entry)
        else:
            # No repo url, can't check
            log_failure(entry, "No github_base_repo_url provided", repos_dir)

    print(f"Checking {len(entries)} entries across {len(repo_groups)} repositories...")

    # Parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for repo_url, group_entries in repo_groups.items():
            futures.append(executor.submit(process_repo_group, repo_url, group_entries, repos_dir))
            
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Worker exception: {e}")

if __name__ == "__main__":
    main()
