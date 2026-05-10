import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import gradio as gr

from src.search import VertexSearchClient
from src.generate import GeminiGenerator

_required = {"GCP_PROJECT_ID", "VERTEX_SEARCH_DATA_STORE_ID"}
_missing = _required - set(os.environ)
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(sorted(_missing))}")

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LOCATION = os.environ.get("GCP_LOCATION", "global")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "us-central1")
DATA_STORE_ID = os.environ["VERTEX_SEARCH_DATA_STORE_ID"]
API_NAME = os.environ.get("API_NAME", "API Docs Agent")

# ENGINES: comma-separated "Label:engine-id" pairs, e.g.
# ENGINES="Kubernetes:k8s-engine-id,Stripe:stripe-engine-id"
# Falls back to the single DATA_STORE_ID if not set.
_engines_raw = os.environ.get("ENGINES", "")
ENGINES: dict[str, str] = {}
if _engines_raw:
    for entry in _engines_raw.split(","):
        if ":" in entry:
            label, eid = entry.split(":", 1)
            ENGINES[label.strip()] = eid.strip()
if not ENGINES:
    ENGINES[API_NAME] = DATA_STORE_ID

def _make_search_client(engine_id: str) -> VertexSearchClient:
    return VertexSearchClient(project_id=PROJECT_ID, location=LOCATION, data_store_id=engine_id)

search_client = _make_search_client(DATA_STORE_ID)
generator = GeminiGenerator(project_id=PROJECT_ID, location=GEMINI_LOCATION)


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

    with gr.Row():
        engine_dropdown = gr.Dropdown(
            choices=list(ENGINES.keys()),
            value=list(ENGINES.keys())[0],
            label="API",
            visible=len(ENGINES) > 1,
            scale=1,
        )
        msg_input = gr.Textbox(placeholder="Ask a question...", show_label=False, scale=4)

    chatbot = gr.Chatbot(height=500)

    with gr.Accordion("Sources", open=False):
        sources_display = gr.Markdown("No sources retrieved yet.")

    def respond(message, chat_history, chunks, engine_label):
        client = _make_search_client(ENGINES[engine_label])
        search_query = generator.rewrite_query(message)
        retrieved = client.search(search_query, num_results=5)
        chat_history = chat_history + [{"role": "user", "content": message}]
        if not retrieved:
            fallback = "I couldn't find any relevant documentation for that question. Try rephrasing or asking about a specific endpoint, resource, or parameter."
            yield "", chat_history + [{"role": "assistant", "content": fallback}], chunks, "No sources retrieved."
            return
        # Stream response with conversation history
        partial = ""
        for fragment in generator.stream(message, retrieved, history=chat_history[:-1]):
            partial += fragment
            yield "", chat_history + [{"role": "assistant", "content": partial}], chunks, format_sources(retrieved)
        yield "", chat_history + [{"role": "assistant", "content": partial}], retrieved, format_sources(retrieved)

    msg_input.submit(
        respond,
        inputs=[msg_input, chatbot, chunks_state, engine_dropdown],
        outputs=[msg_input, chatbot, chunks_state, sources_display],
    )

if __name__ == "__main__":
    demo.launch(share=True)
