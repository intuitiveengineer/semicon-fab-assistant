"""Compare full-RAG vs no-RAG eval results and print an ablation table.

Reads the two most recent summary JSON files from eval/results/ whose names
contain "full" and "no-rag", then prints a side-by-side delta table.

Usage:
    uv run python eval/compare_ablation.py
    uv run python eval/compare_ablation.py --full path/to/full_summary.json \\
                                           --no-rag path/to/no-rag_summary.json
"""

import argparse
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
METRICS = [
    ("recall",          "Recall@5"),
    ("reciprocal_rank", "MRR"),
    ("cause_match",     "Cause Match"),
    ("judge_mean",      "Judge (1-5)"),
]


def _latest(tag: str) -> Path:
    """Return the most recent *_summary.json matching the given tag."""
    candidates = sorted(RESULTS_DIR.glob(f"*_{tag}_summary.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No summary file matching '*_{tag}_summary.json' in {RESULTS_DIR}. "
            "Run eval/run_eval.py first."
        )
    return candidates[0]


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _fmt(val: float | None, is_judge: bool = False) -> str:
    if val is None:
        return "   -  "
    if is_judge:
        return f"{val:.2f}/5"
    return f"{val:.3f}"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "     "
    d = a - b
    sign = "+" if d >= 0 else ""
    return f"({sign}{d:.3f})"


def print_table(full: dict, no_rag: dict) -> None:
    difficulties = ["overall"] + list(full.get("by_difficulty", {}).keys())

    def _get(summary: dict, difficulty: str, metric: str) -> float | None:
        if difficulty == "overall":
            return summary["overall"].get(metric)
        return summary.get("by_difficulty", {}).get(difficulty, {}).get(metric)

    print()
    print("=" * 72)
    print("ABLATION TABLE  —  full RAG vs. no-RAG baseline")
    print("=" * 72)
    header = f"{'Metric':<18}  {'Split':<14}  {'no-RAG':>9}  {'full-RAG':>9}  {'delta':>9}"
    print(header)
    print("-" * 72)

    for key, label in METRICS:
        is_judge = key == "judge_mean"
        for diff in difficulties:
            a = _get(full,   diff, key)
            b = _get(no_rag, diff, key)
            row = (
                f"  {label:<16}  {diff:<14}  "
                f"{_fmt(b, is_judge):>9}  "
                f"{_fmt(a, is_judge):>9}  "
                f"{_delta(a, b):>9}"
            )
            print(row)
        print()

    print("=" * 72)
    # Bottom-line summary
    overall_full   = full["overall"]
    overall_no_rag = no_rag["overall"]
    rec_delta = (overall_full.get("recall") or 0) - (overall_no_rag.get("recall") or 0)
    cm_delta  = (overall_full.get("cause_match") or 0) - (overall_no_rag.get("cause_match") or 0)
    print(
        f"\nRAG adds  +{rec_delta:.3f} recall  |  +{cm_delta:.3f} cause-match  "
        f"(overall, n={overall_full.get('n', '?')} items)"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--full",   default=None, help="Path to full-config summary JSON (auto-detected if omitted)")
    p.add_argument("--no-rag", default=None, help="Path to no-rag summary JSON (auto-detected if omitted)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    full_path   = Path(args.full)   if args.full   else _latest("full")
    no_rag_path = Path(getattr(args, "no_rag")) if getattr(args, "no_rag") else _latest("no-rag")

    print(f"full   : {full_path.name}")
    print(f"no-rag : {no_rag_path.name}")

    full   = _load(full_path)
    no_rag = _load(no_rag_path)

    print_table(full, no_rag)
