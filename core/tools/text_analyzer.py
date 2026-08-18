from typing import Any, Dict


class TextAnalyzerTool:

    @property
    def name(self) -> str:
        return "text_analyzer"

    @property
    def description(self) -> str:
        return "Analyzes text and returns character count, word count, and line count."

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, int]:
        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a dictionary.")

        text = arguments.get("text")
        if text is None:
            raise ValueError("Missing required argument: 'text'")

        text = str(text)
        words = text.split()
        lines = text.splitlines()

        return {
            "char_count": len(text),
            "word_count": len(words),
            "line_count": len(lines) if text else 0,
        }
