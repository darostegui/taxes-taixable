"""Dependency container for the tool service.

Keeps the FastAPI layer thin: all collaborators (residency rules, the Elastic-backed
retrievers, the DB engine) are injected. Tests inject fakes + an in-memory SQLite
engine; production wires Elastic + Cloud SQL via `build_default_deps`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Engine

from taixable_copilot.models import Country
from taixable_copilot.rates import RateLookup
from taixable_copilot.treaty import Retriever

if TYPE_CHECKING:
    from taixable_copilot.citations import Citation
    from taixable_copilot.knowledge import KnowledgeSearch
    from taixable_copilot.legislation import LegislationLookup

# Fallback day-count rules so residency works before the YAML corpus exists.
DEFAULT_RESIDENCY_RULES: dict[Country, dict] = {
    Country.ES: {"days_threshold": 183, "citation_id": "ES#residency-183"},
    Country.UK: {"days_threshold": 183, "citation_id": "UK#srt-183"},
    Country.DE: {"days_threshold": 183, "citation_id": "DE#residency-183"},
}


@dataclass
class Deps:
    residency_rules: dict[Country, dict]
    treaty_retriever: Retriever
    rate_lookup: RateLookup
    engine: Engine
    # When set, the API rejects any citation id not in this set (guardrail against
    # hallucinated sources). None disables the check (e.g. tests with fake retrievers).
    known_citation_ids: set[str] | None = None
    # id -> Citation (label + source URL); None resolves ids to themselves.
    citation_index: "dict[str, Citation] | None" = None
    # Maps the engine's citation ids to curated supporting-legislation passages.
    # None means no supporting legislation is attached (e.g. tests with fakes).
    legislation_lookup: "LegislationLookup | None" = None
    # Free-text hybrid Elasticsearch search over the curated tax-knowledge base,
    # used by the conversational agent's search_tax_knowledge tool. None disables
    # it (the tool then returns no passages).
    knowledge_search: "KnowledgeSearch | None" = None
    # Progressive tax bands per country code, backing the illustrative liability
    # estimates. None disables estimates (e.g. tests with fake retrievers).
    tax_bands: dict[str, dict] | None = None


def _load_residency_rules() -> dict[Country, dict]:
    path = Path(__file__).resolve().parents[1] / "data" / "residency_rules.yaml"
    if not path.exists():
        return DEFAULT_RESIDENCY_RULES
    import yaml

    raw = yaml.safe_load(path.read_text()) or {}
    return {Country(k): v for k, v in raw.items()}


def build_default_deps() -> Deps:
    """Build production-style deps from the environment.

    Retrievers are corpus-backed by default (fully local) and Elastic-backed when
    ELASTIC_URL is set (the hosted demo). Persistence targets DATABASE_URL.
    """
    from taixable_copilot.citations import build_citation_index
    from taixable_copilot.db.repository import make_engine
    from taixable_copilot.knowledge import build_knowledge_search
    from taixable_copilot.legislation import build_legislation_lookup
    from taixable_copilot.search import all_citation_ids, build_retrievers
    from taixable_copilot.taxbands import load_tax_bands

    db_url = os.environ.get("DATABASE_URL", "sqlite:///taixable.db")
    engine = make_engine(db_url)
    treaty_retriever, rate_lookup = build_retrievers()

    return Deps(
        residency_rules=_load_residency_rules(),
        treaty_retriever=treaty_retriever,
        rate_lookup=rate_lookup,
        engine=engine,
        known_citation_ids=all_citation_ids(),
        citation_index=build_citation_index(),
        legislation_lookup=build_legislation_lookup(),
        knowledge_search=build_knowledge_search(),
        tax_bands=load_tax_bands(),
    )
