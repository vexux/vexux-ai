class DatasetFormatter:

    @staticmethod
    def format(dataset):

        def convert(example):

            return {
                "messages": [
                    {
                        "role": "user",
                        "content": example["instruction"]
                        + ("\n\n" + example["input"] if example["input"] else "")
                    },
                    {
                        "role": "assistant",
                        "content": example["output"]
                    },
                ]
            }

        return dataset.map(convert)