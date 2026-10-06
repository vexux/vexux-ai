from core.contracts.capabilities import ModelProviderContract


class QwenProvider:

    def __init__(
        self,
        model_name: str,
        adapter_path: str | None = None,
        *,
        load_in_4bit: bool = False,
        compute_dtype: str = "float16",
        quant_type: str = "nf4",
        use_double_quant: bool = True,
    ):
        # Keep the heavyweight ML stack out of module import and pytest
        # collection; it is needed only when this provider is instantiated.
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._name = "qwen"
        self.model_name = model_name
        self.adapter_path = adapter_path
        self.load_in_4bit = load_in_4bit
        self._torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if load_in_4bit and not torch.cuda.is_available():
            raise RuntimeError(
                "4-bit Qwen adapter inference requires CUDA, but no CUDA device is available."
            )

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name
        )

        self.tokenizer.pad_token = (
            self.tokenizer.eos_token
        )

        model_kwargs = {"device_map": "auto"}
        if load_in_4bit:
            try:
                dtype = getattr(torch, compute_dtype)
            except AttributeError as exc:
                raise ValueError(f"Unsupported Qwen compute dtype: {compute_dtype}") from exc
            if compute_dtype == "bfloat16" and not torch.cuda.is_bf16_supported():
                raise RuntimeError(
                    "bfloat16 Qwen inference is enabled, but the selected CUDA device "
                    "does not support it."
                )
            model_kwargs.update({
                "torch_dtype": dtype,
                "quantization_config": BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=dtype,
                    bnb_4bit_quant_type=quant_type,
                    bnb_4bit_use_double_quant=use_double_quant,
                ),
            })
        else:
            model_kwargs["torch_dtype"] = torch.float32
        base_model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
        self.model = (
            PeftModel.from_pretrained(base_model, adapter_path)
            if adapter_path
            else base_model
        )

        self.model.eval()

    @property
    def name(self) -> str:

        return self._name

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "provider": self.name,
            "model": self.model_name,
            "adapter_path": self.adapter_path or "",
            "runtime_mode": "local",
        }

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

        with self._torch.no_grad():
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