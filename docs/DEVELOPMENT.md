# Vexux-AI Development Guide

This document outlines the environment setup, test execution, coding guidelines, and development methodology for the Vexux-AI repository.

---

## 1. Environment Setup

### 1.1 Prerequisites
- Python 3.10 or Python 3.11 recommended
- CUDA-compatible GPU recommended for model inference and training (CPU fallback is supported in provider code)
- Git

### 1.2 Virtual Environment Setup

1. **Create and activate a virtual environment**:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python -m venv venv
   source venv/bin/activate
   ```

2. **Install runtime dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install development dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```

> [!NOTE]
> Ensure supporting RAG packages such as `sentence-transformers` and `faiss-cpu` (or `faiss-gpu`) are installed in the active environment if working on retrieval components.

---

## 2. Running Existing Tests & Scripts

The repository includes targeted verification scripts at the root level:

### 2.1 End-to-End Agent Verification
Tests the complete loop: intent classification, plan creation, execution against capabilities (RAG, Tool, Model), observation, and response generation.
```bash
python test_agent.py
```

### 2.2 Component Verification Scripts
- **Planner & Intent Classification**:
  ```bash
  python test_planner.py
  ```
  Validates model-based intent parsing (`retrieval`, `tool`, `general`) and `Plan` object generation.

- **Tool Registry & Calculator**:
  ```bash
  python test_tools.py
  ```
  Validates tool registration, listing, and execution with input argument dicts.

- **Model Gateway & Qwen Provider**:
  ```bash
  python test_model.py
  ```
  Tests direct text generation via `ModelGateway` backed by `QwenProvider` and the local LoRA checkpoint.

- **RAG Pipeline Test**:
  ```bash
  python test.py
  ```
  Tests document loading, FAISS vector search, and context-augmented response generation.

- **Contract Integration Check**:
  ```bash
  python test_contracts.py
  ```
  Validates component initialization contracts between embedder, vector store, and retriever.

### 2.3 Running Pytest
```bash
pytest
```

---

## 3. Training & Inference Workflows

### 3.1 QLoRA Fine-Tuning
To run the SFT fine-tuning pipeline using the dataset in `data/datasets/` and configuration in `configs/`:
```bash
python -m training.train
```
Alternatively, for the standalone experiment script:
```bash
python experiments/qlora_train.py
```

### 3.2 Interactive CLI Inference
To interact directly with the fine-tuned model via a terminal prompt:
```bash
python -m training.inference
```

---

## 4. Vertical-Slice Development Approach

Vexux-AI strictly adheres to a **Vertical-Slice Development Workflow**. Instead of creating broad horizontal abstractions across the whole system upfront, features and architectural concepts are developed one slice at a time across all three layers:

```text
┌────────────────────────────────────────────────────────┐
│ 1. Define Contract (core/contracts/)                   │
│    Create or update strict dataclass / Protocol        │
├────────────────────────────────────────────────────────┤
│ 2. Implement Capability / Logic                        │
│    Implement tool, provider, or agent submodule        │
├────────────────────────────────────────────────────────┤
│ 3. Wire Dependencies (core/composition.py)             │
│    Inject new components at the composition root       │
├────────────────────────────────────────────────────────┤
│ 4. Verify End-to-End (test_*.py)                       │
│    Run tests to validate full dataflow                 │
├────────────────────────────────────────────────────────┤
│ 5. Document (docs/)                                    │
│    Update architecture, contracts, and roadmap docs    │
└────────────────────────────────────────────────────────┘
```

### Step-by-Step Vertical Slice Checklist:
1. **Explain the Change**: Articulate why the architectural change is necessary and identify any alternatives.
2. **Review Existing Contracts**: Inspect `core/contracts/` to see if an existing contract can be reused or extended.
3. **Make the Smallest Vertical Change**: Implement only the minimal logic required to connect the layers.
4. **Preserve Isolation**: Ensure no domain logic (e.g. specialized keywords, business rules) leaks into `Agent`, `Observer`, `DecisionMaker`, or `ExecutionManager`.
5. **Execute Verification Tests**: Run the test suite and confirm all verification scripts pass.
6. **Update Documentation**: Keep `docs/CONTRACTS.md` and `docs/ARCHITECTURE.md` synchronized with the code.

---

## 5. Code Quality & Conventions

- **Formatting**: Run `black .` to maintain uniform Python formatting.
- **Linting**: Run `flake8` to detect syntax issues or unused imports.
- **Type Annotations**: Use Python type hints (`typing.Dict`, `typing.List`, `typing.Optional`, `typing.Protocol`, `dataclass`) across all contracts and method signatures.
- **Safety**: Tools performing dynamic evaluation or external execution must sandbox inputs and prevent arbitrary code execution (see `CalculatorTool`'s restricted builtins implementation).
