import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig


class GeminiGenerator:
    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        model: str = "gemini-2.5-pro",
    ):
        self.project_id = project_id
        self.location = location
        self.model_name = model
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model)
        self.generation_config = GenerationConfig(
            temperature=0.2,
            max_output_tokens=2048,
        )

    def _build_prompt(self, question: str, retrieved_chunks: list[dict], history: list[dict] | None = None) -> str:
        chunks_text = ""
        for i, chunk in enumerate(retrieved_chunks, start=1):
            meta = chunk.get("metadata", {})
            meta_parts = []
            for key in ("path", "method", "api_group", "version", "kind", "source", "url"):
                if meta.get(key):
                    meta_parts.append(f"{key}: {meta[key]}")
            meta_str = " | ".join(meta_parts) if meta_parts else "no metadata"
            content = chunk.get("content", "").strip()
            chunks_text += f"[Chunk {i}] ({meta_str})\n{content}\n\n"

        history_text = ""
        if history:
            for turn in history[-6:]:  # last 3 exchanges
                role = "User" if turn["role"] == "user" else "Assistant"
                history_text += f"{role}: {turn['content']}\n"
            history_text = f"## Conversation History\n\n{history_text.strip()}\n\n"

        prompt = f"""You are an API documentation assistant. Your role is to answer questions about the API accurately and clearly, based solely on the provided documentation chunks.

## Retrieved Documentation Chunks

{chunks_text.strip()}

{history_text}## Question

{question}

## Instructions

- Provide a clear, well-structured answer using sections and bullet points where appropriate.
- Base your answer only on the chunks above.
- Cite the chunk numbers you relied on (e.g., [Chunk 1], [Chunk 3]) inline or at the end of relevant statements.
- If the answer cannot be determined from the provided chunks, say so honestly and do not speculate.
- Be concise but complete; do not omit important details from the chunks.

## Answer
"""
        return prompt

    def generate(self, question: str, retrieved_chunks: list[dict], history: list[dict] | None = None) -> dict:
        prompt = self._build_prompt(question, retrieved_chunks, history)
        response = self.model.generate_content(prompt, generation_config=self.generation_config)
        return {"answer": response.text.strip(), "sources": retrieved_chunks}

    def stream(self, question: str, retrieved_chunks: list[dict], history: list[dict] | None = None):
        prompt = self._build_prompt(question, retrieved_chunks, history)
        for chunk in self.model.generate_content(
            prompt,
            generation_config=self.generation_config,
            stream=True,
        ):
            if chunk.text:
                yield chunk.text
