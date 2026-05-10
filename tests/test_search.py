import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.search import VertexSearchClient

client = VertexSearchClient(
    project_id=os.environ["GCP_PROJECT_ID"],
    location=os.environ.get("GCP_LOCATION", "global"),
    data_store_id=os.environ["VERTEX_SEARCH_DATA_STORE_ID"],
)

results = client.search("how do I list all pods in a namespace", num_results=3)
for r in results:
    print(r["metadata"])
    print(r["content"][:200])
    print("---")
