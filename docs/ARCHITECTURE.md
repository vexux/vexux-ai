# Vexux-AI Architecture

## 1. Overview & System Philosophy

Vexux-AI is a modular, use-case-independent AI agent framework built around Small Language Models (SLMs), Retrieval-Augmented Generation (RAG), tool execution, and an iterative plan-execute-observe-decide control loop.

The core architecture is organized to keep the agent control flow completely decoupled from underlying model weights, specific prompt structures, vector stores, and external tool implementations.

---

## 2. The Three Conceptual Layers

```text
┌─────────────────────────────────────────────────────────────────┐
│                      INNER / AGENT LAYER                        │
│                                                                 │
│   ┌─────────────┐        ┌─────────────┐       ┌────────────┐   │
│   │   Planner   │ ───►   │  Execution  │ ───►  │  Observer  │   │
│   └─────────────┘        └─────────────┘       └────────────┘   │
│          ▲                                            │         │
│          │                 ┌───────────────┐          │         │
│          └──────────────── │ DecisionMaker │ ◄────────┘         │
│               (Replan)     └───────────────┘                    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                    MIDDLE / ARCHITECTURE LAYER                  │
│                                                                 │
│  - Model Gateway (core/model_gateway/gateway.py)                │
│  - Tool Registry (core/tools/registry.py)                       │
│  - Execution Manager (agent/execution_manager.py)               │
│  - Context Manager (core/context/context_manager.py)            │
│  - Contracts & Protocols (core/contracts/)                      │
│  - Dependency Injection Composition Root (core/composition.py)  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                     DATA / CAPABILITY LAYER                     │
│                                                                 │
│  - RAG Pipeline (DocumentLoader, Chunker, Embedder, FAISS, ...) │
│  - Model Providers (QwenProvider with PEFT LoRA adapter)        │
│  - Training & Fine-Tuning (SFTTrainer, LoRAManager, Datasets)   │
│  - Concrete Tools (CalculatorTool)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 1: Inner / Agent Layer
Contains the cognitive and control-loop primitives. This layer is responsible for planning, executing tasks against context, evaluating outcomes, recovering from failures, and synthesizing final answers.
- **Agent** (`agent/agent.py`): Coordinates the lifecycle loop across multiple tasks and manages replanning.
  - **Planner** (`agent/planner.py`): Generates and validates structured sequential plans, including scoped recovery plans.
- **Observer** (`agent/observer.py`): Normalizes raw execution outcomes into structured observations linked with `task_id`.
- **DecisionMaker** (`agent/decision.py`): Determines whether an observation satisfies the goal (`DONE`) or requires a new plan (`REPLAN`).
- **ResponseSynthesizer** (`agent/response_synthesizer.py`): Synthesizes multi-task observation outputs into a clear, unified final response.

### Layer 2: Middle / Architecture Layer
Provides structural boundaries, data contracts, and dependency mediation.
- **Contracts** (`core/contracts/`): Strict dataclasses and `typing.Protocol` interfaces defining execution payloads, observations, capabilities, and agent responses.
- **ContextManager** (`core/context/context_manager.py`): Maintains state, tracks historical execution traces, records completed tasks, and isolates session/request metadata.
- **ModelGateway** (`core/model_gateway/gateway.py`): Mediates LLM/SLM generation behind a standardized interface (`ModelProviderContract`).
- **ToolRegistry** (`core/tools/registry.py`): In-memory registry for discovering and executing tools implementing `ToolContract`.
- **ExecutionManager** (`agent/execution_manager.py`): Dispatches execution tasks to RAG, tools, or direct model calls.
- **Composition Root** (`core/composition.py`): Factory module (`create_agent()`) that wires concrete instances and handles dependency injection.
- **FastAPI API** (`api/main.py`): Thin HTTP boundary delegating requests to the composition-root Agent.
- **Evaluation Suite** (`evaluation/`): Deterministic system-level evaluation runner with 44 scenarios.

### Layer 3: Data / Capability Layer
Houses the domain-specific models, data processors, vector indices, training loops, and concrete tools.
- **RAG Subsystem** (`rag/`): File-based document loader, sliding-window chunker, `SentenceTransformer` embedder (`BAAI/bge-small-en-v1.5`), FAISS flat IP vector index, and contextual prompt builder.
- **Model Subsystem** (`models/`, `training/`): Hugging Face causal LM loader with 4-bit BitsAndBytes quantization, fine-tuned LoRA adapters (Qwen 2.5 0.5B Instruct), and standalone inference scripts.
- **Tools Subsystem** (`core/tools/`): Standalone capabilities such as the mathematical expression evaluator (`CalculatorTool`).
- **Training Subsystem** (`training/`, `lora/`, `data/`, `experiments/`): SFTTrainer fine-tuning factory, dataset loaders, JSONL formatters, and QLoRA training scripts.

---

## 3. Implementation Status: Implemented vs. Planned

| Component | Status | Location / Details |
| :--- | :--- | :--- |
| **Agent Loop (Multi-Task & Recovery)** | **IMPLEMENTED** | `agent/agent.py` — supports sequential multi-task execution, scoped failure recovery, retry loop (up to 2 retries), and trace preservation. |
| **Structured Planning & Recovery** | **IMPLEMENTED** | `agent/planner.py` — generates validated sequential `Plan`/`Task` JSON and targeted recovery plans. |
| **Observer & Decision Maker** | **IMPLEMENTED** | `agent/observer.py`, `agent/decision.py` — maps `ExecutionResult` to `Observation` (with `task_id`) and decides `DONE`/`REPLAN`. |
| **Response Synthesizer** | **IMPLEMENTED** | `agent/response_synthesizer.py` — synthesizes multi-task observation outputs into unified final answers. |
| **Context Management & Sessions** | **IMPLEMENTED** | `core/context/context_manager.py` — manages request traces and bounded in-memory conversation history by `session_id`. |
| **Model Gateway** | **IMPLEMENTED** | `core/model_gateway/gateway.py` — wraps `ModelProviderContract`. |
| **Tool Registry & Calculator Tool** | **IMPLEMENTED** | `core/tools/registry.py`, `core/tools/calculator.py` — registered tool execution. |
| **Local RAG Pipeline** | **IMPLEMENTED** | `rag/` — scored retrieval through `RAGPipeline.retrieve()` with configurable top-k and relevance handling. |
| **Knowledge Source Abstraction** | **IMPLEMENTED** | `KnowledgeSourceRegistry` dispatches the current RAG source through `RAGKnowledgeSource`; multi-source planning is not implemented. |
| **Qwen 2.5 SLM Provider (LoRA)** | **IMPLEMENTED** | `models/providers/qwen.py` — loads `Qwen/Qwen2.5-0.5B-Instruct` with PEFT adapter from `models/checkpoints`. |
| **QLoRA Fine-Tuning Pipeline** | **IMPLEMENTED** | `training/train.py`, `training/factory.py`, `experiments/qlora_train.py`. |
| **Contracts (`execution`, `observation`, `response`, `capabilities`)** | **IMPLEMENTED** | `core/contracts/` — dataclasses and protocols. |
| **Multi-Agent Execution** | **PLANNED** | Not implemented. The current system is strictly single-agent. |
| **Dynamic Multi-Step Graph / DAG Planning** | **PLANNED** | Not implemented. Dynamic DAG execution with complex dependency graphs is planned. |
| **Dynamic Tool Discovery** | **IMPLEMENTED** | `ToolRegistry` metadata, including lightweight input schemas, is injected into Planner prompts. |
| **Persistent Memory (`MemoryContract`)** | **PLANNED** | Protocol defined in `core/contracts/capabilities.py`, but no concrete store exists. |
| **Evaluation Suite (`evaluation/`)** | **IMPLEMENTED** | 44 deterministic system-level scenarios with category and failure reporting. |
| **Streaming / Asynchronous Execution** | **PLANNED** | All current execution and generation calls are synchronous. |

---

## 4. Current Execution Flow

When a client invokes `agent.run(query)`:

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Agent as Agent (agent.py)
    participant ContextMgr as ContextManager
    participant Planner as Planner (planner.py)
    participant ModelGW as ModelGateway
    participant ExecMgr as ExecutionManager
    participant Capability as Capability (RAG / Tool / Model)
    participant Observer as Observer (observer.py)
    participant Decision as DecisionMaker (decision.py)
    participant Synthesizer as ResponseSynthesizer

    Client->>Agent: run(query)
    Agent->>ContextMgr: create(request_id, session_id, user_id)
    ContextMgr-->>Agent: AgentContext

    loop Up to max_retries (default: 2)
        alt First Attempt (retry_count == 0)
                Agent->>Planner: create_plan(query, conversation_context)
                Planner->>ModelGW: generate(structured plan prompt)
                ModelGW-->>Planner: validated JSON plan
                Planner-->>Agent: Plan (List of Tasks)
        else Subsequent Retries (replan)
            Agent->>Planner: replan(query, last_observation, failed_task)
            Planner->>ModelGW: generate(prompt)
            ModelGW-->>Planner: JSON recovery response
            Planner-->>Agent: Recovery Plan (Scoped to failed task)
        end

        Agent->>ContextMgr: set_plan(context, plan)

        loop For each Task in Plan.tasks
            Agent->>ContextMgr: set_task(context, task)
            Agent->>ExecMgr: execute(task, context)

            alt capability == "retrieval"
                ExecMgr->>Capability: KnowledgeSourceRegistry.get(source).retrieve(query, top_k)
            else capability == "tool"
                ExecMgr->>Capability: ToolRegistry.execute(tool_name, arguments)
            else capability == "model"
                ExecMgr->>Capability: ModelGateway.generate(prompt)
            end
              Capability-->>ExecMgr: structured retrieval/tool/model output
            ExecMgr-->>Agent: ExecutionResult(success, output, error)

            Agent->>Observer: observe(execution_result, task)
            Observer-->>Agent: Observation(success, output, error, summary, task_id)
            Agent->>ContextMgr: add_observation(context, observation)

            Agent->>Decision: decide(observation)
            Decision-->>Agent: DecisionType (DONE or REPLAN)

            alt Decision == DONE
                Agent->>ContextMgr: add_completed_task(context, task)
                Note over Agent: Continue loop to next task
            else Decision == REPLAN
                Note over Agent: Break task loop & increment retry_count
            end
        end

        opt All Tasks in Plan completed successfully
            Agent->>Synthesizer: synthesize(query, context.observations)
            Synthesizer-->>Agent: final_output
            Agent-->>Client: AgentResponse(success=True, output=final_output, trace)
        end
    end

    alt Exhausted retries without completion
        Agent-->>Client: AgentResponse(success=False, error="Agent could not complete the request.", trace)
    end
```

---

## 5. Component Breakdown

### 5.1 Agent (`agent/agent.py`)
- **Class**: `Agent`
- **Responsibilities**:
  - Initializes request context via `ContextManager`.
  - Executes the outer retry loop (bounded by `max_retries = 2`).
  - Dispatches tasks sequentially from the active `Plan`.
  - Invokes `Observer` and `DecisionMaker` after every task.
  - On task success, records the task into `context.completed_tasks`.
  - On task failure, triggers `Planner.replan()` with the failed task and preserves remaining unexecuted tasks without repeating completed tasks.
  - Delegates final response generation to `ResponseSynthesizer` upon successful completion.

### 5.2 Planner (`agent/planner.py`)
- **Class**: `Planner`
- **Responsibilities**:
  - `create_plan(query, conversation_context)`: Prompts the SLM for a structured JSON plan and validates every task before creating `Plan` and `Task` objects.
  - `replan(query, observation, failed_task, conversation_context)`: Generates and validates a single recovery task scoped specifically to `failed_task`.
  - Tool metadata and input schemas are obtained dynamically from `ToolRegistry`; individual tool implementations are not embedded in the Planner.

### 5.3 Execution Manager (`agent/execution_manager.py`)
- **Class**: `ExecutionManager`
- **Responsibilities**:
  - Inspects `task.metadata["capability"]`.
  - Routes `retrieval` through `KnowledgeSourceRegistry` when configured and returns the existing structured query/results/context output.
  - Routes `tool` to `ToolRegistry.execute()`.
  - Routes `model` to `ModelGateway.generate()`.
  - Wraps results and exceptions into an `ExecutionResult`.

### 5.4 Observer (`agent/observer.py`)
- **Class**: `Observer`
- **Responsibilities**:
  - Evaluates `ExecutionResult.success`.
  - Produces an `Observation` dataclass instance with `task_id` and descriptive summary annotations.

### 5.5 Decision Maker (`agent/decision.py`)
- **Class**: `DecisionMaker`
- **Responsibilities**:
  - Evaluates an `Observation` to return `DecisionType.DONE` (if `observation.success` is `True`) or `DecisionType.REPLAN` (if `False`).

### 5.6 Response Synthesizer (`agent/response_synthesizer.py`)
- **Class**: `ResponseSynthesizer`
- **Responsibilities**:
  - Collects outputs from all successful observations in the request trace.
  - Invokes `ModelGateway.generate()` to compose a cohesive, clean user-facing response combining multi-task outputs without revealing internal agent execution details.

### 5.7 Context Manager (`core/context/context_manager.py`)
- **Class**: `ContextManager`
- **Responsibilities**:
  - Instantiates and updates `AgentContext`.
  - Manages `observations`, `current_plan`, `current_task`, and `completed_tasks`.
  - Maintains bounded in-memory conversation history isolated by `session_id`.

### 5.8 Model Gateway & Providers (`core/model_gateway/`, `models/providers/`)
- **`ModelGateway`**: Dispatches generation prompts to any implementation of `ModelProviderContract`.
- **`QwenProvider`**: Implements `ModelProviderContract` using Hugging Face's `AutoTokenizer` and `AutoModelForCausalLM` combined with a PEFT LoRA adapter loaded from `models/checkpoints`. Supports greedy decoding (`do_sample=False`) and sampling (`temperature`, `top_p`, `top_k`).

### 5.12 API and Observability
- **FastAPI** (`api/main.py`): Exposes `POST /api/v1/agent/run`, validates requests, delegates to `Agent.run()`, and serializes `AgentResponse`.
- **Structured observability** (`agent/agent.py`): Logs request/session/task identifiers, capability, execution outcome, and duration for each task.
- The API does not contain planning, execution, observation, or retry orchestration logic.

### 5.9 Tool Registry & Concrete Tools (`core/tools/`)
- **`ToolRegistry`**: In-memory registry with `register()`, `get()`, `list_tools()`, `describe_tools()`, and `execute()` methods.
- **`CalculatorTool`**: Implements `ToolContract`, executing arithmetic expressions using a restricted `eval` namespace (`__builtins__: {}`).

### 5.10 RAG Pipeline (`rag/`)
- **`DocumentLoader`**: Reads `.txt` files from `data/documents/`.
- **`TextChunker`**: Fixed sliding-window text chunking (`chunk_size=80`, `overlap=20`).
- **`Embedder`**: Wraps `SentenceTransformer("BAAI/bge-small-en-v1.5")` with normalized output embeddings.
- **`VectorStore`**: Manages a FAISS `IndexFlatIP` index with document metadata storage.
- **`Retriever`**: Takes raw text queries, encodes them via `Embedder`, and searches `VectorStore`.
- **`PromptBuilder`**: Constructs context-augmented prompts for answer generation.
- **`RAGPipeline`**: Orchestrates loading, indexing, retrieval, and invokes `InferencePipeline` to answer questions.
- **`RAGKnowledgeSource`**: Adapts `RAGPipeline.retrieve()` to the generic `KnowledgeSourceContract` without changing RAG behavior.

### 5.11 Knowledge Sources (`core/knowledge/`)
- **`KnowledgeSourceRegistry`**: Registers and describes domain-agnostic sources, with the first registered source serving existing retrieval tasks by default.
- **Current source**: `RAGKnowledgeSource` only. SQL, knowledge graph, API documentation, and external knowledge sources are not implemented, and no planner-based source routing exists.

### 5.12 Composition Root (`core/composition.py`)
- **Function**: `create_agent()`
- **Responsibilities**:
  - Wires all subsystems together via dependency injection.
  - Instantiates `QwenProvider` -> `ModelGateway` -> `RAGPipeline` -> `RAGKnowledgeSource` -> `KnowledgeSourceRegistry` -> `ToolRegistry` -> `ExecutionManager` -> `Planner` -> `Observer` -> `DecisionMaker` -> `ContextManager` -> `ResponseSynthesizer` -> `Agent`.

