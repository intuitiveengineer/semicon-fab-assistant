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
# Generator: maintenance work orders  (LLM-backed; plants root_cause + fix)
# ---------------------------------------------------------------------------

_WORK_ORDER_PROMPT = """\
You are a semiconductor fab maintenance technician writing up a completed work order.

Tool ID: {tool_id}
Chamber: {chamber}
Process type: {process_type}
Work order number: {wo_num}
Opened: {open_date}
Closed: {close_date}
Technician: {tech}
Reported symptom: {symptom}
Root cause subsystem: {root_cause_subsystem}
Root cause: {root_cause}
Fix applied: {fix}

Write a realistic maintenance work order with these sections (use the exact headings):

PROBLEM DESCRIPTION:
(1–2 sentences — what the operator reported)

FINDINGS:
(2–4 sentences — what the technician found on inspection; reference the root cause \
subsystem and specific observations like measurements or visual findings)

ACTIONS TAKEN:
(2–3 sentences — what was replaced, adjusted, or cleaned; reference the fix)

RESULT:
(1 sentence — whether process parameters recovered after the repair)

Be specific and technical. Use realistic fab language. Do not invent tool IDs, alarm \
codes, or subsystem names beyond what is provided.\
"""

_TECH_NAMES = ["J. Park", "M. Torres", "S. Nguyen", "R. Patel", "A. Kim", "L. Chen", "D. Okafor"]


def generate_work_orders(dry_run: bool = False) -> list[dict]:
    """Work order docs: one planted per signature (all 20), plus random distractors."""
    docs = []

    # --- Planted: one work order per signature (covers root_cause + fix) ---
    for sig_id, sig in SIGNATURES.items():
        tool_id = rng.choice(sig.tools)
        tool = TOOLS[tool_id]
        chamber = rng.choice(tool.chamber_ids())
        close_date = _random_date_before(days_max=150, days_min=14)
        open_dt = datetime.date.fromisoformat(close_date) - datetime.timedelta(days=rng.randint(1, 3))
        open_date = open_dt.isoformat()
        wo_num = f"WO-{rng.randint(10000, 99999)}"
        tech = rng.choice(_TECH_NAMES)
        sub = SUBSYSTEMS.get(sig.root_cause_subsystem)
        sub_name = sub.name if sub else sig.root_cause_subsystem

        text = (
            f"[dry-run] Would generate work order for {sig_id} on {tool_id}/{chamber}"
            if dry_run
            else _llm_call(_WORK_ORDER_PROMPT.format(
                tool_id=tool_id,
                chamber=chamber,
                process_type=tool.process_type,
                wo_num=wo_num,
                open_date=open_date,
                close_date=close_date,
                tech=tech,
                symptom=sig.symptom,
                root_cause_subsystem=sub_name,
                root_cause=sig.root_cause,
                fix=sig.fix,
            ))
        )

        alarm_codes = [sig.preceding_alarm] if sig.preceding_alarm else []
        docs.append({
            "doc_id": f"WO-{sig_id}-{tool_id}",
            "doc_type": "work_order",
            "tool_id": tool_id,
            "chamber": chamber,
            "alarm_codes": alarm_codes,
            "subsystem": sig.root_cause_subsystem,
            "date": close_date,
            "text": text,
            "metadata": {
                "tool_id": tool_id,
                "chamber": chamber,
                "alarm_codes": alarm_codes,
                "subsystem": sig.root_cause_subsystem,
                "date": close_date,
                "wo_number": wo_num,
                "technician": tech,
                "signature_id": sig_id,
                "is_planted": True,
            },
        })

    # --- Distractors: random tool + subsystem, generic maintenance language ---
    _DISTRACTOR_WO_PROMPT = """\
You are a semiconductor fab maintenance technician writing up a routine work order.

Tool ID: {tool_id}
Chamber: {chamber}
Process type: {process_type}
Work order number: {wo_num}
Opened: {open_date}
Closed: {close_date}
Technician: {tech}
Subsystem serviced: {subsystem_name}

Write a short realistic routine maintenance work order (PM check or minor repair) \
with sections: PROBLEM DESCRIPTION, FINDINGS, ACTIONS TAKEN, RESULT.
Keep it 6–10 sentences total. Be specific and technical.\
"""

    all_subs = list(SUBSYSTEMS.values())
    for i in range(20):
        tool_id, tool = rng.choice(list(TOOLS.items()))
        sub = rng.choice([s for s in all_subs if tool.module_type in s.applies_to])
        chamber = rng.choice(tool.chamber_ids())
        close_date = _random_date_before(days_max=150, days_min=14)
        open_dt = datetime.date.fromisoformat(close_date) - datetime.timedelta(days=rng.randint(1, 2))
        wo_num = f"WO-{rng.randint(10000, 99999)}"
        tech = rng.choice(_TECH_NAMES)

        text = (
            f"[dry-run] Would generate distractor work order on {tool_id}/{chamber} ({sub.name})"
            if dry_run
            else _llm_call(_DISTRACTOR_WO_PROMPT.format(
                tool_id=tool_id,
                chamber=chamber,
                process_type=tool.process_type,
                wo_num=wo_num,
                open_date=open_dt.isoformat(),
                close_date=close_date,
                tech=tech,
                subsystem_name=sub.name,
            ))
        )

        docs.append({
            "doc_id": f"WO-DIST-{i:03d}",
            "doc_type": "work_order",
            "tool_id": tool_id,
            "chamber": chamber,
            "alarm_codes": [],
            "subsystem": sub.subsystem_id,
            "date": close_date,
            "text": text,
            "metadata": {
                "tool_id": tool_id,
                "chamber": chamber,
                "alarm_codes": [],
                "subsystem": sub.subsystem_id,
                "date": close_date,
                "wo_number": wo_num,
                "technician": tech,
                "is_planted": False,
            },
        })

    return docs

# ---------------------------------------------------------------------------
# Generator: shift handoff notes  (LLM-backed; plants symptom as first observed)
# ---------------------------------------------------------------------------

_SHIFT_NOTE_PROMPT = """\
You are a semiconductor fab process technician writing a brief shift handoff note at the \
end of your shift. Write in a natural, slightly informal tone — you are briefing the \
incoming crew, not writing a formal report.

Tool: {tool_id} ({process_type} {module_type})
Chamber: {chamber}
Shift end time: {dt}
Observation: {symptom}
Subsystem of concern: {subsystem_name}

Write 3–6 sentences as a shift note. Include:
- What you observed (use the symptom, but phrase it naturally as a first-hand observation)
- When it started or how often it occurs
- What you did or didn't do about it yet
- A recommendation for the incoming crew

Do NOT use alarm codes, formal headings, or structured format. Write as plain prose, \
as if typed quickly at end of shift. Do not invent tool IDs or chamber names beyond \
what is provided.\
"""

_DISTRACTOR_SHIFT_PROMPT = """\
You are a semiconductor fab process technician writing a routine shift handoff note.

Tool: {tool_id} ({process_type} {module_type})
Chamber: {chamber}
Shift end time: {dt}
Subsystem: {subsystem_name}

Write 2–4 sentences: a routine, unremarkable shift note mentioning a minor observation \
or completed check on this subsystem. No major issues. Informal tone, plain prose.\
"""


def generate_shift_notes(dry_run: bool = False) -> list[dict]:
    """Shift handoff note docs: one planted per signature, plus random distractors."""
    docs = []

    # --- Planted: one shift note per signature capturing the symptom ---
    for sig_id, sig in SIGNATURES.items():
        tool_id = rng.choice(sig.tools)
        tool = TOOLS[tool_id]
        chamber = rng.choice(tool.chamber_ids())
        date_str, dt_str = _random_datetime(days_max=160, days_min=20)
        sub = SUBSYSTEMS.get(sig.root_cause_subsystem)
        sub_name = sub.name if sub else sig.root_cause_subsystem

        text = (
            f"[dry-run] Would generate shift note for {sig_id} on {tool_id}/{chamber}"
            if dry_run
            else _llm_call(_SHIFT_NOTE_PROMPT.format(
                tool_id=tool_id,
                chamber=chamber,
                process_type=tool.process_type,
                module_type=tool.module_type,
                dt=dt_str,
                symptom=sig.symptom,
                subsystem_name=sub_name,
            ))
        )

        alarm_codes = [sig.preceding_alarm] if sig.preceding_alarm else []
        docs.append({
            "doc_id": f"SHIFTNOTE-{sig_id}-{tool_id}",
            "doc_type": "shift_note",
            "tool_id": tool_id,
            "chamber": chamber,
            "alarm_codes": alarm_codes,
            "subsystem": sig.root_cause_subsystem,
            "date": date_str,
            "text": text,
            "metadata": {
                "tool_id": tool_id,
                "chamber": chamber,
                "alarm_codes": alarm_codes,
                "subsystem": sig.root_cause_subsystem,
                "date": date_str,
                "signature_id": sig_id,
                "is_planted": True,
            },
        })

    # --- Distractors: routine observations, no signature facts ---
    all_subs = list(SUBSYSTEMS.values())
    for i in range(20):
        tool_id, tool = rng.choice(list(TOOLS.items()))
        sub = rng.choice([s for s in all_subs if tool.module_type in s.applies_to])
        chamber = rng.choice(tool.chamber_ids())
        date_str, dt_str = _random_datetime(days_max=160, days_min=20)

        text = (
            f"[dry-run] Would generate distractor shift note on {tool_id}/{chamber} ({sub.name})"
            if dry_run
            else _llm_call(_DISTRACTOR_SHIFT_PROMPT.format(
                tool_id=tool_id,
                chamber=chamber,
                process_type=tool.process_type,
                module_type=tool.module_type,
                dt=dt_str,
                subsystem_name=sub.name,
            ))
        )

        docs.append({
            "doc_id": f"SHIFTNOTE-DIST-{i:03d}",
            "doc_type": "shift_note",
            "tool_id": tool_id,
            "chamber": chamber,
            "alarm_codes": [],
            "subsystem": sub.subsystem_id,
            "date": date_str,
            "text": text,
            "metadata": {
                "tool_id": tool_id,
                "chamber": chamber,
                "alarm_codes": [],
                "subsystem": sub.subsystem_id,
                "date": date_str,
                "is_planted": False,
            },
        })

    return docs

# ---------------------------------------------------------------------------
# Generator: SOP / manual excerpts  (subsystem-indexed reference material)
# ---------------------------------------------------------------------------

_SOP_PROMPT = """\
You are a semiconductor fab process engineer writing an OEM-style standard operating \
procedure excerpt.

Subsystem: {subsystem_name}
Applicable equipment: {applies_to_str}
Procedure type: {procedure_type}
Document ID: {sop_ref}
Revision date: {date}

Write an SOP excerpt of 180–250 words. Use the following headings exactly:

PURPOSE:
(one sentence — what this procedure achieves)

SCOPE:
(which equipment or module types this applies to)

PROCEDURE:
(5–8 numbered steps with specific check criteria, threshold values, and pass/fail \
conditions — invent plausible but realistic numeric values)

ESCALATION:
(when to stop and call engineering support)

Formal technical language only. No narrative prose.\
"""

_SOP_PROCEDURE_TYPES = [
    "Inspection and check procedure",
    "Routine preventive maintenance checklist",
    "Fault response procedure",
    "Component replacement procedure",
    "Calibration and verification procedure",
]


def generate_sop_excerpts(dry_run: bool = False) -> list[dict]:
    """SOP / manual excerpt docs: one per subsystem, plus tool-specific extras."""
    docs = []
    used_date = _random_date_before(days_max=730, days_min=90)  # revision dates ~months ago

    # --- Primary: one SOP per subsystem ---
    for sub_id, sub in SUBSYSTEMS.items():
        applies_str = " and ".join(sub.applies_to) + " equipment"
        procedure_type = rng.choice(_SOP_PROCEDURE_TYPES)
        sop_ref = f"SOP-{sub_id.upper().replace('_', '-')}-{rng.randint(100, 999)}"
        rev_date = _random_date_before(days_max=730, days_min=90)

        text = (
            f"[dry-run] Would generate SOP for {sub_id} ({procedure_type})"
            if dry_run
            else _llm_call(_SOP_PROMPT.format(
                subsystem_name=sub.name,
                applies_to_str=applies_str,
                procedure_type=procedure_type,
                sop_ref=sop_ref,
                date=rev_date,
            ))
        )

        docs.append({
            "doc_id": f"SOP-{sub_id}",
            "doc_type": "sop_excerpt",
            "tool_id": None,
            "chamber": None,
            "alarm_codes": [],
            "subsystem": sub_id,
            "date": rev_date,
            "text": text,
            "metadata": {
                "subsystem": sub_id,
                "subsystem_name": sub.name,
                "applies_to": list(sub.applies_to),
                "procedure_type": procedure_type,
                "sop_ref": sop_ref,
                "date": rev_date,
            },
        })

    # --- Extras: tool-process-specific checklists for variety ---
    _SOP_EXTRA_PROMPT = """\
You are a semiconductor fab process engineer writing a tool-specific maintenance \
checklist excerpt.

Tool: {tool_id} ({process_type} {module_type})
Subsystem: {subsystem_name}
Document ID: {sop_ref}
Revision date: {date}

Write a concise tool-specific checklist of 120–180 words with these sections:

PURPOSE: (one sentence)
CHECKLIST: (6–9 numbered check items with pass/fail criteria and numeric thresholds \
specific to {process_type} equipment)
NOTES: (1–2 sentences on common pitfalls for this tool type)

Formal technical language. No narrative.\
"""

    for i in range(15):
        tool_id, tool = rng.choice(list(TOOLS.items()))
        sub = rng.choice([s for s in SUBSYSTEMS.values() if tool.module_type in s.applies_to])
        sop_ref = f"SOP-{tool_id}-{sub.subsystem_id.upper().replace('_', '-')}-{rng.randint(10, 99)}"
        rev_date = _random_date_before(days_max=730, days_min=90)

        text = (
            f"[dry-run] Would generate tool-specific SOP for {tool_id} / {sub.subsystem_id}"
            if dry_run
            else _llm_call(_SOP_EXTRA_PROMPT.format(
                tool_id=tool_id,
                process_type=tool.process_type,
                module_type=tool.module_type,
                subsystem_name=sub.name,
                sop_ref=sop_ref,
                date=rev_date,
            ))
        )

        docs.append({
            "doc_id": f"SOP-EXTRA-{i:03d}",
            "doc_type": "sop_excerpt",
            "tool_id": tool_id,
            "chamber": None,
            "alarm_codes": [],
            "subsystem": sub.subsystem_id,
            "date": rev_date,
            "text": text,
            "metadata": {
                "tool_id": tool_id,
                "subsystem": sub.subsystem_id,
                "subsystem_name": sub.name,
                "procedure_type": "tool-specific checklist",
                "sop_ref": sop_ref,
                "date": rev_date,
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

    print("Generating work orders...")
    wo_docs = generate_work_orders(dry_run=dry_run)
    if not dry_run:
        write_corpus(wo_docs)
    print(f"  {len(wo_docs)} docs")

    print("Generating shift notes...")
    shift_docs = generate_shift_notes(dry_run=dry_run)
    if not dry_run:
        write_corpus(shift_docs)
    print(f"  {len(shift_docs)} docs")

    print("Generating SOP excerpts...")
    sop_docs = generate_sop_excerpts(dry_run=dry_run)
    if not dry_run:
        write_corpus(sop_docs)
    print(f"  {len(sop_docs)} docs")

    if not dry_run:
        total = sum(1 for _ in CORPUS_FILE.open())
        print(f"\nCorpus total: {total} docs → {CORPUS_FILE}")


if __name__ == "__main__":
    main()
