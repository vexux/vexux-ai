from trl import SFTConfig, SFTTrainer

class TrainerFactory:

    @staticmethod
    def create(
        model,
        tokenizer,
        train_dataset,
        validation_dataset,
        config,
        *,
        max_steps: int = -1,
        peft_config=None,
    ):
        training = config["training"]
        args = SFTConfig(
            output_dir=training["output_dir"],
            learning_rate=training["learning_rate"],
            num_train_epochs=training["epochs"],
            per_device_train_batch_size=training["per_device_train_batch_size"],
            per_device_eval_batch_size=training["per_device_eval_batch_size"],
            gradient_accumulation_steps=training["gradient_accumulation_steps"],
            optim=training["optimizer"],
            gradient_checkpointing=training["gradient_checkpointing"],
            gradient_checkpointing_kwargs={"use_reentrant": False},
            fp16=training["fp16"],
            bf16=training["bf16"],
            logging_steps=training["logging_steps"],
            eval_strategy=training["eval_strategy"],
            eval_steps=training.get("eval_steps"),
            save_strategy=training["save_strategy"],
            save_steps=training["save_steps"],
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            report_to="none",
            max_length=training["max_sequence_length"],
            seed=training["seed"],
            data_seed=training["seed"],
            max_steps=max_steps,
        )

        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=train_dataset,
            eval_dataset=validation_dataset,
            args=args,
            peft_config=peft_config,
        )
        print_trainable = getattr(
            getattr(trainer, "model", None),
            "print_trainable_parameters",
            None,
        )
        if callable(print_trainable):
            print_trainable()
        return trainer