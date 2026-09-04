"""Deterministic selection of explicitly mentioned registered knowledge resources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List
from core.contracts.authorization import AuthorizationRequest


@dataclass(frozen=True)
class ResourceSelection:
    name: str
    resource_type: str
    resource: Any


@dataclass(frozen=True)
class ResourceRoute:
    selections: List[ResourceSelection]
    graph_requests: List[Dict[str, Any]]
    source_tasks: List[Dict[str, Any]]


class ResourceRouter:
    """Select registered resources; authorization remains outside this class."""

    def __init__(self, knowledge_source_registry=None, knowledge_graph_registry=None):
        self.knowledge_source_registry = knowledge_source_registry
        self.knowledge_graph_registry = knowledge_graph_registry

    def _resources(self) -> List[ResourceSelection]:
        resources: List[ResourceSelection] = []
        if self.knowledge_graph_registry is not None:
            for item in self.knowledge_graph_registry.describe_graphs():
                graph = self.knowledge_graph_registry.get(item["name"])
                resources.append(ResourceSelection(item["name"], "knowledge_graph", graph))
        if self.knowledge_source_registry is not None:
            for item in self.knowledge_source_registry.describe_sources():
                source = self.knowledge_source_registry.get(item["name"])
                resources.append(ResourceSelection(item["name"], "knowledge_source", source))
        return resources

    @staticmethod
    def _terms(selection: ResourceSelection) -> set[str]:
        resource = selection.resource
        aliases = getattr(resource, "aliases", ()) or ()
        name = selection.name.replace("_", " ")
        return {name.lower(), selection.name.lower(), *(str(alias).lower() for alias in aliases)}

    def select(self, query: str) -> List[ResourceSelection]:
        lowered = query.lower()
        resources = self._resources()
        selected = [resource for resource in resources if any(term in lowered for term in self._terms(resource))]
        explicit_tokens = set(re.findall(r"\b[a-z0-9]+_(?:graph|db)\b", lowered))
        known_names = {selection.name.lower() for selection in resources}
        unknown = sorted(token for token in explicit_tokens if token not in known_names)
        if unknown:
            raise ValueError(f"Unknown or unavailable knowledge resource: {unknown[0]}")
        return selected

    @staticmethod
    def is_authorization_query(query: str) -> bool:
        return bool(re.search(
            r"\b(?:am\s+i\s+(?:allowed|authorized)|can\s+i\s+access|"
            r"do\s+i\s+have\s+permission|permission\s+to|authorized\s+to|"
            r"allowed\s+to)\b",
            query.lower(),
        ))

    def authorization_requests(
        self,
        query: str,
        actor: str | None,
        context: dict | None = None,
    ) -> List[AuthorizationRequest]:
        return [
            AuthorizationRequest(
                actor=actor,
                resource_type=selection.resource_type,
                resource_name=selection.name,
                action="read",
                context=context,
            )
            for selection in self.select(query)
        ]

    def route(self, query: str) -> ResourceRoute | None:
        selections = self.select(query)
        if not selections:
            return None
        identifier_match = re.search(r"\b[A-Z]\d+\b", query)
        identifier = identifier_match.group(0) if identifier_match else None
        graph_requests = []
        source_tasks = []
        for selection in selections:
            if selection.resource_type == "knowledge_graph":
                node_id = identifier or getattr(selection.resource, "default_node_id", None)
                params = {"node_id": node_id} if node_id else {}
                graph_requests.append({
                    "graph_name": selection.name,
                    "operation": "get_neighbors",
                    "params": params,
                })
            else:
                default_query = getattr(selection.resource, "default_query", None)
                if not default_query:
                    raise ValueError(
                        f"Knowledge resource '{selection.name}' has no default read query for natural-language routing."
                    )
                source_tasks.append({
                    "source": selection.name,
                    "query": default_query,
                    "parameters": (identifier,) if identifier else (),
                })
        return ResourceRoute(selections, graph_requests, source_tasks)
