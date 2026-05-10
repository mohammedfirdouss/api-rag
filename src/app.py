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

_engines_raw = os.environ.get("ENGINES", "")
ENGINES: dict[str, str] = {}
if _engines_raw:
    for entry in _engines_raw.split(","):
        if ":" in entry:
            label, eid = entry.split(":", 1)
            ENGINES[label.strip()] = eid.strip()
if not ENGINES:
    ENGINES[API_NAME] = DATA_STORE_ID

EXAMPLES = [
    "How do I create a Deployment?",
    "What endpoints are available for Pods?",
    "How do I delete a Namespace?",
    "What parameters does the StatefulSet API accept?",
]


def _make_search_client(engine_id: str) -> VertexSearchClient:
    return VertexSearchClient(project_id=PROJECT_ID, location=LOCATION, data_store_id=engine_id)


search_client = _make_search_client(DATA_STORE_ID)
generator = GeminiGenerator(project_id=PROJECT_ID, location=GEMINI_LOCATION)


def format_sources(chunks: list[dict]) -> str:
    if not chunks:
        return "_No sources retrieved yet._"
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


def respond(message, chat_history, chunks, engine_label):
    if not message.strip():
        yield "", chat_history, chunks, format_sources(chunks)
        return
    client = _make_search_client(ENGINES[engine_label])
    search_query = generator.rewrite_query(message)
    retrieved = client.search(search_query, num_results=5)
    chat_history = chat_history + [{"role": "user", "content": message}]
    if not retrieved:
        fallback = "I couldn't find any relevant documentation for that question. Try rephrasing or asking about a specific endpoint, resource, or parameter."
        yield "", chat_history + [{"role": "assistant", "content": fallback}], chunks, "_No sources retrieved._"
        return
    partial = ""
    for fragment in generator.stream(message, retrieved, history=chat_history[:-1]):
        partial += fragment
        yield "", chat_history + [{"role": "assistant", "content": partial}], chunks, format_sources(retrieved)
    yield "", chat_history + [{"role": "assistant", "content": partial}], retrieved, format_sources(retrieved)


def clear_chat():
    return [], [], "_No sources retrieved yet._"


theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "sans-serif"],
)

css = """
footer { display: none !important; }
.sources-col { border-left: 1px solid var(--border-color-primary); padding-left: 16px; }
.example-row { gap: 6px !important; flex-wrap: wrap; }
.example-row button { font-size: 0.8rem !important; padding: 4px 10px !important; }
"""

with gr.Blocks(title=API_NAME) as demo:
    gr.Markdown(f"# {API_NAME}")
    gr.Markdown("Ask anything about the API documentation. Sources are shown on the right.")

    chunks_state = gr.State([])

    with gr.Row(equal_height=False):
        # ── Left: chat ──────────────────────────────────────────────
        with gr.Column(scale=3):
            engine_dropdown = gr.Dropdown(
                choices=list(ENGINES.keys()),
                value=list(ENGINES.keys())[0],
                label="API",
                visible=len(ENGINES) > 1,
            )
            chatbot = gr.Chatbot(
                height=520,
                show_label=False,
                avatar_images=(
                    None,
                    "https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg",
                ),
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Ask a question...",
                    show_label=False,
                    scale=5,
                    container=False,
                    autofocus=True,
                )
                submit_btn = gr.Button("Send", variant="primary", scale=1, min_width=80)
                clear_btn = gr.Button("Clear", variant="secondary", scale=1, min_width=80)

            gr.Markdown("**Try asking:**")
            with gr.Row(elem_classes="example-row"):
                example_btns = [gr.Button(ex, size="sm") for ex in EXAMPLES]

        # ── Right: sources ───────────────────────────────────────────
        with gr.Column(scale=2, elem_classes="sources-col"):
            gr.Markdown("### Sources")
            sources_display = gr.Markdown("_No sources retrieved yet._")

    # Wire up events (after all components are defined)
    submit_btn.click(
        respond,
        inputs=[msg_input, chatbot, chunks_state, engine_dropdown],
        outputs=[msg_input, chatbot, chunks_state, sources_display],
    )
    msg_input.submit(
        respond,
        inputs=[msg_input, chatbot, chunks_state, engine_dropdown],
        outputs=[msg_input, chatbot, chunks_state, sources_display],
    )
    clear_btn.click(clear_chat, outputs=[chatbot, chunks_state, sources_display])

    for ex, btn in zip(EXAMPLES, example_btns):
        btn.click(fn=lambda e=ex: e, outputs=msg_input).then(
            respond,
            inputs=[msg_input, chatbot, chunks_state, engine_dropdown],
            outputs=[msg_input, chatbot, chunks_state, sources_display],
        )

if __name__ == "__main__":
    demo.launch(share=True, theme=theme, css=css)
