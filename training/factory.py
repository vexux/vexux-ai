from trl import SFTTrainer, SFTConfig

class TrainerFactory:

    @staticmethod
    def create(
        model,  
        tokenizer,
        dataset,
        config,
    ):

        training = config["training"]

        args = SFTConfig(

            output_dir=training["output_dir"],

            learning_rate=training["learning_rate"],

            num_train_epochs=training["epochs"],

            per_device_train_batch_size=training["batch_size"],

            gradient_accumulation_steps=training["gradient_accumulation_steps"],

            logging_steps=training["logging_steps"],

            save_steps=training["save_steps"],

            bf16=False,

            fp16=False,

            report_to="none",

            max_length=512,
        )

        trainer = SFTTrainer(

            model=model,

            processing_class=tokenizer,

            train_dataset=dataset,

            args=args,
        )

        return trainer