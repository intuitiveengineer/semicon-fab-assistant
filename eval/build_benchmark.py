"""Build the gold benchmark set from planted failure signatures.

Writes eval/benchmark.jsonl — one JSON line per benchmark item.
Commit the output file; it is ground truth, not a generated artifact.

Each signature produces two items:
  A: multi-doc synthesis — symptom query requiring shift note + work order + alarm log
  B: alarm-focused (if preceding_alarm exists) or PM-timing (if no alarm)

Usage:
    uv run python eval/build_benchmark.py
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.taxonomy import ALARMS, SIGNATURES, TOOLS

BENCHMARK_FILE = Path(__file__).parent / "benchmark.jsonl"


def _fix_keywords(fix: str) -> list[str]:
    """Extract 2-3 meaningful keywords from a fix description."""
    stop = {"and", "the", "or", "to", "a", "an", "if", "per", "with", "of", "in"}
    words = [w.strip("().,-").lower() for w in fix.split()]
    return [w for w in words if len(w) > 3 and w not in stop][:4]


def build() -> list[dict]:
    items = []

    for sig_id, sig in SIGNATURES.items():
        tool_id = sig.tools[0]
        tool = TOOLS[tool_id]

        # Base planted doc IDs for this signature
        wo_id   = f"WO-{sig_id}-{tool_id}"
        sn_id   = f"SHIFTNOTE-{sig_id}-{tool_id}"
        al_id   = f"ALARMLOG-{sig_id}-{tool_id}" if sig.preceding_alarm else None
        ts_id   = f"TOOLSUM-{tool_id}"

        # -----------------------------------------------------------------
        # Item A — multi-doc synthesis
        # -----------------------------------------------------------------
        relevant_a = [wo_id, sn_id]
        if al_id:
            relevant_a.append(al_id)

        items.append({
            "id":               f"{sig_id}-A",
            "signature_id":     sig_id,
            "difficulty":       "multi_doc",
            "query": (
                f"{tool_id} is exhibiting {sig.symptom.lower()}. "
                f"What is the likely root cause and what fix would you recommend?"
            ),
            "relevant_doc_ids":    relevant_a,
            "expected_subsystem":  sig.root_cause_subsystem,
            "expected_alarm_code": sig.preceding_alarm,
            "expected_fix_keywords": _fix_keywords(sig.fix),
        })

        # -----------------------------------------------------------------
        # Item B — alarm-focused OR PM-timing (tool_required)
        # -----------------------------------------------------------------
        if sig.preceding_alarm:
            alarm = ALARMS[sig.preceding_alarm]
            relevant_b = [al_id, wo_id]
            difficulty_b = "single_doc"
            query_b = (
                f"We keep seeing alarm {sig.preceding_alarm} on {tool_id}. "
                f"What does this alarm indicate and what subsystem should we investigate?"
            )
        else:
            # No alarm — ask about PM timing, which requires compute_mtbf + work order
            relevant_b = [wo_id, ts_id]
            difficulty_b = "tool_required"
            query_b = (
                f"{tool_id} is showing {sig.symptom.lower()}. "
                f"Could overdue preventive maintenance be a factor? "
                f"When was the last PM and is it within the expected MTBF?"
            )

        items.append({
            "id":               f"{sig_id}-B",
            "signature_id":     sig_id,
            "difficulty":       difficulty_b,
            "query":            query_b,
            "relevant_doc_ids":    relevant_b,
            "expected_subsystem":  sig.root_cause_subsystem,
            "expected_alarm_code": sig.preceding_alarm,
            "expected_fix_keywords": _fix_keywords(sig.fix),
        })

    return items


def main() -> None:
    items = build()

    with BENCHMARK_FILE.open("w") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")

    # Summary
    from collections import Counter
    diff_counts = Counter(i["difficulty"] for i in items)
    print(f"Wrote {len(items)} benchmark items to {BENCHMARK_FILE}")
    print(f"  multi_doc:    {diff_counts['multi_doc']}")
    print(f"  single_doc:   {diff_counts['single_doc']}")
    print(f"  tool_required:{diff_counts['tool_required']}")
    print()
    print("Sample item:")
    print(json.dumps(items[0], indent=2))


if __name__ == "__main__":
    main()
