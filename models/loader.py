from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)

import torch


class ModelLoader:

    @staticmethod
    def load(config):

        model_config = config["model"]
        tokenizer_config = config["tokenizer"]
        quant_config = config["quantization"]
        device_config = config["device"]

        quantization = None

        if quant_config["enabled"]:

            compute_dtype = getattr(
                torch,
                quant_config["compute_dtype"]
            )

            quantization = BitsAndBytesConfig(
                load_in_4bit=quant_config["load_in_4bit"],
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_quant_type=quant_config["quant_type"],
                bnb_4bit_use_double_quant=quant_config["use_double_quant"],
            )

        tokenizer = AutoTokenizer.from_pretrained(
            model_config["name"],
            trust_remote_code=tokenizer_config["trust_remote_code"],
        )

        tokenizer.padding_side = tokenizer_config["padding_side"]

        model = AutoModelForCausalLM.from_pretrained(
            model_config["name"],
            device_map=device_config["device_map"],
            quantization_config=quantization,
            torch_dtype=torch.float16,
            trust_remote_code=tokenizer_config["trust_remote_code"],
        )

        return model, tokenizer