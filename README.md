# Vexux-AI

Vexux-AI is a modular, use-case-independent AI agent platform designed around Small Language Models (SLMs), Retrieval-Augmented Generation (RAG), tools, and agentic execution.

The goal is to build a reusable agent architecture whose core remains stable while domains, tools, knowledge sources, and use cases can change independently.

---

## Vision

Vexux-AI is being developed as a general-purpose agent architecture rather than a single domain-specific application.

The system is designed around three conceptual layers:

```text
┌──────────────────────────────────────────────┐
│              INNER / AGENT LAYER             │
│                                              │
│ Planner → Execution → Observation → Decision │
│                     ↑                        │
│                   Replan                     │
└──────────────────────────┬───────────────────┘
                           │
┌──────────────────────────▼───────────────────┐
│             MIDDLE / ARCHITECTURE            │
│                                              │
│ Model Gateway                                │
│ Tool Registry                                │
│ Execution Manager                            │
│ Context Management                           │
│ Contracts                                    │
│ RAG Integration                              │
└──────────────────────────┬───────────────────┘
                           │
┌──────────────────────────▼───────────────────┐
│              DATA / CAPABILITY               │
│                                              │
│ Documents                                    │
│ Embeddings                                   │
│ Vector Store                                 │
│ Tools                                        │
│ External APIs                                │
└──────────────────────────────────────────────┘