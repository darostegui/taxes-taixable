"""Central cross-border treatment resolver (fail-closed).

A single place that turns a (residence, source, income_type) flow into either a
*modelled* treaty treatment (curated article + withholding rate) or an explicit
*not modelled* result — never a fabricated rate. Both ``obligations`` and
``taxbands`` consume this so the LookupError from an uncurated country pair is
caught exactly once, with consistent fallback citations.

Imports are deliberately limited to ``treaty``, ``rates`` and ``models`` to avoid
a circular dependency with ``citations``/``search`` (which derive the citation
allowlist). The known-citation allowlist is injected as ``known_ids``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from taixable_copilot.models import Country, IncomeType
from taixable_copilot.rates import RateLookup, get_withholding_rate
from taixable_copilot.treaty import Retriever, resolve_treaty_article


@dataclass
class CrossBorderTreatment:
    income_type: IncomeType
    source: Country
    residence: Country
    modelled: bool
    article_no: str | None = None
    rate: float | None = None
    relief: str | None = None
    citation_ids: list[str] = field(default_factory=list)
    reason: str = ""


def resolve_cross_border(
    residence: Country,
    source: Country,
    income_type: IncomeType,
    treaty_retriever: Retriever,
    rate_lookup: RateLookup,
    known_ids: set[str] | None = None,
) -> CrossBorderTreatment:
    """Resolve a cross-border flow, failing closed on uncurated country pairs.

    On success returns ``modelled=True`` with the curated article + rate. On a
    missing treaty/rate entry returns ``modelled=False`` with NO asserted rate;
    fallback citations point at each country's income-tax framework card, but are
    filtered to ``known_ids`` so we never emit an id outside the guardrail
    allowlist. When ``known_ids`` is ``None`` we emit no fallback cites at all
    (strict fail-closed).
    """
    try:
        article = resolve_treaty_article(residence, source, income_type, treaty_retriever)
        rate = get_withholding_rate(residence, source, income_type, rate_lookup)
    except LookupError:
        candidates = [f"{source}#income-tax", f"{residence}#income-tax"]
        if known_ids is None:
            cites: list[str] = []
        else:
            cites = [c for c in candidates if c in known_ids]
        return CrossBorderTreatment(
            income_type=income_type,
            source=source,
            residence=residence,
            modelled=False,
            citation_ids=cites,
            reason=(
                f"No curated double-tax treaty / withholding entry for "
                f"{Country.pair(residence, source)} ({income_type}). The amount is "
                f"flagged for professional review rather than asserting a rate."
            ),
        )

    return CrossBorderTreatment(
        income_type=income_type,
        source=source,
        residence=residence,
        modelled=True,
        article_no=article.article_no,
        rate=rate.rate,
        relief=rate.relief,
        citation_ids=[article.citation_id, rate.citation_id],
    )
