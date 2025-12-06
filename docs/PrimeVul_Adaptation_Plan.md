# PrimeVul Dataset Adaptation Plan

## Overview
This document outlines the strategy for adapting the current vulnerability dataset (dataset_patch) into the PrimeVul format.

## Target Format
The goal is to generate a `ds.jsonl` file with the following fields:
- `id`: Unique identifier (e.g., `CVE-XXXX-XXXX_<commit_hash>_<func_name>`)
- `project`: Project name
- `vuln_type`: Vulnerability type (from dataset directory structure)
- `cve_id`: CVE ID
- `label`: 1 (Vulnerable) or 0 (Benign)
- `func_src`: Complete function source code (or file content if change is global)
- `commit_time`: Timestamp of the commit
- `commit_id`: Commit hash

## Adaptation Process

### 1. Data Source
- Input: `dataset/dataset_patch/index.csv`
- Repositories: Cloned in `dataset/dataset_patch/repos/`

### 2. Extraction Logic (`dataset_patch_to_primevul_format.py`)
For each entry in `index.csv`:
1.  **Repository Setup**: Ensure the repository is cloned.
2.  **Commit Processing**:
    *   **Vulnerable Version**: Use `last_vuln_commit` (if available). Label = 1.
    *   **Fixed Version**: Use `patch_commit`. Label = 0.
3.  **Function Extraction**:
    *   Identify changed files between `last_vuln_commit` and `patch_commit`.
    *   For each changed file, identify changed functions.
    *   **PrimeVul Filtering Rules**:
        *   **OneFunc**: If only one function is modified in the commit.
        *   **NVDCheck**: If NVD description (from JSON) mentions the function name.
    *   **Patch-Based Extraction (Optional `--using_patch`)**:
        *   Parse the `.patch` file in the dataset directory to identify changed files and line ranges.
        *   Extract functions from the repository at `last_vuln_commit` and `patch_commit` that overlap with these line ranges.
    *   **Content Check (Optional `--ds_filter`)**:
        *   Ensure that the extracted vulnerable function content is strictly different from the fixed function content.
    *   *Relaxation*: If the change is outside any function (global), extract the full file (as per user request).
4.  **Output**: Append to `ds.jsonl`.

### 3. Dataset Splitting (`split_dataset.py`)
1.  Load `ds.jsonl`.
2.  Sort by `commit_time`.
3.  Split into Train (80%), Validation (10%), Test (10%).
4.  Constraint: Keep samples from the same commit together (PrimeVul logic).
5.  Output: `index.csv` mapping ID to Split.

## Tools & Libraries
- Python `ast` for Python parsing.
- Regex/Heuristics for Java/Node.js parsing (due to lack of heavy parsers).
- `git` CLI for repo operations.

## Validation
- `case_summary.csv` will track success/failure rates and filtering reasons.
- A test script will verify the pipeline on a small subset.
