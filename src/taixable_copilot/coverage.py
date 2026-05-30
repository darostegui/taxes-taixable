"""Knowledge-coverage dashboard — the Elasticsearch *aggregations* showcase.

The "verifiable AI" promise is only credible if its coverage is measurable. This
module answers "what does the advisor actually know, and how fresh is it?" by
aggregating over the curated Elastic indices:

  * passages per jurisdiction / content type (``tax-knowledge`` terms aggs)
  * treaty pairs covered (``treaty-articles``)
  * withholding-rate rows covered (``withholding-rates``)
  * total documents per index

It reframes limited coverage as a *feature*: we measure it and expand safely.

Like every other Elastic feature here it degrades gracefully — when no
``ELASTIC_URL`` is configured it computes the identical shape from the in-process
corpus, so the dashboard renders offline too.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from taixable_copilot.knowledge import KNOWLEDGE_INDEX, build_knowledge_corpus
from taixable_copilot.search import RATES_INDEX, TREATY_INDEX

DATA_DIR = Path(__file__).resolve().parent / "data"

# A coverage provider takes no arguments and returns a dashboard envelope.
Coverage = Callable[[], dict[str, Any]]


def _buckets(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"key": key, "doc_count": count}
        for key, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        if key
    ]


@lru_cache(maxsize=1)
def _treaty_pairs() -> list[str]:
    raw = json.loads((DATA_DIR / "treaty_articles.json").read_text())
    return sorted({e["country_pair"] for e in raw["treaty_articles"]})


@lru_cache(maxsize=1)
def _rate_pairs() -> list[str]:
    raw = json.loads((DATA_DIR / "withholding_rates.json").read_text())
    return sorted({e["country_pair"] for e in raw["withholding_rates"]})


def corpus_coverage() -> Coverage:
    """Compute the coverage dashboard from the in-process curated corpus."""

    def coverage() -> dict[str, Any]:
        corpus = build_knowledge_corpus()
        by_jur: Counter[str] = Counter()
        by_type: Counter[str] = Counter()
        for d in corpus:
            by_jur[d.get("jurisdiction") or d.get("country_pair") or ""] += 1
            by_type[d.get("content_type", "")] += 1
        treaty_pairs = _treaty_pairs()
        rate_pairs = _rate_pairs()
        return {
            "mode": "corpus",
            "totals": {
                KNOWLEDGE_INDEX: len(corpus),
                TREATY_INDEX: len(treaty_pairs),
                RATES_INDEX: len(rate_pairs),
            },
            "by_jurisdiction": _buckets(by_jur),
            "by_content_type": _buckets(by_type),
            "treaty_pairs": treaty_pairs,
            "rate_pairs": rate_pairs,
        }

    return coverage


def elastic_coverage(url: str, api_key: str | None) -> Coverage:
    """Compute the coverage dashboard with Elasticsearch terms aggregations."""
    from elasticsearch import Elasticsearch

    es = Elasticsearch(url, api_key=api_key) if api_key else Elasticsearch(url)
    fallback = corpus_coverage()

    def coverage() -> dict[str, Any]:
        try:
            resp = es.search(
                index=KNOWLEDGE_INDEX,
                size=0,
                aggs={
                    "by_jurisdiction": {"terms": {"field": "jurisdiction", "size": 50}},
                    "by_content_type": {"terms": {"field": "content_type", "size": 50}},
                },
            )
            aggs = resp.get("aggregations", {})
            knowledge_total = resp["hits"]["total"]["value"]
            treaty_pairs = _agg_keys(es, TREATY_INDEX, "country_pair")
            rate_pairs = _agg_keys(es, RATES_INDEX, "country_pair")
            return {
                "mode": "elastic",
                "totals": {
                    KNOWLEDGE_INDEX: knowledge_total,
                    TREATY_INDEX: _count(es, TREATY_INDEX),
                    RATES_INDEX: _count(es, RATES_INDEX),
                },
                "by_jurisdiction": _normalise_buckets(aggs.get("by_jurisdiction")),
                "by_content_type": _normalise_buckets(aggs.get("by_content_type")),
                "treaty_pairs": treaty_pairs,
                "rate_pairs": rate_pairs,
            }
        except Exception:  # noqa: BLE001 - Elastic unreachable -> corpus dashboard
            out = fallback()
            out["mode"] = "corpus_fallback"
            return out

    return coverage


def _normalise_buckets(agg: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not agg:
        return []
    return [
        {"key": b["key"], "doc_count": b["doc_count"]}
        for b in agg.get("buckets", [])
        if b.get("key")
    ]


def _agg_keys(es: Any, index: str, field: str) -> list[str]:
    resp = es.search(index=index, size=0, aggs={"k": {"terms": {"field": field, "size": 200}}})
    keys = [b["key"] for b in resp.get("aggregations", {}).get("k", {}).get("buckets", [])]
    return sorted(k for k in keys if k)


def _count(es: Any, index: str) -> int:
    return int(es.count(index=index).get("count", 0))


def build_coverage() -> Coverage:
    """Pick the Elastic aggregation backend when ``ELASTIC_URL`` is set, else corpus."""
    url = os.environ.get("ELASTIC_URL")
    if url:
        return elastic_coverage(url, os.environ.get("ELASTIC_API_KEY"))
    return corpus_coverage()
