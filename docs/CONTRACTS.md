# Vexux-AI Contracts Reference

This document provides the authoritative documentation for all data structures and protocol interfaces defined in `core/contracts/`.

All inter-module communication in Vexux-AI is governed by these contracts.

## API Contracts

`POST /api/v1/agent/run` and `POST /api/v1/orchestrator/run` accept `query`,
optional `session_id`/`user_id`, and the existing routing fields (`agent`,
`workflow`, and `delegations`). Responses contain `success`, redacted `output`
and `error`, request/session identity, optional `orchestration_id`, and safe
metadata. Validation failures are handled by FastAPI; execution failures retain
the existing controlled `AgentResponse` semantics.

The API emits request start/completion audit events and the trace endpoint
filters by request or orchestration ID. It never returns prompts, credentials,
stack traces, or unredacted secret-bearing payloads. `/health` performs no
dependency calls; `/ready` validates provider configuration only.

---

## Knowledge graph contract

`KnowledgeGraphContract` defines generic node, relationship, and neighbor
operations. `KnowledgeGraphRegistry` is the sole registration boundary. The
repository includes `InMemoryKnowledgeGraph` and an optional
`Neo4jKnowledgeGraph` adapter; Neo4j records are normalized into the contract's
plain dictionaries before reaching execution, evidence, or audit layers.
Neo4j identifiers are passed as query parameters, and arbitrary Cypher is not
part of the contract.

Multiple graph instances may use different contract implementations in one
request. Authorization is evaluated for every named graph before execution;
results retain each graph name as evidence provenance for cross-graph
aggregation.

## SQL knowledge source

`SQLKnowledgeSource` implements `KnowledgeSourceContract` for structured
relational reads. `SQLiteBackend` supplies real SQLite execution through the
existing `KnowledgeSourceRegistry`; the source validates one read-only
`SELECT`, passes optional DB-API parameters to the backend, and normalizes
rows to `structured_data` evidence. Vendor-specific SQL drivers require their
own backend adapter and configuration.

---

## 1. Execution Contracts (`core/contracts/execution.py`)

### 1.1 `Task`
A dataclass representing an individual, executable action within a plan.

```python
@dataclass
class Task:
    id: str
    description: str
    input: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Optional dependency list: other task IDs that must complete successfully
    # before this task becomes ready. Backward compatible: omit or empty means
    # no dependencies.
    depends_on: list[str] = field(default_factory=list)

```

- **Fields (added behavior):**
  - `depends_on` (`list[str]`): Optional list of task IDs this task depends on. When present, the Planner and Agent will validate that the referenced IDs exist, that no self-dependencies or cycles are present, and that execution follows dependency semantics (ready tasks only execute when all predecessors succeeded). Default: `[]`.
```

- **Fields**:
  - `id` (`str`): Unique identifier for the task (e.g. `"task-1"`).
  - `description` (`str`): Human-readable description of what the task accomplishes.
  - `input` (`Dict[str, Any]`): Input parameters and arguments required for execution (e.g., `{"query": "..."}` or `{"tool": "calculator", "arguments": {...}}`). Default: `{}`.
  - `metadata` (`Dict[str, Any]`): Metadata specifying routing and execution constraints (e.g. `{"capability": "retrieval" | "tool" | "model"}`). Default: `{}`.
- **Producer**: `Planner` (`create_plan`, `replan`).
- **Consumer**: `ExecutionManager` (`execute`, `_execute_*`), `AgentContext` (`current_task`).
- **Purpose**: Encapsulates a discrete unit of work to be dispatched to a capability.

---

### 1.2 `Plan`
A dataclass holding an ordered sequence of tasks to fulfill a request.

```python
@dataclass
class Plan:
    tasks: list[Task] = field(default_factory=list)
```

- **Fields**:
  - `tasks` (`list[Task]`): List of `Task` instances in the intended order of execution. Default: `[]`.
- **Producer**: `Planner` (`create_plan`, `replan`).
- **Consumer**: `Agent` (`run`), `ContextManager` (`set_plan`).
- **Purpose**: Represents the full execution plan devised by the planner.


> Configuration note: Bounded local concurrency is exposed via the environment variable `AGENT_MAX_PARALLEL_TASKS` (integer). By default this is `1` to preserve legacy sequential behavior. When set to a value >1 the Agent may execute independent ready tasks concurrently (bounded ThreadPoolExecutor). This configuration does not change the Task/Plan contracts themselves; it only affects the Agent's scheduling behavior.

---

### 1.3 `AgentContext`
A dataclass containing the full execution context and state for an agent request.

```python
@dataclass
class AgentContext:
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    current_plan: Optional[Plan] = None
    current_task: Optional[Task] = None
    observations: list[Observation] = field(default_factory=list)
    completed_tasks: list[Task] = field(default_factory=list)
    conversation_history: list[Dict[str, Any]] = field(default_factory=list)
```

- **Fields**:
  - `request_id` (`str`): Unique identifier for the current execution run (typically a UUID).
  - `session_id` (`Optional[str]`): Optional session identifier for multi-turn conversations. Default: `None`.
  - `user_id` (`Optional[str]`): Optional user identifier. Default: `None`.
  - `metadata` (`Dict[str, Any]`): Arbitrary runtime context metadata. Default: `{}`.
  - `created_at` (`datetime`): UTC timestamp when the context was initialized. Default: `datetime.utcnow`.
  - `current_plan` (`Optional[Plan]`): The active `Plan` currently being executed. Default: `None`.
  - `current_task` (`Optional[Task]`): The `Task` currently being processed. Default: `None`.
  - `observations` (`list[Observation]`): Chronological history of observations produced during this execution run. Default: `[]`.
  - `completed_tasks` (`list[Task]`): Chronological list of `Task` objects that completed execution with successful observations. Default: `[]`.
  - `conversation_history` (`list[Dict[str, Any]]`): Bounded prior session turns copied into this request context. Default: `[]`.
- **Producer**: `ContextManager` (`create`, `set_plan`, `set_task`, `add_observation`, `add_completed_task`).
- **Consumer**: `Agent` (`run`), `ExecutionManager` (`execute`).
- **Purpose**: Holds runtime state, active pointers, and execution traces for a single agent invocation.

---

### 1.4 `ExecutionResult`
A dataclass capturing the raw outcome returned by capability execution.

```python
@dataclass
class ExecutionResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

- **Fields**:
  - `success` (`bool`): `True` if execution completed without error, `False` otherwise.
  - `output` (`Any`): The raw output payload produced by the capability (e.g. calculation result, answer string, or query results). Default: `None`.
  - `error` (`Optional[str]`): Error message if execution failed. Default: `None`.
  - `metadata` (`Dict[str, Any]`): Optional execution metadata. Default: `{}`.
- **Producer**: `ExecutionManager` (`execute`, `_execute_retrieval`, `_execute_tool`, `_execute_model`).
- **Consumer**: `Observer` (`observe`).
- **Purpose**: Bridges low-level execution outcomes back to the agent layer before observation normalization.

---

### 1.5 `Intent`
A dataclass representing the classified user intent and extracted parameters.

```python
@dataclass
class Intent:
    name: str
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
```

- **Fields**:
  - `name` (`str`): The classification category name (`"retrieval"`, `"tool"`, or `"general"`).
  - `confidence` (`float`): Model confidence score between 0.0 and 1.0. Default: `0.0`.
  - `entities` (`Dict[str, Any]`): Extracted parameters (e.g., `{"topic": "EC2"}` or `{"tool": "calculator", "math_expression": "24 * 7"}`). Default: `{}`.
- **Producer**: `Planner` (`understand_intent`, `_parse_intent`) for compatibility and focused intent tests.
- **Consumer**: Intent-specific callers and tests; the active Agent path uses structured `create_plan()` directly.
- **Purpose**: Retained intent representation; it is not the active multi-task planning contract.

---

### 1.6 Specialized Agent Contract (`core/contracts/orchestrator.py`)
A thin protocol for role-specific adapters that can be selected by the orchestrator.

```python
class SpecializedAgentContract(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    def run(self, request: Any, session_id: str | None = None, user_id: str | None = None) -> AgentResponse:
        ...
```

- **Fields**:
  - `name` (`str`): Stable identifier used for deterministic explicit selection, e.g. `"research"`.
  - `description` (`str`): Short capability description for discovery and metadata.
- **Producer**: Any specialized adapter implementing a role-specific entrypoint.
- **Consumer**: `Orchestrator` when an explicit `agent` key is present in the request.
- **Purpose**: Keeps role-specific execution opt-in and domain-agnostic without duplicating the base `Agent` control loop.

> Explicit deterministic specialization is currently the only supported model. Automatic agent selection and multi-agent coordination remain future work.

### Integration contract usage

Phase 29 integration tests exercise these existing contracts together rather than
introducing new execution contracts. Multi-graph retrieval carries explicit graph
names and identifiers into `ExecutionManager`, authorization decisions remain
resource-level, and results retain `EvidenceSet` provenance. Delegation uses the
existing `DelegationPlan` and `DelegationResult` contracts. Audit records and
responses must contain safe metadata only; prompts, credentials, and raw
secret-bearing outputs are not part of these application contracts.

---

### 1.7 Authorization Contracts (`core/contracts/authorization.py`)
A minimal resource-level authorization contract used by the policy layer to decide whether an actor may perform an action on a named resource.

```python
@dataclass
class AuthorizationRequest:
    actor: Optional[str]
    resource_type: str
    resource_name: Optional[str]
    action: str
    context: Optional[dict] = None

@dataclass
class AuthorizationDecision:
    allowed: bool
    reason: Optional[str] = None
    policy_name: str = "authorization"
```

- **Purpose**: Encapsulate a simple allow/deny decision for resource types such as `knowledge_graph`, `knowledge_source`, `specialized_agent`, and `workflow`.
- **Producer**: Policy implementations (e.g., `DefaultPolicy.authorize_resource`).
- **Consumer**: Enforcement points in `ExecutionManager` and `Orchestrator` which call into the policy to make deterministic allow/deny decisions before using protected resources.

Notes:
- The contract is intentionally small and resource-oriented — it is not a full RBAC/IAM model and deliberately omits external identity provider integration.
- Decisions must be surfaced as controlled failures (error + safe metadata) and must not leak raw protected outputs.

### 1.8 DelegationPlan Contract

The controlled multi-agent planning layer uses a domain-agnostic, explicit delegation plan that reuses the existing `Task` dependency semantics without introducing a second graph abstraction.

```python
@dataclass
class DelegationRequest:
    target_agent: str
    request: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    delegation_id: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    input: Any = None

@dataclass
class DelegationPlan:
    delegations: list[DelegationRequest] = field(default_factory=list)
```

- **Fields**:
  - `target_agent` (`str`): registered agent name to invoke.
  - `request` (`Any`): request payload or query for that agent.
  - `delegation_id` (`Optional[str]`): stable identifier for the work unit.
  - `depends_on` (`list[str]`): IDs of upstream delegated work that must complete before this delegation becomes eligible.
  - `input` (`Any`): optional structured input payload or dataflow-bound object.
- **Producer**: `DelegationPlanner` in the specialized-agent planning layer.
- **Consumer**: `Orchestrator` to validate, order, and execute the explicit plan.
- **Purpose**: small, structured, deterministic delegation scheduling without autonomous agent spawning or multi-agent memory.

### Orchestration metadata
The orchestrator enriches every delegation run with minimal, privacy-conscious observability metadata. When a request contains `delegations` the returned `AgentResponse` will include an `orchestration_id` in `response.metadata` and each `DelegationResult.metadata` will include:
- `orchestration_id`: stable id for this fan-out run
- `delegation_id`: the delegation's id
- `selected_agent`: the agent name used
- `dependency_status`: one of `executed` or `blocked`

This metadata is intentionally small and safe for logging and trace correlation. Sensitive raw outputs remain subject to existing policy and redaction rules.

### 1.8 Delegation Request / Result Contracts
The orchestrator still returns per-delegation results in a minimal, deterministic structure.

```python
@dataclass
class DelegationResult:
    target_agent: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    delegation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

- **Producer**: `Orchestrator` when a request includes an explicit `delegations` list or a single `agent` selection.
- **Consumer**: callers that need a structured result for each delegated execution without introducing a separate agent messaging protocol.
- **Purpose**: preserves the target agent, per-delegation identity, success/failure state, and safe metadata while keeping all execution inside the existing `Agent` and `SpecializedAgent` contracts.

---

## 2. Observation Contract (`core/contracts/observation.py`)

### 2.1 `Observation`
A dataclass capturing the evaluated semantic outcome of a task execution.

```python
@dataclass
class Observation:
    success: bool
    output: Any = None
    error: Optional[str] = None
    summary: Optional[str] = None
    task_id: Optional[str] = None
```

- **Fields**:
  - `success` (`bool`): Boolean flag indicating whether the execution achieved its intended goal.
  - `output` (`Any`): Evaluated output payload forwarded from `ExecutionResult`. Default: `None`.
  - `error` (`Optional[str]`): Error details forwarded from `ExecutionResult`. Default: `None`.
  - `summary` (`Optional[str]`): Human-readable textual summary of what occurred during execution. Default: `None`.
  - `task_id` (`Optional[str]`): Unique identifier of the `Task` that generated this observation. Default: `None`.
- **Producer**: `Observer` (`observe`).
- **Consumer**: `DecisionMaker` (`decide`), `Agent` (`run`), `ContextManager` (`add_observation`), `Planner` (`replan`, `understand_intent`).
- **Purpose**: Provides a standardized observation contract that drives decision making and replanning.

---

## 3. Response Contract (`core/contracts/response.py`)

### 3.1 `AgentResponse`
A dataclass representing the final output delivered by the agent to the caller.

```python
@dataclass
class AgentResponse:
    success: bool
    output: Any = None
    error: Optional[str] = None
    trace: Optional[list] = None
  metadata: Dict[str, Any] = field(default_factory=dict)
```

- **Fields**:
  - `success` (`bool`): Overall success status of the agent run.
  - `output` (`Any`): Final output payload returned to the user/client. Default: `None`.
  - `error` (`Optional[str]`): Top-level failure description if the request could not be satisfied. Default: `None`.
  - `trace` (`Optional[list]`): Chronological list of `Observation` objects capturing every step taken during the run. Default: `None`.
  - `metadata` (`Dict[str, Any]`): Request/session/user identifiers and other response metadata. Default: `{}`.
- **Producer**: `Agent` (`run`).
- **Consumer**: External caller, API client, or test scripts (`test_agent.py`).
- **Purpose**: Unified response packet providing result data and full execution auditability.

---

## 4. Capability Protocols (`core/contracts/capabilities.py`)

### 4.1 `Capability` (Protocol)
Generic structural interface for any pluggable capability.

```python
class Capability(Protocol):
    @property
    def name(self) -> str: ...
    def execute(self, input_data: Dict[str, Any]) -> Any: ...
```
- **Members**:
  - `name -> str`: Name of the capability.
  - `execute(input_data: Dict[str, Any]) -> Any`: Executes the capability with input dictionary.
- **Purpose**: Generic contract for modular capability extensions.

---

### 4.2 `RetrievalContract` (Protocol)
Structural interface for retrieval and knowledge components.

```python
class RetrievalContract(Protocol):
    def retrieve(self, query: str, k: int = 3) -> List[Dict[str, Any]]: ...
```
- **Members**:
  - `retrieve(query: str, k: int = 3) -> List[Dict[str, Any]]`: Searches for top-`k` relevant chunks given a text query.
- **Purpose**: Standard contract for semantic and lexical retrievers.

---

### 4.3 `KnowledgeSourceContract` (Protocol)
Domain-agnostic interface for registered knowledge providers.

```python
class KnowledgeSourceContract(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def capabilities(self) -> List[str]: ...
    def retrieve(query: str, k: int | None = None) -> List[Dict[str, Any]]: ...
```
- **Members**:
  - `name -> str`: Stable source identifier.
  - `description -> str`: Human-readable source summary.
  - `capabilities -> List[str]`: Operations offered by the source.
  - `retrieve(query, k)`: Retrieves source-specific knowledge for the existing retrieval capability; successful registry retrievals retain the existing structured result fields and add the selected `source` name.
- **Implemented By**: `RAGKnowledgeSource` (`rag/knowledge_source.py`).
- **Managed By**: `KnowledgeSourceRegistry` (`core/knowledge/registry.py`).
- **Purpose**: Allows future knowledge implementations to be registered without changing the Agent control loop.

---

### 4.4 `ToolContract` (Protocol)
Structural interface for agent-invocable tools.

```python
class ToolContract(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def input_schema(self) -> Dict[str, Any]: ...
    def execute(self, arguments: Dict[str, Any]) -> Any: ...
```
- **Members**:
  - `name -> str`: Identifier of the tool (e.g. `"calculator"`).
  - `description -> str`: Textual description of what the tool does.
  - `input_schema -> Dict[str, Any]`: Lightweight object schema describing accepted arguments.
  - `execute(arguments: Dict[str, Any]) -> Any`: Performs tool computation using provided arguments dict.
- **Implemented By**: `CalculatorTool` (`core/tools/calculator.py`).
- **Managed By**: `ToolRegistry` (`core/tools/registry.py`).
- **Purpose**: Interface ensuring plug-and-play tool integration.

---

### 4.5 `MemoryContract` (Protocol)
Structural interface for memory stores.

```python
class MemoryContract(Protocol):
    def store(self, key: str, value: Any) -> None: ...
    def retrieve(self, key: str) -> Any: ...
```
- **Members**:
  - `store(key: str, value: Any) -> None`: Persists a key-value pair.
  - `retrieve(key: str) -> Any`: Retrieves the value associated with a key.
- **Purpose**: Interface for future session, episodic, or long-term memory systems (currently planned).

---

### 4.5 `ModelProviderContract` (Protocol)
Structural interface for language model backends.

```python
class ModelProviderContract(Protocol):
    @property
    def name(self) -> str: ...
    def generate(self, prompt: str, **kwargs) -> str: ...
```
- **Members**:
  - `name -> str`: Identifier of the model provider (e.g. `"qwen"`).
  - `generate(prompt: str, **kwargs) -> str`: Generates text completion for the provided prompt.
- **Implemented By**: `QwenProvider` (`models/providers/qwen.py`).
- **Used By**: `ModelGateway` (`core/model_gateway/gateway.py`).
- **Purpose**: Decouples model inference details (tokenization, chat templates, quantization, sampling) from the rest of the application.

---

## MemoryContract (core/contracts/capabilities.py)

The `MemoryContract` documents the minimal interface for persistent memory backends used in Phase 9.

```python
class MemoryContract(Protocol):
    @property
    def name(self) -> str: ...

    def store(self, scope: str, content: str, memory_id: Optional[str] = None) -> str: ...

    def retrieve(self, scope: str, query: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]: ...

    def clear(self, scope: str) -> None: ...
```

- **Behavioral guarantees**:
  - `store` MUST return a stable `memory_id` for the persisted record.
  - Implementations SHOULD reject obvious secret-like values and MAY apply repository redaction utilities.
  - `retrieve` MUST only return records for the provided `scope` — scopes are isolated by design.
  - `clear` MUST remove all records belonging to the given `scope`.

- **Purpose**: Keep the contract domain-agnostic and small so different storage backends (SQLite, cloud DB) can be plugged in safely.

---

## KnowledgeRequest (core/contracts/knowledge.py)

A small, domain-agnostic dataclass used by the KnowledgeDecision component to express which knowledge capability should be used to satisfy a query.

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class KnowledgeRequest:
    kind: str  # one of "rag", "knowledge_source", "graph"
    query: str
    source: Optional[str] = None
    operation: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    graph_requests: list[Dict[str, Any]] = field(default_factory=list)
```

- **Purpose**: Normalize and validate the intent to use a particular knowledge capability without executing retrievals. The contract is intentionally small and domain-agnostic so it can be used across the Planner, Decision, and Execution components. When a single high-level request needs multiple independent graph lookups, callers may populate `graph_requests` with explicit `graph_name`, `operation`, and `parameters` entries; the execution layer then executes those requests in parallel and aggregates them without inventing a second graph contract or a domain-specific request type.
