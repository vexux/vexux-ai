import torch

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
)

from peft import PeftModel

from core.contracts.capabilities import ModelProviderContract


class QwenProvider:

    def __init__(
        self,
        model_name: str,
        adapter_path: str,
    ):

        self._name = "qwen"

        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name
        )

        self.tokenizer.pad_token = (
            self.tokenizer.eos_token
        )

        base_model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float32,
            device_map="auto",
        )

        self.model = PeftModel.from_pretrained(
            base_model,
            adapter_path,
        )

        self.model.eval()

    @property
    def name(self) -> str:

        return self._name

    def generate(
        self,
        prompt: str,
        **kwargs
    ) -> str:

        messages = [
            {
                "role": "user",
                "content": prompt,
            }
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer(
            text,
            return_tensors="pt"
        )

        input_device = (
            self.model.get_input_embeddings()
            .weight.device
        )

        inputs = {
            key: value.to(input_device)
            for key, value in inputs.items()
        }

        generation_kwargs = {
            "max_new_tokens": 200,
            "pad_token_id": self.tokenizer.eos_token_id,
        }

        generation_kwargs.update(kwargs)

        do_sample = generation_kwargs.pop(
            "do_sample",
            True
        )

        if do_sample:

            generation_kwargs.update({
                "do_sample": True,
                "temperature": generation_kwargs.pop(
                    "temperature",
                    0.7
                ),
                "top_p": generation_kwargs.pop(
                    "top_p",
                    0.9
                ),
                "top_k": generation_kwargs.pop(
                    "top_k",
                    50
                ),
            })

        else:

            # Explicitly tell Transformers not to use
            # sampling parameters for greedy decoding.
            generation_kwargs.update({
                "do_sample": False,
            })

        if not do_sample:

            self.model.generation_config.temperature = None
            self.model.generation_config.top_p = None
            self.model.generation_config.top_k = None    

        with torch.no_grad():

            outputs = self.model.generate(
                **inputs,
                **generation_kwargs,
            )

        generated = outputs[
            0
        ][inputs["input_ids"].shape[-1]:]

        response = self.tokenizer.decode(
            generated,
            skip_special_tokens=True,
        )

        return response.strip()