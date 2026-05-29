from taixable_copilot.models import IncomeType
from taixable_copilot.search import all_citation_ids, corpus_retrievers


def test_corpus_treaty_and_rate_lookup():
    treaty, rate = corpus_retrievers()
    art = treaty("ES-UK", IncomeType.RENTAL)
    assert art["article_no"] == "6"
    assert art["citation_id"] == "ES-UK#art6"
    r = rate("ES-UK", IncomeType.RENTAL)
    assert r is not None
    assert 0.0 <= r["rate"] <= 1.0
    assert r["citation_id"] == "ES-UK#art6-rate"


def test_corpus_missing_returns_empty_or_none():
    treaty, rate = corpus_retrievers()
    assert treaty("ES-UK", IncomeType.CAPITAL_GAIN) == {}
    assert rate("ES-UK", IncomeType.CAPITAL_GAIN) is None


def test_all_citation_ids_covers_treaty_rate_and_deadlines():
    ids = all_citation_ids()
    assert "ES-UK#art6" in ids
    assert "ES-UK#art6-rate" in ids
    assert "UK#sa-deadline" in ids
    assert "UK#srt-183" in ids
