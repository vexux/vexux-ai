# Vexux-AI Contracts Reference

This document provides the authoritative documentation for all data structures and protocol interfaces defined in `core/contracts/`.

All inter-module communication in Vexux-AI is governed by these contracts.

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
  - `retrieve(query, k)`: Retrieves source-specific knowledge for the existing retrieval capability.
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
