import json
import re
from pathlib import Path

import requests

MAX_CONTENT_CHARS = 6000

SPEC_URL = "https://raw.githubusercontent.com/kubernetes/kubernetes/master/api/openapi-spec/swagger.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "kubernetes_chunks.jsonl"


def download_spec(url: str) -> dict:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


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
        param_type = param.get("type") or param.get("schema", {}).get("type", "")
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


def chunk_operations(spec: dict) -> list[dict]:
    paths = spec.get("paths", {})
    chunks = []

    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            operation = path_item.get(method)
            if not operation:
                continue

            operation_id = operation.get("operationId", f"{method}_{path}")
            tags = operation.get("tags", [])
            summary = operation.get("summary", "").strip()
            description = operation.get("description", "").strip()
            parameters = operation.get("parameters", [])
            responses = operation.get("responses", {})
            api_group = derive_api_group(tags, path)

            content_parts = [
                f"Path: {path}",
                f"Method: {method.upper()}",
            ]
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

            chunk = {
                "id": f"{method}_{operation_id}",
                "content": content,
                "metadata": {
                    "path": path,
                    "method": method.upper(),
                    "operationId": operation_id,
                    "tags": tags,
                    "api_group": api_group,
                },
            }
            chunks.append(chunk)

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


def chunk_definitions(spec: dict) -> list[dict]:
    definitions = spec.get("definitions", {})
    chunks = []

    for schema_name, schema in definitions.items():
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

        chunk = {
            "id": f"schema_{safe_id}",
            "content": content,
            "metadata": {
                "schema_name": schema_name,
                "type": schema_type,
                "kind": "schema_definition",
            },
        }
        chunks.append(chunk)

    return chunks


def main():
    print("Downloading Kubernetes OpenAPI spec...")
    spec = download_spec(SPEC_URL)

    print("Chunking API operations...")
    operation_chunks = chunk_operations(spec)
    print(f"Total operations found: {len(operation_chunks)}")

    print("Chunking schema definitions...")
    schema_chunks = chunk_definitions(spec)
    print(f"Total schemas found: {len(schema_chunks)}")

    all_chunks = operation_chunks + schema_chunks

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk) + "\n")

    print(f"Total chunks written: {len(all_chunks)}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
