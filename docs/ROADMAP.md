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
Knowledge source abstraction                            SQL/API/graph knowledge sources
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
- `RAGKnowledgeSource` and `KnowledgeSourceRegistry` provide a domain-agnostic retrieval seam; only the RAG source is implemented.
- Retrieval tasks can select registered sources and grounded responses attribute the actual selected source; advanced semantic routing remains future work.

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
- Task dependencies (Phase 13 implemented): Planner supports Task.depends_on, the Agent performs dependency-aware deterministic scheduling. See limitations below.
- Phase 14 (bounded local concurrency): Agent now supports bounded parallel execution of independent ready tasks via ThreadPoolExecutor. Configure the degree of parallelism with the environment variable `AGENT_MAX_PARALLEL_TASKS` (default `1` for legacy sequential behavior). This is local-only concurrency and does not change replanning semantics.
- Future work: conditional branching, richer dataflow (output substitution), distributed DAG execution and advanced recovery strategies.


### Notes on Phase 13/14 (current limitations)
- Execution is deterministic: when multiple tasks are ready the Agent preserves plan order for deterministic submission; with parallelism enabled independent tasks may execute concurrently.
- Parallelism is bounded and local — no distributed scheduling or external worker pools.
- No general output substitution or complex dataflow between tasks in Phase 13/14; that belongs to a subsequent phase.
- If multiple tasks fail in the same batch, a deterministic selection rule (earliest by original plan order) selects which failed task drives replanning.
- Recovery plan merging remains based on the existing replanning model and preserves task IDs for recovery tasks.

### 4.2 Specialized Agent Delegation
- Explicit, deterministic specialization via an orchestrator-level selection mechanism.
- Reference implementation: `ResearchAgent`, a thin adapter around the existing Agent that reuses the current planning, DAG, workflow, and execution stack instead of creating a second planner or scheduler.
- Controlled multi-agent delegation is supported only when a request explicitly names a target agent or includes a list of `delegations`.
- Old behavior remains the default when no specialized agent is explicitly requested.
- Multi-agent collaboration, automatic agent selection, recursive delegation, and shared multi-agent memory remain future work.

### 4.3 Persistent Conversation and Memory Storage
- Durable session state, episodic memory, and entity memory backends.

### 4.4 Expanded Tool Ecosystem
- Sandboxed code execution, web/API tools, and structured database tools.

### 4.5 Additional Knowledge Sources
- SQL, knowledge graph, API documentation, and external knowledge implementations behind `KnowledgeSourceContract`.
- Phase 11: Introduce a small domain-agnostic KnowledgeDecision layer that normalizes and validates which knowledge capability (RAG, registered knowledge source, or knowledge graph) should be used for a request. This component does NOT execute retrievals and intentionally does not perform multi-source fusion or ranking.
- Planner-based selection among multiple knowledge sources (multi-source routing and source fusion) remains future work.

### 4.6 Streaming and Asynchronous Execution
- Non-blocking generation, streaming responses, and asynchronous task scheduling.

### 4.6 Multi-Backend Model Gateway
- Optional vLLM, Ollama, Llama.cpp, and remote provider implementations.
