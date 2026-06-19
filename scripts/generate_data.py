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
import hashlib
import json
import random
import sys
from pathlib import Path

# Ensure project root is importable regardless of invocation path.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.taxonomy import ALARMS, SIGNATURES, SUBSYSTEMS, TOOLS  # noqa: E402

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
# LLM infrastructure  (lazy import so dry-run never needs config/openai)
# ---------------------------------------------------------------------------

def _cache_path(prompt: str) -> Path:
    key = hashlib.sha256(prompt.encode()).hexdigest()[:20]
    return DATA_RAW / f"{key}.json"


def _llm_call(prompt: str, model: str = "gpt-4o-mini") -> str:
    """Call the OpenAI chat API with a prompt; return the text response.

    Results are cached to data/raw/ by prompt hash so reruns are free.
    """
    cache = _cache_path(prompt)
    if cache.exists():
        return json.loads(cache.read_text())["content"]

    import config  # triggers load_dotenv + key validation  # noqa: F401
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    content = response.choices[0].message.content
    cache.write_text(json.dumps({"model": model, "content": content}))
    return content

# ---------------------------------------------------------------------------
# Generator: alarm logs  (LLM-backed; plants preceding_alarm from signatures)
# ---------------------------------------------------------------------------

_ALARM_LOG_PROMPT = """\
You are a semiconductor fab equipment alarm logger. Generate a realistic alarm log entry.

Tool ID: {tool_id}
Chamber: {chamber}
Alarm code: {alarm_code} — {alarm_text}
Subsystem: {subsystem_name}
Typical causes: {causes}
Event time: {dt}

Write 4–8 lines of machine-formatted log output in pipe-delimited form:
- A header line: TIMESTAMP | TOOL | CHAMBER | ALARM_CODE | SHORT_MESSAGE
- 2–4 parameter lines showing the sensor reading or setpoint deviation that triggered \
the alarm (invent plausible numeric values consistent with the alarm type)
- An "Action:" line with the automatic system response (interlock, operator alert, \
or process abort)

Be terse and technical. No narrative or explanation.\
"""


def _alarm_log_text(tool_id: str, chamber: str, alarm_code: str, dt: str) -> str:
    alarm = ALARMS[alarm_code]
    sub = SUBSYSTEMS[alarm.subsystem]
    prompt = _ALARM_LOG_PROMPT.format(
        tool_id=tool_id,
        chamber=chamber,
        alarm_code=alarm_code,
        alarm_text=alarm.text,
        subsystem_name=sub.name,
        causes="; ".join(alarm.typical_causes),
        dt=dt,
    )
    return _llm_call(prompt)


def _random_datetime(days_max: int = 180, days_min: int = 30) -> tuple[str, str]:
    """Return (iso_date, datetime_str) for a random past timestamp."""
    date_str = _random_date_before(days_max=days_max, days_min=days_min)
    time_str = f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
    return date_str, f"{date_str} {time_str}"


def generate_alarm_logs(dry_run: bool = False) -> list[dict]:
    """Alarm log docs: one planted entry per signature×tool, plus random distractors."""
    docs = []

    # --- Planted: one alarm log per signature that has a preceding_alarm ---
    for sig_id, sig in SIGNATURES.items():
        if sig.preceding_alarm is None:
            continue
        alarm_code = sig.preceding_alarm
        for tool_id in sig.tools:
            tool = TOOLS[tool_id]
            chamber = rng.choice(tool.chamber_ids())
            date_str, dt_str = _random_datetime()
            text = (
                f"[dry-run] Would generate alarm log for {alarm_code} on {tool_id}/{chamber}"
                if dry_run
                else _alarm_log_text(tool_id, chamber, alarm_code, dt_str)
            )
            docs.append({
                "doc_id": f"ALARMLOG-{sig_id}-{tool_id}",
                "doc_type": "alarm_log",
                "tool_id": tool_id,
                "chamber": chamber,
                "alarm_codes": [alarm_code],
                "subsystem": ALARMS[alarm_code].subsystem,
                "date": date_str,
                "text": text,
                "metadata": {
                    "tool_id": tool_id,
                    "chamber": chamber,
                    "alarm_codes": [alarm_code],
                    "subsystem": ALARMS[alarm_code].subsystem,
                    "date": date_str,
                    "signature_id": sig_id,
                    "is_planted": True,
                },
            })

    # --- Distractors: random tool + alarm, not tied to any signature ---
    all_alarm_codes = list(ALARMS)
    for i in range(22):
        tool_id, tool = rng.choice(list(TOOLS.items()))
        alarm_code = rng.choice(all_alarm_codes)
        alarm = ALARMS[alarm_code]
        # Only use this alarm if the subsystem applies to the tool's module type
        sub = SUBSYSTEMS[alarm.subsystem]
        if tool.module_type not in sub.applies_to:
            continue
        chamber = rng.choice(tool.chamber_ids())
        date_str, dt_str = _random_datetime()
        text = (
            f"[dry-run] Would generate distractor alarm log for {alarm_code} on {tool_id}/{chamber}"
            if dry_run
            else _alarm_log_text(tool_id, chamber, alarm_code, dt_str)
        )
        docs.append({
            "doc_id": f"ALARMLOG-DIST-{i:03d}",
            "doc_type": "alarm_log",
            "tool_id": tool_id,
            "chamber": chamber,
            "alarm_codes": [alarm_code],
            "subsystem": alarm.subsystem,
            "date": date_str,
            "text": text,
            "metadata": {
                "tool_id": tool_id,
                "chamber": chamber,
                "alarm_codes": [alarm_code],
                "subsystem": alarm.subsystem,
                "date": date_str,
                "is_planted": False,
            },
        })

    return docs

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

    dry_run = args.dry_run

    if dry_run:
        print("[dry-run] Generation plan:")
        print("  doc types: tool_summary, alarm_log, work_order, shift_note, sop_excerpt")
        print("  signatures to plant: 20")
        print("  target corpus size: ~350 docs")
        print(f"  output: {CORPUS_FILE}")

    if not dry_run:
        # Wipe corpus on each full run so it's always regenerated from scratch.
        CORPUS_FILE.write_text("")

    print("\nGenerating tool summaries...")
    tool_docs = generate_tool_summaries()
    if not dry_run:
        DATA_STRUCTURED.joinpath("tool_summaries.json").write_text(
            json.dumps([d["metadata"] for d in tool_docs], indent=2)
        )
        write_corpus(tool_docs)
    print(f"  {len(tool_docs)} docs")

    print("Generating alarm logs...")
    alarm_docs = generate_alarm_logs(dry_run=dry_run)
    if not dry_run:
        write_corpus(alarm_docs)
    print(f"  {len(alarm_docs)} docs")

    if not dry_run:
        total = sum(1 for _ in CORPUS_FILE.open())
        print(f"\nCorpus total: {total} docs → {CORPUS_FILE}")


if __name__ == "__main__":
    main()
