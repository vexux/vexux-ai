from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool


def main():

    registry = ToolRegistry()

    calculator = CalculatorTool()

    registry.register(calculator)

    print("Available tools:")
    print(registry.list_tools())

    result = registry.execute(
        "calculator",
        {
            "expression": "24 * 7"
        }
    )

    print("\nCalculation result:")
    print(result)


if __name__ == "__main__":
    main()