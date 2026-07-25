# api-rag

![CI](https://github.com/mohammedfirdouss/api-rag/actions/workflows/ci.yml/badge.svg)

Finding a specific endpoint, parameter, or code example in API documentation usually means a lot of scrolling, searching, and tab-switching. This project is a chat interface that sits in front of your API docs — you ask a question in plain English and get a direct, sourced answer.

It works by searching your documentation first, then using that retrieved content to compose the answer. The response includes references to the source chunks so you can verify it or read further. It does not guess or generate information that isn't in your docs.

This example uses the **Kubernetes API**, but the same pipeline works for any API with an OpenAPI spec or existing documentation.

![Chat demo](assets/chat-demo.png)

*Chat on the left, retrieved source chunks on the right. Answers stream in real time.*

![Sources panel](assets/sources-panel.png)

*Each source shows the HTTP method, endpoint path, and a snippet from the indexed documentation.*

## How it works

1. **Ingest** — Parses your API spec and chunks it into documents (one per endpoint, one per schema). Outputs a JSONL file.
2. **Index** — The chunks are indexed for retrieval, either in a local Chroma vector store (default, no GCP data store needed) or in Vertex AI Search, for production-scale deployments.
3. **Query** — The Gradio web app takes a question, retrieves the top 5 matching chunks, and passes them to Gemini to generate a structured answer with citations.

`SEARCH_BACKEND` picks the retrieval backend independently of generation, which always uses Gemini — the local backend just removes the need to set up and pay for a Vertex AI Search data store while you're trying the project out.

## Requirements

- Python 3.10+
- A Google Cloud project with the Vertex AI API enabled (`aiplatform.googleapis.com`), for Gemini generation
- Application Default Credentials configured (`gcloud auth application-default login`)

**Only if you use the Vertex AI Search backend** (`SEARCH_BACKEND=vertex`, see below):
- The Discovery Engine / Vertex AI Search API enabled (`discoveryengine.googleapis.com`)
- No manual data store creation needed — `ingest.py --upload --backend vertex` creates it for you.

## Setup

Install `uv` if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install dependencies:

```bash
git clone <repo-url>
cd api-rag
uv pip install -r requirements.txt
```

If you want to keep local environment values in a file, copy the example template first:

```bash
cp env.txt.example env.txt
```

## Step 1 — Ingest and index your API spec

Point the ingester at any OpenAPI spec — a URL or a local file, JSON or YAML, OpenAPI 2.0 or 3.0 — and pass `--upload` to index it immediately:

```bash
# From a URL
python -m src.ingest --spec https://example.com/openapi.json --name myapi --upload

# From a local file — same flags either way
python -m src.ingest --spec ./openapi.yaml --name myapi --upload
```

By default (no `--backend` flag) this writes `data/myapi_chunks.jsonl` (one chunk per endpoint operation, one per schema definition) and indexes it into a local Chroma collection named `myapi` under `data/chroma/` — no GCP data store needed.

Add `--docs-base-url https://your-docs-site.example.com/reference` to attach a link back to your hosted docs on each retrieved source, shown in the app's sources panel.

**To index into Vertex AI Search instead** (for production-scale deployments), add `--backend vertex`. This creates the data store for you if it doesn't already exist — no manual console steps required:

```bash
python -m src.ingest --spec ./openapi.yaml --name myapi --upload --backend vertex
```

(You can still create/import via the [Vertex AI Search console](https://console.cloud.google.com/gen-app-builder/data-stores) if you prefer — `data/<name>_chunks.jsonl` is a valid **JSONL with document IDs** import.)

**Kubernetes example:**
```bash
python -m src.ingest \
  --spec https://raw.githubusercontent.com/kubernetes/kubernetes/v1.36.0/api/openapi-spec/swagger.json \
  --name kubernetes --upload
```

## Step 2 — Run the app

Set the required environment variables:

```bash
export GCP_PROJECT_ID="your-project-id"     # required — Gemini generation always runs on Vertex AI
export GEMINI_LOCATION="us-central1"        # optional, defaults to us-central1
export API_NAME="API Docs Agent"            # optional, used in the UI title

# Retrieval backend (defaults to local, matching `ingest.py --upload` above)
export SEARCH_BACKEND="local"               # or "vertex"
export LOCAL_COLLECTION="myapi"             # local backend: must match the --name used during ingest
# export VERTEX_SEARCH_DATA_STORE_ID="..."  # vertex backend only
```

Then launch:

```bash
python src/app.py
```

This starts a Gradio web app on `localhost` by default. Open the printed URL in your browser.

By default the app is **not** shared publicly and has no login. If you do want a shareable link (e.g. a workshop or demo), set both of these so you don't expose a billed Gemini/Vertex endpoint with no login:

```bash
export GRADIO_SHARE=true
export GRADIO_AUTH="username:password"
```

### Answer feedback

Each answer in the chat has thumbs up/down. Ratings are logged to `data/feedback.jsonl` (question, answer, sources, rating) — useful for building a real eval set from actual usage instead of guessing at test cases.

## Using as an MCP server

Instead of the web app, you can run the same retrieval pipeline as an MCP server. This lets Claude (via Claude Code or Claude Desktop) call your API docs directly as a tool while writing code.

The server exposes two tools:
- `search_docs(query, num_results=5)` — search for endpoints, parameters, or usage details
- `get_schema(schema_name)` — look up a specific resource type by name

**Claude Code** — add to `.claude/settings.json` in your project:

```json
{
  "mcpServers": {
    "api-rag": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "env": {
        "GCP_PROJECT_ID": "your-project-id",
        "SEARCH_BACKEND": "local",
        "LOCAL_COLLECTION": "myapi",
        "API_NAME": "API Docs Agent"
      }
    }
  }
}
```

**Claude Desktop** — add the same block under `mcpServers` in `claude_desktop_config.json`.

Once connected, Claude will automatically call `search_docs` when you ask questions about your API in the chat.

## Running in Google Colab

Open `notebooks/api_rag_colab.ipynb` in Colab. It walks through ingesting a spec, indexing it (local Chroma by default, or Vertex AI Search), and launching the app with a public share link (with a generated login, since Colab has no `localhost` to fall back to).

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GCP_PROJECT_ID` | Yes | — | Your Google Cloud project ID (Gemini generation always uses Vertex AI) |
| `SEARCH_BACKEND` | No | `local` | Retrieval backend: `local` (Chroma, no GCP data store) or `vertex` |
| `LOCAL_COLLECTION` | No | `docs` | Local backend: Chroma collection name, must match `ingest.py --name` |
| `LOCAL_INDEX_DIR` | No | `data/chroma` | Local backend: where the Chroma index is persisted |
| `VERTEX_SEARCH_DATA_STORE_ID` | Only if `SEARCH_BACKEND=vertex` | — | ID of your Vertex AI Search data store |
| `GCP_LOCATION` | No | `global` | GCP region for Vertex AI Search |
| `GEMINI_LOCATION` | No | `us-central1` | GCP region for Gemini |
| `API_NAME` | No | `API` | Display name shown in the UI title |
| `ENGINES` | No | — | Comma-separated `label:engine_id` pairs for multi-API dropdowns |
| `ENABLE_QUERY_REWRITE` | No | `true` | Whether to spend an extra Gemini call rewriting the query before search |
| `GRADIO_SHARE` | No | `false` | Publish a public Gradio share link |
| `GRADIO_AUTH` | No | — | `username:password` login required before sharing (strongly recommended if `GRADIO_SHARE=true`) |
