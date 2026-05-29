"""Dependency container for the tool service.

Keeps the FastAPI layer thin: all collaborators (residency rules, the Elastic-backed
retrievers, the DB engine) are injected. Tests inject fakes + an in-memory SQLite
engine; production wires Elastic + Cloud SQL via `build_default_deps`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from taixable_copilot.models import Country
from taixable_copilot.rates import RateLookup
from taixable_copilot.treaty import Retriever

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


def _load_residency_rules() -> dict[Country, dict]:
    path = Path(__file__).resolve().parents[1] / "data" / "residency_rules.yaml"
    if not path.exists():
        return DEFAULT_RESIDENCY_RULES
    import yaml

    raw = yaml.safe_load(path.read_text()) or {}
    return {Country(k): v for k, v in raw.items()}


def _unconfigured_retriever(*_args, **_kwargs):
    raise RuntimeError(
        "Elastic retriever is not configured. Set ELASTIC_URL/ELASTIC_API_KEY and "
        "build the search provider (Phase 2/5), or inject a retriever for local runs."
    )


def build_default_deps() -> Deps:
    """Build production-style deps from the environment.

    Elastic retrievers are wired in Phase 5; until then they raise a clear error
    when invoked, while residency + persistence remain functional.
    """
    from taixable_copilot.db.repository import make_engine

    db_url = os.environ.get("DATABASE_URL", "sqlite:///taixable.db")
    engine = make_engine(db_url)

    treaty_retriever: Retriever = _unconfigured_retriever
    rate_lookup: RateLookup = _unconfigured_retriever
    try:
        from taixable_copilot.search import build_retrievers

        treaty_retriever, rate_lookup = build_retrievers()
    except Exception:  # noqa: BLE001 - search provider optional until Phase 5
        pass

    return Deps(
        residency_rules=_load_residency_rules(),
        treaty_retriever=treaty_retriever,
        rate_lookup=rate_lookup,
        engine=engine,
    )
