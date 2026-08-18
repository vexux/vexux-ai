import torch

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
)

from peft import PeftModel

from utils.config import ConfigLoader


class InferencePipeline:

    def __init__(self):

        config = ConfigLoader.load("configs/model.yaml")

        self.model_name = config["model"]["name"]

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name
        )

        self.tokenizer.pad_token = self.tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.float32,
        )

        self.model = PeftModel.from_pretrained(
            base_model,
            "models/checkpoints"
        )

        self.model = self.model.to(self.device)

        self.model.eval()

    def generate(self, prompt):

        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self.tokenizer(
            text,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():

            outputs = self.model.generate(

                **inputs,

                max_new_tokens=200,

                temperature=0.7,

                top_p=0.9,

                do_sample=True,

                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[-1]:]

        response = self.tokenizer.decode(
            generated,
            skip_special_tokens=True,
        )

        return response.strip()


def main():

    pipeline = InferencePipeline()

    print("=" * 60)
    print("Vexux-AI")
    print("Type 'exit' to quit")
    print("=" * 60)

    while True:

        prompt = input("\nYou: ")

        if prompt.lower() == "exit":
            break

        answer = pipeline.generate(prompt)

        print("\nVexux:", answer)


if __name__ == "__main__":
    main()