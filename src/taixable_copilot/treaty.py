"""Treaty article matcher.

Maps a (residence, source, income_type) request to the applicable double-tax
treaty article. The actual lookup is delegated to an injected `retriever`
callable, which in production wraps Elastic hybrid search over the treaty corpus.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from taixable_copilot.models import Country, IncomeType

Retriever = Callable[[str, IncomeType], dict]


@dataclass
class TreatyArticle:
    article_no: str
    topic: str
    text: str
    citation_id: str


def resolve_treaty_article(
    residence: Country,
    source: Country,
    income_type: IncomeType,
    retriever: Retriever,
) -> TreatyArticle:
    """Resolve the applicable treaty article for a cross-border income flow."""
    country_pair = Country.pair(residence, source)
    hit = retriever(country_pair, income_type)
    if not hit:
        raise LookupError(f"No treaty article found for {country_pair} / {income_type}")
    return TreatyArticle(
        article_no=str(hit["article_no"]),
        topic=hit.get("topic", ""),
        text=hit.get("text", ""),
        citation_id=hit["citation_id"],
    )
