"""Scoring functions for the benchmark evaluation harness.

Each function takes a benchmark item dict and a Diagnosis object (or trace dict)
and returns a numeric score or structured result.

Public surface:
    score_item(item, diagnosis)  ->  dict of all scores for one item
    aggregate(scores)            ->  dict of mean scores + breakdown by difficulty
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pydantic import BaseModel, Field
from openai import OpenAI

from agent.schemas import Diagnosis

_client = OpenAI()

# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def recall(relevant: list[str], cited: list[str]) -> float:
    """Fraction of relevant doc_ids that appear in the citation list."""
    if not relevant:
        return 1.0
    cited_set = set(cited)
    hits = sum(1 for doc_id in relevant if doc_id in cited_set)
    return hits / len(relevant)


def reciprocal_rank(relevant: list[str], cited: list[str]) -> float:
    """1 / rank of the first relevant doc in the citation list (0.0 if none found)."""
    relevant_set = set(relevant)
    for rank, doc_id in enumerate(cited, start=1):
        if doc_id in relevant_set:
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------------------
# Answer accuracy
# ---------------------------------------------------------------------------

def cause_match(expected_subsystem: str, diagnosis: Diagnosis) -> bool:
    """True if the expected subsystem appears in the agent's top cause string.

    Converts subsystem_id (e.g. 'rf_match') to space-separated tokens and
    checks whether any token appears in the top cause (case-insensitive).
    """
    if not diagnosis.likely_causes:
        return False
    top_cause = diagnosis.likely_causes[0].cause.lower()
    tokens = expected_subsystem.lower().replace("_", " ").split()
    return any(token in top_cause for token in tokens)


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

class JudgeScore(BaseModel):
    correctness:    int = Field(ge=1, le=5, description="Does the diagnosis identify the right root cause? (1=wrong, 5=spot-on)")
    grounding:      int = Field(ge=1, le=5, description="Are claims tied to cited doc_ids? (1=hallucinated, 5=fully grounded)")
    actionability:  int = Field(ge=1, le=5, description="Are recommended checks specific and useful? (1=vague, 5=precise)")
    reasoning:      str = Field(description="One sentence justifying the scores.")


_JUDGE_PROMPT = """\
You are evaluating an AI maintenance assistant's diagnosis.

QUERY:
{query}

REFERENCE ANSWER (ground truth):
- Root cause subsystem: {expected_subsystem}
- Fix keywords: {fix_keywords}

AGENT DIAGNOSIS:
Summary: {summary}

Likely causes:
{causes}

Recommended checks:
{checks}

Citations: {citations}

Rate the diagnosis on three dimensions (1–5 each). Be strict and critical.\
"""


def llm_judge(item: dict, diagnosis: Diagnosis) -> JudgeScore:
    """Ask GPT-4o-mini to rate correctness, grounding, and actionability."""
    causes_str = "\n".join(
        f"  [{c.confidence:.0%}] {c.cause} (evidence: {c.evidence_doc_ids})"
        for c in diagnosis.likely_causes
    )
    checks_str = "\n".join(f"  - {r}" for r in diagnosis.recommended_checks)

    prompt = _JUDGE_PROMPT.format(
        query=item["query"],
        expected_subsystem=item["expected_subsystem"].replace("_", " "),
        fix_keywords=", ".join(item.get("expected_fix_keywords", [])),
        summary=diagnosis.summary,
        causes=causes_str,
        checks=checks_str,
        citations=", ".join(diagnosis.citations),
    )

    response = _client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=JudgeScore,
    )
    return response.choices[0].message.parsed


# ---------------------------------------------------------------------------
# Combined per-item scoring
# ---------------------------------------------------------------------------

def score_item(item: dict, diagnosis: Diagnosis, run_judge: bool = True) -> dict:
    """Compute all scores for one benchmark item.

    Args:
        item:       One row from benchmark.jsonl.
        diagnosis:  The agent's Diagnosis for this item.
        run_judge:  Set False to skip the LLM judge call (saves cost during dev).

    Returns:
        Dict with all numeric scores plus metadata.
    """
    rel = item["relevant_doc_ids"]
    cited = diagnosis.citations

    r = recall(rel, cited)
    rr = reciprocal_rank(rel, cited)
    cm = cause_match(item["expected_subsystem"], diagnosis)

    result = {
        "id":             item["id"],
        "signature_id":   item["signature_id"],
        "difficulty":     item["difficulty"],
        "recall":         round(r, 3),
        "reciprocal_rank": round(rr, 3),
        "cause_match":    cm,
        "judge_correctness":   None,
        "judge_grounding":     None,
        "judge_actionability": None,
        "judge_mean":          None,
        "judge_reasoning":     None,
        "diagnosis_summary":   diagnosis.summary,
        "diagnosis_confidence": diagnosis.confidence,
        "citations":           cited,
    }

    if run_judge:
        judge = llm_judge(item, diagnosis)
        result["judge_correctness"]   = judge.correctness
        result["judge_grounding"]     = judge.grounding
        result["judge_actionability"] = judge.actionability
        result["judge_mean"]          = round((judge.correctness + judge.grounding + judge.actionability) / 3, 2)
        result["judge_reasoning"]     = judge.reasoning

    return result


# ---------------------------------------------------------------------------
# Aggregate across items
# ---------------------------------------------------------------------------

def aggregate(scores: list[dict]) -> dict:
    """Compute mean metrics overall and by difficulty level."""

    def _mean(key: str, items: list[dict]) -> float | None:
        vals = [s[key] for s in items if s[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    def _bool_mean(key: str, items: list[dict]) -> float | None:
        vals = [1.0 if s[key] else 0.0 for s in items if s[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    metrics = ["recall", "reciprocal_rank", "judge_correctness", "judge_grounding",
               "judge_actionability", "judge_mean"]

    overall = {m: _mean(m, scores) for m in metrics}
    overall["cause_match"] = _bool_mean("cause_match", scores)
    overall["n"] = len(scores)

    by_difficulty = {}
    for diff in ("multi_doc", "single_doc", "tool_required"):
        subset = [s for s in scores if s["difficulty"] == diff]
        if subset:
            by_difficulty[diff] = {m: _mean(m, subset) for m in metrics}
            by_difficulty[diff]["cause_match"] = _bool_mean("cause_match", subset)
            by_difficulty[diff]["n"] = len(subset)

    return {"overall": overall, "by_difficulty": by_difficulty}
