# Vexux-AI Technical Roadmap

This document outlines the current state, ongoing architectural refinements, and planned future capabilities for the Vexux-AI platform.

---

## 1. Project Status Matrix

```text
┌────────────────────────┬─────────────────────────┬────────────────────────┐
│      COMPLETED         │       IN PROGRESS       │        PLANNED         │
├────────────────────────┼─────────────────────────┼────────────────────────┤
│ ✓ Core Agent Loop      │ ◐ Dynamic Tool Schemas  │ ○ Multi-Agent Systems  │
│ ✓ Multi-Task Planning  │ ◐ RAG-Gateway Decouple  │ ○ Multi-Step DAG Plans │
│ ✓ Scoped Replanning    │ ◐ Formal Pytest Suite   │ ○ Memory Store Impl    │
│ ✓ Response Synthesizer │ ◐ ExecutionManager Ref  │ ○ Tool Ecosystem       │
│ ✓ Core Contracts       │                         │ ○ Automated Evaluation │
│ ✓ Model Gateway & LoRA │                         │ ○ Async/Streaming Exec │
│ ✓ Tool Registry & Calc │                         │ ○ vLLM / Ollama        │
│ ✓ Local RAG (FAISS)    │                         │                        │
│ ✓ QLoRA Fine-Tuning    │                         │                        │
└────────────────────────┴─────────────────────────┴────────────────────────┘
```

---

## 2. Completed Capabilities

### 2.1 Core Agent Architecture
- **Multi-Task Agent Control Loop**: Sequential execution cycle (`Plan -> Execute -> Observe -> Decide -> Replan -> Synthesize`) with bounded retries (`agent/agent.py`).
- **Scoped Failure Recovery & Replanning**: Isolates failures to the specific failed task, records `completed_tasks`, preserves unexecuted tasks, and prompts the SLM for targeted recovery plans without re-splitting or repeating already completed tasks (`agent/agent.py`, `agent/planner.py`).
- **Response Synthesis**: Aggregates intermediate outputs from multi-task observations into a coherent, clean final answer (`agent/response_synthesizer.py`).
- **Standardized Contracts**: Formal dataclass and protocol contracts in `core/contracts/` (`Task`, `Plan`, `AgentContext`, `ExecutionResult`, `Intent`, `Observation`, `AgentResponse`, `Capability`, `RetrievalContract`, `ToolContract`, `MemoryContract`, `ModelProviderContract`).
- **Context Management**: Request-scoped runtime context tracking active plans, current task, completed tasks, and full observation histories (`core/context/context_manager.py`).
- **Observer & Decision Maker**: Execution result normalization with `task_id` tracking and binary `DONE`/`REPLAN` transition logic (`agent/observer.py`, `agent/decision.py`).

### 2.2 Model Gateway & Inference
- **Model Gateway**: Abstraction layer separating model consumers from underlying providers (`core/model_gateway/gateway.py`).
- **Fine-Tuned Qwen 2.5 Provider**: Hugging Face causal LM provider with PEFT LoRA adapter support and chat templates (`models/providers/qwen.py`).
- **Config-Driven Model Loader**: YAML-based 4-bit BitsAndBytes quantization and device configuration (`models/loader.py`, `configs/model.yaml`).

### 2.3 Tools & Capabilities
- **Tool Registry**: Dynamic registration and lookup for tools satisfying `ToolContract` (`core/tools/registry.py`).
- **Calculator Tool**: Sandboxed arithmetic evaluation tool (`core/tools/calculator.py`).

### 2.4 Retrieval-Augmented Generation (RAG)
- **Local RAG Pipeline**: File document loader, sliding-window chunker, `SentenceTransformer` embedder (`bge-small-en-v1.5`), FAISS `IndexFlatIP` vector index, and prompt builder (`rag/`).

### 2.5 Training & Experimentation
- **QLoRA Fine-Tuning Pipeline**: SFTTrainer factory with LoRA parameter management and multi-epoch training (`training/train.py`, `training/factory.py`, `experiments/qlora_train.py`).
- **Dataset Handling**: JSONL dataset loader and chat formatting utilities (`data/loader.py`, `data/formatter.py`).

---

## 3. In-Progress Capabilities & Technical Refinements

### 3.1 Dynamic Tool Schema Generation in Planner
- **Objective**: Transition `agent/planner.py` from hardcoded prompt rules (e.g. static references to `"calculator"`) to dynamic prompt schemas derived at runtime from `ToolRegistry.list_tools()` and `tool.description`.
- **Target**: Eliminate domain and tool coupling from the planner.

### 3.2 RAG and Model Gateway Decoupling
- **Objective**: Refactor `RAGPipeline` so that retrieval returns chunks conforming to `RetrievalContract` rather than running its own internal `InferencePipeline`.
- **Target**: Route all SLM generation through the central `ModelGateway`.

### 3.3 Formalizing Test Suite
- **Objective**: Transition root verification scripts (`test_*.py`) into a structured `tests/` directory with pytest fixtures, mock model providers, and deterministic CI execution.

### 3.4 Polymorphic Execution Dispatch
- **Objective**: Replace hardcoded capability conditionals (`if capability == "retrieval": ...`) in `ExecutionManager` with a polymorphic capability registry implementing the `Capability` protocol.

---

## 4. Planned Capabilities (Future Horizons)

### 4.1 Multi-Step & DAG Planning
- Extend `Planner` to generate dependency graphs (DAGs) of tasks where downstream tasks receive outputs from upstream tasks.
- Add support for partial failure recovery and conditional branching during execution.

### 4.2 Multi-Agent Orchestration
- Introduce specialized subagents (e.g., Research Agent, Coding Agent, Review Agent).
- Implement supervisor-worker coordination, inter-agent message passing, and capability delegation protocols.

### 4.3 Persistent Memory Subsystem
- Implement concrete backends for `MemoryContract`:
  - **Short-Term / Session Memory**: Multi-turn conversation buffer.
  - **Episodic Memory**: Vector-indexed past agent trajectories and successful plans.
  - **Entity Memory**: Key-value knowledge graph for user preferences and facts.

### 4.4 Pluggable Tool Ecosystem
- Add sandboxed code execution environment (Python interpreter sandbox).
- Add web search / API query tool.
- Add structured database / SQL querying tools.

### 4.5 Automated Evaluation Suite
- Implement `training/evaluate.py` to benchmark:
  - Intent classification precision/recall on unseen datasets.
  - Plan validity and parameter extraction accuracy.
  - End-to-end task completion rates and token efficiency.

### 4.6 Streaming & Asynchronous Engine
- Implement asynchronous agent execution (`async def run()`) supporting streaming token yields, concurrent tool execution, and non-blocking background tasks.

### 4.7 Multi-Backend Model Gateway
- Expand `ModelProviderContract` implementations to support local high-throughput inference engines (vLLM, Ollama, Llama.cpp) and remote API endpoints.
