from datasets import load_dataset

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    BitsAndBytesConfig,
)

from peft import (
    LoraConfig,
    prepare_model_for_kbit_training,
)

from trl import SFTTrainer

import torch

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

# -----------------------
# Dataset
# -----------------------

dataset = load_dataset(
    "json",
    data_files="data/datasets/train.jsonl",
    split="train",
)

# -----------------------
# Tokenizer
# -----------------------

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME
)

tokenizer.pad_token = tokenizer.eos_token


def formatting_func(example):

    return (
        f"### Instruction:\n"
        f"{example['instruction']}\n\n"
        f"{example['input']}\n\n"
        f"### Response:\n"
        f"{example['output']}"
    )


# -----------------------
# Quantization
# -----------------------

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

# -----------------------
# Model
# -----------------------

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    dtype=torch.float16,   # new API (torch_dtype is deprecated)
)

model = prepare_model_for_kbit_training(model)

# -----------------------
# LoRA
# -----------------------

peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    ],
)

# -----------------------
# Training
# -----------------------

training_args = TrainingArguments(

    output_dir="./experiments/checkpoints",

    per_device_train_batch_size=2,

    gradient_accumulation_steps=4,

    learning_rate=2e-4,

    num_train_epochs=3,

    logging_steps=1,

    save_strategy="epoch",

    fp16=True,

    bf16=False,

    report_to="none",
)

trainer = SFTTrainer(

    model=model,

    args=training_args,

    train_dataset=dataset,

    peft_config=peft_config,

    processing_class=tokenizer,

    formatting_func=formatting_func,
)

trainer.train()

trainer.save_model("./experiments/checkpoints")