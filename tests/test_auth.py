"""Tests for the login guardrail and the topic guardrail."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from taixable_copilot.api import auth
from taixable_copilot.api.app import create_app
from taixable_copilot.api.deps import DEFAULT_RESIDENCY_RULES, Deps
from taixable_copilot.db.repository import make_engine
from taixable_copilot.topic_guard import is_on_topic


def _deps() -> Deps:
    return Deps(
        residency_rules=DEFAULT_RESIDENCY_RULES,
        treaty_retriever=lambda *a, **k: None,
        rate_lookup=lambda *a, **k: None,
        engine=make_engine("sqlite:///:memory:"),
    )


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A client with auth ENFORCED (overrides the global test bypass)."""
    monkeypatch.setenv("TAIXABLE_ENV", "production")
    monkeypatch.delenv("TAIXABLE_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("TAIXABLE_AUTH_SECRET", "unit-test-secret")
    monkeypatch.setenv("TAIXABLE_ADMIN_PASSWORD", "s3cret-pw")
    auth._failures.clear()
    return TestClient(create_app(_deps()))


# --- auth module unit tests ------------------------------------------------
def test_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_AUTH_SECRET", "abc")
    monkeypatch.setenv("TAIXABLE_ADMIN_PASSWORD", "pw")
    token, ttl = auth.issue_token("admin")
    assert ttl > 0
    assert auth.verify_token(token) == "admin"


def test_tampered_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_AUTH_SECRET", "abc")
    token, _ = auth.issue_token("admin")
    assert auth.verify_token(token + "x") is None
    assert auth.verify_token("garbage") is None
    assert auth.verify_token(None) is None


def test_token_rejected_under_different_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_AUTH_SECRET", "secret-one")
    token, _ = auth.issue_token("admin")
    monkeypatch.setenv("TAIXABLE_AUTH_SECRET", "secret-two")
    assert auth.verify_token(token) is None


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_AUTH_SECRET", "abc")
    token, _ = auth.issue_token("admin", ttl_seconds=-1)
    assert auth.verify_token(token) is None


def test_verify_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("TAIXABLE_USERS", "alice:wonder")
    assert auth.verify_credentials("admin", "pw")
    assert auth.verify_credentials("alice", "wonder")
    assert not auth.verify_credentials("admin", "wrong")
    assert not auth.verify_credentials("ghost", "x")


def test_auth_disabled_only_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_ENV", "production")
    monkeypatch.setenv("TAIXABLE_AUTH_DISABLED", "1")
    assert auth.auth_disabled() is False
    monkeypatch.setenv("TAIXABLE_ENV", "dev")
    assert auth.auth_disabled() is True


# --- endpoint gating -------------------------------------------------------
def test_protected_endpoint_requires_token(auth_client: TestClient) -> None:
    r = auth_client.post("/tools/assess_obligations", json={"profile": {
        "residence_country": "UK", "days_present": {"UK": 300, "ES": 65},
        "income": [], "customer_token": "CUST-1"}, "tax_year": 2025})
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_open_endpoints_need_no_token(auth_client: TestClient) -> None:
    assert auth_client.get("/healthz").status_code == 200
    assert auth_client.get("/").status_code == 200


def test_login_and_use_token(auth_client: TestClient) -> None:
    bad = auth_client.post("/login", json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401

    ok = auth_client.post("/login", json={"username": "admin", "password": "s3cret-pw"})
    assert ok.status_code == 200
    token = ok.json()["token"]

    r = auth_client.post(
        "/tools/assess_obligations",
        json={"profile": {
            "residence_country": "UK", "days_present": {"UK": 300, "ES": 65},
            "income": [], "customer_token": "CUST-1"}, "tax_year": 2025},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_login_throttle_locks_out(auth_client: TestClient) -> None:
    for _ in range(5):
        auth_client.post("/login", json={"username": "admin", "password": "wrong"})
    r = auth_client.post("/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 429


# --- topic guardrail -------------------------------------------------------
def test_on_topic_allows_tax_questions() -> None:
    assert is_on_topic("Where do I pay tax if I split the year between Spain and the UK?")
    assert is_on_topic("What is the Beckham regime?")
    assert is_on_topic("I work 190 days in Mallorca, rest in London")


def test_on_topic_allows_short_followups() -> None:
    assert is_on_topic("what about Spain?")
    assert is_on_topic("hi")
    assert is_on_topic("and Germany?")


def test_off_topic_blocks_unrelated_requests() -> None:
    assert not is_on_topic("Write me a Python script to sort a list")
    assert not is_on_topic("Write a poem about the ocean")
    assert not is_on_topic("Give me a recipe for chocolate cake")
    assert not is_on_topic("Debug this null pointer exception in my Java code")


def test_off_topic_does_not_block_tax_code_phrases() -> None:
    assert is_on_topic("What does the Spanish tax code say about residency?")
    assert is_on_topic("How do I write my tax return for rental income?")


def test_chat_blocks_off_topic_without_calling_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import taixable_copilot.chat as chat_mod

    def _boom():  # pragma: no cover - must never be called
        raise AssertionError("model client should not be created for off-topic input")

    monkeypatch.setattr(chat_mod, "_make_client", _boom)
    result = chat_mod.chat(deps=_deps(), history=[], message="Write me a Python script")
    assert result["blocked"] is True
    assert result["available"] is True
    assert result["used_tool"] is False
