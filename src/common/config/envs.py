import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

# Add project-level folder paths here so the rest of the codebase can import
# canonical locations from a single place. Use `ROOT_DIR` + project-relative
# paths when referencing files or folders inside the repository.
# Example: path to the top-level `dataset` folder used by the project.
DATASET_DIR = os.path.join(ROOT_DIR, "dataset")
