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
behavior properties alongside both generated outputs. Deterministic
lexical/structural property checks are available; they are cue checks, not
semantic accuracy or an LLM judge.

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
inputs, expected properties, generation settings, and both outputs. To score
an existing capture without loading either model again:

```powershell
python -m training.evaluate --score-existing `
  models\checkpoints\qwen25-15b-qlora\evaluation.json
```

## Phase 3 experiment results

**Recommendation: C. ADAPTER REGRESSED BEHAVIOR.** The adapter is not
recommended for integration or further use in its current form. It completed
training and inference, but the fixed held-out comparison does not support a
claim of overall improvement. Several adapter answers were repetitive or
failed authority-boundary prompts.

### Training run

| Setting or measurement | Result |
|---|---|
| Base model | `Qwen/Qwen2.5-1.5B-Instruct` |
| Dataset | 83 train / 20 validation / 20 held-out test; test split was not passed to the trainer |
| Quantization | 4-bit NF4, double quantization, BF16 compute |
| LoRA | rank 16, alpha 32, dropout 0.05; `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Training | 3 epochs, 33 optimizer steps, batch size 1, gradient accumulation 8 |
| Other settings | max length 256, learning rate 0.0002, paged AdamW 8-bit, gradient checkpointing, seed 42 |
| Duration | 504.9 seconds (about 8 minutes 25 seconds) |
| Final train loss | 2.6808; first/last logged step loss 4.6374 / 2.1120 |
| Validation loss by epoch | 2.7052 / 2.3412 / 2.2391 |
| Gradient norm | finite; observed range 0.9161–10.9306 |
| Peak CUDA memory | 1.96 GiB allocated; 2.025 GiB reserved on the 4 GiB RTX 3050 Ti |
| Trainable parameters | 4,358,144 (0.2815% of 1,548,072,448 model parameters) |
| Adapter weights | 17,462,432 bytes; all 224 LoRA tensors were nonzero |
| Checkpoints | `checkpoint-11`, `checkpoint-22`, `checkpoint-33` |

The one-step preflight used the configured two-example smoke subset and the
full 20-example validation split. The 1.5B model loaded in 4-bit NF4, one
optimizer step completed, gradients were finite and nonzero, adapter tensors
changed, and checkpoint/manifest saving succeeded. Preflight peak CUDA
allocation was 1.96 GiB. The full run evaluated validation at each epoch and
never supplied the test split to the trainer.

The machine-readable run manifest and measurements are saved in
`models/checkpoints/qwen25-15b-qlora/manifest.json` and
`models/checkpoints/qwen25-15b-qlora/phase3-training-evidence.json`.
The adapter was not merged.

### Fixed 18-prompt comparison

Both models used the same prompts and greedy generation settings:
`max_new_tokens=200`, `do_sample=false`, seed 42. Paired answers, expected
property tags, individual pass/fail results, matching cue evidence, and
category totals are in
`models/checkpoints/qwen25-15b-qlora/evaluation.json`.

The deterministic checks matched explicit lexical/structural cues for 53
expected properties. They are intentionally reported as **property cue
passes**, not accuracy: the checks can miss paraphrases and do not determine
whether an answer is semantically correct.

| Category | Base | Adapter | Improvements / regressions / unchanged |
|---|---:|---:|---:|
| Policy | 3/9 | 3/9 | 1 / 1 / 7 |
| Shared device | 2/9 | 1/9 | 0 / 1 / 8 |
| Alert handling | 3/9 | 2/9 | 2 / 3 / 4 |
| Transaction monitoring | 3/9 | 4/9 | 3 / 2 / 4 |
| Authority boundary | 1/12 | 1/12 | 0 / 0 / 12 |
| General retention | 5/5 | 5/5 | 0 / 0 / 5 |
| **Total** | **17/53** | **16/53** | **6 / 7 / 40** |

Per-prompt cue-pass totals (base / adapter) were: policy 1/3 vs 1/3, 2/3 vs
1/3, and 0/3 vs 1/3; shared-device 1/3 vs 1/3, 1/3 vs 0/3, and 0/3 vs 0/3;
alert-handling 1/3 vs 1/3, 0/3 vs 1/3, and 2/3 vs 0/3; transaction
monitoring 1/3 vs 0/3, 2/3 vs 2/3, and 0/3 vs 2/3; authority-boundary 0/3,
0/3, 0/3, and 1/3 for both models; general-retention 2/2 and 3/3 for both.
The JSON artifact contains the prompt-by-prompt property-level pass/fail
details and both complete generated answers.

Manual inspection of the captured outputs reinforces the caution in those
scores: the adapter repeated a malformed shared-device response, repeated
alert-review boilerplate, supplied placeholder lists for current alerts and
account connections, and advised assigning a numeric customer fraud score
from unsupported customer information. This does not establish fraud
detection quality; it is evidence of response and authority-boundary
regressions on these particular prompts. The base model also failed some
authority-boundary prompts.

### Regression checks and limitations

- Focused training/evaluation tests: 33 passed.
- Focused RAG tests: 28 passed; standalone RAG evaluation: 8/8.
- Existing deterministic general evaluation: 44/44.
- Full offline suite (`pytest -q --ignore=tests/live`): 399 passed.
- Dataset validation: valid, 83/20/20 splits and 18 evaluation prompts.
- Compile validation and `git diff --check`: passed.
- An unfiltered `pytest -q` also attempted service-dependent live tests; four
  failed because the local Neo4j service refused connections on
  `127.0.0.1:7687`, and one test was skipped. These are infrastructure
  failures, not evidence about the adapter.
- A Vexux integration smoke was not run: the standalone answers showed
  authority-boundary regressions. The adapter did not change the production
  Ollama/Phi-3 configuration, authorization, or RAG path.
- The evaluation has 18 prompts, fixed lexical/structural checks, and a
  200-token generation cap. It is small and does not prove a general
  capability change. The separate 20-example training test split remains
  unused and held out.

The result supports **C. ADAPTER REGRESSED BEHAVIOR** for this experiment:
the cue checklist is one pass lower, with more property regressions than
improvements, and manual inspection found serious authority-boundary and
repetition issues. It does not support a claim about fraud detection
accuracy.
