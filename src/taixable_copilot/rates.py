"""Withholding / relief rate resolver.

Delegates the structured lookup to an injected `lookup` callable, which in
production wraps an Elastic ES|QL query over the withholding-rates index.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from taixable_copilot.models import Country, IncomeType

RateLookup = Callable[[str, IncomeType], dict | None]


@dataclass
class RateResult:
    rate: float
    relief: str
    citation_id: str


def get_withholding_rate(
    residence: Country,
    source: Country,
    income_type: IncomeType,
    lookup: RateLookup,
) -> RateResult:
    """Return the applicable withholding rate + relief mechanism for an income flow."""
    country_pair = Country.pair(residence, source)
    hit = lookup(country_pair, income_type)
    if not hit:
        raise LookupError(f"No withholding rate found for {country_pair} / {income_type}")
    return RateResult(
        rate=float(hit["rate"]),
        relief=hit.get("relief", ""),
        citation_id=hit["citation_id"],
    )
