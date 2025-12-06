import os

# This file is in src/adapted_tools/iris/core_adapted/config.py
# We want WORKSPACE_ROOT
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# ../../../../ -> src/adapted_tools/iris/core_adapted -> src/adapted_tools/iris -> src/adapted_tools -> src -> root
WORKSPACE_ROOT = os.path.abspath(os.path.join(THIS_DIR, "../../../../"))

IRIS_ROOT_DIR = os.path.join(WORKSPACE_ROOT, "src/adapted_tools/iris")

CODEQL_DIR = os.path.join(WORKSPACE_ROOT, "tools/codeql_home/codeql")
CODEQL_DB_PATH = os.path.join(WORKSPACE_ROOT, "src/adapted_tools/iris/results/dbs")
PROJECT_SOURCE_CODE_DIR = os.path.join(WORKSPACE_ROOT, "dataset/dataset_patch/repos")
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, "src/adapted_tools/iris/results/output")

# These might not be used if I override them, but good to have defaults
PACKAGE_MODULES_PATH = os.path.join(WORKSPACE_ROOT, "src/adapted_tools/iris/results/package-names")
ALL_METHOD_INFO_DIR = "" # Not used
BUILD_INFO = "" # Not used
CVES_MAPPED_W_COMMITS_DIR = "" # Not used
DATA_DIR = "" # Not used
DEP_CONFIGS = "" # Not used

CODEQL_QUERY_VERSION = "1.8.1"

