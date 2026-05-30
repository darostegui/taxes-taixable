"""QA tests for the broad cited reference corpus (PwC + tax-authority pointers).

These entries are searchable, source-linked REFERENCE cards for ~147 jurisdictions
worldwide. They are deliberately NOT computable liability: the deterministic engine
stays anchored on UK/ES/DE. The tests below lock in the no-hallucination contract for
this tier — every entry must resolve to a real source URL, carry provenance, and must
NOT assert any legal rule (no day-count thresholds, rates or article numbers).
"""

import json
import re
from pathlib import Path

from taixable_copilot.citations import build_citation_index
from taixable_copilot.coverage import corpus_coverage
from taixable_copilot.search import all_citation_ids

_LEGISLATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "taixable_copilot"
    / "data"
    / "legislation.json"
)


def _reference_entries() -> list[dict]:
    data = json.loads(_LEGISLATION.read_text(encoding="utf-8"))
    entries = data["legislation"] if isinstance(data, dict) else data
    return [e for e in entries if e.get("content_type") == "curated_reference"]


def test_reference_corpus_is_present_and_large():
    entries = _reference_entries()
    # 143 PwC territories x 2 pages + Russia tax-authority pointer.
    assert len(entries) >= 280


def test_reference_ids_are_unique():
    ids = [e["citation_id"] for e in _reference_entries()]
    assert len(ids) == len(set(ids))


def test_reference_ids_resolve_in_citation_index():
    index = build_citation_index()
    missing = [e["citation_id"] for e in _reference_entries() if e["citation_id"] not in index]
    assert missing == [], f"unresolved reference ids: {missing[:10]}"


def test_reference_ids_are_known_citations():
    known = all_citation_ids()
    missing = [e["citation_id"] for e in _reference_entries() if e["citation_id"] not in known]
    assert missing == [], f"reference ids not in all_citation_ids: {missing[:10]}"


def test_reference_entries_carry_provenance():
    for entry in _reference_entries():
        assert entry.get("package_version") == "2025.1"
        assert entry.get("generator_version") == "reference-corpus/1.0"
        assert entry.get("retrieved_at"), entry["citation_id"]
        assert entry.get("source_content_hash"), entry["citation_id"]
        url = entry.get("source_url", "")
        assert url.startswith("http"), entry["citation_id"]


def test_reference_summaries_assert_no_legal_rules():
    """Reference-only: summaries must not smuggle in computable claims."""
    forbidden = re.compile(r"\b(183|90|180|days?\s+rule|article\s+\d+|\d+\s*%)\b", re.IGNORECASE)
    offenders = []
    for entry in _reference_entries():
        text = entry.get("summary", "")
        if forbidden.search(text):
            offenders.append((entry["citation_id"], text))
    assert offenders == [], f"reference summaries assert rules: {offenders[:5]}"


def test_reference_index_entries_are_tagged_curated_reference():
    index = build_citation_index()
    for entry in _reference_entries():
        cit = index[entry["citation_id"]]
        assert cit.category == "curated_reference", entry["citation_id"]


def test_engine_citations_keep_engine_category():
    index = build_citation_index()
    engine = index["ES#residency-183"]
    assert engine.category == "engine"


def test_coverage_reports_broad_jurisdiction_breadth():
    cov = corpus_coverage()()
    assert cov["totals"]["distinct_jurisdictions"] >= 140
    by_type = {b["key"]: b["doc_count"] for b in cov["by_content_type"]}
    assert by_type.get("curated_reference", 0) >= 280
