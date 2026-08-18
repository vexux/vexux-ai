# Vexux-AI Agent Instructions & Architectural Rules

This document outlines the mandatory rules, principles, and workflows that any AI coding assistant or engineer must follow when interacting with and evolving the Vexux-AI codebase.

---

## 1. Core Architecture Principles

1. **Strict Separation of Concerns**
   - **Agent**: Purely a control loop coordinator. It manages the execution lifecycle (context initialization, plan execution, observation collection, retry/replan loops). It must never contain business logic, tool execution code, or direct model inference logic.
   - **Planner**: Responsible for intent classification, plan generation, and replanning using the `ModelGateway`. It constructs task lists (`Plan`) consisting of discrete `Task` objects.
   - **ExecutionManager**: Dispatches tasks to the appropriate capability implementations. It translates contract-compliant `Task` objects into execution calls and returns an `ExecutionResult`.
   - **Observer**: Inspects the raw `ExecutionResult` and produces a normalized `Observation` with status, output, errors, and summary.
   - **DecisionMaker**: Analyzes an `Observation` to determine the next control-flow transition (`DecisionType.DONE` vs. `DecisionType.REPLAN`).
   - **ResponseSynthesizer**: Synthesizes intermediate results and observations from multiple completed tasks into a unified, clean final user response using the `ModelGateway`.
   - **ContextManager**: Owns the lifecycle and controlled mutation of execution state (`AgentContext`), recording active plans, current tasks, completed tasks, and chronological observation traces.
   - **ModelGateway**: Mediates all LLM/SLM generation behind the `ModelProviderContract`, isolating model access and provider-specific generation behavior from the rest of the system.
   - **ToolRegistry**: Manages tool registration and resolution, and provides access to registered tools conforming to the `ToolContract`.
   - **Capabilities (RAG, Tools, Models)**: Standalone implementations that conform to capability contracts and know nothing about the Agent or Planner.

2. **Domain-Agnostic Core**
   - The Agent, ContextManager, Observer, DecisionMaker, and ExecutionManager must remain completely use-case and domain independent.
   - Do not hardcode domain-specific keywords, tool names, dataset paths, or prompt schemas directly into core agent logic.
   - Domain-specific knowledge belongs in data documents, vector stores, custom tools, or fine-tuning datasets.

3. **Contract-First Design & Dependency Injection**
   - Inter-component communication must strictly adhere to the contracts defined in `core/contracts/`.
   - Dependencies must be injected from the composition root (`core/composition.py`) rather than instantiated directly inside consumers.

4. **No Speculative Abstractions**
   - Do not introduce abstractions, base classes, wrappers, or design patterns without a concrete, immediate architectural need.
   - Prefer simple, readable, and small vertical changes over broad horizontal refactorings.

5. **Protect Working Architecture**
   - Do not rewrite working architecture or working modules unnecessarily.
   - Evolve the codebase incrementally by making minimal changes that preserve existing contracts and behavior.

6. **Contract Compatibility**
   - Do not rename, remove, or change the meaning of contract fields without first inspecting all producers and consumers.
   - When a contract must change, update the contract, implementations, consumers, and tests as one vertical slice.
   - Preserve compatibility between components that communicate through shared contracts.

---

## 2. Agent Operational Rules

When modifying or extending this codebase, any AI agent MUST:

1. **Review Existing Code Before Modifying**
   - Always inspect the relevant files, contracts, and tests before making any edits.
   - Understand existing data structures, field names, and interfaces. Never assume or guess fields.

2. **Follow Vertical-Slice Development**
   - Implement one single architectural concept or feature at a time across layers (e.g., Contract -> Implementation -> DI Wire-up -> Test).
   - Ensure the new capability works end-to-end before moving to the next feature.

3. **Run Tests After Behavioral Changes**
   - Every behavioral modification, refactoring, or capability addition must be verified by running the test suite (`test_*.py` / `pytest`).
   - If a new contract or capability is added, corresponding tests must be added to validate correctness.

4. **Preserve Documentation Integrity**
   - Update contracts documentation (`docs/CONTRACTS.md`), architecture guides (`docs/ARCHITECTURE.md`), and the development roadmap (`docs/ROADMAP.md`) whenever architectural changes occur.

5. **Do Not Hide Failures**
   - Do not convert execution failures into successful responses merely to make tests pass.
   - Preserve the distinction between task execution, replanning, and final response generation.
   - If an execution fails and the Agent successfully recovers through replanning, the final response may be successful, but the execution trace must still preserve the earlier failure.

---

## 3. Component Reference Table

| Component | Location | Primary Contract / Interface | Responsibility |
| :--- | :--- | :--- | :--- |
| **Agent** | `agent/agent.py` | `AgentContext`, `AgentResponse` | Orchestrates the control loop (Plan -> Execute -> Observe -> Decide -> Replan -> Synthesize). |
| **Planner** | `agent/planner.py` | `Intent`, `Plan`, `Task` | Classifies query intent, builds multi-task plans, and generates scoped recovery plans on failure. |
| **ExecutionManager** | `agent/execution_manager.py` | `Task`, `ExecutionResult` | Dispatches task execution to appropriate capability implementations. |
| **Observer** | `agent/observer.py` | `ExecutionResult`, `Observation` | Evaluates task execution results and generates structured observations linked to `task_id`. |
| **DecisionMaker** | `agent/decision.py` | `Observation`, `DecisionType` | Determines whether the control loop should conclude or trigger replanning. |
| **ResponseSynthesizer** | `agent/response_synthesizer.py` | `ModelGateway` | Synthesizes intermediate results from multi-task observations into a coherent user response. |
| **ContextManager** | `core/context/context_manager.py` | `AgentContext` | Creates and updates the stateful runtime context (active plans, completed tasks, observations). |
| **ModelGateway** | `core/model_gateway/gateway.py` | `ModelProviderContract` | Provides a unified generation API wrapping model providers. |
| **ToolRegistry** | `core/tools/registry.py` | `ToolContract` | Registers and resolves tools conforming to the tool contract. |
| **Composition Root** | `core/composition.py` | `create_agent()` | Wires concrete dependencies together via dependency injection. |

---

## 4. Dependency Rules

- The Composition Root (`core/composition.py`) is responsible for constructing and wiring concrete implementations.
- Components should receive their dependencies through constructors or other explicit dependency injection mechanisms.
- Components should not instantiate their own major infrastructure dependencies internally.
- The Agent should not directly construct:
  - Models
  - Tools
  - Vector stores
  - Retrievers
  - External API clients
  - Database clients

The intended dependency direction is:

```text
Composition Root
       │
       ▼
     Agent
       │
       ├── Planner
       ├── ExecutionManager
       ├── Observer
       ├── DecisionMaker
       ├── ResponseSynthesizer
       └── ContextManager
```