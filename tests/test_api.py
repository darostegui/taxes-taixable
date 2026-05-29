from fastapi.testclient import TestClient

from taixable_copilot.api.app import create_app
from taixable_copilot.api.deps import DEFAULT_RESIDENCY_RULES, Deps
from taixable_copilot.db.repository import make_engine


def _fake_treaty(country_pair, income_type):
    return {
        "article_no": "6",
        "topic": "Income from immovable property",
        "text": "Income may be taxed in the State where the property is situated.",
        "citation_id": f"{country_pair}#art6",
    }


def _fake_rate(country_pair, income_type):
    return {"rate": 0.19, "relief": "foreign tax credit", "citation_id": f"{country_pair}#rate"}


def _deps():
    return Deps(
        residency_rules=DEFAULT_RESIDENCY_RULES,
        treaty_retriever=_fake_treaty,
        rate_lookup=_fake_rate,
        engine=make_engine("sqlite:///:memory:"),
    )


def _client():
    return TestClient(create_app(_deps()))


_PROFILE = {
    "residence_country": "UK",
    "days_present": {"UK": 300, "ES": 65},
    "income": [{"type": "rental", "source_country": "ES", "amount": 12000}],
    "customer_token": "CUST-TEST01",
}


def test_assess_obligations_returns_cited_assessment():
    r = _client().post(
        "/tools/assess_obligations", json={"profile": _PROFILE, "tax_year": 2025}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["primary_residence"] == "UK"
    assert len(body["obligations"]) == 1
    ob = body["obligations"][0]
    assert ob["source_country"] == "ES"
    assert ob["treaty_article"] == "6"
    assert ob["citation_ids"]
    assert any(d["jurisdiction"] == "UK" for d in body["deadlines"])
    assert body["citations"] == sorted(body["citations"])
    # Fake deps don't wire a legislation lookup, so the field is present but empty.
    assert body["legislation"] == []


def test_assess_obligations_surfaces_supporting_legislation():
    from taixable_copilot.api.app import create_app
    from taixable_copilot.api.deps import build_default_deps

    client = TestClient(create_app(build_default_deps()))
    r = client.post(
        "/tools/assess_obligations", json={"profile": _PROFILE, "tax_year": 2025}
    )
    assert r.status_code == 200, r.text
    leg = r.json()["legislation"]
    assert leg, "expected supporting legislation passages"
    ids = {p["citation_id"] for p in leg}
    # The UK residency conclusion must be backed by a curated passage.
    assert "UK#srt-183" in ids
    for p in leg:
        assert p["content_type"] == "curated_summary"
        assert p["source_url"].startswith("http")


def test_generate_memo_includes_token_and_sources():
    r = _client().post(
        "/tools/generate_memo",
        json={"profile": _PROFILE, "tax_year": 2025, "customer_token": "CUST-TEST01"},
    )
    assert r.status_code == 200, r.text
    memo = r.json()["memo_markdown"]
    assert "CUST-TEST01" in memo
    assert "## Sources" in memo


def test_persist_case_rejected_without_approval():
    r = _client().post(
        "/tools/persist_case",
        json={
            "approved": False,
            "approved_by": "advisor@firm.example",
            "customer_token": "CUST-TEST01",
            "residence_country": "UK",
            "tax_year": 2025,
            "primary_residence": "UK",
        },
    )
    assert r.status_code == 409


def test_persist_case_succeeds_when_approved():
    client = _client()
    r = client.post(
        "/tools/persist_case",
        json={
            "approved": True,
            "approved_by": "advisor@firm.example",
            "customer_token": "CUST-TEST01",
            "residence_country": "UK",
            "display_label": "UK contractor",
            "tax_year": 2025,
            "primary_residence": "UK",
            "summary": "UK resident with ES rental income",
            "deadlines": [
                {
                    "jurisdiction": "UK",
                    "description": "UK annual tax return for 2025",
                    "due_date": "2026-01-31",
                    "citation_id": "UK#sa-deadline",
                }
            ],
            "citation_ids": ["ES-UK#art6", "ES-UK#rate"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["case_id"] >= 1


def test_healthz():
    assert _client().get("/healthz").json() == {"status": "ok"}


def test_index_serves_html():
    r = _client().get("/")
    assert r.status_code == 200
    assert "Virtual Tax Advisor" in r.text
