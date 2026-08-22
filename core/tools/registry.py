from typing import Dict, List, Any

from core.contracts.capabilities import ToolContract


class ToolRegistry:

    def __init__(self):

        self._tools: Dict[str, ToolContract] = {}

    def register(
        self,
        tool: ToolContract,
    ) -> None:

        if tool.name in self._tools:

            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(
        self,
        name: str,
    ) -> ToolContract:

        if name not in self._tools:

            raise KeyError(
                f"Tool not found: {name}"
            )

        return self._tools[name]

    def list_tools(self) -> List[str]:

        return list(self._tools.keys())

    def describe_tools(self) -> List[Dict[str, Any]]:

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> Any:

        tool = self.get(name)

        return tool.execute(arguments)
