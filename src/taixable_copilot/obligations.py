"""Cross-border obligation + deadline assessment.

Orchestrates the residency engine, treaty matcher and rate resolver into a single
`Assessment`. Retrieval is injected (treaty_retriever, rate_lookup) so this layer
stays pure and testable; the API layer wires in the Elastic-backed implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from taixable_copilot.models import Country, CustomerProfile, IncomeType
from taixable_copilot.rates import RateLookup, get_withholding_rate
from taixable_copilot.residency import determine_residency
from taixable_copilot.treaty import Retriever, resolve_treaty_article

# Residence-country self-assessment filing deadlines (month, day) for the tax year
# following the year of income, with a citation id resolved from the corpus.
FILING_DEADLINES: dict[Country, dict] = {
    Country.UK: {"month": 1, "day": 31, "offset_years": 1, "citation_id": "UK#sa-deadline"},
    Country.ES: {"month": 6, "day": 30, "offset_years": 1, "citation_id": "ES#renta-deadline"},
    Country.DE: {"month": 7, "day": 31, "offset_years": 1, "citation_id": "DE#est-deadline"},
}


@dataclass
class Obligation:
    income_type: IncomeType
    source_country: Country
    treaty_article: str
    rate: float
    relief: str
    citation_ids: list[str] = field(default_factory=list)


@dataclass
class Deadline:
    jurisdiction: Country
    description: str
    due_date: str  # ISO date
    citation_id: str | None = None


@dataclass
class Assessment:
    primary_residence: Country
    residence_confidence: float
    obligations: list[Obligation] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)


def assess_obligations(
    profile: CustomerProfile,
    tax_year: int,
    residency_rules: dict[Country, dict],
    treaty_retriever: Retriever,
    rate_lookup: RateLookup,
) -> Assessment:
    residency = determine_residency(profile.days_present, residency_rules)
    primary = residency.primary_residence

    obligations: list[Obligation] = []
    citations: list[str] = list(residency.citations)

    # Foreign-sourced is judged against the *computed* primary residence, which may
    # differ from the profile's declared residence_country.
    foreign = [inc for inc in profile.income if inc.source_country != primary]
    for inc in foreign:
        article = resolve_treaty_article(primary, inc.source_country, inc.type, treaty_retriever)
        rate = get_withholding_rate(primary, inc.source_country, inc.type, rate_lookup)
        cite = [article.citation_id, rate.citation_id]
        citations.extend(cite)
        obligations.append(
            Obligation(
                income_type=inc.type,
                source_country=inc.source_country,
                treaty_article=article.article_no,
                rate=rate.rate,
                relief=rate.relief,
                citation_ids=cite,
            )
        )

    deadlines = _filing_deadlines(primary, tax_year)
    for d in deadlines:
        if d.citation_id:
            citations.append(d.citation_id)

    return Assessment(
        primary_residence=primary,
        residence_confidence=residency.confidence,
        obligations=obligations,
        deadlines=deadlines,
        citations=sorted(set(citations)),
    )


def _filing_deadlines(residence: Country, tax_year: int) -> list[Deadline]:
    spec = FILING_DEADLINES.get(residence)
    if not spec:
        return []
    year = tax_year + spec["offset_years"]
    due = f"{year:04d}-{spec['month']:02d}-{spec['day']:02d}"
    return [
        Deadline(
            jurisdiction=residence,
            description=f"{residence} annual tax return for {tax_year}",
            due_date=due,
            citation_id=spec["citation_id"],
        )
    ]
