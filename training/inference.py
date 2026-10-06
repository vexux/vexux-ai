"""Configurable local inference for experimental Qwen PEFT adapters."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

from training.configuration import (
    DEFAULT_CONFIG_PATH,
    load_finetuning_config,
    resolve_config_path,
)


class InferencePipeline:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        *,
        model_name: str | None = None,
        adapter_path: str | Path | None = None,
        load_adapter: bool = True,
        provider_factory=None,
    ):
        from models.providers.qwen import QwenProvider

        config = load_finetuning_config(config_path)
        self.config = config
        self.model_name = model_name or config["model"]["base_model"]
        configured_adapter_path = (
            Path(adapter_path)
            if adapter_path is not None
            else resolve_config_path(config["output"]["directory"], config)
            / config["output"]["experiment_name"]
        )
        if load_adapter and not configured_adapter_path.is_dir():
            raise FileNotFoundError(
                f"Fine-tuned adapter directory does not exist: {configured_adapter_path}"
            )
        selected_adapter = str(configured_adapter_path) if load_adapter else None
        quantization = config["inference"]
        factory = provider_factory or QwenProvider
        self.provider = factory(
            model_name=self.model_name,
            adapter_path=selected_adapter,
            load_in_4bit=quantization["load_in_4bit"],
            compute_dtype=quantization["compute_dtype"],
            quant_type=quantization["quant_type"],
            use_double_quant=quantization["use_double_quant"],
        )
        self.adapter_path = selected_adapter

    def generate(self, prompt: str, **generation_overrides: Any) -> str:
        from transformers import set_seed

        generation = dict(self.config["generation"])
        generation.update(generation_overrides)
        seed = generation.pop("seed", None)
        if seed is not None:
            set_seed(seed)
        return self.provider.generate(prompt, **generation)

    def close(self) -> None:
        import torch

        del self.provider
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def main() -> int:
    pipeline = InferencePipeline()
    try:
        print("Experimental Qwen adapter inference. Type 'exit' to quit.")
        while True:
            prompt = input("\nYou: ")
            if prompt.strip().lower() == "exit":
                break
            print("\nAssistant:", pipeline.generate(prompt))
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
