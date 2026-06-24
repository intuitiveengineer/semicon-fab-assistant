"""Embedding interface for the retrieval layer.

Wraps OpenAI's text-embedding-3-small. To swap in a local model later,
change MODEL and update _embed_batch to call a different backend —
the rest of the codebase only sees embed().
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402  triggers load_dotenv + key validation

from openai import OpenAI

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 100

_client = OpenAI()


def embed(texts: list[str]) -> list[list[float]]:
    """Return one embedding vector per input text.

    Batches requests so large lists don't exceed API limits.
    Order of results matches order of inputs.
    """
    if not texts:
        return []

    results: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = _client.embeddings.create(model=MODEL, input=batch)
        results.extend(item.embedding for item in response.data)
    return results
