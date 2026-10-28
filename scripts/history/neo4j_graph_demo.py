"""Show the generic graph execution boundary with in-memory and Neo4j backends."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from agent.execution_manager import ExecutionManager
from core.contracts.execution import AgentContext, Task


def main():
    registry = KnowledgeGraphRegistry()
    memory = InMemoryKnowledgeGraph()
    memory.name = "fraud_graph"
    memory.add_node("demo")
    registry.register(memory)
    manager = ExecutionManager(knowledge_graph_registry=registry)
    result = manager.execute(
        Task(
            id="demo-graph-read",
            description="Read demo graph node",
            input={
                "query": "demo",
                "source": "fraud_graph",
                "operation": "get_node",
                "params": {"node_id": "demo"},
            },
            metadata={"capability": "retrieval"},
        ),
        AgentContext(request_id="neo4j-plugin-demo"),
    )
    print(f"InMemory backend: generic execution success={result.success}")

    if not os.getenv("NEO4J_URI"):
        print("Neo4j backend: skipped (NEO4J_URI is not configured)")
        return

    try:
        neo4j = Neo4jKnowledgeGraph(
            uri=os.environ["NEO4J_URI"],
            username=os.environ.get("NEO4J_USERNAME", ""),
            password=os.environ.get("NEO4J_PASSWORD", ""),
            database=os.getenv("NEO4J_DATABASE"),
            name=os.getenv("NEO4J_GRAPH_NAME", "customer_graph"),
        )
        registry.register(neo4j)
        print(f"Neo4j backend: registered {neo4j.name}")
        print("Neo4j backend: registered through the same generic graph registry")
    except (RuntimeError, ValueError) as exc:
        print(f"Neo4j backend: unavailable ({exc})")


if __name__ == "__main__":
    main()
