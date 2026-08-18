from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from core.tools.string_formatter import StringFormatterTool
from core.tools.text_analyzer import TextAnalyzerTool


def main():

    registry = ToolRegistry()

    registry.register(CalculatorTool())
    registry.register(StringFormatterTool())
    registry.register(TextAnalyzerTool())

    print("Available tools:")
    print(registry.list_tools())

    calc_result = registry.execute(
        "calculator",
        {
            "expression": "24 * 7"
        }
    )
    print("\nCalculation result (24 * 7):")
    print(calc_result)

    format_result = registry.execute(
        "string_formatter",
        {
            "text": "hello vexux",
            "operation": "uppercase",
        }
    )
    print("\nString Formatter result (uppercase):")
    print(format_result)

    analyzer_result = registry.execute(
        "text_analyzer",
        {
            "text": "Hello world from Vexux AI",
        }
    )
    print("\nText Analyzer result:")
    print(analyzer_result)


if __name__ == "__main__":
    main()