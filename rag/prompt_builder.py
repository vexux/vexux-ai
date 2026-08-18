class PromptBuilder:

    @staticmethod
    def build(question, retrieved_chunks):

        context = ""

        for item in retrieved_chunks:

            context += item["document"]
            context += "\n\n"

        prompt = f"""
You are a helpful assistant.

Answer ONLY using the provided context.

If the answer is not in the context, say you don't know.

Context:

{context}

Question:

{question}

Answer:
"""

        return prompt.strip()