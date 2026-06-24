"""Evaluation harness — runs the benchmark and writes scored results.

Reads eval/benchmark.jsonl, runs each item through the agent, scores it
with eval/metrics.py, and writes per-item results + an aggregate summary
to eval/results/.

Usage:
    uv run python eval/run_eval.py                      # full run
    uv run python eval/run_eval.py --limit 5            # first 5 items only
    uv run python eval/run_eval.py --no-judge           # skip LLM judge (faster/cheaper)
    uv run python eval/run_eval.py --config no-rag      # baseline: no search tool
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.loop_lg import run as agent_run  # LangGraph refactor (v1); see agent/loop.py for v0
from agent.tools import TOOLS
from agent.traces import Tracer
from eval.metrics import aggregate, score_item

BENCHMARK_FILE = Path(__file__).parent / "benchmark.jsonl"
RESULTS_DIR    = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Config: which tools to pass to the agent
# ---------------------------------------------------------------------------

def _tools_for_config(config: str) -> list[dict]:
    if config == "no-rag":
        return [t for t in TOOLS if t["function"]["name"] != "search_maintenance_docs"]
    return TOOLS  # "full" or default


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def run_eval(
    config: str = "full",
    limit: int | None = None,
    run_judge: bool = True,
) -> tuple[list[dict], dict]:
    """Run the benchmark and return (per_item_scores, aggregate_summary)."""

    items = []
    with BENCHMARK_FILE.open() as f:
        for line in f:
            items.append(json.loads(line.strip()))
    if limit:
        items = items[:limit]

    tools = _tools_for_config(config)
    scores = []

    for i, item in enumerate(items, 1):
        print(f"[{i:02d}/{len(items)}] {item['id']} ({item['difficulty']}) ...", end=" ", flush=True)
        t0 = time.time()

        tracer = Tracer()
        try:
            diagnosis = agent_run(item["query"], tracer=tracer, tools_override=tools)
            tracer.save()
            result = score_item(item, diagnosis, run_judge=run_judge)
            result["error"] = None
        except Exception as exc:
            result = {
                "id": item["id"], "signature_id": item["signature_id"],
                "difficulty": item["difficulty"], "error": str(exc),
                "recall": None, "reciprocal_rank": None, "cause_match": None,
                "judge_correctness": None, "judge_grounding": None,
                "judge_actionability": None, "judge_mean": None,
                "judge_reasoning": None, "diagnosis_summary": None,
                "diagnosis_confidence": None, "citations": [],
            }

        elapsed = time.time() - t0
        recall_str = f"recall={result['recall']:.2f}" if result['recall'] is not None else "ERROR"
        cm_str = "✓" if result.get("cause_match") else "✗"
        print(f"{recall_str}  cause={cm_str}  ({elapsed:.1f}s)")
        scores.append(result)

    summary = aggregate(scores)
    return scores, summary


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _save_results(scores: list[dict], summary: dict, config: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    stem = RESULTS_DIR / f"{ts}_{config}"

    # Per-item JSONL
    items_path = Path(str(stem) + "_items.jsonl")
    with items_path.open("w") as f:
        for s in scores:
            f.write(json.dumps(s) + "\n")

    # Aggregate JSON
    summary_path = Path(str(stem) + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))

    return stem


def _print_table(summary: dict, config: str) -> None:
    print()
    print("=" * 60)
    print(f"EVAL RESULTS  config={config}")
    print("=" * 60)

    def row(label: str, d: dict) -> None:
        n    = d.get("n", "-")
        rec  = f"{d['recall']:.3f}"        if d.get("recall")        is not None else "  -  "
        rr   = f"{d['reciprocal_rank']:.3f}" if d.get("reciprocal_rank") is not None else "  -  "
        cm   = f"{d['cause_match']:.3f}"   if d.get("cause_match")   is not None else "  -  "
        jm   = f"{d['judge_mean']:.2f}"    if d.get("judge_mean")    is not None else "  -  "
        print(f"  {label:<18}  n={n:<3}  recall={rec}  mrr={rr}  cause={cm}  judge={jm}")

    row("overall", summary["overall"])
    print()
    for diff, d in summary.get("by_difficulty", {}).items():
        row(diff, d)
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config",   default="full", choices=["full", "no-rag"],
                   help="Agent configuration to evaluate (default: full)")
    p.add_argument("--limit",    type=int, default=None,
                   help="Only run the first N benchmark items")
    p.add_argument("--no-judge", action="store_true",
                   help="Skip LLM judge calls (faster and cheaper during development)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    scores, summary = run_eval(
        config=args.config,
        limit=args.limit,
        run_judge=not args.no_judge,
    )
    stem = _save_results(scores, summary, args.config)
    _print_table(summary, args.config)
    print(f"\nResults saved to: {stem}_*.{{jsonl,json}}")
