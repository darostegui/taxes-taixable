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

    m = client.post(
        "/tools/generate_memo",
        json={"profile": profile, "tax_year": 2025, "customer_token": "CUST-E2E001"},
    )
    assert m.status_code == 200, m.text
    assert "DE-ES#art6" in m.json()["memo_markdown"]
