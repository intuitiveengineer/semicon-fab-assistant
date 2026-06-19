"""Synthetic corpus generator for the semicon-fab-assistant.

Produces ~300-600 documents across five types, grounded in the domain taxonomy
(scripts/taxonomy.py).  Each failure signature is scattered across multiple doc
types so benchmark questions require multi-document synthesis.

Output layout:
  data/raw/         -- one JSON file per LLM call (cache; skip if present)
  data/corpus/      -- final JSONL corpus consumed by the ingest pipeline
  data/structured/  -- structured tool-summary JSON records (non-LLM)

Usage:
  uv run python scripts/generate_data.py            # full run
  uv run python scripts/generate_data.py --dry-run  # print plan, skip LLM calls
"""

import argparse
import datetime
import json
import random
import sys
from pathlib import Path

# Ensure project root is importable regardless of invocation path.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.taxonomy import SIGNATURES, SUBSYSTEMS, TOOLS  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_RAW = _ROOT / "data" / "raw"
DATA_CORPUS = _ROOT / "data" / "corpus"
DATA_STRUCTURED = _ROOT / "data" / "structured"

CORPUS_FILE = DATA_CORPUS / "corpus.jsonl"

# ---------------------------------------------------------------------------
# Seeded RNG  (fixed seed → reproducible corpus)
# ---------------------------------------------------------------------------

SEED = 42
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _random_date_before(days_max: int, days_min: int = 1) -> str:
    """ISO date string between days_min and days_max days before today."""
    offset = rng.randint(days_min, days_max)
    return (datetime.date.today() - datetime.timedelta(days=offset)).isoformat()


def _applicable_subsystems(module_type: str) -> list:
    return [s for s in SUBSYSTEMS.values() if module_type in s.applies_to]


def _open_issues(tool, n: int) -> list[str]:
    """Generate n realistic open-issue strings anchored to the tool's signatures."""
    subs = _applicable_subsystems(tool.module_type)
    related = [s for s in SIGNATURES.values() if tool.tool_id in s.tools]
    issues = []
    for _ in range(n):
        if related and rng.random() < 0.6:
            sig = rng.choice(related)
            sub = SUBSYSTEMS.get(sig.root_cause_subsystem)
            label = sub.name if sub else sig.root_cause_subsystem
            issues.append(f"Intermittent {sig.symptom.lower()} — monitoring {label}")
        else:
            sub = rng.choice(subs)
            issues.append(f"Minor anomaly on {sub.name} — under observation")
    return issues

# ---------------------------------------------------------------------------
# Generator: tool summaries  (no LLM — pure taxonomy transform)
# ---------------------------------------------------------------------------

def generate_tool_summaries() -> list[dict]:
    """One structured tool-summary doc per tool."""
    docs = []
    for tool_id, tool in TOOLS.items():
        mtbf = rng.randint(30, 90)
        last_pm = _random_date_before(days_max=60, days_min=10)
        issues = _open_issues(tool, rng.randint(0, 3))

        record = {
            "tool_id": tool_id,
            "module_type": tool.module_type,
            "process_type": tool.process_type,
            "chambers": tool.chamber_ids(),
            "mtbf_days": mtbf,
            "last_pm_date": last_pm,
            "open_issues": issues,
        }

        chambers_str = ", ".join(tool.chamber_ids())
        issues_str = "; ".join(issues) if issues else "none"
        text = (
            f"Tool status summary for {tool_id} ({tool.process_type} {tool.module_type}).\n"
            f"Chambers: {chambers_str}.\n"
            f"Mean time between failures (MTBF): {mtbf} days.\n"
            f"Last preventive maintenance: {last_pm}.\n"
            f"Open issues: {issues_str}."
        )

        docs.append({
            "doc_id": f"TOOLSUM-{tool_id}",
            "doc_type": "tool_summary",
            "tool_id": tool_id,
            "chamber": None,
            "alarm_codes": [],
            "subsystem": None,
            "date": last_pm,
            "text": text,
            "metadata": record,
        })
    return docs

# ---------------------------------------------------------------------------
# Corpus I/O
# ---------------------------------------------------------------------------

def write_corpus(docs: list[dict]) -> None:
    with CORPUS_FILE.open("a") as f:
        for doc in docs:
            f.write(json.dumps(doc) + "\n")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Print plan without calling LLM or writing files")
    p.add_argument("--seed", type=int, default=SEED, help="Random seed (default: 42)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rng.seed(args.seed)

    if args.dry_run:
        print("[dry-run] Generation plan:")
        print("  doc types: tool_summary, alarm_log, work_order, shift_note, sop_excerpt")
        print("  signatures to plant: 20")
        print("  target corpus size: ~350 docs")
        print(f"  output: {CORPUS_FILE}")
        return

    # Wipe corpus on each full run so it's always regenerated from scratch.
    CORPUS_FILE.write_text("")

    print("Generating tool summaries...")
    tool_docs = generate_tool_summaries()
    DATA_STRUCTURED.joinpath("tool_summaries.json").write_text(
        json.dumps([d["metadata"] for d in tool_docs], indent=2)
    )
    write_corpus(tool_docs)
    print(f"  {len(tool_docs)} docs written")

    total = sum(1 for _ in CORPUS_FILE.open())
    print(f"\nCorpus total: {total} docs → {CORPUS_FILE}")


if __name__ == "__main__":
    main()
