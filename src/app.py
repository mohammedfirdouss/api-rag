import os

import gradio as gr

from src.search import VertexSearchClient
from src.generate import GeminiGenerator

_required = {"GCP_PROJECT_ID", "VERTEX_SEARCH_DATA_STORE_ID"}
_missing = _required - set(os.environ)
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(sorted(_missing))}")

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
DATA_STORE_ID = os.environ["VERTEX_SEARCH_DATA_STORE_ID"]
API_NAME = os.environ.get("API_NAME", "API Docs Agent")

search_client = VertexSearchClient(
    project_id=PROJECT_ID,
    location=LOCATION,
    data_store_id=DATA_STORE_ID,
)

generator = GeminiGenerator(project_id=PROJECT_ID, location=LOCATION)


def format_sources(chunks: list[dict]) -> str:
    if not chunks:
        return "No sources retrieved yet."
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.get("metadata", {})
        path = meta.get("path", "")
        method = meta.get("method", "")
        snippet = chunk.get("content", "").strip()[:300]
        header_parts = [f"**[{i}]**"]
        if method:
            header_parts.append(f"`{method}`")
        if path:
            header_parts.append(f"`{path}`")
        lines.append(" ".join(header_parts))
        if snippet:
            lines.append(f"> {snippet}{'…' if len(chunk.get('content', '')) > 300 else ''}")
        lines.append("")
    return "\n".join(lines)


with gr.Blocks(title=API_NAME) as demo:
    gr.Markdown(f"# {API_NAME}")
    gr.Markdown(f"Ask any question about the API")

    chunks_state = gr.State([])

    chatbot = gr.Chatbot(type="messages", height=500)
    msg_input = gr.Textbox(placeholder=f"Ask a question...", show_label=False)

    with gr.Accordion("Sources", open=False):
        sources_display = gr.Markdown("No sources retrieved yet.")

    def respond(message, chat_history, chunks):
        # 1. Retrieve
        retrieved = search_client.search(message, num_results=5)
        # 2. Stream response — yield partial updates
        chat_history = chat_history + [{"role": "user", "content": message}]
        partial = ""
        for fragment in generator.stream(message, retrieved):
            partial += fragment
            yield "", chat_history + [{"role": "assistant", "content": partial}], chunks, format_sources(retrieved)
        # Final yield with completed answer and updated chunks state
        yield "", chat_history + [{"role": "assistant", "content": partial}], retrieved, format_sources(retrieved)

    msg_input.submit(
        respond,
        inputs=[msg_input, chatbot, chunks_state],
        outputs=[msg_input, chatbot, chunks_state, sources_display],
    )

if __name__ == "__main__":
    demo.launch(share=True)
