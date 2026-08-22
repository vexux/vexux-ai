class CalculatorTool:

    @property
    def name(self) -> str:

        return "calculator"

    @property
    def description(self) -> str:

        return (
            "Performs basic arithmetic calculations."
        )

    @property
    def input_schema(self):

        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate.",
                },
            },
            "required": ["expression"],
        }

    def execute(self, arguments):

        expression = arguments["expression"]

        try:

            result = eval(
                expression,
                {
                    "__builtins__": {}
                },
                {}
            )

            return result

        except Exception as exc:

            raise ValueError(
                f"Invalid calculation: {exc}"
            )
