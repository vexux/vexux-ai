from typing import Any, Dict, List, Optional

from core.contracts.capabilities import KnowledgeSourceContract


class KnowledgeSourceRegistry:

    def __init__(self):

        self._sources: Dict[str, KnowledgeSourceContract] = {}
        self._default_source_name: Optional[str] = None

    def register(
        self,
        source: KnowledgeSourceContract,
    ) -> None:

        if source.name in self._sources:
            raise ValueError(
                f"Knowledge source already registered: {source.name}"
            )

        self._sources[source.name] = source

        if self._default_source_name is None:
            self._default_source_name = source.name

    def get(
        self,
        name: Optional[str] = None,
    ) -> KnowledgeSourceContract:

        if name is None:
            name = self._default_source_name

        if name is None:
            raise KeyError("No knowledge source registered")

        if name not in self._sources:
            raise KeyError(f"Knowledge source not found: {name}")

        return self._sources[name]

    def describe_sources(self) -> List[Dict[str, Any]]:

        return [
            {
                "name": source.name,
                "description": source.description,
                "capabilities": source.capabilities,
            }
            for source in self._sources.values()
        ]
