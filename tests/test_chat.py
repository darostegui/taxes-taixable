"""Tests for the conversational tax-advisor agent.

Network-free: they exercise the engine-backed tool (which runs the real
deterministic engine) and the graceful-fallback contract when Gemini is
unavailable.
"""

from __future__ import annotations

import json

import taixable_copilot.chat as chatmod
from taixable_copilot.api.deps import build_default_deps
from taixable_copilot.chat import _build_profile, _make_assess_tool, chat
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


def test_assess_tool_returns_error_for_unsupported_country():
    deps = build_default_deps()
    tool, _ = _make_assess_tool(deps)
    out = tool(days_present_json=json.dumps({"FR": 365}), income_json="[]")
    assert "error" in out
    assert out["supported_countries"] == ["UK", "ES", "DE"]


def test_chat_graceful_when_unavailable(monkeypatch):
    # No Gemini client → professional fallback pointing at the form.
    monkeypatch.setattr(chatmod, "_make_client", lambda: None)
    deps = build_default_deps()
    result = chat(deps, history=[], message="What do I owe?")
    assert result["available"] is False
    assert result["used_tool"] is False
    assert result["assessment"] is None
    assert "form" in result["reply"].lower()
