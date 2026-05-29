from taixable_copilot.guardrails import validate_citations


def test_rejects_unknown_citation():
    known = {"ES-UK#art6", "UK#sa-deadline"}
    ok, bad = validate_citations(["ES-UK#art6", "ES-UK#art99"], known_ids=known)
    assert ok is False
    assert bad == ["ES-UK#art99"]


def test_all_valid_citations_pass():
    known = {"ES-UK#art6", "ES-UK#art6-rate"}
    ok, bad = validate_citations(["ES-UK#art6", "ES-UK#art6-rate"], known_ids=known)
    assert ok is True
    assert bad == []
