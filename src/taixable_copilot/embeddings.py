"""Vertex AI text embeddings — the semantic-search vectors for Elasticsearch.

Showcases a newer Google AI capability (``gemini-embedding-001``, 3072-dim) used
to power hybrid (keyword + vector) retrieval in Elasticsearch. Kept deliberately
thin and **non-fatal**: if the SDK or credentials are unavailable, the helpers
return ``None`` so callers fall back to lexical search and the agent still runs
fully offline.

The same model embeds both the corpus (at ingest time) and the live query, so
cosine similarity is meaningful. Query embeddings are cached per-process.
"""

from __future__ import annotations

import os
from functools import lru_cache

from taixable_copilot.llm import _make_client

EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
# gemini-embedding-001 emits 3072-dim vectors; keep this in lockstep with the
# Elasticsearch dense_vector mapping in scripts/ingest_elastic.py.
EMBED_DIMS = int(os.getenv("EMBED_DIMS", "3072"))


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of texts. Returns one vector per input, or ``None`` offline."""
    if not texts:
        return []
    client = _make_client()
    if client is None:
        return None
    try:
        resp = client.models.embed_content(model=EMBED_MODEL, contents=texts)
    except Exception:  # noqa: BLE001 - any SDK/auth/quota error → graceful fallback
        return None
    embeddings = getattr(resp, "embeddings", None)
    if not embeddings:
        return None
    return [list(e.values) for e in embeddings]


@lru_cache(maxsize=256)
def embed_query(text: str) -> tuple[float, ...] | None:
    """Embed a single query string (cached). Returns ``None`` when offline."""
    vecs = embed_texts([text])
    if not vecs:
        return None
    return tuple(vecs[0])
