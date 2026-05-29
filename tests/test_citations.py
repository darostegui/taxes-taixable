from taixable_copilot.citations import Citation, build_citation_index, resolve_citations
from taixable_copilot.search import all_citation_ids


def test_index_resolves_every_kind_of_citation_to_a_url():
    idx = build_citation_index()
    # treaty article, withholding rate, residency rule, filing deadline
    for cid in [
        "ES-UK#art6",
        "ES-UK#art6-rate",
        "ES#residency-183",
        "UK#srt-183",
        "UK#sa-deadline",
        "DE#est-deadline",
    ]:
        assert cid in idx, cid
        cit = idx[cid]
        assert cit.url and cit.url.startswith("http"), cid
        assert cit.label and cit.label != cid, cid


def test_index_keys_match_guardrail_known_ids():
    # The guardrail's known-id set and the id->URL index must never drift apart.
    assert set(build_citation_index().keys()) == all_citation_ids()


def test_resolve_preserves_order_and_falls_back_for_unknown_ids():
    out = resolve_citations(["ES-UK#art6", "TOTALLY#unknown"])
    assert [c.id for c in out] == ["ES-UK#art6", "TOTALLY#unknown"]
    assert out[0].url is not None
    # unknown id is surfaced (never dropped) with an id-only fallback
    assert out[1] == Citation("TOTALLY#unknown", "TOTALLY#unknown", None)
