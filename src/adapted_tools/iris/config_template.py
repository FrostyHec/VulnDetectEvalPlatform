from dataclasses import dataclass, field
from typing import List, Optional
import itertools

@dataclass
class IrisConfig:
    model_type: str = "gpt-4"
    key_type: str = "openai"  # 'openai' or 'azure' or 'custom'
    api_base: str = "https://api.openai.com/v1"
    api_keys: List[str] = field(default_factory=lambda: ["sk-placeholder"])
    
    # Internal iterator for key rotation
    _key_iterator: Optional[object] = None

    def __post_init__(self):
        self._key_iterator = itertools.cycle(self.api_keys)

    def get_next_key(self) -> str:
        if not self.api_keys:
            raise ValueError("No API keys provided in config.")
        return next(self._key_iterator)

# Example usage:
# config = IrisConfig(
#     model_type="gpt-4-1106-preview",
#     key_type="openai",
#     api_base="https://api.openai.com/v1",
#     api_keys=["sk-key1", "sk-key2"]
# )
