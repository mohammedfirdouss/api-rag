import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

MAX_CONTENT_CHARS = 6000
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data"
def load_spec(source: str) -> dict:
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        response = requests.get(source, timeout=120)
        response.raise_for_status()
        content = response.text
    else:
        content = Path(source).read_text(encoding="utf-8")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return yaml.safe_load(content)
def detect_format(source: str, data: dict) -> str:
    """Return 'openapi', 'postman', or 'markdown'."""
    if source.endswith(".md") or (Path(source).exists() and Path(source).is_dir()):
        return "markdown"
    if "info" in data and "_postman_schema" in data.get("info", {}):
        return "postman"
    return "openapi"

def get_schemas(spec: dict) -> dict:
    components = spec.get("components", {})
    if components.get("schemas"):
        return components["schemas"]
    return spec.get("definitions", {})
def resolve_ref(ref: str, spec: dict) -> dict:
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node.get(part, {})
    return node
def derive_api_group(tags: list[str], path: str) -> str:
    if tags:
        return tags[0]
    parts = path.strip("/").split("/")
    for i, part in enumerate(parts):
        if part in ("apis", "api") and i + 1 < len(parts):
            return parts[i + 1]
    return "core"
def format_parameters(parameters: list[dict]) -> str:
    if not parameters:
        return ""
    lines = ["Parameters:"]
    for param in parameters:
        name = param.get("name", "")
        location = param.get("in", "")
        required = "required" if param.get("required") else "optional"
        description = param.get("description", "").strip()
        schema = param.get("schema", {})
        param_type = param.get("type") or schema.get("type", "")
        line = f"  - {name} ({location}, {required}"
        if param_type:
            line += f", {param_type}"
        line += ")"
        if description:
            line += f": {description}"
        lines.append(line)
    return "\n".join(lines)
def format_responses(responses: dict) -> str:
    if not responses:
        return ""
    lines = ["Responses:"]
    for status_code, response in responses.items():
        description = response.get("description", "").strip()
        lines.append(f"  - {status_code}: {description}")
    return "\n".join(lines)
def chunk_operations(spec: dict, docs_base_url: str = "") -> list[dict]:
    chunks = []
    for path, path_item in spec.get("paths", {}).items():
        shared_params = path_item.get("parameters", [])
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            operation = path_item.get(method)
            if not operation:
                continue
            operation_id = operation.get("operationId", f"{method}_{path}")
            tags = operation.get("tags", [])
            summary = operation.get("summary", "").strip()
            description = operation.get("description", "").strip()
            raw_params = shared_params + operation.get("parameters", [])
            parameters = [resolve_ref(p["$ref"], spec) if "$ref" in p else p for p in raw_params]
            responses = operation.get("responses", {})
            api_group = derive_api_group(tags, path)

            content_parts = [f"Path: {path}", f"Method: {method.upper()}"]
            if summary:
                content_parts.append(f"Summary: {summary}")
            if description:
                content_parts.append(f"Description: {description}")
            if tags:
                content_parts.append(f"Tags: {', '.join(tags)}")
            params_text = format_parameters(parameters)
            if params_text:
                content_parts.append(params_text)
            responses_text = format_responses(responses)
            if responses_text:
                content_parts.append(responses_text)

            content = "\n".join(content_parts)
            if len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS] + "\n[truncated]"

            struct_data = {
                "content": content,
                "path": path,
                "method": method.upper(),
                "operationId": operation_id,
                "tags": ", ".join(tags),
                "api_group": api_group,
            }
            if docs_base_url:
                struct_data["url"] = f"{docs_base_url.rstrip('/')}#{operation_id}"

            chunks.append({
                "id": f"{method}_{operation_id}",
                "structData": struct_data,
            })
    return chunks
def format_properties(properties: dict, required: list[str]) -> str:
    if not properties:
        return ""
    lines = ["Properties:"]
    for prop_name, prop_schema in properties.items():
        req_marker = " (required)" if prop_name in required else ""
        prop_type = prop_schema.get("type", "")
        prop_ref = prop_schema.get("$ref", "")
        prop_desc = prop_schema.get("description", "").strip()
        type_info = prop_type or (prop_ref.split("/")[-1] if prop_ref else "object")
        line = f"  - {prop_name}{req_marker} [{type_info}]"
        if prop_desc:
            line += f": {prop_desc}"
        lines.append(line)
    return "\n".join(lines)
def chunk_schemas(spec: dict, docs_base_url: str = "") -> list[dict]:
    chunks = []
    for schema_name, schema in get_schemas(spec).items():
        description = schema.get("description", "").strip()
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        schema_type = schema.get("type", "object")
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", schema_name)

        content_parts = [f"Schema: {schema_name}", f"Type: {schema_type}"]
        if description:
            content_parts.append(f"Description: {description}")
        props_text = format_properties(properties, required)
        if props_text:
            content_parts.append(props_text)

        content = "\n".join(content_parts)
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS] + "\n[truncated]"

        struct_data = {
            "content": content,
            "schema_name": schema_name,
            "type": schema_type,
            "kind": "schema_definition",
        }
        if docs_base_url:
            struct_data["url"] = f"{docs_base_url.rstrip('/')}#{schema_name}"

        chunks.append({
            "id": f"schema_{safe_id}",
            "structData": struct_data,
        })
    return chunks

def _iter_postman_requests(items: list, folder: str = "") -> list[tuple]:
    results = []
    for item in items:
        name = item.get("name", "")
        if "item" in item:
            results.extend(_iter_postman_requests(item["item"], folder=name))
        elif "request" in item:
            results.append((folder, name, item["request"]))
    return results
def chunk_postman(collection: dict, docs_base_url: str = "") -> list[dict]:
    chunks = []
    for folder, name, req in _iter_postman_requests(collection.get("item", [])):
        method = req.get("method", "GET").upper()
        url_obj = req.get("url", {})
        url = url_obj if isinstance(url_obj, str) else url_obj.get("raw", "")
        path = "/" + "/".join(url_obj.get("path", [])) if isinstance(url_obj, dict) else url
        description = req.get("description", "")
        if isinstance(description, dict):
            description = description.get("content", "")
        description = description.strip()

        content_parts = [f"Name: {name}", f"Method: {method}", f"URL: {url}"]
        if folder:
            content_parts.append(f"Folder: {folder}")
        if description:
            content_parts.append(f"Description: {description}")
        headers = req.get("header", [])
        if headers:
            content_parts.append("Headers: " + ", ".join(h.get("key", "") for h in headers if not h.get("disabled")))
        body = req.get("body", {})
        if body and body.get("mode") == "raw" and body.get("raw"):
            content_parts.append(f"Body:\n{body['raw'].strip()[:500]}")

        content = "\n".join(content_parts)
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS] + "\n[truncated]"

        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{method}_{folder}_{name}")
        struct_data = {
            "content": content,
            "name": name,
            "method": method,
            "path": path,
            "folder": folder,
            "kind": "postman_request",
        }
        if docs_base_url:
            struct_data["url"] = f"{docs_base_url.rstrip('/')}#{safe_id}"

        chunks.append({
            "id": safe_id,
            "structData": struct_data,
        })
    return chunks

def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, content) sections on H1/H2 boundaries."""
    pattern = re.compile(r"^(#{1,2} .+)$", re.MULTILINE)
    positions = [m.start() for m in pattern.finditer(text)]
    if not positions:
        return [("Document", text)]
    sections = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        block = text[pos:end].strip()
        heading_end = block.index("\n") if "\n" in block else len(block)
        heading = block[:heading_end].lstrip("#").strip()
        body = block[heading_end:].strip()
        if body:
            sections.append((heading, block))
    return sections
def chunk_markdown(source: str, docs_base_url: str = "") -> list[dict]:
    p = Path(source)
    files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
    chunks = []
    for md_file in files:
        text = md_file.read_text(encoding="utf-8")
        for i, (heading, content) in enumerate(_split_markdown_sections(text)):
            if len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS] + "\n[truncated]"
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{md_file.stem}_{heading}_{i}")
            struct_data = {
                "content": content,
                "heading": heading,
                "source": md_file.name,
                "kind": "markdown_section",
            }
            if docs_base_url:
                struct_data["url"] = f"{docs_base_url.rstrip('/')}/{md_file.name}"

            chunks.append({
                "id": safe_id,
                "structData": struct_data,
            })
    return chunks

def ensure_vertex_datastore(project_id: str, location: str, data_store_id: str) -> None:
    """Create the Vertex AI Search data store if it doesn't already exist, so
    `--upload` works end-to-end without a manual console step."""
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import discoveryengine_v1 as discoveryengine

    client = discoveryengine.DataStoreServiceClient()
    parent = f"projects/{project_id}/locations/{location}/collections/default_collection"
    data_store = discoveryengine.DataStore(
        display_name=data_store_id,
        industry_vertical=discoveryengine.IndustryVertical.GENERIC,
        solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
        content_config=discoveryengine.DataStore.ContentConfig.NO_CONTENT,
    )
    try:
        print(f"Creating Vertex AI Search data store '{data_store_id}'...")
        operation = client.create_data_store(
            request=discoveryengine.CreateDataStoreRequest(
                parent=parent,
                data_store=data_store,
                data_store_id=data_store_id,
            )
        )
        operation.result()
        print("Data store created.")
    except AlreadyExists:
        print(f"Data store '{data_store_id}' already exists, reusing it.")


def upload_to_vertex(jsonl_path: Path, project_id: str, location: str, data_store_id: str) -> None:
    from google.cloud import discoveryengine_v1 as discoveryengine

    ensure_vertex_datastore(project_id, location, data_store_id)

    client = discoveryengine.DocumentServiceClient()
    parent = (
        f"projects/{project_id}/locations/{location}"
        f"/collections/default_collection/dataStores/{data_store_id}/branches/default_branch"
    )
    documents = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            chunk = json.loads(line)
            documents.append(discoveryengine.Document(id=chunk["id"], struct_data=chunk["structData"]))

    print(f"Uploading {len(documents)} documents to Vertex AI Search...")
    operation = client.import_documents(
        request=discoveryengine.ImportDocumentsRequest(
            parent=parent,
            inline_source=discoveryengine.ImportDocumentsRequest.InlineSource(documents=documents),
            reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.FULL,
        )
    )
    print("Waiting for import to complete...")
    print(f"Import complete: {operation.result()}")

def main():
    parser = argparse.ArgumentParser(description="Ingest API docs into JSONL chunks for Vertex AI Search.")
    parser.add_argument("--spec", required=True, help="OpenAPI spec (URL or file), Postman collection JSON, or Markdown file/directory")
    parser.add_argument("--name", required=True, help="Short name for the API (used in the output filename)")
    parser.add_argument("--version", default="", help="Optional version string, e.g. 'v1.36.0'")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--docs-base-url", default="", help="Base URL of your hosted docs; used to add a source link to each chunk")
    parser.add_argument(
        "--backend", choices=("local", "vertex"), default="local",
        help="Where --upload indexes the chunks: a local Chroma index (default, no GCP data store needed) or Vertex AI Search",
    )
    parser.add_argument("--upload", action="store_true", help="Index the chunks (into the local Chroma store or Vertex AI Search, per --backend) after ingestion")
    args = parser.parse_args()

    filename = f"{args.name}_{args.version}_chunks.jsonl" if args.version else f"{args.name}_chunks.jsonl"
    output_path = Path(args.output_dir) / filename

    # Markdown: no HTTP load needed
    if Path(args.spec).exists() and (Path(args.spec).is_dir() or args.spec.endswith(".md")):
        print("Format: markdown")
        all_chunks = chunk_markdown(args.spec, docs_base_url=args.docs_base_url)
    else:
        print(f"Loading spec from: {args.spec}")
        data = load_spec(args.spec)
        fmt = detect_format(args.spec, data)
        print(f"Format: {fmt}")

        if fmt == "postman":
            print("Chunking Postman requests...")
            all_chunks = chunk_postman(data, docs_base_url=args.docs_base_url)
        else:
            print(f"OpenAPI version: {data.get('openapi') or data.get('swagger', 'unknown')}")
            print("Chunking API operations...")
            operation_chunks = chunk_operations(data, docs_base_url=args.docs_base_url)
            print(f"  Operations: {len(operation_chunks)}")
            print("Chunking schema definitions...")
            schema_chunks = chunk_schemas(data, docs_base_url=args.docs_base_url)
            print(f"  Schemas: {len(schema_chunks)}")
            all_chunks = operation_chunks + schema_chunks

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk) + "\n")

    print(f"Total chunks written: {len(all_chunks)}")
    print(f"Output: {output_path}")

    if args.upload:
        if args.backend == "local":
            from src.local_search import build_local_index, DEFAULT_PERSIST_DIR
            import os
            persist_dir = os.environ.get("LOCAL_INDEX_DIR", str(DEFAULT_PERSIST_DIR))
            count = build_local_index(output_path, collection_name=args.name, persist_dir=persist_dir)
            print(f"Indexed {count} chunks into local Chroma collection '{args.name}' at {persist_dir}")
            print(f"Run the app with SEARCH_BACKEND=local and LOCAL_COLLECTION={args.name}")
        else:
            import os
            upload_to_vertex(output_path, os.environ["GCP_PROJECT_ID"], os.environ.get("GCP_LOCATION", "global"), os.environ["VERTEX_SEARCH_DATA_STORE_ID"])
if __name__ == "__main__":
    main()
