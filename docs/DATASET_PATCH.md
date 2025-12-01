# Dataset Patch Documentation

## Overview
This document describes the structure and processing of the `dataset/dataset_patch` directory.
The goal is to generate an index of vulnerabilities, their corresponding patch commits, and repository information to facilitate the creation of vulnerability-fix pairs.

## Directory Structure
The dataset is organized as follows:
```
dataset/dataset_patch/dataset_patch/
├── {Language} (e.g., Java, Node.js, Python)
│   ├── {Vulnerability Type} (e.g., SQL 注入, 反序列化漏洞)
│   │   ├── {CVE_ID} (e.g., CVE-2016-0788)
│   │   │   ├── GHSA-xxxx-xxxx-xxxx.json (Metadata file)
│   │   │   └── ... (Patch files, etc.)
```

## Metadata Extraction
We extract metadata from the `GHSA-*.json` files found in each CVE directory.

### Fields
- **Project Type**: Derived from the `{Language}` directory name.
- **Vulnerability Type**: Derived from the `{Vulnerability Type}` directory name.
- **CVE ID**: Derived from the `{CVE_ID}` directory name.
- **GitHub Base Repo URL**: Extracted from the `github_repos` field in the JSON.
- **Patch Commit**: Extracted from the `ghsa.patch_commits` list in the JSON.
  - If multiple patch commits exist, they are stored as a semicolon-separated list (e.g., `hash1;hash2`).
  - The commit hash is extracted from the URL (e.g., `.../commit/{hash}`).
- **Last Vuln Commit**: This field represents the commit immediately preceding the patch commit (the "buggy" version).
  - **Current Limitation**: The metadata files only contain the *patch* commit URLs.
  - **Handling**: The script now automatically clones the repository (cached in `___temp/repos`) and resolves the parent commit of the earliest patch commit using `git rev-parse <commit>^`.
  - **Fallback**: If the repository cannot be cloned or the commit cannot be found, it defaults to `unknown`.

## Special Cases
1.  **Multiple Patch Commits**:
    -   Some vulnerabilities are fixed by multiple commits.
    -   **Strategy**: All patch commit hashes are listed in the `patch_commit` column, separated by `;`.
    -   **Last Vuln Commit Resolution**: The script identifies the earliest commit among the list (based on committer timestamp) and selects its parent as the `last_vuln_commit`.
2.  **Missing Patch Commits**:
    -   If `ghsa.patch_commits` is empty or missing, the entry is skipped or marked as incomplete.
3.  **Non-GitHub URLs**:
    -   If the patch URL is not a GitHub commit URL, we attempt to extract a hash if the format is recognized, otherwise we store the full URL.

## Output
The processing script generates an `index.csv` file in `src/scripts/dataset_preprocessing/dataset_patch/` (or a specified output location).
