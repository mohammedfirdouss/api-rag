"""
End-to-end eval harness.

Each case has a question and a list of keywords that must appear in the answer.
Run from the project root:

    python tests/eval.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from src.search import VertexSearchClient
from src.generate import GeminiGenerator

CASES = [
    {
        "question": "What HTTP method and path do I use to list all pods in a namespace?",
        "must_contain": ["GET", "/api/v1/namespaces/{namespace}/pods"],
    },
    {
        "question": "How do I create a Deployment?",
        "must_contain": ["POST", "deployments"],
    },
    {
        "question": "What fields are required in a Pod spec?",
        "must_contain": ["containers"],
    },
    {
        "question": "How do I delete a Service?",
        "must_contain": ["DELETE"],
    },
    {
        "question": "What does a 401 response mean?",
        "must_contain": ["Unauthorized"],
    },
]

client = VertexSearchClient(
    project_id=os.environ["GCP_PROJECT_ID"],
    location=os.environ.get("GCP_LOCATION", "global"),
    data_store_id=os.environ["VERTEX_SEARCH_DATA_STORE_ID"],
)
generator = GeminiGenerator(project_id=os.environ["GCP_PROJECT_ID"])

passed = 0
failed = 0

for i, case in enumerate(CASES, 1):
    question = case["question"]
    search_query = generator.rewrite_query(question)
    chunks = client.search(search_query, num_results=5)
    if not chunks:
        answer = ""
    else:
        answer = "".join(generator.stream(question, chunks))

    missing = [kw for kw in case["must_contain"] if kw.lower() not in answer.lower()]
    if missing:
        print(f"FAIL [{i}] {question}")
        print(f"     Missing: {missing}")
        print(f"     Answer:  {answer[:200]}")
        failed += 1
    else:
        print(f"PASS [{i}] {question}")
        passed += 1

print(f"\n{passed}/{passed + failed} passed")
sys.exit(0 if failed == 0 else 1)
