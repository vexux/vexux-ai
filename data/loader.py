from datasets import load_dataset


class DatasetLoader:
    """
    Loads train, validation and test datasets.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def load(self):

        dataset = load_dataset(
            "json",
            data_files={
                "train": f"{self.data_dir}/train.jsonl",
                "validation": f"{self.data_dir}/validation.jsonl",
                "test": f"{self.data_dir}/test.jsonl",
            },
        )

        return dataset