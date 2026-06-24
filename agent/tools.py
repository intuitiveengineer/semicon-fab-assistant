"""Agent tools: OpenAI function schemas + Python implementations.

Each tool has two parts:
  1. A schema (dict) — what the LLM sees: name, description, argument types.
  2. An implementation (_fn) — what Python runs when the LLM calls it.

The LLM reads the descriptions to decide which tool to call and with what
arguments. Implementations return plain dicts; errors are returned as
{"error": "..."} so the LLM can recover rather than crash.

Public surface:
  TOOLS   — list of tool schemas to pass to the OpenAI API
  dispatch(name, args) — execute a tool by name with a dict of arguments
"""

import datetime
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.retriever import COLLECTION, QDRANT_URL, search

_TOOL_SUMMARIES_PATH = _ROOT / "data" / "structured" / "tool_summaries.json"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_tool_summaries() -> dict[str, dict]:
    """Return tool_summaries keyed by tool_id."""
    records = json.loads(_TOOL_SUMMARIES_PATH.read_text())
    return {r["tool_id"]: r for r in records}


def _qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=QDRANT_URL)

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _search_maintenance_docs(
    query: str,
    tool_id: str | None = None,
    subsystem: str | None = None,
    doc_type: str | None = None,
    k: int = 5,
) -> dict:
    hits = search(query, k=k, tool_id=tool_id, doc_type=doc_type, subsystem=subsystem)
    return {
        "results": [
            {
                "doc_id":   h["doc_id"],
                "doc_type": h["doc_type"],
                "tool_id":  h.get("tool_id"),
                "date":     h.get("date"),
                "snippet":  h["text"][:400],
            }
            for h in hits
        ]
    }


def _lookup_alarm_code(code: str) -> dict:
    from scripts.taxonomy import ALARMS
    alarm = ALARMS.get(code.upper())
    if alarm is None:
        return {"error": f"Alarm code '{code}' not found in catalog."}
    return {
        "code":           alarm.code,
        "description":    alarm.text,
        "subsystem":      alarm.subsystem,
        "typical_causes": list(alarm.typical_causes),
    }


def _get_tool_status(tool_id: str) -> dict:
    summaries = _load_tool_summaries()
    record = summaries.get(tool_id.upper())
    if record is None:
        return {"error": f"Tool '{tool_id}' not found."}
    return record


def _get_recent_alarms(tool_id: str, window_days: int = 30) -> dict:
    client = _qdrant()
    cutoff = (datetime.date.today() - datetime.timedelta(days=window_days)).isoformat()

    results, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="tool_id",  match=MatchValue(value=tool_id.upper())),
                FieldCondition(key="doc_type", match=MatchValue(value="alarm_log")),
            ]
        ),
        limit=50,
        with_payload=True,
        with_vectors=False,
    )

    # Filter by date in Python (ISO strings sort correctly with string comparison).
    recent = [
        {
            "doc_id":      r.payload["doc_id"],
            "date":        r.payload.get("date"),
            "alarm_codes": r.payload.get("alarm_codes", []),
            "snippet":     r.payload["text"][:300],
        }
        for r in results
        if (r.payload.get("date") or "") >= cutoff
    ]

    if not recent:
        return {"message": f"No alarm logs found for {tool_id} in the last {window_days} days."}
    return {"tool_id": tool_id, "window_days": window_days, "alarms": recent}


def _compute_mtbf(tool_id: str) -> dict:
    summaries = _load_tool_summaries()
    record = summaries.get(tool_id.upper())
    if record is None:
        return {"error": f"Tool '{tool_id}' not found."}

    last_pm = record.get("last_pm_date")
    days_since_pm = None
    if last_pm:
        delta = datetime.date.today() - datetime.date.fromisoformat(last_pm)
        days_since_pm = delta.days

    return {
        "tool_id":       tool_id,
        "mtbf_days":     record["mtbf_days"],
        "last_pm_date":  last_pm,
        "days_since_pm": days_since_pm,
        "overdue":       days_since_pm > record["mtbf_days"] if days_since_pm else None,
    }

# ---------------------------------------------------------------------------
# Tool schemas (what the LLM sees)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_maintenance_docs",
            "description": (
                "Search the maintenance document corpus for work orders, alarm logs, "
                "shift notes, SOP excerpts, and tool summaries relevant to a symptom "
                "or question. Use this first to gather evidence before forming a diagnosis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language symptom or question to search for.",
                    },
                    "tool_id": {
                        "type": "string",
                        "description": "Restrict results to a specific tool (e.g. 'ETCH02').",
                    },
                    "subsystem": {
                        "type": "string",
                        "description": "Restrict results to a specific subsystem (e.g. 'rf_source').",
                    },
                    "doc_type": {
                        "type": "string",
                        "enum": ["work_order", "alarm_log", "shift_note", "sop_excerpt", "tool_summary"],
                        "description": "Restrict results to one document type.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_alarm_code",
            "description": (
                "Look up a specific alarm code (e.g. 'ALM-005') in the alarm catalog. "
                "Returns the alarm description, subsystem, and typical causes. "
                "Use when an alarm code appears in retrieved documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The alarm code to look up (e.g. 'ALM-005').",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tool_status",
            "description": (
                "Get the current status summary for a tool: MTBF, last preventive "
                "maintenance date, open issues, and chamber list."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_id": {
                        "type": "string",
                        "description": "Tool identifier (e.g. 'ETCH02').",
                    },
                },
                "required": ["tool_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_alarms",
            "description": (
                "Retrieve recent alarm log entries for a tool within a date window. "
                "Use to check whether alarm activity preceded the reported symptom."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_id": {
                        "type": "string",
                        "description": "Tool identifier (e.g. 'ETCH02').",
                    },
                    "window_days": {
                        "type": "integer",
                        "description": "How many days back to look (default 30).",
                    },
                },
                "required": ["tool_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_mtbf",
            "description": (
                "Compute mean-time-between-failures stats for a tool and report "
                "whether it is overdue for preventive maintenance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_id": {
                        "type": "string",
                        "description": "Tool identifier (e.g. 'ETCH02').",
                    },
                },
                "required": ["tool_id"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Dispatch: name → implementation
# ---------------------------------------------------------------------------

_REGISTRY = {
    "search_maintenance_docs": _search_maintenance_docs,
    "lookup_alarm_code":       _lookup_alarm_code,
    "get_tool_status":         _get_tool_status,
    "get_recent_alarms":       _get_recent_alarms,
    "compute_mtbf":            _compute_mtbf,
}


def dispatch(name: str, args: dict) -> dict:
    """Execute a tool by name and return its result as a dict.

    Returns {"error": "..."} if the tool name is not recognised.
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'."}
    return fn(**args)
