"""Retrieval providers for treaty articles and withholding rates.

Two backends behind one interface:
  * **corpus** (default) — loads the curated JSON in `data/` and serves lookups
    in-process, so the whole agent runs end-to-end locally with no cloud.
  * **elastic** — queries an Elastic index (used in production / the hosted demo).

`build_retrievers()` picks elastic when `ELASTIC_URL` is set, otherwise corpus.
Both return the same `(treaty_retriever, rate_lookup)` callable pair that the
domain layer expects.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from taixable_copilot.models import IncomeType
from taixable_copilot.rates import RateLookup
from taixable_copilot.treaty import Retriever

DATA_DIR = Path(__file__).resolve().parent / "data"
TREATY_INDEX = "treaty-articles"
RATES_INDEX = "withholding-rates"


@lru_cache(maxsize=1)
def _treaty_by_key() -> dict[tuple[str, str], dict]:
    raw = json.loads((DATA_DIR / "treaty_articles.json").read_text())
    index: dict[tuple[str, str], dict] = {}
    for entry in raw["treaty_articles"]:
        for itype in entry["income_types"]:
            index[(entry["country_pair"], itype)] = entry
    return index


@lru_cache(maxsize=1)
def _rates_by_key() -> dict[tuple[str, str], dict]:
    raw = json.loads((DATA_DIR / "withholding_rates.json").read_text())
    return {(e["country_pair"], e["income_type"]): e for e in raw["withholding_rates"]}


def corpus_retrievers() -> tuple[Retriever, RateLookup]:
    treaty = _treaty_by_key()
    rates = _rates_by_key()

    def treaty_retriever(country_pair: str, income_type: IncomeType) -> dict:
        return treaty.get((country_pair, str(income_type)), {})

    def rate_lookup(country_pair: str, income_type: IncomeType) -> dict | None:
        return rates.get((country_pair, str(income_type)))

    return treaty_retriever, rate_lookup


def elastic_retrievers(url: str, api_key: str | None) -> tuple[Retriever, RateLookup]:
    from elasticsearch import Elasticsearch

    es = Elasticsearch(url, api_key=api_key) if api_key else Elasticsearch(url)

    def treaty_retriever(country_pair: str, income_type: IncomeType) -> dict:
        resp = es.search(
            index=TREATY_INDEX,
            query={
                "bool": {
                    "filter": [
                        {"term": {"country_pair": country_pair}},
                        {"term": {"income_types": str(income_type)}},
                    ]
                }
            },
            size=1,
        )
        hits = resp["hits"]["hits"]
        return hits[0]["_source"] if hits else {}

    def rate_lookup(country_pair: str, income_type: IncomeType) -> dict | None:
        resp = es.search(
            index=RATES_INDEX,
            query={
                "bool": {
                    "filter": [
                        {"term": {"country_pair": country_pair}},
                        {"term": {"income_type": str(income_type)}},
                    ]
                }
            },
            size=1,
        )
        hits = resp["hits"]["hits"]
        return hits[0]["_source"] if hits else None

    return treaty_retriever, rate_lookup


def build_retrievers() -> tuple[Retriever, RateLookup]:
    url = os.environ.get("ELASTIC_URL")
    if url:
        return elastic_retrievers(url, os.environ.get("ELASTIC_API_KEY"))
    return corpus_retrievers()


def all_citation_ids() -> set[str]:
    """Every citation id present in the corpus — used by the guardrail."""
    ids: set[str] = set()
    for entry in _treaty_by_key().values():
        ids.add(entry["citation_id"])
    for entry in _rates_by_key().values():
        ids.add(entry["citation_id"])
    import yaml

    rules = yaml.safe_load((DATA_DIR / "residency_rules.yaml").read_text()) or {}
    for r in rules.values():
        if "citation_id" in r:
            ids.add(r["citation_id"])
    # Filing-deadline citation ids defined in the obligations module.
    from taixable_copilot.obligations import FILING_DEADLINES

    for spec in FILING_DEADLINES.values():
        ids.add(spec["citation_id"])
    return ids
