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
import json
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_CORPUS = ROOT / "data" / "corpus"
DATA_STRUCTURED = ROOT / "data" / "structured"

CORPUS_FILE = DATA_CORPUS / "corpus.jsonl"

# ---------------------------------------------------------------------------
# Seeded RNG  (fixed seed → reproducible corpus)
# ---------------------------------------------------------------------------

SEED = 42
rng = random.Random(SEED)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Print generation plan without calling the LLM or writing files")
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
        print("  output: data/corpus/corpus.jsonl")
        return

    print("Corpus generation: not yet implemented (Step 2+)")


if __name__ == "__main__":
    main()
