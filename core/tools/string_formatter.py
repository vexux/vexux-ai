from typing import Any, Dict


class StringFormatterTool:

    @property
    def name(self) -> str:
        return "string_formatter"

    @property
    def description(self) -> str:
        return "Transforms text using operations: uppercase, lowercase, reverse, title."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to transform."},
                "operation": {
                    "type": "string",
                    "description": "uppercase, lowercase, reverse, or title.",
                },
            },
            "required": ["text"],
        }

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
