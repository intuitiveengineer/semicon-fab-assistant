"""Hybrid retriever: dense vector + BM25 sparse, fused with Reciprocal Rank Fusion.

Public API:
    search(query, k, tool_id, doc_type, subsystem) -> list[dict]

Each returned dict contains the chunk's text and all metadata fields.
The agent cites results by their doc_id.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastembed.sparse.bm25 import Bm25
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    Prefetch,
    SparseVector,
)

from rag.embeddings import embed

COLLECTION = "semicon_maintenance"
QDRANT_URL = "http://localhost:6333"

_client = QdrantClient(url=QDRANT_URL)
_bm25 = Bm25("Qdrant/bm25")


def _build_filter(
    tool_id: str | None,
    doc_type: str | None,
    subsystem: str | None,
) -> Filter | None:
    """Build a Qdrant payload filter from optional agent-supplied constraints."""
    conditions = []
    if tool_id:
        conditions.append(FieldCondition(key="tool_id", match=MatchValue(value=tool_id)))
    if doc_type:
        conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
    if subsystem:
        conditions.append(FieldCondition(key="subsystem", match=MatchValue(value=subsystem)))
    return Filter(must=conditions) if conditions else None


def search(
    query: str,
    k: int = 5,
    tool_id: str | None = None,
    doc_type: str | None = None,
    subsystem: str | None = None,
) -> list[dict]:
    """Hybrid search over the maintenance corpus.

    Runs dense (semantic) and sparse (BM25 keyword) searches in parallel,
    fuses their ranked results with Reciprocal Rank Fusion, and returns the
    top-k chunks with their full metadata payloads.

    Args:
        query:    Natural-language symptom or question.
        k:        Number of results to return.
        tool_id:  If set, restrict results to this tool (e.g. "ETCH02").
        doc_type: If set, restrict to one doc type (e.g. "work_order").
        subsystem: If set, restrict to one subsystem (e.g. "rf_source").

    Returns:
        List of dicts, each containing chunk text and metadata (doc_id, tool_id, etc.).
    """
    payload_filter = _build_filter(tool_id, doc_type, subsystem)

    dense_vec = embed([query])[0]
    sparse_result = next(_bm25.embed([query]))
    sparse_vec = SparseVector(
        indices=sparse_result.indices.tolist(),
        values=sparse_result.values.tolist(),
    )

    hits = _client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            Prefetch(query=dense_vec, using="dense", limit=k * 3, filter=payload_filter),
            Prefetch(query=sparse_vec, using="bm25", limit=k * 3, filter=payload_filter),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=k,
        with_payload=True,
    )

    return [hit.payload for hit in hits.points]
