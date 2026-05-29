"""Residency determination engine.

Rules are injected as plain data (loaded from data/residency_rules.yaml in
production) so the engine is fully unit-testable without I/O.
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


def determine_residency(
    days_present: dict[Country, int],
    rules: dict[Country, dict],
) -> ResidencyFinding:
    """Determine primary tax residence from day-count tests.

    Each country is resident if days present meet/exceed its threshold. The
    primary residence is the country with the most days present; confidence is
    high when that country clears its threshold and no other does.
    """
    if not days_present:
        raise ValueError("days_present must contain at least one country")

    per_country: dict[Country, bool] = {}
    citations: list[str] = []
    for country, days in days_present.items():
        rule = rules.get(country, {})
        threshold = rule.get("days_threshold", 183)
        is_resident = days >= threshold
        per_country[country] = is_resident
        if "citation_id" in rule:
            citations.append(rule["citation_id"])

    primary = max(days_present, key=lambda c: days_present[c])
    residents = [c for c, r in per_country.items() if r]
    if per_country.get(primary) and len(residents) == 1:
        confidence = 0.95
    elif per_country.get(primary):
        confidence = 0.7  # resident here but also resident elsewhere (tie-break needed)
    else:
        confidence = 0.5  # nobody clears the threshold; fell back to most-days

    return ResidencyFinding(
        primary_residence=primary,
        per_country=per_country,
        citations=citations,
        confidence=confidence,
    )
