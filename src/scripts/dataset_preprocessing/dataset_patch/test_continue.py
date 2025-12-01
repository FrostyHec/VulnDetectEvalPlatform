import os
import sys
import subprocess
import csv

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

def test_continue_functionality():
    index_csv = os.path.join(DATASET_DIR, "dataset_patch", "index.csv")
    script_path = os.path.join(current_dir, "generate_index.py")
    
    print("Step 1: Run generate_index.py --test (fresh start)")
    if os.path.exists(index_csv):
        os.remove(index_csv)
        
    subprocess.run([sys.executable, script_path, "--test"], check=True)
    
    # Verify we have 5 entries
    with open(index_csv, 'r') as f:
        lines = f.readlines()
        # Header + 5 entries = 6 lines
        if len(lines) != 6:
            print(f"Error: Expected 6 lines, got {len(lines)}")
            return False
            
    print("Step 2: Simulate interruption (delete last line)")
    with open(index_csv, 'w') as f:
        f.writelines(lines[:-1])
        
    # Verify we have 4 entries
    with open(index_csv, 'r') as f:
        lines_interrupted = f.readlines()
        if len(lines_interrupted) != 5:
            print(f"Error: Expected 5 lines, got {len(lines_interrupted)}")
            return False
            
    print("Step 3: Run generate_index.py --test --continue")
    subprocess.run([sys.executable, script_path, "--test", "--continue"], check=True)
    
    # Verify we have 5 entries again (header + 5)
    # Note: The order might be different if parallelism is involved, but --test usually runs sequentially enough or we check count.
    # Actually, --test limits to first 5 found in directory traversal.
    # If we skip the first 4, we should process the 5th again.
    
    with open(index_csv, 'r') as f:
        lines_restored = f.readlines()
        if len(lines_restored) != 6:
            print(f"Error: Expected 6 lines after continue, got {len(lines_restored)}")
            print("Content:")
            print("".join(lines_restored))
            return False
            
    print("Success: Continue functionality verified.")
    return True

if __name__ == "__main__":
    test_continue_functionality()
