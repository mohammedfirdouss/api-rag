import os

from mcp.server.fastmcp import FastMCP

from src.search import VertexSearchClient

_required = {"GCP_PROJECT_ID", "VERTEX_SEARCH_DATA_STORE_ID"}
_missing = _required - set(os.environ)
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(sorted(_missing))}")

_search_client = VertexSearchClient(
    project_id=os.environ["GCP_PROJECT_ID"],
    location=os.environ.get("GCP_LOCATION", "us-central1"),
    data_store_id=os.environ["VERTEX_SEARCH_DATA_STORE_ID"],
)

_api_name = os.environ.get("API_NAME", "API Docs Agent")

mcp = FastMCP(f"{_api_name} Docs")


def _format_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No results found."
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.get("metadata", {})
        lines = [f"## Result {i}"]
        if meta.get("method") and meta.get("path"):
            lines.append(f"**Endpoint:** `{meta['method']} {meta['path']}`")
        if meta.get("api_group"):
            lines.append(f"**Group:** {meta['api_group']}")
        if meta.get("schema_name"):
            lines.append(f"**Schema:** {meta['schema_name']}")
        lines.append("")
        lines.append(chunk.get("content", "").strip())
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def search_docs(query: str, num_results: int = 5) -> str:
    """
    Search the API documentation for endpoints, parameters, schemas, or usage details.

    Use this whenever you need to answer a question about the API — how to call an
    endpoint, what fields a resource has, what a status code means, etc.

    Args:
        query: Natural language question or keyword search.
        num_results: Number of documentation chunks to retrieve (1-10).
    """
    num_results = max(1, min(num_results, 10))
    chunks = _search_client.search(query, num_results=num_results)
    return _format_chunks(chunks)


@mcp.tool()
def get_schema(schema_name: str) -> str:
    """
    Look up a specific API schema or resource type by name.

    Use this when you know the exact resource name you want details on — its fields,
    types, required properties, and description.

    Args:
        schema_name: The name of the schema or resource (e.g. 'Deployment', 'ServiceSpec').
    """
    chunks = _search_client.search(f"schema {schema_name} properties fields", num_results=3)
    if not chunks:
        return f"No schema found matching '{schema_name}'."
    return _format_chunks(chunks)


if __name__ == "__main__":
    mcp.run()
