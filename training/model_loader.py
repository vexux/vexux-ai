"""Local Hugging Face model loading for QLoRA training."""

from __future__ import annotations

from typing import Any


class TrainingModelLoader:
    @staticmethod
    def load(model_name: str, config: dict[str, Any]):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        quantization = config["quantization"]
        if quantization["load_in_4bit"] and not torch.cuda.is_available():
            raise RuntimeError(
                "QLoRA requires CUDA when 4-bit loading is enabled; no CUDA device is available."
            )
        if config["training"]["bf16"] and (
            not torch.cuda.is_available() or not torch.cuda.is_bf16_supported()
        ):
            raise RuntimeError(
                "bfloat16 training is enabled, but the selected CUDA device does not support it. "
                "Configure fp16 with a float16 compute dtype for this device."
            )

        dtype_name = quantization["compute_dtype"]
        try:
            compute_dtype = getattr(torch, dtype_name)
        except AttributeError as exc:
            raise ValueError(f"Unsupported quantization compute dtype: {dtype_name}") from exc

        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=config.get("tokenizer", {}).get("trust_remote_code", True),
        )
        if tokenizer.pad_token is None:
            if tokenizer.eos_token is None:
                raise ValueError(
                    f"Tokenizer for {model_name} has neither a pad token nor an EOS token."
                )
            tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = config.get("tokenizer", {}).get("padding_side", "right")

        quantization_config = None
        if quantization["load_in_4bit"]:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_quant_type=quantization["quant_type"],
                bnb_4bit_use_double_quant=quantization["use_double_quant"],
            )

        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map=config.get("device", {}).get("device_map", "auto"),
            quantization_config=quantization_config,
            torch_dtype=compute_dtype,
            trust_remote_code=config.get("tokenizer", {}).get("trust_remote_code", True),
        )
        return model, tokenizer
