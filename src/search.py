from google.cloud import discoveryengine_v1 as discoveryengine


class VertexSearchClient:
    def __init__(self, project_id: str, location: str, data_store_id: str):
        self.project_id = project_id
        self.location = location
        self.data_store_id = data_store_id
        self.client = discoveryengine.SearchServiceClient()
        self.serving_config = (
            f"projects/{project_id}/locations/{location}"
            f"/collections/default_collection"
            f"/dataStores/{data_store_id}"
            f"/servingConfigs/default_config"
        )

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        content_search_spec = discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True,
            ),
            extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_answer_count=1,
                max_extractive_segment_count=1,
            ),
        )

        request = discoveryengine.SearchRequest(
            serving_config=self.serving_config,
            query=query,
            page_size=num_results,
            content_search_spec=content_search_spec,
        )

        response = self.client.search(request=request)

        results = []
        for result in response.results:
            document = result.document
            doc_data = type(document).to_dict(document)

            content = ""
            derived = doc_data.get("derived_struct_data", {})

            extractive_answers = derived.get("extractive_answers", [])
            if extractive_answers:
                content = extractive_answers[0].get("content", "")

            if not content:
                extractive_segments = derived.get("extractive_segments", [])
                if extractive_segments:
                    content = extractive_segments[0].get("content", "")

            if not content:
                snippets = derived.get("snippets", [])
                if snippets:
                    content = snippets[0].get("snippet", "")

            if not content:
                struct_data = doc_data.get("struct_data", {})
                content = struct_data.get("content", "") or struct_data.get("text", "")

            metadata = {}
            struct_data = doc_data.get("struct_data", {})
            for key in ("path", "method", "api_group", "version", "kind", "source", "url"):
                if key in struct_data:
                    metadata[key] = struct_data[key]
            if not metadata:
                metadata = {k: v for k, v in struct_data.items() if k not in ("content", "text")}

            results.append({
                "id": document.id,
                "content": content,
                "metadata": metadata,
            })

        return results
