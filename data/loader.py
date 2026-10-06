from datasets import load_dataset
from pathlib import Path


class DatasetLoader:
    """
    Loads train, validation and test datasets.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def load(self):
        split_files = {
            split: str(self.data_dir / f"{split}.jsonl")
            for split in ("train", "validation", "test")
        }
        missing = [path for path in split_files.values() if not Path(path).is_file()]
        if missing:
            raise FileNotFoundError(
                "Required fine-tuning dataset split file(s) are missing: "
                + ", ".join(missing)
            )
        dataset = load_dataset(
            "json",
            data_files=split_files,
        )
        if set(dataset.keys()) != {"train", "validation", "test"}:
            raise ValueError("Dataset loader did not return train, validation, and test splits.")
        for split_name in ("train", "validation", "test"):
            for index, example in enumerate(dataset[split_name]):
                if "messages" in example:
                    messages = example["messages"]
                    if not isinstance(messages, list) or not messages:
                        raise ValueError(f"{split_name} example {index} messages must be a non-empty list.")
                    for message in messages:
                        if not isinstance(message, dict) or message.get("role") not in {
                            "system", "user", "assistant",
                        }:
                            raise ValueError(
                                f"{split_name} example {index} contains an unsupported message role."
                            )
                        if not isinstance(message.get("content"), str) or not message["content"].strip():
                            raise ValueError(
                                f"{split_name} example {index} messages need non-empty content."
                            )
                    if not any(message["role"] == "user" for message in messages):
                        raise ValueError(f"{split_name} example {index} must contain a user message.")
                    if not any(message["role"] == "assistant" for message in messages):
                        raise ValueError(
                            f"{split_name} example {index} must contain an assistant response."
                        )
                else:
                    instruction = example.get("instruction")
                    response = example.get("output")
                    extra_input = example.get("input", "")
                    if not isinstance(instruction, str) or not instruction.strip():
                        raise ValueError(
                            f"{split_name} example {index} must have a non-empty instruction."
                        )
                    if not isinstance(response, str) or not response.strip():
                        raise ValueError(
                            f"{split_name} example {index} must have a non-empty output."
                        )
                    if not isinstance(extra_input, str):
                        raise ValueError(f"{split_name} example {index} input must be a string.")
        return dataset