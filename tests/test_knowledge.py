"""Tests for the Elasticsearch tax-knowledge search layer.

Network-free: they exercise the corpus builder and the offline lexical search
(the fail-safe fallback). The Elastic hybrid path is covered by the live verify
step against the Dockerised cluster, not the unit suite.
"""

from __future__ import annotations

from taixable_copilot.knowledge import (
    build_knowledge_corpus,
    corpus_knowledge_search,
    known_knowledge_ids,
)
from taixable_copilot.search import all_citation_ids


def test_corpus_is_unique_by_citation_id():
    corpus = build_knowledge_corpus()
    ids = [d["citation_id"] for d in corpus]
    assert len(ids) == len(set(ids)), "knowledge corpus must not contain duplicate ids"
    # Every passage carries the display + grounding fields the UI/agent need.
    for d in corpus:
        assert d["citation_id"] and d["title"] and d["text"]
        assert d["source_url"].startswith("http")


def test_every_knowledge_id_is_a_known_engine_citation():
    # The Elastic path fails closed against this allowlist; it must be a subset of
    # the engine's known citation ids so nothing un-citable can be surfaced.
    assert known_knowledge_ids() <= all_citation_ids()


def test_lexical_search_finds_spanish_residency_rule():
    search = corpus_knowledge_search()
    out = search("what is the 183 day residency rule in Spain", jurisdiction="ES")
    ids = [r["citation_id"] for r in out["results"]]
    assert "ES#residency-183" in ids
    assert out["meta"]["mode"] == "corpus"
    assert out["meta"]["retrieval"] == "lexical"


def test_lexical_search_respects_jurisdiction_filter():
    search = corpus_knowledge_search()
    out = search("tax rules", jurisdiction="DE")
    for r in out["results"]:
        juris = (r["jurisdiction"] + " " + r["country_pair"]).upper()
        assert "DE" in juris


def test_lexical_search_returns_deadline_for_spain():
    search = corpus_knowledge_search()
    out = search("when is the Spanish income tax return deadline", jurisdiction="ES")
    assert out["results"]
    assert out["results"][0]["citation_id"] == "ES#renta-deadline"


def test_lexical_search_caps_results_at_k():
    search = corpus_knowledge_search()
    out = search("tax treaty income", k=3)
    assert len(out["results"]) <= 3


def test_lexical_search_returns_only_allowlisted_ids():
    search = corpus_knowledge_search()
    allow = known_knowledge_ids()
    out = search("double taxation relief pension dividends rental", k=10)
    for r in out["results"]:
        assert r["citation_id"] in allow
