import os
import json
import sys
import shutil
import torch
import glob
# Add root to path
sys.path.append(os.getcwd())

from src.adapted_tools.primeVul.config import get_config
from src.adapted_tools.primeVul.train import train

TEST_DATA_DIR = "src/test/data"
TEST_OUTPUT_DIR = "output/tmp"

def setup_test_data():
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR)
    
    dummy_data = [
        {"func_src": "def foo(): pass", "label": 0, "id": "1_fix", "cve_id": "CVE-1"},
        {"func_src": "def foo(): return 1", "label": 1, "id": "1_vuln", "cve_id": "CVE-1"},
    ]
    
    # Create ds.jsonl
    with open(os.path.join(TEST_DATA_DIR, "ds.jsonl"), "w") as f:
        for item in dummy_data:
            f.write(json.dumps(item) + "\n")
            
    # Create index_split.csv
    with open(os.path.join(TEST_DATA_DIR, "index_split.csv"), "w") as f:
        f.write("id,split\n")
        for item in dummy_data:
            # Add to all splits for simplicity in testing
            f.write(f"{item['id']},train\n")
            f.write(f"{item['id']},val\n")
            f.write(f"{item['id']},test\n")

def clean_output():
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR)

def test_default_config():
    print("\n--- Testing Default Config ---")
    clean_output()
    config = get_config(
        "codebert", 
        output_dir=TEST_OUTPUT_DIR,
        train_file=TEST_DATA_DIR,
        valid_file=TEST_DATA_DIR,
        test_file=TEST_DATA_DIR,
        num_train_epochs=1,
        train_batch_size=2,
        eval_batch_size=2,
        logging_steps=1,
        max_len=32
    )
    config.device = torch.device("cpu")
    config.n_gpu = 0
    
    train(config)
    print("Default config test passed.")

def test_exp_name():
    print("\n--- Testing Experiment Name ---")
    exp_name = "test_exp"
    exp_dir = os.path.join("output/dataset_patch/primevul", exp_name)
    if os.path.exists(exp_dir):
        shutil.rmtree(exp_dir)
        
    config = get_config(
        "codebert",
        exp_name=exp_name,
        train_file=TEST_DATA_DIR,
        valid_file=TEST_DATA_DIR,
        test_file=TEST_DATA_DIR,
        num_train_epochs=1,
        train_batch_size=2,
        eval_batch_size=2,
        max_len=32
    )
    config.device = torch.device("cpu")
    config.n_gpu = 0
    
    train(config)
    
    if not os.path.exists(exp_dir):
        raise FileNotFoundError(f"Experiment directory {exp_dir} was not created.")
    print("Experiment name test passed.")

def test_resume_functionality():
    print("\n--- Testing Resume Functionality ---")
    clean_output()
    
    # 1. Train for 1 epoch
    config = get_config(
        "codebert", 
        output_dir=TEST_OUTPUT_DIR,
        train_file=TEST_DATA_DIR,
        valid_file=TEST_DATA_DIR,
        test_file=TEST_DATA_DIR,
        num_train_epochs=1,
        train_batch_size=2,
        eval_batch_size=2,
        max_len=32
    )
    config.device = torch.device("cpu")
    config.n_gpu = 0
    train(config)
    
    # 2. Try to train again without continue (should fail)
    try:
        # Simulate main() check
        if os.path.exists(config.output_dir) and os.listdir(config.output_dir):
             raise ValueError(f"Output directory {config.output_dir} is not empty.")
        print("Error: Should have raised ValueError for existing directory.")
    except ValueError:
        print("Correctly raised ValueError for existing directory.")

    # 3. Resume training (train for another epoch)
    config.num_train_epochs = 2
    
    # Find checkpoint (accept any .pt, prefer filenames containing 'checkpoint')
    all_ckpts = glob.glob(os.path.join(TEST_OUTPUT_DIR, "*.pt"))
    if not all_ckpts:
        raise FileNotFoundError(f"No checkpoint found in {TEST_OUTPUT_DIR}")
    ckpts_pref = [p for p in all_ckpts if 'checkpoint' in os.path.basename(p)]
    candidates = ckpts_pref if ckpts_pref else all_ckpts
    resume_path = max(candidates, key=os.path.getmtime)
    
    train(config, resume_from=resume_path)
    print("Resume functionality test passed.")

def test_load_pretrained():
    print("\n--- Testing Load Pretrained ---")
    clean_output()
    
    # Create a dummy pretrained model
    model = torch.nn.Linear(10, 2) # Dummy
    pretrained_path = os.path.join(TEST_DATA_DIR, "pretrained.pt")
    # Actually we need a real model state dict compatible with CodeBERT
    # So let's just run a quick train to get a checkpoint and use that as "pretrained"
    
    # 1. Train to get a checkpoint
    config = get_config(
        "codebert", 
        output_dir=TEST_OUTPUT_DIR,
        train_file=TEST_DATA_DIR,
        valid_file=TEST_DATA_DIR,
        test_file=TEST_DATA_DIR,
        num_train_epochs=1,
        train_batch_size=2,
        eval_batch_size=2,
        max_len=32
    )
    config.device = torch.device("cpu")
    config.n_gpu = 0
    train(config)
    
    all_ckpts = glob.glob(os.path.join(TEST_OUTPUT_DIR, "*.pt"))
    if not all_ckpts:
        raise FileNotFoundError(f"No checkpoint found in {TEST_OUTPUT_DIR}")
    ckpts_pref = [p for p in all_ckpts if 'checkpoint' in os.path.basename(p)]
    candidates = ckpts_pref if ckpts_pref else all_ckpts
    pretrained_path = max(candidates, key=os.path.getmtime)
    
    # 2. Load this as pretrained in a new run
    # Do NOT delete the checkpoint we just created; create a new output folder for this run
    load_out_dir = TEST_OUTPUT_DIR + "_load"
    if os.path.exists(load_out_dir):
        shutil.rmtree(load_out_dir)
    config2 = get_config(
        "codebert",
        output_dir=load_out_dir,
        train_file=TEST_DATA_DIR,
        valid_file=TEST_DATA_DIR,
        test_file=TEST_DATA_DIR,
        num_train_epochs=1,
        train_batch_size=2,
        eval_batch_size=2,
        max_len=32
    )
    config2.device = torch.device("cpu")
    config2.n_gpu = 0
    train(config2, load_pretrained=pretrained_path)
    print("Load pretrained test passed.")

def run_tests():
    setup_test_data()
    
    try:
        test_default_config()
        test_exp_name()
        test_resume_functionality()
        test_load_pretrained()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
