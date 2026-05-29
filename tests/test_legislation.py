"""Tests for the supporting-legislation lookup layer.

The lookup must be deterministic and fail closed: it only ever returns curated
passages for the exact citation ids the engine produced, preserving order, and
silently skips anything it does not have. Every curated passage id must also be
a valid engine citation id so cards never reference an unknown source.
"""

from taixable_copilot.citations import build_citation_index
from taixable_copilot.legislation import (
    build_legislation_lookup,
    corpus_legislation_lookup,
    known_legislation_ids,
)


def test_corpus_lookup_returns_passages_for_known_ids():
    lookup = corpus_legislation_lookup()
    out = lookup(["ES#residency-183", "DE-ES#art6"])
    assert [p["citation_id"] for p in out] == ["ES#residency-183", "DE-ES#art6"]
    first = out[0]
    assert first["content_type"] == "curated_summary"
    assert first["source_url"].startswith("http")
    assert first["summary"]


def test_corpus_lookup_preserves_order_and_dedupes():
    lookup = corpus_legislation_lookup()
    out = lookup(["DE-ES#art6", "ES#residency-183", "DE-ES#art6"])
    assert [p["citation_id"] for p in out] == ["DE-ES#art6", "ES#residency-183"]


def test_corpus_lookup_skips_unknown_ids():
    lookup = corpus_legislation_lookup()
    out = lookup(["ES#residency-183", "TOTALLY#unknown", "ES-UK#art6-rate"])
    # The unknown id and the -rate id (not in the curated corpus) are dropped;
    # only the curated residency passage remains.
    assert [p["citation_id"] for p in out] == ["ES#residency-183"]


def test_lookup_empty_for_no_ids():
    assert corpus_legislation_lookup()([]) == []


def test_default_lookup_is_corpus_when_no_elastic(monkeypatch):
    monkeypatch.delenv("ELASTIC_URL", raising=False)
    lookup = build_legislation_lookup()
    out = lookup(["UK#srt-183"])
    assert out and out[0]["citation_id"] == "UK#srt-183"


def test_every_legislation_id_is_a_valid_engine_citation():
    index = build_citation_index()
    unknown = sorted(known_legislation_ids() - set(index.keys()))
    assert unknown == [], f"legislation ids not in citation index: {unknown}"
