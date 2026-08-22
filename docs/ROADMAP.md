# Vexux-AI Technical Roadmap

This document outlines the current state and planned future capabilities of the Vexux-AI platform.

## 1. Project Status Matrix

```text
COMPLETED                    IN PROGRESS               PLANNED
Agent control loop           RAG-Gateway decoupling    Multi-Agent Systems
Structured planning          Test organization         Multi-Step DAG Plans
Scoped replanning            Capability dispatch      Persistent storage
Tool extensibility                                      Expanded tool ecosystem
Hardened local RAG                                      Async/streaming execution
Session conversation                                     Multi-backend inference
FastAPI and observability
Evaluation suite
```

## 2. Completed Capabilities

### 2.1 Core Agent Architecture
- Sequential control loop: `Plan -> Execute -> Observe -> Decide -> Replan -> Synthesize`.
- Structured multi-task planning with validated `Plan` and `Task` objects.
- Scoped failure recovery that preserves successful tasks and unexecuted remaining tasks.
- Response synthesis for multi-task results.
- Observer and DecisionMaker integration with bounded retries.

### 2.2 Tools and Capabilities
- Generic `ToolContract` and in-memory `ToolRegistry`.
- Dynamic tool metadata and lightweight input schemas supplied to the Planner.
- Calculator, string formatter, and text analyzer tools.

### 2.3 RAG
- File loader, sliding-window chunking, normalized embeddings, and FAISS vector search.
- `RAGPipeline.retrieve()` with configurable top-k and similarity threshold handling.
- Controlled no-result and retrieval-exception behavior through `ExecutionManager`.

### 2.4 Sessions, API, and Observability
- Bounded in-memory conversation history isolated by `session_id`.
- FastAPI endpoint: `POST /api/v1/agent/run`.
- Structured task logs containing request/session/task IDs, capability, outcome, and duration.

### 2.5 Evaluation and Training
- Deterministic system evaluation: `python -m evaluation`, currently 44 scenarios.
- QLoRA fine-tuning and dataset handling under `training/`, `lora/`, and `data/`.

## 3. In-Progress Capabilities

### 3.1 RAG and Model Gateway Decoupling
- Route all answer generation through the central `ModelGateway`.
- Keep retrieval and answer generation as distinct capability responsibilities.

### 3.2 Test Organization
- Gradually consolidate root verification scripts into a structured test package while retaining deterministic coverage.

### 3.3 Polymorphic Capability Dispatch
- Replace the current capability conditionals in `ExecutionManager` with a capability registry only when a concrete need justifies it.

## 4. Planned Capabilities

### 4.1 Multi-Step and DAG Planning
- Task dependencies, conditional branching, and partial DAG recovery.

### 4.2 Multi-Agent Orchestration
- Specialized agents and supervisor-worker coordination.

### 4.3 Persistent Conversation and Memory Storage
- Durable session state, episodic memory, and entity memory backends.

### 4.4 Expanded Tool Ecosystem
- Sandboxed code execution, web/API tools, and structured database tools.

### 4.5 Streaming and Asynchronous Execution
- Non-blocking generation, streaming responses, and asynchronous task scheduling.

### 4.6 Multi-Backend Model Gateway
- Optional vLLM, Ollama, Llama.cpp, and remote provider implementations.
