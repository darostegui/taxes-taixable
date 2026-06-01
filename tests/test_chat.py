"""Tests for the conversational tax-advisor agent.

Network-free: they exercise the engine-backed tool (which runs the real
deterministic engine) and the graceful-fallback contract when Gemini is
unavailable.
"""

from __future__ import annotations

import json

import taixable_copilot.chat as chatmod
from taixable_copilot.api.deps import build_default_deps
from taixable_copilot.chat import (
    _build_profile,
    _make_assess_tool,
    _make_search_tool,
    chat,
)
from taixable_copilot.models import Country


def test_build_profile_infers_residence_from_max_days():
    profile = _build_profile({"UK": 180, "ES": 185}, [], residence_country="")
    assert profile.residence_country == Country.ES  # 185 > 180


def test_build_profile_respects_explicit_residence():
    profile = _build_profile({"UK": 180, "ES": 185}, [], residence_country="uk")
    assert profile.residence_country == Country.UK


def test_assess_tool_runs_engine_and_returns_cited_sources():
    deps = build_default_deps()
    tool, captured = _make_assess_tool(deps)
    out = tool(
        days_present_json=json.dumps({"UK": 180, "ES": 185}),
        income_json=json.dumps(
            [{"type": "rental", "source_country": "ES", "amount": 12000}]
        ),
    )
    assert out["primary_residence"] == "ES"
    assert out["sources"], "engine must return at least one cited source"
    assert all(s["id"] for s in out["sources"])
    # At least one source carries a real URL.
    assert any((s.get("url") or "").startswith("http") for s in out["sources"])
    assert captured["assessment"] == out


def test_assess_tool_returns_error_for_unknown_country_code():
    deps = build_default_deps()
    tool, _ = _make_assess_tool(deps)
    out = tool(days_present_json=json.dumps({"ZZ": 365}), income_json="[]")
    assert "error" in out
    assert out["computable_amount_countries"] == ["UK", "ES", "DE", "IE", "PT", "AD"]


def test_assess_tool_models_residency_without_bands_honestly():
    # France is in the day-count residency tier but has no computable bands.
    # The engine must determine residence (no crash, no error) yet refuse to
    # invent an amount for it.
    deps = build_default_deps()
    tool, _ = _make_assess_tool(deps)
    out = tool(days_present_json=json.dumps({"FR": 365}), income_json="[]")
    assert "error" not in out
    assert out["primary_residence"] == "FR"
    assert out["residency_modelled"] is True
    # No FR income-tax bands exist, so no residence amount is fabricated.
    assert not any(
        e["role"] == "residence" and e.get("gross_tax") is not None
        for e in out["estimates"]
    )


def test_chat_graceful_when_unavailable(monkeypatch):
    # No Gemini client → professional fallback pointing at the form.
    monkeypatch.setattr(chatmod, "_make_client", lambda: None)
    deps = build_default_deps()
    result = chat(deps, history=[], message="What do I owe?")
    assert result["available"] is False
    assert result["used_tool"] is False
    assert result["used_search"] is False
    assert result["assessment"] is None
    assert result["knowledge"] == []
    assert "form" in result["reply"].lower()


def test_chat_fails_closed_when_daily_budget_exceeded(monkeypatch):
    # When the spend guard refuses, chat must block BEFORE creating a client.
    from taixable_copilot import spend_guard

    spend_guard._reset_for_tests()
    monkeypatch.setattr(spend_guard, "check_and_reserve", lambda: False)

    def _boom():  # pragma: no cover - must never be reached
        raise AssertionError("model client must not be created once budget is hit")

    monkeypatch.setattr(chatmod, "_make_client", _boom)
    deps = build_default_deps()
    result = chat(deps, history=[], message="Where do I pay tax?", language="es")
    assert result["available"] is False
    assert result["blocked"] is True
    assert result["used_tool"] is False
    assert result["assessment"] is None
    # Localised budget message (Spanish copy mentions the structured form).
    assert "formulario" in result["reply"].lower()
    spend_guard._reset_for_tests()


def test_search_tool_returns_cited_passages_and_captures():
    deps = build_default_deps()
    tool, captured = _make_search_tool(deps)
    out = tool(query="what is the 183 day rule in Spain", jurisdiction="ES")
    assert out["results"], "search must return at least one passage"
    assert captured["used"] is True
    assert captured["meta"]["mode"] in {"corpus", "elastic", "corpus_fallback"}
    # Every passage is cited with a real source URL (no hallucinated evidence).
    for p in out["results"]:
        assert p["citation_id"]
        assert (p["source_url"] or "").startswith("http")
    assert captured["passages"], "passages are captured for the UI evidence drawer"


def test_search_tool_dedupes_across_multiple_calls():
    deps = build_default_deps()
    tool, captured = _make_search_tool(deps)
    tool(query="Spain residency 183 days")
    tool(query="Spain residency 183 days")  # same query again
    ids = [p["citation_id"] for p in captured["passages"]]
    assert len(ids) == len(set(ids)), "captured passages must be de-duplicated"


def test_both_tools_have_concrete_annotations_for_function_calling():
    # google-genai automatic function calling does isinstance() against these;
    # `from __future__ import annotations` would stringify them and break the SDK.
    deps = build_default_deps()
    assess_tool, _ = _make_assess_tool(deps)
    search_tool, _ = _make_search_tool(deps)
    for fn in (assess_tool, search_tool):
        for name, typ in fn.__annotations__.items():
            assert isinstance(typ, type), f"{fn.__name__}.{name} must be a real type"
