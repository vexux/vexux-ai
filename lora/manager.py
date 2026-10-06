from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
)


class LoRAManager:

    @staticmethod
    def create_config(model, config):
        lora = config["lora"]
        target_modules = lora["target_modules"]
        module_names = [name for name, _ in model.named_modules()]
        missing_targets = [
            target for target in target_modules
            if not any(name == target or name.endswith(f".{target}") for name in module_names)
        ]
        if missing_targets:
            raise ValueError(
                "LoRA target modules were not found in the selected model: "
                + ", ".join(missing_targets)
            )
        return LoraConfig(
            r=lora["r"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            bias=lora.get("bias", "none"),
            task_type=lora.get("task_type", "CAUSAL_LM"),
            target_modules=target_modules,
        )

    @staticmethod
    def apply(model, config):
        lora_config = LoRAManager.create_config(model, config)
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=config["training"]["gradient_checkpointing"],
        )
        return get_peft_model(model, lora_config)