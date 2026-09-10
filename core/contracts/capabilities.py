from typing import Any, Dict, List, Protocol


class Capability(Protocol):

    @property
    def name(self) -> str:
        ...

    def execute(
        self,
        input_data: Dict[str, Any]
    ) -> Any:
        ...


class RetrievalContract(Protocol):

    def retrieve(
        self,
        query: str,
        k: int = 3
    ) -> List[Dict[str, Any]]:
        ...


class KnowledgeSourceContract(Protocol):

    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def capabilities(self) -> List[str]:
        ...

    def retrieve(
        self,
        query: str,
        k: int | None = None,
    ) -> List[Dict[str, Any]]:
        ...


class ToolContract(Protocol):

    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def input_schema(self) -> Dict[str, Any]:
        ...

    @property
    def security_metadata(self) -> Dict[str, Any]:
        ...

    def execute(
        self,
        arguments: Dict[str, Any]
    ) -> Any:
        ...


class MemoryContract(Protocol):

    @property
    def name(self) -> str:
        ...

    def store(
        self,
        scope: str,
        content: str,
        memory_id: str | None = None,
    ) -> str:
        ...

    def retrieve(
        self,
        scope: str,
        query: str | None = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        ...


class ModelProviderContract(Protocol):

    @property
    def name(self) -> str:
        ...

    def generate(
        self,
        prompt: str,
        response_format: str | None = None,
        **kwargs
    ) -> str:
        ...
