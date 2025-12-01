#!/usr/bin/env bash
set -euo pipefail

# Initialize or update the conda environment for this project and optionally
# install torch/torchvision via pip. Idempotent and can be re-run safely.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/environment.yml"
ENV_NAME="adaptourds"
INSTALL_TORCH=false
NO_SHELL=false

usage() {
  cat <<EOF
Usage: $0 [--name NAME] [--install-torch] [--no-shell] [--help]

Options:
  --name NAME        Environment name (default: adaptourds)
  --install-torch    After creating/activating env, install torch and torchvision via pip3
  --no-shell         Do not spawn a new shell; only create/update the env
  --help             Show this help

Notes:
  - For CUDA-enabled builds please follow the official PyTorch install
    instructions and run the recommended `pip3 install` command for
    your CUDA version. A typical command is:
      pip3 install torch torchvision
    This script can run that command when --install-torch is provided.
EOF
}

if [[ ${#@} -gt 0 ]]; then
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --name)
        ENV_NAME="$2"; shift 2;;
      --install-torch)
        INSTALL_TORCH=true; shift;;
      --no-shell)
        NO_SHELL=true; shift;;
      --help)
        usage; exit 0;;
      *)
        echo "Unknown option: $1" >&2; usage; exit 1;;
    esac
  done
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "Error: 'conda' not found in PATH. Please install Miniconda or Anaconda and try again." >&2
  exit 1
fi

CONDA_BASE=$(conda info --base)
if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
  # make 'conda activate' available in this script
  # shellcheck source=/dev/null
  source "$CONDA_BASE/etc/profile.d/conda.sh"
else
  echo "Warning: could not source conda.sh; 'conda activate' may not work." >&2
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: environment file not found at $ENV_FILE" >&2
  exit 1
fi

echo "Using environment file: $ENV_FILE"
echo "Environment name: $ENV_NAME"

# Check if environment exists
if conda env list | awk '{print $1}' | grep -xq "$ENV_NAME"; then
  echo "Environment '$ENV_NAME' exists — updating from $ENV_FILE"
  conda env update -n "$ENV_NAME" -f "$ENV_FILE"
else
  echo "Creating environment '$ENV_NAME' from $ENV_FILE"
  conda env create -n "$ENV_NAME" -f "$ENV_FILE"
fi

echo "Conda environment '$ENV_NAME' is ready."

if [ "$NO_SHELL" = false ]; then
  echo "Activating environment and opening a new login shell..."
  conda activate "$ENV_NAME"

  if [ "$INSTALL_TORCH" = true ]; then
    echo "Installing torch & torchvision via pip3 inside the activated env..."
    pip3 install --upgrade pip
    pip3 install torch torchvision
  else
    echo "To install PyTorch for your CUDA version, run inside the activated env:" 
    echo "  pip3 install torch torchvision"
    echo "Or re-run this script with --install-torch to install automatically."
  fi

  exec "$SHELL" --login
else
  echo "Skipping spawning a new shell. To activate manually run:"
  echo "  conda activate $ENV_NAME"
  if [ "$INSTALL_TORCH" = true ]; then
    echo "Installing torch & torchvision into environment via 'conda run'..."
    conda run -n "$ENV_NAME" pip3 install --upgrade pip
    conda run -n "$ENV_NAME" pip3 install torch torchvision
  fi
fi
