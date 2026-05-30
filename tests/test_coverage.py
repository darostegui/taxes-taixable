"""Tests for the knowledge-coverage dashboard (Elastic aggregations showcase).

Network-free: exercise the corpus backend, which mirrors the shape the Elastic
aggregation path returns. The live aggregation path is covered by the verify step
against the Dockerised cluster.
"""

from __future__ import annotations

from taixable_copilot.coverage import corpus_coverage


def test_corpus_coverage_reports_totals_and_buckets():
    out = corpus_coverage()()
    assert out["mode"] == "corpus"
    assert out["totals"]["tax-knowledge"] > 0
    assert out["totals"]["treaty-articles"] > 0
    assert out["totals"]["withholding-rates"] > 0
    # Jurisdiction buckets are sorted by descending doc_count and non-empty.
    jur = out["by_jurisdiction"]
    assert jur and all(b["key"] for b in jur)
    counts = [b["doc_count"] for b in jur]
    assert counts == sorted(counts, reverse=True)


def test_corpus_coverage_lists_known_jurisdictions():
    out = corpus_coverage()()
    keys = {b["key"] for b in out["by_jurisdiction"]}
    assert {"ES", "UK", "DE"} & keys


def test_corpus_coverage_lists_treaty_pairs():
    out = corpus_coverage()()
    assert any("-" in p for p in out["treaty_pairs"])
    assert out["rate_pairs"]
