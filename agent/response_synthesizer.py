class ResponseSynthesizer:

    def __init__(
        self,
        model_gateway,
    ):
        self.model_gateway = model_gateway

    def synthesize(
        self,
        query: str,
        observations: list,
    ) -> str:

        successful_outputs = [
            observation.output
            for observation in observations
            if observation.success
            and observation.output is not None
        ]

        if not successful_outputs:
            return (
                "The request could not be completed."
            )

        # No need to call the model when there is
        # only one result.
        if len(successful_outputs) == 1:
            return str(
                successful_outputs[0]
            )

        results_text = "\n\n".join(
            f"Result {index + 1}:\n{output}"
            for index, output
            in enumerate(successful_outputs)
        )

        prompt = f"""
You are producing the final response for an AI agent.

Original user request:
{query}

The agent executed multiple tasks and produced these results:

{results_text}

Create one clear final answer that answers the original
user request using the task results.

IMPORTANT:
- Use the provided results.
- Do not invent additional facts.
- Preserve numerical results exactly.
- Do not mention internal tasks, observations, planning,
  tools, or agent architecture.
- Answer naturally and concisely.

Final answer:
"""

        return self.model_gateway.generate(
            prompt,
            max_new_tokens=300,
            do_sample=False,
        )