"""End-to-end: the API wired to the real corpus retrievers (no fakes), proving the
agent's tool layer runs fully locally, and that every citation it emits is known."""

from fastapi.testclient import TestClient

from taixable_copilot.api.app import create_app
from taixable_copilot.api.deps import Deps, _load_residency_rules
from taixable_copilot.db.repository import make_engine
from taixable_copilot.guardrails import validate_citations
from taixable_copilot.search import all_citation_ids, corpus_retrievers


def _client() -> TestClient:
    treaty, rate = corpus_retrievers()
    deps = Deps(
        residency_rules=_load_residency_rules(),
        treaty_retriever=treaty,
        rate_lookup=rate,
        engine=make_engine("sqlite:///:memory:"),
        known_citation_ids=all_citation_ids(),
    )
    return TestClient(create_app(deps))


def test_full_flow_assess_then_memo_with_valid_citations():
    profile = {
        "residence_country": "DE",
        "days_present": {"DE": 250, "ES": 60},
        "income": [
            {"type": "rental", "source_country": "ES", "amount": 18000},
            {"type": "dividend", "source_country": "ES", "amount": 4000},
        ],
        "customer_token": "CUST-E2E001",
    }
    client = _client()
    a = client.post("/tools/assess_obligations", json={"profile": profile, "tax_year": 2025})
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["primary_residence"] == "DE"
    assert len(body["obligations"]) == 2

    ok, invalid = validate_citations(body["citations"], all_citation_ids())
    assert ok, f"unknown citations: {invalid}"

    # Every emitted citation resolves to a real, clickable source URL, in the same
    # order as the citation ids.
    details = body["citation_details"]
    assert [d["id"] for d in details] == body["citations"]
    assert details and all(d["url"] and d["url"].startswith("http") for d in details)

    m = client.post(
        "/tools/generate_memo",
        json={"profile": profile, "tax_year": 2025, "customer_token": "CUST-E2E001"},
    )
    assert m.status_code == 200, m.text
    memo = m.json()["memo_markdown"]
    assert "DE-ES#art6" in memo
    # memo Sources are rendered as markdown links to the primary source
    assert "](http" in memo


def test_guardrail_rejects_hallucinated_citation():
    """A retriever that emits a citation id outside the known set is rejected (422)."""

    def bad_treaty(country_pair, income_type):
        return {"article_no": "6", "topic": "x", "text": "y", "citation_id": "FAKE#999"}

    def ok_rate(country_pair, income_type):
        return {"rate": 0.1, "relief": "credit", "citation_id": "ES-UK#art6-rate"}

    deps = Deps(
        residency_rules=_load_residency_rules(),
        treaty_retriever=bad_treaty,
        rate_lookup=ok_rate,
        engine=make_engine("sqlite:///:memory:"),
        known_citation_ids=all_citation_ids(),
    )
    client = TestClient(create_app(deps))
    r = client.post(
        "/tools/assess_obligations",
        json={
            "profile": {
                "residence_country": "UK",
                "days_present": {"UK": 320, "ES": 40},
                "income": [{"type": "rental", "source_country": "ES", "amount": 12000}],
            },
            "tax_year": 2025,
        },
    )
    assert r.status_code == 422
    assert "FAKE#999" in r.text
