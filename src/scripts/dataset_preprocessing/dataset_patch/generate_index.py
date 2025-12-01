import os
import json
import csv
import sys
import re
import subprocess
import concurrent.futures
import threading
import random
from collections import defaultdict

PARALLEL_WORKERS = 128

# Add the src directory to sys.path to allow imports from common
# Assuming this script is run from the project root or we can find the root relative to this file
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.common.config.envs import DATASET_DIR, ROOT_DIR
except ImportError:
    # Fallback if running from a different context where src is not a package
    # Try to find src relative to this script
    src_path = os.path.join(project_root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from common.config.envs import DATASET_DIR, ROOT_DIR

class RepoHandler:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        self.locks = defaultdict(threading.Lock)
        self.global_lock = threading.Lock()
    
    def get_repo_name_from_url(self, url):
        # https://github.com/owner/repo -> owner_repo
        if not url: return None
        url = url.strip("/")
        if url.endswith(".git"):
            url = url[:-4]
        parts = url.split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}_{parts[-1]}"
        return "unknown_repo"

    def clone_or_fetch(self, repo_url):
        repo_name = self.get_repo_name_from_url(repo_url)
        if not repo_name:
            return None
        
        repo_path = os.path.join(self.temp_dir, repo_name)
        
        # Acquire lock for this specific repo to prevent concurrent clones
        with self.global_lock:
            lock = self.locks[repo_name]
        
        with lock:
            if os.path.exists(repo_path) and os.path.exists(os.path.join(repo_path, ".git")):
                # We assume if it exists and has .git, we can use it. 
                pass
            else:
                # Clean up partial/empty directory if it exists
                if os.path.exists(repo_path):
                    import shutil
                    shutil.rmtree(repo_path)
                    
                print(f"Cloning {repo_url} to {repo_path}...")
                try:
                    subprocess.run(["git", "clone", repo_url, repo_path], check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to clone {repo_url}: {e}")
                    return None
        
        return repo_path

    def fetch_commit(self, repo_name, repo_path, commit_hash):
        # Acquire lock for this specific repo to prevent concurrent fetches
        with self.global_lock:
            lock = self.locks[repo_name]
            
        with lock:
            try:
                subprocess.run(
                    ["git", "fetch", "origin", commit_hash],
                    cwd=repo_path, capture_output=True, check=True
                )
                return True
            except subprocess.CalledProcessError:
                return False

    def get_commit_timestamp(self, repo_path, commit_hash):
        try:
            # %ct: committer date, UNIX timestamp
            result = subprocess.run(
                ["git", "show", "-s", "--format=%ct", commit_hash], 
                cwd=repo_path, capture_output=True, text=True, check=True
            )
            return int(result.stdout.strip())
        except:
            return float('inf')

    def get_parent_commit(self, repo_path, commit_hash):
        try:
            # Get parent hash: git rev-parse commit^
            result = subprocess.run(
                ["git", "rev-parse", f"{commit_hash}^"], 
                cwd=repo_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except:
            return "unknown"

    def is_valid_repo_url(self, url):
        if not url: return False
        if "github.com/advisories/" in url: return False
        # Basic check for github.com/owner/repo
        # Could be more robust, but this filters out the obvious bad ones
        return "github.com" in url and len(url.strip("/").split("/")) >= 4

    def resolve_last_vuln_commit(self, repo_urls_str, patch_commits):
        if not repo_urls_str or not patch_commits:
            return "unknown"
        
        # Handle multiple repo urls
        candidate_urls = []
        if ";" in repo_urls_str:
            candidate_urls = repo_urls_str.split(";")
        else:
            candidate_urls = [repo_urls_str]
            
        # Filter and prioritize URLs
        valid_urls = [u for u in candidate_urls if self.is_valid_repo_url(u)]
        
        # If no valid URLs found after filtering, try the original list (fallback)
        if not valid_urls:
            valid_urls = candidate_urls

        for repo_url in valid_urls:
            repo_name = self.get_repo_name_from_url(repo_url)
            repo_path = self.clone_or_fetch(repo_url)
            if not repo_path:
                continue
                
            # Find earliest patch commit
            earliest_commit = None
            min_ts = float('inf')
            found_commit = False
            
            for commit in patch_commits:
                ts = self.get_commit_timestamp(repo_path, commit)
                
                if ts == float('inf'):
                    # Try fetching the commit explicitly
                    self.fetch_commit(repo_name, repo_path, commit)
                    ts = self.get_commit_timestamp(repo_path, commit)
                
                if ts < min_ts:
                    min_ts = ts
                    earliest_commit = commit
                    found_commit = True
                    
            if found_commit and earliest_commit:
                parent = self.get_parent_commit(repo_path, earliest_commit)
                if parent != "unknown":
                    return parent
                    
        return "unknown"

def extract_commit_hash(url):
    """
    Extracts the commit hash from a GitHub commit URL.
    Example: https://github.com/jenkinsci/jenkins/commit/1ec232ca... -> 1ec232ca...
    """
    if not url:
        return None
    # Match .../commit/{hash}
    match = re.search(r'/commit/([a-fA-F0-9]{40})', url)
    if match:
        return match.group(1)
    return url # Return original if regex fails (might be non-standard URL)

def extract_commit_from_patch_file(cve_dir):
    """
    Looks for a .patch file in the directory and extracts the commit hash from the header.
    Header format: From <hash> ...
    """
    patch_file = None
    for f in os.listdir(cve_dir):
        if f.endswith(".patch"):
            patch_file = os.path.join(cve_dir, f)
            break
    
    if not patch_file:
        return None
        
    try:
        with open(patch_file, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            # Example: From 465fb51bec7549c12caf70b737e663f9ed5dbedc Mon Sep 17 00:00:00 2001
            match = re.match(r'^From\s+([a-fA-F0-9]{40})\s+', first_line)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"Error reading patch file {patch_file}: {e}")
        
    return None

def process_single_entry(entry_data, repo_handler):
    json_file, language, vuln_type, cve_id = entry_data
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Extract fields
        github_repo = data.get("github_repos", "")
        if isinstance(github_repo, list):
            github_repo = ";".join(github_repo)
        
        ghsa_info = data.get("ghsa", {})
        patch_commits_urls = ghsa_info.get("patch_commits", [])
        if patch_commits_urls is None:
            patch_commits_urls = []
        
        patch_commits_hashes = []
        for url in patch_commits_urls:
            commit_hash = extract_commit_hash(url)
            if commit_hash:
                patch_commits_hashes.append(commit_hash)
        
        # Fallback: If no patch commits found from JSON, try .patch file
        if not patch_commits_hashes:
            cve_dir = os.path.dirname(json_file)
            patch_hash = extract_commit_from_patch_file(cve_dir)
            if patch_hash:
                patch_commits_hashes.append(patch_hash)
        
        patch_commit_str = ";".join(patch_commits_hashes)
        
        # Resolve last_vuln_commit
        last_vuln_commit = "unknown"
        if patch_commits_hashes and github_repo:
            last_vuln_commit = repo_handler.resolve_last_vuln_commit(github_repo, patch_commits_hashes)
        
        return {
            "project_type": language,
            "vuln_type": vuln_type,
            "cve_id": cve_id,
            "last_vuln_commit": last_vuln_commit,
            "patch_commit": patch_commit_str,
            "github_base_repo_url": github_repo
        }
        
    except Exception as e:
        print(f"Error processing {json_file}: {e}")
        return None

def load_existing_index(output_file):
    existing_entries = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Store unique identifier for processed entries
                    # (project_type, vuln_type, cve_id)
                    existing_entries.add((row["project_type"], row["vuln_type"], row["cve_id"]))
        except Exception as e:
            print(f"Error reading existing index: {e}")
    return existing_entries

def cleanup_repos(repos_dir, existing_entries, repo_handler):
    # Identify repos that are referenced in the existing index
    # We need to map existing entries back to repo names.
    # This is tricky because we don't have the repo URL in the key, but we have it in the CSV row if we read it.
    # Let's modify load_existing_index to return more info or read it here.
    pass # Implemented inside process_dataset for better context access

def process_dataset(output_file, test_mode=False, max_workers=32, target=None, continue_mode=False):
    dataset_patch_root = os.path.join(DATASET_DIR, "dataset_patch", "dataset_patch")
    
    if not os.path.exists(dataset_patch_root):
        print(f"Error: Dataset directory not found at {dataset_patch_root}")
        return

    print(f"Scanning dataset at: {dataset_patch_root}")
    if target:
        print(f"Targeting specific entry: {target}")
    
    # Initialize RepoHandler
    repos_dir = os.path.join(DATASET_DIR, "dataset_patch", "repos")
    repo_handler = RepoHandler(repos_dir)

    headers = [
        "project_type", 
        "vuln_type", 
        "cve_id", 
        "last_vuln_commit", 
        "patch_commit", 
        "github_base_repo_url"
    ]
    
    existing_keys = set()
    referenced_repos = set()
    
    if continue_mode and os.path.exists(output_file):
        print(f"Continue mode: Loading existing index from {output_file}...")
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_keys.add((row["project_type"], row["vuln_type"], row["cve_id"]))
                    
                    # Collect referenced repos to avoid deleting them
                    repo_url = row.get("github_base_repo_url", "")
                    if repo_url:
                        # Handle multiple URLs
                        urls = repo_url.split(";")
                        for u in urls:
                            repo_name = repo_handler.get_repo_name_from_url(u)
                            if repo_name:
                                referenced_repos.add(repo_name)
                                
        except Exception as e:
            print(f"Error reading existing index: {e}")
            
        print(f"Found {len(existing_keys)} existing entries.")
        
        # Cleanup repos not referenced in index
        if os.path.exists(repos_dir):
            print("Cleaning up unreferenced repositories...")
            for item in os.listdir(repos_dir):
                item_path = os.path.join(repos_dir, item)
                if os.path.isdir(item_path):
                    if item not in referenced_repos:
                        # Double check: is this a repo folder?
                        # We assume all folders in repos_dir are repo folders managed by us.
                        print(f"Removing unreferenced repo: {item}")
                        import shutil
                        try:
                            shutil.rmtree(item_path)
                        except Exception as e:
                            print(f"Failed to remove {item}: {e}")
    
    tasks = []
    
    # Walk through the directory structure
    count = 0
    for language in sorted(os.listdir(dataset_patch_root)):
        lang_path = os.path.join(dataset_patch_root, language)
        if not os.path.isdir(lang_path):
            continue
            
        for vuln_type in sorted(os.listdir(lang_path)):
            vuln_path = os.path.join(lang_path, vuln_type)
            if not os.path.isdir(vuln_path):
                continue
                
            for cve_id in sorted(os.listdir(vuln_path)):
                if target and target not in cve_id:
                    continue
                
                if test_mode and count >= 5:
                    break
                
                # Check if valid directory first
                cve_path = os.path.join(vuln_path, cve_id)
                if not os.path.isdir(cve_path):
                    continue

                # Skip if already processed in continue mode
                # We increment count here to ensure test_mode respects the global order
                if continue_mode and (language, vuln_type, cve_id) in existing_keys:
                    count += 1
                    continue
                
                # Look for JSON file
                json_file = None
                for f in os.listdir(cve_path):
                    if f.endswith(".json") and f.startswith("GHSA"):
                        json_file = os.path.join(cve_path, f)
                        break
                
                if not json_file:
                    continue
                
                tasks.append((json_file, language, vuln_type, cve_id))
                count += 1
            
            if test_mode and count >= 5:
                break
        if test_mode and count >= 5:
            break

    print(f"Found {len(tasks)} new entries to process. Starting parallel execution with {max_workers} workers...")
    
    # Shuffle tasks to avoid convoy effect on repo locks (where many threads wait for the same repo to clone)
    random.shuffle(tasks)
    
    # Prepare output file
    # If continue_mode, append. Else write new.
    # If target mode, we might not want to touch the file unless we are sure.
    # But assuming standard usage:
    
    mode = 'a' if (continue_mode and os.path.exists(output_file)) else 'w'
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Open file and keep it open to write results as they come in
    # Note: In 'a' mode, we need to be careful about headers.
    # If file is empty or we just created it, write header.
    
    write_header = False
    if mode == 'w':
        write_header = True
    elif mode == 'a':
        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            write_header = True
            
    # We will use a lock for writing to file just in case, though we are writing from main thread.
    
    with open(output_file, mode, newline='', encoding='utf-8', buffering=1) as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if write_header:
            writer.writeheader()
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_entry = {executor.submit(process_single_entry, task, repo_handler): task for task in tasks}
            
            for future in concurrent.futures.as_completed(future_to_entry):
                result = future.result()
                if result:
                    # Write immediately
                    writer.writerow(result)
                    f.flush() # Ensure it's written to disk
                    
                    if target:
                        print(result)

    if not target:
        print(f"Successfully generated/updated index at {output_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run on first 5 entries only")
    parser.add_argument("--workers", type=int, default=PARALLEL_WORKERS, help="Number of parallel workers")
    parser.add_argument("--target", type=str, help="Target specific CVE ID substring")
    parser.add_argument("--continue", dest="continue_mode", action="store_true", help="Continue from existing index")
    args = parser.parse_args()
    
    # Output to dataset/dataset_patch/index.csv as requested
    output_csv = os.path.join(DATASET_DIR, "dataset_patch", "index.csv")
    process_dataset(output_csv, test_mode=args.test, max_workers=args.workers, target=args.target, continue_mode=args.continue_mode)
