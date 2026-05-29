"""Tests for the optional Gemini narration layer.

These never hit the network: they exercise the pure prompt builder and the
graceful-fallback contract (no credentials → ``None`` → deterministic memo).
"""

from __future__ import annotations

import taixable_copilot.llm as llm
from taixable_copilot.citations import build_citation_index, resolve_citations
from taixable_copilot.llm import build_narration_prompt, narrate_assessment


def test_prompt_contains_only_engine_facts(sample_assessment):
    prompt = build_narration_prompt(
        sample_assessment, "CUST-001", build_citation_index()
    )
    # Facts the engine computed must be present...
    assert "CUST-001" in prompt
    assert "UK" in prompt  # primary residence
    assert "rental" in prompt.lower()
    assert "treaty article 6" in prompt
    assert "due 2026-01-31" in prompt
    # ...and the anti-hallucination guidance must constrain the model.
    assert "do not add" in prompt.lower()


def test_prompt_lists_resolved_source_labels(sample_assessment):
    prompt = build_narration_prompt(
        sample_assessment, "CUST-001", build_citation_index()
    )
    # Source names are the human labels, not bare IDs, and come from the index.
    labels = [
        c.label
        for c in resolve_citations(sample_assessment.citations, build_citation_index())
    ]
    assert labels
    for label in labels:
        assert label in prompt


def test_narrate_returns_none_without_credentials(monkeypatch, sample_assessment):
    # No env credentials configured → no client → graceful fallback (None).
    for var in (
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GCP_PROJECT",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    assert narrate_assessment(sample_assessment, "CUST-001") is None


def test_narrate_returns_none_when_client_unavailable(monkeypatch, sample_assessment):
    # Even if creds exist, a client-build failure must not raise.
    monkeypatch.setattr(llm, "_make_client", lambda: None)
    assert narrate_assessment(sample_assessment, "CUST-001") is None
