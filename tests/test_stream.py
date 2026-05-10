import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.search import VertexSearchClient
from src.generate import GeminiGenerator

client = VertexSearchClient(
    project_id=os.environ["GCP_PROJECT_ID"],
    location=os.environ.get("GCP_LOCATION", "global"),
    data_store_id=os.environ["VERTEX_SEARCH_DATA_STORE_ID"],
)
generator = GeminiGenerator(project_id=os.environ["GCP_PROJECT_ID"])

question = "What fields are required in a Pod spec?"
chunks = client.search(question, num_results=5)

print("Streaming response:\n")
for fragment in generator.stream(question, chunks):
    print(fragment, end="", flush=True)
print()
