import os
import torch
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class Config:
    model_type: str = "codebert"
    model_name_or_path: str = "microsoft/codebert-base"
    my_primevul_format: bool = False
    output_dir: str = "output/dataset_patch/primevul/default"
    
    train_file: str = "dataset/dataset_patch/primevul_format/train.jsonl"
    valid_file: str = "dataset/dataset_patch/primevul_format/valid.jsonl"
    test_file: str = "dataset/dataset_patch/primevul_format/test.jsonl"
    
    max_len: int = 512
    train_batch_size: int = 16
    eval_batch_size: int = 32
    learning_rate: float = 2e-5
    num_train_epochs: int = 50
    seed: int = 42
    
    gradient_accumulation_steps: int = 1
    weight_decay: float = 0.0
    adam_epsilon: float = 1e-8
    max_grad_norm: float = 1.0
    
    logging_steps: int = 100
    save_steps: int = 500
    
    device: torch.device = field(init=False)
    n_gpu: int = field(init=False)

    def __post_init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.n_gpu = torch.cuda.device_count()

    def save(self, path):
        with open(path, 'w') as f:
            f.write(str(asdict(self)))
            
    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

# Pre-defined configurations
CONFIG_DICT = {
    "codebert": Config(
        model_type="codebert",
        model_name_or_path="microsoft/codebert-base",
        my_primevul_format=True,
        train_file="dataset/dataset_patch/primevul_format",
        valid_file="dataset/dataset_patch/primevul_format",
        test_file="dataset/dataset_patch/primevul_format"
    ),
    "unixcoder": Config(
        model_type="unixcoder",
        model_name_or_path="microsoft/unixcoder-base",
        my_primevul_format=True,
        train_file="dataset/dataset_patch/primevul_format",
        valid_file="dataset/dataset_patch/primevul_format",
        test_file="dataset/dataset_patch/primevul_format"
    ),
    "codet5": Config(
        model_type="codet5",
        model_name_or_path="Salesforce/codet5-base",
        my_primevul_format=True,
        train_file="dataset/dataset_patch/primevul_format",
        valid_file="dataset/dataset_patch/primevul_format",
        test_file="dataset/dataset_patch/primevul_format",
        learning_rate=1e-5,
        train_batch_size=4,
        eval_batch_size=4
    )
}

def get_config(model_name: str, exp_name: Optional[str] = None, output_dir: Optional[str] = None, **kwargs) -> Config:
    """
    Factory function to get a Config object.
    
    Args:
        model_name: Key in CONFIG_DICT (e.g., 'codebert', 'unixcoder', 'codet5')
        exp_name: If provided, output_dir will be 'output/dataset_patch/primevul/{exp_name}'
        output_dir: If provided, overrides exp_name logic.
        **kwargs: Other config parameters to override.
    """
    if model_name not in CONFIG_DICT:
        raise ValueError(f"Model {model_name} not found in CONFIG_DICT. Available: {list(CONFIG_DICT.keys())}")
    
    # Create a copy of the default config for this model
    base_config = CONFIG_DICT[model_name]
    # We need to create a new instance to avoid modifying the global preset
    # We use asdict to get values, but we need to exclude fields that are init=False
    config_data = {k: v for k, v in asdict(base_config).items() if k not in ['device', 'n_gpu']}
    config = Config(**config_data)
    
    # Determine output directory
    if output_dir:
        config.output_dir = output_dir
    elif exp_name:
        config.output_dir = os.path.join("output/dataset_patch/primevul", exp_name)
    else:
        config.output_dir = "output/dataset_patch/primevul/default"
        
    # Override other parameters
    config.update(**kwargs)
    
    # Ensure output directory exists
    if not os.path.exists(config.output_dir):
        os.makedirs(config.output_dir, exist_ok=True)
        
    return config
