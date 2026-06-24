"""Smoke test for the hybrid retriever.

Runs a handful of queries and prints top results so we can verify
retrieval is working before building the agent on top of it.

Usage:
    uv run python scripts/smoke_retrieval.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rag.retriever import search

QUERIES = [
    {
        "label": "Semantic — symptom description",
        "query": "etch rate drift and across-wafer non-uniformity",
        "kwargs": {},
    },
    {
        "label": "Exact keyword — alarm code (BM25 strength)",
        "query": "ALM-005",
        "kwargs": {},
    },
    {
        "label": "Semantic — subsystem failure",
        "query": "RF match network degraded causing process instability",
        "kwargs": {},
    },
    {
        "label": "Filtered — work orders only for ETCH02",
        "query": "root cause of etch failure",
        "kwargs": {"tool_id": "ETCH02", "doc_type": "work_order"},
    },
    {
        "label": "Filtered — SOP excerpts for RF subsystem",
        "query": "RF source inspection procedure",
        "kwargs": {"subsystem": "rf_source", "doc_type": "sop_excerpt"},
    },
]


def run() -> None:
    for q in QUERIES:
        print(f"\n{'='*70}")
        print(f"QUERY: {q['label']}")
        print(f"  \"{q['query']}\"", end="")
        if q["kwargs"]:
            print(f"  filters={q['kwargs']}", end="")
        print()
        print("-" * 70)

        results = search(q["query"], k=3, **q["kwargs"])

        if not results:
            print("  (no results)")
            continue

        for i, hit in enumerate(results, 1):
            print(f"  [{i}] {hit['doc_id']}  ({hit['doc_type']})")
            if hit.get("tool_id"):
                print(f"      tool={hit['tool_id']}  subsystem={hit.get('subsystem', '-')}  date={hit.get('date', '-')}")
            preview = hit["text"].replace("\n", " ")[:200]
            print(f"      {preview}...")


if __name__ == "__main__":
    run()
