class DatasetFormatter:

    @staticmethod
    def format(dataset):
        def convert(example):
            messages = example.get("messages")
            if messages is not None:
                if not isinstance(messages, list) or not messages:
                    raise ValueError("Every fine-tuning example must have non-empty messages.")
                for message in messages:
                    if (
                        not isinstance(message, dict)
                        or message.get("role") not in {"system", "user", "assistant"}
                        or not isinstance(message.get("content"), str)
                        or not message["content"].strip()
                    ):
                        raise ValueError(
                            "Fine-tuning messages require an allowed role and non-empty content."
                        )
                return {"messages": messages}
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