"""Structure-aware document chunker.

Reads corpus.jsonl and produces chunks ready for embedding and indexing.

Strategy:
  - alarm_log, shift_note, tool_summary, work_order: keep whole (all under ~1500 chars)
  - sop_excerpt: split by section heading (PURPOSE / SCOPE / PROCEDURE / ESCALATION /
    CHECKLIST / NOTES) so each retrievable unit covers one focused topic

Every chunk carries the parent doc_id so the agent can cite the source document.
"""

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

CORPUS_FILE = _ROOT / "data" / "corpus" / "corpus.jsonl"

# Headings the LLM uses in SOP excerpts (bold markdown or plain, colon-terminated).
_SOP_HEADING = re.compile(
    r"(?:^|\n)\s*\*{0,2}(PURPOSE|SCOPE|PROCEDURE|ESCALATION|CHECKLIST|NOTES)\*{0,2}\s*:",
    re.IGNORECASE,
)


def _base_fields(doc: dict) -> dict:
    """Pull the metadata fields every chunk needs for Qdrant payload + citations."""
    return {
        "doc_id":      doc["doc_id"],
        "doc_type":    doc["doc_type"],
        "tool_id":     doc.get("tool_id"),
        "chamber":     doc.get("chamber"),
        "alarm_codes": doc.get("alarm_codes", []),
        "subsystem":   doc.get("subsystem"),
        "date":        doc.get("date"),
    }


def _whole(doc: dict) -> list[dict]:
    """Return the document as a single chunk."""
    return [{
        **_base_fields(doc),
        "chunk_id": f"{doc['doc_id']}-0",
        "text": doc["text"],
    }]


def _split_sop(doc: dict) -> list[dict]:
    """Split an SOP excerpt into one chunk per section heading.

    Falls back to a single chunk if no headings are found.
    """
    text = doc["text"]
    matches = list(_SOP_HEADING.finditer(text))

    if not matches:
        return _whole(doc)

    chunks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        if len(section_text) < 30:  # skip near-empty sections
            continue
        chunks.append({
            **_base_fields(doc),
            "chunk_id": f"{doc['doc_id']}-{i}",
            "text": section_text,
        })

    return chunks if chunks else _whole(doc)


def chunk_corpus(corpus_path: Path = CORPUS_FILE) -> list[dict]:
    """Read corpus.jsonl and return all chunks."""
    chunks = []
    with corpus_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            if doc["doc_type"] == "sop_excerpt":
                chunks.extend(_split_sop(doc))
            else:
                chunks.extend(_whole(doc))
    return chunks


if __name__ == "__main__":
    chunks = chunk_corpus()
    by_type: dict[str, int] = {}
    for c in chunks:
        by_type[c["doc_type"]] = by_type.get(c["doc_type"], 0) + 1
    print(f"Total chunks: {len(chunks)}")
    for dt, count in sorted(by_type.items()):
        print(f"  {dt}: {count}")
