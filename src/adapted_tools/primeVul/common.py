import os
import json
import torch
import csv
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer

class PrimeVulDataset(Dataset):
    def __init__(self, file_path, tokenizer, max_length=512, split=None, my_primevul_format=False):
        self.file_path = file_path
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.split = split
        self.my_primevul_format = my_primevul_format
        self.samples = self._load_data()

    def _load_data(self):
        if self.my_primevul_format:
            return self._load_data_from_split()

        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")
            
        samples = []
        with open(self.file_path, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    samples.append(item)
                except json.JSONDecodeError:
                    continue
        return samples

    def _load_data_from_split(self):
        # file_path is the directory
        index_file = os.path.join(self.file_path, 'index_split.csv')
        data_file = os.path.join(self.file_path, 'ds.jsonl')
        
        if not os.path.exists(index_file):
            raise FileNotFoundError(f"Index file not found: {index_file}")
        if not os.path.exists(data_file):
            raise FileNotFoundError(f"Data file not found: {data_file}")
            
        # Load split info
        valid_ids = set()
        with open(index_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['split'] == self.split:
                    valid_ids.add(row['id'])
        
        if not valid_ids:
            print(f"Warning: No samples found for split '{self.split}' in {index_file}")
            return []
            
        samples = []
        with open(data_file, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    if item.get('id') in valid_ids:
                        samples.append(item)
                except json.JSONDecodeError:
                    continue
        
        print(f"Loaded {len(samples)} samples for split '{self.split}'")
        return samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        item = self.samples[idx]
        # Support both 'func_src' (PrimeVul) and 'code' (generic) keys
        code = item.get('func_src', item.get('code', ''))
        label = int(item.get('label', 0))
        
        encoding = self.tokenizer(
            code,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].squeeze(),
            'attention_mask': encoding['attention_mask'].squeeze(),
            'label': torch.tensor(label, dtype=torch.long),
            'id': item.get('id', str(idx)),
            'cve_id': item.get('cve_id', '')
        }

def get_dataloader(file_path, tokenizer, batch_size=16, max_length=512, shuffle=False, num_workers=4, split=None, my_primevul_format=False):
    dataset = PrimeVulDataset(file_path, tokenizer, max_length, split=split, my_primevul_format=my_primevul_format)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, num_workers=num_workers)
