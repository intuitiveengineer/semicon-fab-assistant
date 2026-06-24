"""Build the Qdrant collection from the corpus.

Reads corpus.jsonl → chunks → embeds (dense + sparse BM25) → upserts into Qdrant.
Safe to re-run: exits early if the collection already exists unless
--recreate is passed, which drops and rebuilds from scratch.

Usage:
    uv run python ingest/index.py             # build (skip if exists)
    uv run python ingest/index.py --recreate  # wipe and rebuild
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastembed.sparse.bm25 import Bm25
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from ingest.chunk import chunk_corpus
from rag.embeddings import DIMENSIONS, embed

COLLECTION = "semicon_maintenance"
QDRANT_URL = "http://localhost:6333"
UPSERT_BATCH = 100

# BM25 model — tokenizer-based, no neural weights to download.
_bm25 = Bm25("Qdrant/bm25")


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def create_collection(client: QdrantClient, recreate: bool = False) -> None:
    exists = client.collection_exists(COLLECTION)
    if exists and not recreate:
        print(f"Collection '{COLLECTION}' already exists — skipping creation.")
        print("Pass --recreate to wipe and rebuild.")
        return
    if exists and recreate:
        client.delete_collection(COLLECTION)
        print(f"Deleted existing collection '{COLLECTION}'.")

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={"dense": VectorParams(size=DIMENSIONS, distance=Distance.COSINE)},
        sparse_vectors_config={"bm25": SparseVectorParams(modifier=Modifier.IDF)},
    )
    print(f"Created collection '{COLLECTION}' (dense dim={DIMENSIONS} + BM25 sparse).")


def build_index(recreate: bool = False) -> None:
    client = get_client()
    create_collection(client, recreate=recreate)

    print("Loading and chunking corpus...")
    chunks = chunk_corpus()
    print(f"  {len(chunks)} chunks to index")

    texts = [c["text"] for c in chunks]

    print("Computing dense embeddings (OpenAI)...")
    dense_vectors = embed(texts)
    print(f"  {len(dense_vectors)} dense vectors")

    print("Computing sparse BM25 vectors...")
    sparse_vectors = list(_bm25.embed(texts))
    print(f"  {len(sparse_vectors)} sparse vectors")

    print("Upserting into Qdrant...")
    points = [
        PointStruct(
            id=i,
            vector={
                "dense": dense_vectors[i],
                "bm25": SparseVector(
                    indices=sparse_vectors[i].indices.tolist(),
                    values=sparse_vectors[i].values.tolist(),
                ),
            },
            payload=chunks[i],
        )
        for i in range(len(chunks))
    ]

    for start in range(0, len(points), UPSERT_BATCH):
        batch = points[start : start + UPSERT_BATCH]
        client.upsert(collection_name=COLLECTION, points=batch)
        print(f"  upserted {min(start + UPSERT_BATCH, len(points))}/{len(points)}")

    info = client.get_collection(COLLECTION)
    print(f"\nDone. Collection '{COLLECTION}' has {info.points_count} points.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--recreate", action="store_true", help="Drop and rebuild the collection from scratch")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_index(recreate=args.recreate)
