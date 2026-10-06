class DatasetFormatter:

    @staticmethod
    def format(dataset):
        def convert(example):
            instruction = example.get("instruction")
            response = example.get("output")
            extra_input = example.get("input", "")
            if not isinstance(instruction, str) or not instruction.strip():
                raise ValueError("Every fine-tuning example must have a non-empty instruction.")
            if not isinstance(response, str) or not response.strip():
                raise ValueError("Every fine-tuning example must have a non-empty output.")
            if not isinstance(extra_input, str):
                raise ValueError("Fine-tuning example input must be a string.")
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": instruction
                        + ("\n\n" + extra_input if extra_input else "")
                    },
                    {
                        "role": "assistant",
                        "content": response
                    },
                ]
            }

        columns = getattr(dataset, "column_names", None)
        if columns:
            return dataset.map(convert, remove_columns=columns)
        return dataset.map(convert)