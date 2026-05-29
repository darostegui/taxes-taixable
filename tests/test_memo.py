from taixable_copilot.citations import build_citation_index
from taixable_copilot.memo import render_memo


def test_memo_contains_citations_and_sections(sample_assessment):
    md = render_memo(sample_assessment, customer_token="CUST-001")
    assert "## Obligations" in md
    assert "## Filing deadlines" in md
    assert "ES-UK#art6" in md
    assert "CUST-001" in md
    # tokenized memo must not leak the word 'name' fields etc. (no raw PII present here)
    assert "rental" in md.lower()


def test_memo_sources_render_clickable_urls_with_index(sample_assessment):
    md = render_memo(
        sample_assessment, customer_token="CUST-001", citation_index=build_citation_index()
    )
    # Sources section links each cited id to its real primary source.
    assert "## Sources" in md
    assert "](https://" in md
    assert "ES-UK#art6" in md
