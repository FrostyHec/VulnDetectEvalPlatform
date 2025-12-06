import os
import sys
import csv
import json
import argparse
import subprocess
import ast
import re
import glob
from datetime import datetime
import concurrent.futures
import hashlib

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
sys.path.insert(0, project_root)

from src.common.config.envs import DATASET_DIR

# Configuration
DATASET_PATCH_ROOT = os.path.join(DATASET_DIR, "dataset_patch", "dataset_patch")
REPOS_DIR = os.path.join(DATASET_DIR, "dataset_patch", "repos")
INDEX_FILE = os.path.join(DATASET_DIR, "dataset_patch", "index.csv")
PRIMEVUL_DIR = os.path.join(DATASET_DIR, "dataset_patch", "primevul_format")
os.makedirs(PRIMEVUL_DIR, exist_ok=True)
OUTPUT_JSONL = os.path.join(PRIMEVUL_DIR, "ds.jsonl")
SUMMARY_CSV = os.path.join(PRIMEVUL_DIR, "case_summary.csv")

def run_git(cmd, cwd):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True, errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_commit_time(repo_path, commit_hash):
    ts = run_git(["git", "show", "-s", "--format=%ct", commit_hash], repo_path)
    return int(ts) if ts else 0

def get_changed_files(repo_path, commit_hash):
    # Get files changed in this commit (compared to parent)
    # git show --name-only --pretty="" commit_hash
    out = run_git(["git", "show", "--name-only", "--pretty=", commit_hash], repo_path)
    if out:
        return out.splitlines()
    return []

def get_file_content(repo_path, commit_hash, file_path):
    out = run_git(["git", "show", f"{commit_hash}:{file_path}"], repo_path)
    return out

# --- Parsers ---

def extract_functions_python(content):
    funcs = []
    try:
        tree = ast.parse(content)
        lines = content.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno
                # Extract source
                func_source = "\n".join(lines[start-1:end])
                funcs.append({
                    "name": node.name,
                    "start": start,
                    "end": end,
                    "content": func_source
                })
    except:
        pass
    return funcs

def extract_functions_java(content):
    # Simple brace-counting parser for Java
    funcs = []
    lines = content.splitlines()
    
    # Regex for method signature (simplified)
    # public/private/protected static? final? Type name(args) throws? {
    method_pattern = re.compile(r'(public|protected|private|static|\s) +[\w\<\>\[\]]+\s+(\w+) *\([^\)]*\) *(\{?|[^;])')
    
    for i, line in enumerate(lines):
        match = method_pattern.search(line)
        if match and '{' in line and 'class ' not in line and 'new ' not in line:
            name = match.group(2)
            start = i + 1
            
            # Find end brace
            brace_count = 0
            found_end = False
            end = start
            
            # Scan forward
            for j in range(i, len(lines)):
                l = lines[j]
                brace_count += l.count('{')
                brace_count -= l.count('}')
                if brace_count == 0:
                    end = j + 1
                    found_end = True
                    break
            
            if found_end:
                func_source = "\n".join(lines[start-1:end])
                funcs.append({
                    "name": name,
                    "start": start,
                    "end": end,
                    "content": func_source
                })
    return funcs

def extract_functions_js(content):
    # Very basic JS parser
    funcs = []
    lines = content.splitlines()
    # function name() { ... }
    # const name = () => { ... }
    # name: function() { ... }
    
    patterns = [
        re.compile(r'function\s+(\w+)\s*\('),
        re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:function|\(.*?\)|.*?=>)'),
        re.compile(r'(\w+)\s*:\s*function')
    ]
    
    for i, line in enumerate(lines):
        name = None
        for p in patterns:
            m = p.search(line)
            if m:
                name = m.group(1)
                break
        
        if name and '{' in line:
            start = i + 1
            brace_count = 0
            found_end = False
            end = start
            
            for j in range(i, len(lines)):
                l = lines[j]
                brace_count += l.count('{')
                brace_count -= l.count('}')
                if brace_count == 0:
                    end = j + 1
                    found_end = True
                    break
            
            if found_end:
                func_source = "\n".join(lines[start-1:end])
                funcs.append({
                    "name": name,
                    "start": start,
                    "end": end,
                    "content": func_source
                })
    return funcs

def extract_functions(language, content):
    if not content: return []
    if language == "Python":
        return extract_functions_python(content)
    elif language == "Java":
        return extract_functions_java(content)
    elif language == "Node.js":
        return extract_functions_js(content)
    return []

# --- Main Logic ---

def get_nvd_description(project_type, vuln_type, cve_id):
    path = os.path.join(DATASET_PATCH_ROOT, project_type, vuln_type, cve_id)
    json_files = glob.glob(os.path.join(path, "GHSA*.json"))
    if json_files:
        try:
            with open(json_files[0], 'r') as f:
                data = json.load(f)
                return data.get("nvd", {}).get("description", "")
        except:
            pass
    return ""

def parse_patch_file(project_type, vuln_type, cve_id):
    """
    Parses the .patch file to identify changed files and line ranges.
    Returns a dict: {file_path: [list of changed line numbers in OLD version]}
    Note: We are interested in the OLD version (vulnerable) to match functions in vuln_commit.
    """
    path = os.path.join(DATASET_PATCH_ROOT, project_type, vuln_type, cve_id)
    patch_files = glob.glob(os.path.join(path, "*.patch"))
    if not patch_files:
        return None
    
    patch_file = patch_files[0]
    changed_files = {}
    current_file = None
    
    try:
        with open(patch_file, 'r', errors='replace') as f:
            for line in f:
                # --- a/path/to/file
                if line.startswith("--- a/"):
                    current_file = line.strip()[6:] # Remove "--- a/"
                    changed_files[current_file] = []
                elif line.startswith("+++ b/"):
                    # Just confirmation, usually follows ---
                    pass
                elif line.startswith("@@") and current_file:
                    # @@ -start,length +start,length @@
                    # We care about the first part (-start,length) which refers to the old file
                    match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                    if match:
                        start_line = int(match.group(1))
                        length = int(match.group(2)) if match.group(2) else 1
                        # We mark these lines as changed
                        # Just storing the range is enough
                        changed_files[current_file].append((start_line, start_line + length))
    except Exception as e:
        print(f"Error parsing patch {patch_file}: {e}")
        return None
        
    return changed_files

def process_entry(row, args):
    # row: project_type, vuln_type, cve_id, last_vuln_commit, patch_commit, github_base_repo_url
    lang = row['project_type']
    vuln_type = row['vuln_type']
    cve_id = row['cve_id']
    vuln_commit = row['last_vuln_commit']
    fix_commit = row['patch_commit']
    repo_url = row['github_base_repo_url']
    
    if not repo_url or repo_url == "unknown":
        return None, "No Repo URL"
    
    # Determine repo name
    repo_name = repo_url.strip("/").split("/")[-2] + "_" + repo_url.strip("/").split("/")[-1]
    if repo_name.endswith(".git"): repo_name = repo_name[:-4]
    repo_path = os.path.join(REPOS_DIR, repo_name)
    
    if not os.path.exists(repo_path):
        return None, "Repo not found locally"

    if fix_commit == "unknown" or not fix_commit:
        return None, "No fix commit"
        
    # Handle multiple fix commits (take first for now)
    if ";" in fix_commit:
        fix_commit = fix_commit.split(";")[0]
        
    # If vuln_commit is unknown, try parent of fix
    if vuln_commit == "unknown" or not vuln_commit:
        vuln_commit = run_git(["git", "rev-parse", f"{fix_commit}^"], repo_path)
        if not vuln_commit:
            return None, "Could not resolve vuln commit"

    # Get changed files
    source_files = []
    patch_info = None
    
    if args.using_patch:
        patch_info = parse_patch_file(lang, vuln_type, cve_id)
        if patch_info:
            # Filter files by extension
            exts = {
                "Python": [".py"],
                "Java": [".java"],
                "Node.js": [".js", ".ts"]
            }
            valid_exts = exts.get(lang, [])
            source_files = [f for f in patch_info.keys() if any(f.endswith(e) for e in valid_exts)]
        else:
            # Fallback to git diff if patch parsing fails or no patch file
            pass 
            
    if not source_files:
        # Fallback or default behavior
        changed_files = get_changed_files(repo_path, fix_commit)
        exts = {
            "Python": [".py"],
            "Java": [".java"],
            "Node.js": [".js", ".ts"]
        }
        valid_exts = exts.get(lang, [])
        source_files = [f for f in changed_files if any(f.endswith(e) for e in valid_exts)]
    
    if not source_files:
        return None, "No source files changed"

    # Get NVD description
    nvd_desc = get_nvd_description(lang, vuln_type, cve_id)
    
    all_changed_funcs = [] # List of (file_path, func_vuln, func_fix)
    
    for file_path in source_files:
        content_vuln = get_file_content(repo_path, vuln_commit, file_path)
        content_fix = get_file_content(repo_path, fix_commit, file_path)
        
        if not content_vuln or not content_fix:
            continue
            
        funcs_vuln = extract_functions(lang, content_vuln)
        funcs_fix = extract_functions(lang, content_fix)
        
        map_fix = {f['name']: f for f in funcs_fix}
        for fv in funcs_vuln:
            name = fv['name']
            if name in map_fix:
                ff = map_fix[name]
                
                is_changed = False
                
                if args.using_patch and patch_info and file_path in patch_info:
                    # Check if function overlaps with patch ranges
                    # fv['start'], fv['end'] vs ranges in patch_info[file_path]
                    for r_start, r_end in patch_info[file_path]:
                        # Check overlap
                        if not (fv['end'] < r_start or fv['start'] > r_end):
                            is_changed = True
                            break
                else:
                    # Content diff check
                    if fv['content'] != ff['content']:
                        is_changed = True
                
                if is_changed:
                    # DS Filter Check (Content must be different)
                    if args.ds_filter and fv['content'] == ff['content']:
                        continue
                        
                    all_changed_funcs.append((file_path, fv, ff))
    
    # Decision Logic
    final_samples = []
    
    is_one_func = (len(all_changed_funcs) == 1)
    
    # 1. Handle Function Changes
    if all_changed_funcs:
        if is_one_func:
            # Rule 1: Exactly one function changed
            file_path, fv, ff = all_changed_funcs[0]
            final_samples.append(create_sample_pair(repo_name, vuln_type, cve_id, fv['name'], fv['content'], ff['content'], vuln_commit, fix_commit, repo_path, lang, "PRIMEVUL-ONEFUNC"))
        else:
            # Rule 2: Multiple functions, check NVD
            matched_any = False
            for file_path, fv, ff in all_changed_funcs:
                func_name = fv['name']
                file_name = os.path.basename(file_path)
                funcs_in_this_file = [x for x in all_changed_funcs if x[0] == file_path]
                
                keep = False
                rule = ""
                
                if func_name in nvd_desc:
                    keep = True
                    rule = "PRIMEVUL-NVDCHECK-NAME"
                elif file_name in nvd_desc and len(funcs_in_this_file) == 1:
                    keep = True
                    rule = "PRIMEVUL-NVDCHECK-FILE"
                
                if keep:
                    matched_any = True
                    final_samples.append(create_sample_pair(repo_name, vuln_type, cve_id, fv['name'], fv['content'], ff['content'], vuln_commit, fix_commit, repo_path, lang, rule))
            
            if not matched_any:
                return None, f"Skipped: {len(all_changed_funcs)} functions changed, no NVD match"

    # 2. Handle Global/Non-Function Changes (only if no functions were found changed)
    else:
        # If no functions changed, check if we have a clean single-file change
        if len(source_files) == 1:
            file_path = source_files[0]
            content_vuln = get_file_content(repo_path, vuln_commit, file_path)
            content_fix = get_file_content(repo_path, fix_commit, file_path)

            if content_vuln and content_fix and content_vuln != content_fix:
                final_samples.append(create_sample_pair(repo_name, vuln_type, cve_id, os.path.basename(file_path), content_vuln, content_fix, vuln_commit, fix_commit, repo_path, lang, "PRIMEVUL-ONEFILE-GLOBAL"))
        elif len(source_files) > 1:
            return None, f"Skipped: {len(source_files)} files changed (global), ambiguous"
        else:
            return None, "Skipped: No content changes detected"

    if final_samples:
        # Flatten the list of pairs
        flat_samples = []
        for pair in final_samples:
            flat_samples.extend(pair)
        return flat_samples, "Success"
    else:
        return None, "Filtered out by PrimeVul rules"

# Redefining create_sample properly and updating the call sites
def create_sample_pair(repo_name, vuln_type, cve_id, name, content_vuln, content_fix, vuln_commit, fix_commit, repo_path, project_lan, rule):
    base_id = f"{cve_id}_{fix_commit[:8]}_{name}"
    
    vuln_sample = {
        "id": f"{base_id}_vuln",
        "project": repo_name,
        "project_lan": project_lan,
        "vuln_type": vuln_type,
        "cve_id": cve_id,
        "label": 1,
        "func_src": content_vuln,
        "commit_time": get_commit_time(repo_path, vuln_commit),
        "commit_id": vuln_commit,
        "rule": rule
    }
    
    fix_sample = {
        "id": f"{base_id}_fix",
        "project": repo_name,
        "project_lan": project_lan,
        "vuln_type": vuln_type,
        "cve_id": cve_id,
        "label": 0,
        "func_src": content_fix,
        "commit_time": get_commit_time(repo_path, fix_commit),
        "commit_id": fix_commit,
        "rule": rule
    }
    return [vuln_sample, fix_sample]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--languages", type=str, default="Java,Python,Node.js")
    parser.add_argument("--vuln_types", type=str, default=None)
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument("--using_patch", action="store_true", default=True, help="Use .patch files to identify changed lines")
    parser.add_argument("--no_using_patch", action="store_false", dest="using_patch", help="Do not use .patch files")
    parser.add_argument("--ds_filter", action="store_true", default=True, help="Filter out functions where content is identical")
    parser.add_argument("--no_ds_filter", action="store_false", dest="ds_filter", help="Do not filter identical content")
    args = parser.parse_args()
    
    langs = [l.lower() for l in args.languages.split(",")]
    vtypes = args.vuln_types.split(",") if args.vuln_types else None
    
    # Read Index
    entries = []
    with open(INDEX_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['project_type'].lower() in langs:
                if vtypes is None or row['vuln_type'] in vtypes:
                    entries.append(row)
    
    if args.max_samples:
        entries = entries[:args.max_samples]
        
    print(f"Processing {len(entries)} entries...")
    print(f"Configuration: using_patch={args.using_patch}, ds_filter={args.ds_filter}")
    
    # Open files for incremental writing
    with open(OUTPUT_JSONL, 'w') as f_jsonl, open(SUMMARY_CSV, 'w') as f_summary:
        summary_writer = csv.DictWriter(f_summary, fieldnames=["cve_id", "status", "rule"])
        summary_writer.writeheader()
        
        total_samples = 0
        
        # Sequential for now to debug, can be parallelized
        for row in entries:
            samples, status = process_entry(row, args)
            
            # Write Summary immediately
            summary_row = {
                "cve_id": row['cve_id'],
                "status": status,
                "rule": samples[0]['rule'] if samples else ""
            }
            summary_writer.writerow(summary_row)
            f_summary.flush()
            
            if samples:
                # Write Samples immediately
                for r in samples:
                    # Remove internal 'rule' field if not needed in final jsonl
                    r_copy = r.copy()
                    r_copy.pop('rule', None) 
                    f_jsonl.write(json.dumps(r_copy) + "\n")
                f_jsonl.flush()
                
                total_samples += len(samples)
                print(f"Processed {row['cve_id']}: {len(samples)} samples generated ({samples[0]['rule']})")
            else:
                print(f"Skipped {row['cve_id']}: {status}")

    print(f"Done. Generated {total_samples} samples.")

if __name__ == "__main__":
    main()
