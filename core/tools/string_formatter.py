from typing import Any, Dict


class StringFormatterTool:

    @property
    def name(self) -> str:
        return "string_formatter"

    @property
    def description(self) -> str:
        return "Transforms text using operations: uppercase, lowercase, reverse, title."

    def execute(self, arguments: Dict[str, Any]) -> str:
        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a dictionary.")

        text = arguments.get("text")
        if text is None:
            raise ValueError("Missing required argument: 'text'")

        text = str(text)
        operation = arguments.get("operation", "uppercase").lower()

        if operation == "uppercase":
            return text.upper()
        elif operation == "lowercase":
            return text.lower()
        elif operation == "reverse":
            return text[::-1]
        elif operation == "title":
            return text.title()
        else:
            raise ValueError(
                f"Unsupported operation: '{operation}'. Supported operations: uppercase, lowercase, reverse, title."
            )
