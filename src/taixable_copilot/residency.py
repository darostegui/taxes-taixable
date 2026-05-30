"""Residency determination engine.

Rules are injected as plain data (loaded from data/residency_rules.yaml in
production) so the engine is fully unit-testable without I/O.

Two rule tiers, both fail-closed:
  * COMPUTABLE — rule carries ``days_threshold``; residence is concluded from a
    day count (confidence capped below 0.95 when ``confidence_cap`` is set,
    because other statutory tests also exist).
  * COVERAGE-ONLY — rule omits ``days_threshold``; the primary residency test is
    not a simple calendar-year day count, so we do NOT conclude residence from
    days. ``residency_modelled`` is False and confidence stays low.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from taixable_copilot.models import Country


@dataclass
class ResidencyFinding:
    primary_residence: Country
    per_country: dict[Country, bool]
    citations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    residency_modelled: bool = True
    tax_base_scope: str | None = None
    scope_note: str | None = None
    scope_citation_id: str | None = None
    other_tests_exist: bool = False


def determine_residency(
    days_present: dict[Country, int],
    rules: dict[Country, dict],
) -> ResidencyFinding:
    """Determine primary tax residence from day-count tests.

    Countries whose rule carries ``days_threshold`` are resident when days
    present meet/exceed it. Countries without a ``days_threshold`` (coverage-only
    tier) are never concluded resident from days — their residency is flagged as
    not modelled. The primary residence is the country with the most days
    present; confidence is high when that country clears its threshold and no
    other does, then capped by the primary rule's ``confidence_cap``.
    """
    if not days_present:
        raise ValueError("days_present must contain at least one country")

    per_country: dict[Country, bool] = {}
    citations: list[str] = []
    for country, days in days_present.items():
        rule = rules.get(country, {})
        if "days_threshold" in rule:
            is_resident = days >= rule["days_threshold"]
        else:
            # Coverage-only tier: cannot conclude residence from a day count.
            is_resident = False
        per_country[country] = is_resident
        if "citation_id" in rule:
            citations.append(rule["citation_id"])

    primary = max(days_present, key=lambda c: days_present[c])
    primary_rule = rules.get(primary, {})
    primary_modelled = "days_threshold" in primary_rule

    residents = [c for c, r in per_country.items() if r]
    if not primary_modelled:
        # Residence not concluded from days for the most-present country.
        confidence = 0.4
    elif per_country.get(primary) and len(residents) == 1:
        confidence = 0.95
    elif per_country.get(primary):
        confidence = 0.7  # resident here but also resident elsewhere (tie-break needed)
    else:
        confidence = 0.5  # nobody clears the threshold; fell back to most-days

    cap = primary_rule.get("confidence_cap")
    if cap is not None:
        confidence = min(confidence, cap)

    scope_citation_id = primary_rule.get("scope_citation_id")
    if scope_citation_id and scope_citation_id not in citations:
        citations.append(scope_citation_id)

    return ResidencyFinding(
        primary_residence=primary,
        per_country=per_country,
        citations=citations,
        confidence=confidence,
        residency_modelled=primary_modelled,
        tax_base_scope=primary_rule.get("tax_base_scope"),
        scope_note=primary_rule.get("basis"),
        scope_citation_id=scope_citation_id,
        other_tests_exist=bool(primary_rule.get("other_tests_exist")),
    )
