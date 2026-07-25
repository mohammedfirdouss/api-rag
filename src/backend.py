"""Factory for the retrieval backend.

SEARCH_BACKEND=local (default) uses a local Chroma index — no GCP data store
required, good for trying the project out. SEARCH_BACKEND=vertex uses Vertex AI
Search, for production-scale deployments.
"""
import os


def get_backend_name() -> str:
    return os.environ.get("SEARCH_BACKEND", "local").strip().lower()


def required_env_vars() -> set[str]:
    """Env vars required for retrieval, given the selected backend."""
    if get_backend_name() == "vertex":
        return {"VERTEX_SEARCH_DATA_STORE_ID"}
    return set()


def create_search_client(engine_id: str | None = None):
    """Create a search client. `engine_id` overrides the default data store / collection,
    used for multi-engine setups (see ENGINES in app.py)."""
    backend = get_backend_name()

    if backend == "vertex":
        from src.search import VertexSearchClient
        data_store_id = engine_id or os.environ["VERTEX_SEARCH_DATA_STORE_ID"]
        return VertexSearchClient(
            project_id=os.environ["GCP_PROJECT_ID"],
            location=os.environ.get("GCP_LOCATION", "global"),
            data_store_id=data_store_id,
        )

    if backend == "local":
        from src.local_search import LocalSearchClient, DEFAULT_PERSIST_DIR
        collection_name = engine_id or os.environ.get("LOCAL_COLLECTION", "docs")
        persist_dir = os.environ.get("LOCAL_INDEX_DIR", str(DEFAULT_PERSIST_DIR))
        return LocalSearchClient(collection_name=collection_name, persist_dir=persist_dir)

    raise RuntimeError(f"Unknown SEARCH_BACKEND '{backend}'; expected 'local' or 'vertex'.")


def default_engine_id() -> str:
    """The engine id to use when ENGINES isn't explicitly configured."""
    if get_backend_name() == "vertex":
        return os.environ["VERTEX_SEARCH_DATA_STORE_ID"]
    return os.environ.get("LOCAL_COLLECTION", "docs")
