import os
from dotenv import load_dotenv
load_dotenv()

from src.search import VertexSearchClient
from src.generate import GeminiGenerator

client = VertexSearchClient(
    project_id=os.environ["GCP_PROJECT_ID"],
    location=os.environ.get("GCP_LOCATION", "global"),
    data_store_id=os.environ["VERTEX_SEARCH_DATA_STORE_ID"],
)
generator = GeminiGenerator(project_id=os.environ["GCP_PROJECT_ID"])

question = "What HTTP method and path do I use to create a Deployment?"
chunks = client.search(question, num_results=5)
result = generator.generate(question, chunks)

print(result["answer"])
print(f"\nSources used: {len(result['sources'])}")
