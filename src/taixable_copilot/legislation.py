"""Supporting-legislation lookup: curated legal passages keyed by citation id.

This is the "load the laws into Elasticsearch" capability, implemented in a way
that **cannot** become a hallucination channel. The deterministic engine already
emits the citation ids that justify every figure it produces; this module maps
those exact ids to curated, source-linked legal passages so the UI can show the
*supporting legal context* for a conclusion the engine already reached.

The agent never free-text-searches this corpus and never derives numbers from it
— passages are selected deterministically by id, validated against the curated
allowlist, and rendered as labelled evidence cards outside the model's reply.

Two interchangeable backends, mirroring :mod:`search`:
  * **corpus** (default) — serves the curated JSON in ``data/`` in-process, so
    the whole agent runs offline with no cloud dependency.
  * **elastic** — fetches the same documents from a ``tax-legislation`` index
    when ``ELASTIC_URL`` is set. Elastic is treated as a retrieval cache, never
    as the source of truth: only ids present in the local curated allowlist (and
    matching its package version) are ever returned.

Passages are summaries, not verbatim statute, and are tagged
``content_type="curated_summary"`` so the UI can label them honestly and point
to the authoritative ``source_url``.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Callable

DATA_DIR = Path(__file__).resolve().parent / "data"
LEGISLATION_INDEX = "tax-legislation"

# A lookup takes the citation ids the engine produced and returns the curated
# passages for the ones we have, preserving input order and de-duplicating.
LegislationLookup = Callable[[list[str]], list[dict]]

_FIELDS = (
    "citation_id",
    "jurisdiction",
    "title",
    "article",
    "summary",
    "content_type",
    "effective_date",
    "source_url",
    "package_version",
)


@lru_cache(maxsize=1)
def _corpus_by_id() -> dict[str, dict]:
    raw = json.loads((DATA_DIR / "legislation.json").read_text(encoding="utf-8"))
    return {e["citation_id"]: e for e in raw["legislation"]}


@lru_cache(maxsize=1)
def _package_version() -> str:
    raw = json.loads((DATA_DIR / "legislation.json").read_text(encoding="utf-8"))
    return str(raw.get("package_version", ""))


def known_legislation_ids() -> set[str]:
    """The curated allowlist of legislation passage ids (the guardrail set)."""
    return set(_corpus_by_id().keys())


def _ordered_unique(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid in ids:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def corpus_legislation_lookup() -> LegislationLookup:
    by_id = _corpus_by_id()

    def lookup(citation_ids: list[str]) -> list[dict]:
        return [by_id[cid] for cid in _ordered_unique(citation_ids) if cid in by_id]

    return lookup


def elastic_legislation_lookup(url: str, api_key: str | None) -> LegislationLookup:
    from elasticsearch import Elasticsearch

    es = Elasticsearch(url, api_key=api_key) if api_key else Elasticsearch(url)
    allow = known_legislation_ids()
    version = _package_version()

    def lookup(citation_ids: list[str]) -> list[dict]:
        wanted = [cid for cid in _ordered_unique(citation_ids) if cid in allow]
        if not wanted:
            return []
        resp = es.mget(index=LEGISLATION_INDEX, ids=wanted)
        found: dict[str, dict] = {}
        for doc in resp.get("docs", []):
            if not doc.get("found"):
                continue
            src = doc["_source"]
            cid = src.get("citation_id") or doc.get("_id")
            # Fail closed: never surface a passage that is not on the local
            # allowlist or whose package version drifts from the curated corpus.
            if cid in allow and str(src.get("package_version", "")) == version:
                found[cid] = {k: src.get(k) for k in _FIELDS}
        return [found[cid] for cid in wanted if cid in found]

    return lookup


def build_legislation_lookup() -> LegislationLookup:
    """Pick the Elastic backend when ``ELASTIC_URL`` is set, else the corpus."""
    url = os.environ.get("ELASTIC_URL")
    if url:
        return elastic_legislation_lookup(url, os.environ.get("ELASTIC_API_KEY"))
    return corpus_legislation_lookup()
