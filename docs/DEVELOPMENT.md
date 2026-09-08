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
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python -m venv .venv
   source .venv/bin/activate
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
python scripts/manual/run_agent.py
```

### 2.2 Authoritative commands

The complete local setup, database bootstrap, provider behavior, and startup
commands are maintained in [docs/SETUP.md](SETUP.md). Avoid relying on old
root-level demo names; current manual entry points live under
`scripts/manual/`.

### 2.3 Running Pytest
```bash
python -m pytest
```

### 2.4 Canonical deterministic validation

From the repository root, use these commands for the same checks run in CI:

```bash
python -m pytest
python -m evaluation
```

CI sets `MODEL_PROVIDER=fake`, so deterministic tests do not require external
credentials. The live Mistral test is separate and requires both
`MISTRAL_API_KEY` and `RUN_LIVE_MISTRAL_TESTS=1`.

### 2.5 Running the API

```bash
MODEL_PROVIDER=fake uvicorn api.main:app --host 0.0.0.0 --port 8000
```

On Windows PowerShell:

```powershell
$env:MODEL_PROVIDER = "fake"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The API exposes `POST /api/v1/agent/run`, `POST /api/v1/orchestrator/run`,
`GET /health`, and `GET /ready`. The fake provider is intended for local and CI
validation; no provider credentials are required.

### 2.6 Optional Neo4j graph backend

The generic `KnowledgeGraphContract` is implemented by both the in-memory
backend and the optional `Neo4jKnowledgeGraph` adapter. Configure
`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and optionally
`NEO4J_DATABASE`/`NEO4J_GRAPH_NAME`. Neo4j is registered through the existing
`KnowledgeGraphRegistry` only when configured; normal startup and tests do not
require a Neo4j server. The adapter uses parameterized queries and does not
provide arbitrary Cypher execution.

### 2.7 Optional SQL knowledge source

`SQLKnowledgeSource` provides a contract-level adapter to relational data.
Set `SQL_DATABASE_PATH` to an existing SQLite database to register the
`business_db` source. Queries are read-only single `SELECT` statements and
support parameterized values; writes and multiple statements are rejected.
The source runs through `KnowledgeSourceRegistry`, `KnowledgeDecision`, and
`ExecutionManager`, so existing authorization, audit, and evidence behavior
is preserved. Use [SETUP.md](SETUP.md) for the authoritative local database
bootstrap and verification flow. Historical demonstrations are retained under
`scripts/history/` and are not authoritative entry points.

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
