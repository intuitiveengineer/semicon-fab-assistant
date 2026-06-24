"""End-to-end smoke test for the agent loop.

Runs three representative queries through the full stack:
  user query → loop → tool calls → structured Diagnosis → JSONL trace

Usage:
    uv run python scripts/smoke_agent.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.loop import run
from agent.traces import Tracer

QUERIES = [
    "ETCH02 is showing etch-rate drift and across-wafer non-uniformity. What is the likely root cause and recommended fix?",
    "We are seeing particle contamination and wafer defect excursions on ETCH02. What should we check?",
    "PECVD01 has a deposition rate that keeps drifting low. What subsystem should we investigate?",
]


def print_diagnosis(query: str, diagnosis) -> None:
    width = 70
    print("=" * width)
    print(f"QUERY: {query}")
    print("-" * width)
    print(f"SUMMARY:\n  {diagnosis.summary}")
    print()
    print("LIKELY CAUSES:")
    for c in diagnosis.likely_causes:
        print(f"  [{c.confidence:.0%}] {c.cause}")
        print(f"         evidence: {c.evidence_doc_ids}")
    print()
    print("RECOMMENDED CHECKS:")
    for r in diagnosis.recommended_checks:
        print(f"  - {r}")
    print()
    print(f"CITATIONS:  {diagnosis.citations}")
    print(f"CONFIDENCE: {diagnosis.confidence:.0%}")


def main() -> None:
    traces_saved = []

    for query in QUERIES:
        print()
        tracer = Tracer()
        diagnosis = run(query, verbose=True, tracer=tracer)
        path = tracer.save()
        traces_saved.append(path)
        print()
        print_diagnosis(query, diagnosis)
        print()

    print(f"\n{len(QUERIES)} runs complete. Traces saved to:")
    for p in traces_saved:
        print(f"  {p}")


if __name__ == "__main__":
    main()
