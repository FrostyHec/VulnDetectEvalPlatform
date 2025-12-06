from .llm import LLM

class DummyModel(LLM):
    def __init__(self, model_name, logger, **kwargs):
        super().__init__(model_name, logger, {"dummy": "dummy"}, **kwargs)

    def predict(self, prompt, expect_json=False, batch_size=0, no_progress_bar=False):
        if isinstance(prompt, list) and len(prompt) > 0 and isinstance(prompt[0], list):
            # Batch of prompts
            return ["none"] * len(prompt)
        return "none"
