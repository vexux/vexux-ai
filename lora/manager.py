from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
)


class LoRAManager:

    @staticmethod
    def apply(model, config):

        model = prepare_model_for_kbit_training(model)

        lora = config["lora"]

        lora_config = LoraConfig(
            r=lora["r"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            bias=lora["bias"],
            task_type=lora["task_type"],
            target_modules=lora["target_modules"],
        )

        model = get_peft_model(
            model,
            lora_config,
        )

        return model