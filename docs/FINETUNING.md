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

## Curated fraud-domain dataset

The initial generic pipeline fixture remains in `data/datasets/` (20 train,
5 validation, 3 test); it is not the fraud fine-tuning corpus. The curated
instruction dataset is under `data/fraud_finetuning/` and uses the same
conversational `messages` structure consumed by the training pipeline:

| Split | Examples | Use |
|---|---:|---|
| Train | 83 | Adapter optimization |
| Validation | 20 | In-training evaluation and checkpoint selection |
| Test | 20 | Held-out; never passed to the trainer |

The combined split distribution is 42 policy, 21 shared-device, 21
alert/monitoring, 17 response-style, 16 authority-boundary, and 6 general
retention examples. Generic retention is approximately 5% so domain behavior
remains the focus.

Training responses are concise, authored from the project-authored reference
corpus under `apps/fraud/knowledge/`, workflow behavior, and the documented
authority boundaries. They are instruction/response examples rather than
copies of whole retrieval documents. The data contains no live customer,
transaction, alert, account, or graph records; no demo customer IDs; no
credentials; and no database dumps. Customer-specific requests use generic
wording or a placeholder and teach that operational facts must come from
authorized sources. Do not add live fraud customer records to this dataset.

Run deterministic schema, count, category, duplicate, split-leakage, secret,
identifier, path, and content checks with:

```powershell
python -m data.validate_fraud_dataset
```

The separate fixed baseline evaluation prompts are in
`data/evaluation/fraud_baseline.jsonl` (18 prompts covering policy,
shared-device reasoning, alert handling, transaction monitoring, authority
boundaries, and general retention). The evaluator runs precisely those same
prompts against the configured base model and adapter and records expected
behavior properties alongside both generated outputs. It does not apply
subjective judging or claim that the adapter improves model quality.

## Run

In PowerShell, first load the project-scoped cache and temporary-directory
settings into the current session:

```powershell
. .\scripts\set_finetuning_env.ps1
```

This directs Hugging Face, Transformers, PyTorch, CUDA, and Triton cache/temp
activity to the existing `D:\NatWest\` directories. The settings are
process-scoped; dot-source the script again in each new PowerShell session.
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
outputs on the same fixed fraud baseline evaluation prompts:

```powershell
python -m training.evaluate
```

This creates `evaluation.json` beside the configured adapter. It captures
inputs, references, generation settings, and both outputs; it does not claim
that fine-tuning improves fraud detection. Model-quality conclusions require
the later fraud-specific evaluation phase.
