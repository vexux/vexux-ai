# Experimental QLoRA fine-tuning

Fine-tuning is an experimental, separate model-specialization track. The
production Vexux runtime remains Ollama with `phi3:latest`; this training path
does not replace or modify that provider.

The primary local QLoRA target is `Qwen/Qwen2.5-1.5B-Instruct`. The
`Qwen/Qwen2.5-0.5B-Instruct` model is reserved as the lower-memory smoke-test
fallback. Training configuration is isolated in
[`configs/finetuning.yaml`](../configs/finetuning.yaml); production
[`configs/model.yaml`](../configs/model.yaml) is not used to set training
hyperparameters.

## Dataset splits

The current `data/datasets/` files are a small, generic programming/general-AI
dataset for pipeline validation, not fraud-training data. `train.jsonl` is
used for optimization, `validation.jsonl` is passed to trainer evaluation,
and `test.jsonl` is held out for the later base-versus-adapter evaluation.
Training never passes the test split to the trainer. Do not add live fraud
customer records or operational evidence to a training dataset.

## Run

With the repository virtual environment and local Hugging Face dependencies
installed, run the one-step smoke path:

```powershell
python -m training.train --smoke
```

It defaults to the 0.5B model, 4-bit NF4 quantization, one optimizer step,
and writes its adapter below
`models/checkpoints/qwen25-05b-smoke/`. Override the model only when
intentionally selecting another compatible local Qwen checkpoint. For the
primary configured run (not part of routine validation), omit `--smoke`:

```powershell
python -m training.train
```

`training/train.py` is canonical; `experiments/qlora_train.py` is only a
compatibility wrapper. Training uses batch size 1, gradient accumulation 8,
sequence length 256, gradient checkpointing, paged 8-bit AdamW, and BF16
mixed precision on supported GPUs. The current 4 GiB GPU
supports BF16; hardware without BF16 support must explicitly switch both
training and compute dtype to FP16 in the config. The trainer prepares the
quantized base model and attaches LoRA through TRL's supported QLoRA path.
A CUDA device is required for configured 4-bit QLoRA.
CUDA out-of-memory errors are reported as failures, not converted into success.

PEFT adapter weights, the tokenizer, trainer checkpoints, and a machine-readable
`manifest.json` are stored in the experiment directory. Local
`models/checkpoints/` artifacts are ignored by Git.

## Held-out output capture

After an adapter has been produced, capture deterministic base and adapter
outputs on the same held-out test examples:

```powershell
python -m training.evaluate
```

This creates `evaluation.json` beside the configured adapter. It captures
inputs, references, generation settings, and both outputs; it does not claim
that fine-tuning improves fraud detection. Model-quality conclusions require
the later fraud-specific evaluation phase.
