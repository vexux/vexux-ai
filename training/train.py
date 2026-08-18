from utils.config import ConfigLoader

from data.loader import DatasetLoader

from data.formatter import DatasetFormatter

from models.provider import ModelProvider

from lora.manager import LoRAManager

from training.factory import TrainerFactory


def main():

    model_config = ConfigLoader.load(
        "configs/model.yaml"
    )

    training_config = ConfigLoader.load(
        "configs/training.yaml"
    )

    dataset = DatasetLoader(
        "data/datasets"
    ).load()

    model, tokenizer = ModelProvider.load(
        model_config
    )

    dataset = DatasetFormatter.format(
        dataset["train"],
    )

    model = LoRAManager.apply(
        model,
        training_config,
    )

    model.print_trainable_parameters()

    model.config.use_cache = False

    print(dataset[0])

    trainer = TrainerFactory.create(
        model=model,
        tokenizer=tokenizer,
        dataset=dataset,
        config=training_config,
    )

    print("Model dtype:", next(model.parameters()).dtype)
    print("CUDA:", next(model.parameters()).device)

    trainer.train()

    trainer.save_model(
        training_config["training"]["output_dir"]
    )


if __name__ == "__main__":
    main()