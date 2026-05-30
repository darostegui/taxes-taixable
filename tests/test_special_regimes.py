"""QA tests for the special mobility-regimes corpus (``curated_regime``).

Unlike the broad ``curated_reference`` tier, regime cards DO carry concrete
figures (flat rates, caps, durations, thresholds). The no-hallucination contract
is preserved by a different invariant set, locked here: every entry must carry a
real source URL, provenance, a granular status, and structured eligibility data;
ids must be unique and fail-closed (resolvable + in the guardrail allowlist);
regimes that are closed to new movers must say so; and a card's figures must
never be scoped to another jurisdiction (no cross-border figure mixing).
"""

import json
from pathlib import Path

from taixable_copilot.citations import build_citation_index
from taixable_copilot.coverage import corpus_coverage
from taixable_copilot.knowledge import build_knowledge_corpus
from taixable_copilot.search import all_citation_ids

_LEGISLATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "taixable_copilot"
    / "data"
    / "legislation.json"
)

_VALID_STATUS = {"active", "repealed", "closed_to_new_entrants", "replaced"}
_CLOSED_STATUS = {"repealed", "closed_to_new_entrants", "replaced"}


def _regime_entries() -> list[dict]:
    data = json.loads(_LEGISLATION.read_text(encoding="utf-8"))
    entries = data["legislation"] if isinstance(data, dict) else data
    return [e for e in entries if e.get("content_type") == "curated_regime"]


def test_regime_corpus_is_present() -> None:
    entries = _regime_entries()
    assert len(entries) >= 20


def test_regime_ids_are_unique() -> None:
    ids = [e["citation_id"] for e in _regime_entries()]
    assert len(ids) == len(set(ids))


def test_regime_required_fields_and_provenance() -> None:
    for entry in _regime_entries():
        cid = entry["citation_id"]
        assert entry.get("package_version") == "2025.1", cid
        assert entry.get("generator_version") == "special-regimes/1.0", cid
        assert entry.get("retrieved_at"), cid
        assert entry.get("source_content_hash"), cid
        assert entry.get("source_url", "").startswith("http"), cid
        assert entry.get("effective_date"), cid
        assert entry.get("regime_name"), cid
        assert entry.get("status_effective_date"), cid
        # jurisdiction is a single country code (region lives in its own field),
        # so coverage/treaty-pair logic never misreads a regional card as a pair.
        assert "-" not in entry.get("jurisdiction", "-"), cid
        assert isinstance(entry.get("applies_to_new_applicants"), bool), cid
        assert isinstance(entry.get("figures"), list), cid
        assert isinstance(entry.get("eligibility_criteria"), list), cid
        assert isinstance(entry.get("exclusions"), list), cid


def test_regime_status_is_a_known_enum() -> None:
    for entry in _regime_entries():
        assert entry["status"] in _VALID_STATUS, entry["citation_id"]


def test_closed_regimes_are_not_open_to_new_applicants() -> None:
    """A repealed/closed/replaced route must never be recommended for a new move."""
    for entry in _regime_entries():
        if entry["status"] in _CLOSED_STATUS:
            assert entry["applies_to_new_applicants"] is False, entry["citation_id"]


def test_closed_regimes_carry_grandfathering_note() -> None:
    for entry in _regime_entries():
        if entry["status"] in _CLOSED_STATUS:
            assert entry.get("grandfathering") or entry.get("exclusions"), entry["citation_id"]


def test_flagship_volatile_regimes_have_current_status() -> None:
    """Lock the 2024–2025 changes so stale facts can't silently creep back in."""
    by_id = {e["citation_id"]: e for e in _regime_entries()}
    assert by_id["ES#golden-visa-repeal"]["status"] == "repealed"
    assert by_id["ES#golden-visa-repeal"]["applies_to_new_applicants"] is False
    assert by_id["UK#non-dom-abolished"]["status"] == "replaced"
    assert by_id["UK#non-dom-abolished"]["applies_to_new_applicants"] is False
    assert by_id["UK#fig-regime"]["applies_to_new_applicants"] is True
    assert by_id["PT#nhr-closed"]["status"] == "closed_to_new_entrants"
    assert by_id["PT#ifici"]["applies_to_new_applicants"] is True


def test_regime_hard_figures_appear_in_searchable_summary() -> None:
    """Rate/currency figures must be in the summary prose so ES can find/highlight them."""
    import re

    hard = re.compile(r"%|EUR|GBP|USD")
    for entry in _regime_entries():
        summary = entry["summary"]
        for figure in entry["figures"]:
            value = figure["value"]
            token = value.split(" (")[0]
            if not hard.search(token):
                continue  # descriptive figures (durations, scopes) need not be verbatim
            assert token in summary, f"{entry['citation_id']}: '{token}' missing from summary"


def test_regime_figures_do_not_cross_jurisdictions() -> None:
    """No cross-border figure mixing: every figure scope stays within its own country."""
    for entry in _regime_entries():
        country = entry["jurisdiction"]
        for figure in entry["figures"]:
            scope = figure["scope"]
            assert scope.split("-")[0] == country, (
                f"{entry['citation_id']}: figure scope '{scope}' is outside {country}"
            )


def test_regime_summaries_use_screening_language() -> None:
    """Cards must screen ('may be relevant'), never determine ('you qualify')."""
    forbidden = ["you qualify", "you can apply", "this applies to you", "you will pay"]
    for entry in _regime_entries():
        low = entry["summary"].lower()
        for phrase in forbidden:
            assert phrase not in low, f"{entry['citation_id']}: determinative phrase '{phrase}'"


def test_regime_summaries_carry_a_verify_disclaimer() -> None:
    for entry in _regime_entries():
        low = entry["summary"].lower()
        assert "informational regime evidence" in low, entry["citation_id"]
        assert "professional" in low, entry["citation_id"]


def test_regime_ids_resolve_and_are_tagged_curated_regime() -> None:
    index = build_citation_index()
    for entry in _regime_entries():
        cid = entry["citation_id"]
        assert cid in index, cid
        assert index[cid].category == "curated_regime", cid
        assert index[cid].url == entry["source_url"], cid


def test_regime_ids_are_in_the_guardrail_allowlist() -> None:
    """Fail-closed: every regime id is a known citation, so it can be surfaced + verified."""
    known = all_citation_ids()
    missing = [e["citation_id"] for e in _regime_entries() if e["citation_id"] not in known]
    assert missing == [], f"regime ids not in allowlist: {missing[:10]}"


def test_regime_cards_are_searchable_in_knowledge_corpus() -> None:
    corpus = {d["citation_id"]: d for d in build_knowledge_corpus()}
    for entry in _regime_entries():
        cid = entry["citation_id"]
        assert cid in corpus, cid
        assert corpus[cid]["content_type"] == "curated_regime", cid
        # Figures must be in the indexed/highlightable text body.
        body = corpus[cid]["text"]
        assert entry["summary"][:40] in body, cid


def test_regimes_appear_in_coverage_aggregation() -> None:
    cov = corpus_coverage()()
    by_type = {b["key"]: b["doc_count"] for b in cov["by_content_type"]}
    assert by_type.get("curated_regime", 0) >= 20
