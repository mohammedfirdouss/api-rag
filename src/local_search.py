"""GCP-free retrieval backend backed by Chroma with a bundled MiniLM embedding model.

Lets the app run end-to-end (ingest -> index -> search) without a Vertex AI Search
data store, so a new API can be tried in minutes instead of requiring GCP billing
and console setup. Generation still uses Gemini (see src/generate.py), which does
need a GCP project — only retrieval is local here.
"""
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

DEFAULT_PERSIST_DIR = Path(__file__).parent.parent / "data" / "chroma"


def _embedding_function():
    return embedding_functions.DefaultEmbeddingFunction()


class LocalSearchClient:
    def __init__(self, collection_name: str, persist_dir: str | Path = DEFAULT_PERSIST_DIR):
        self.collection_name = collection_name
        self.persist_dir = str(persist_dir)
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=_embedding_function(),
        )

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        count = self.collection.count()
        if count == 0:
            return []
        result = self.collection.query(query_texts=[query], n_results=min(num_results, count))
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        chunks = []
        for doc_id, content, metadata in zip(ids, documents, metadatas):
            chunks.append({
                "id": doc_id,
                "content": content or "",
                "metadata": dict(metadata or {}),
            })
        return chunks


def build_local_index(jsonl_path: Path, collection_name: str, persist_dir: str | Path = DEFAULT_PERSIST_DIR) -> int:
    """Build (or replace) a local Chroma collection from an ingest JSONL file. Returns chunk count."""
    client = chromadb.PersistentClient(path=str(persist_dir))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        embedding_function=_embedding_function(),
    )

    ids, documents, metadatas = [], [], []
    with Path(jsonl_path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            struct_data = chunk["structData"]
            ids.append(chunk["id"])
            documents.append(struct_data.get("content", ""))
            metadatas.append({
                k: v for k, v in struct_data.items()
                if k != "content" and v not in (None, "")
            })

    if not ids:
        return 0

    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )
    return len(ids)
