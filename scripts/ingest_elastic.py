#!/usr/bin/env python3
"""Ingest the curated corpus into Elastic for the hosted demo.

Creates the `treaty-articles` and `withholding-rates` indices and bulk-loads the
JSON in `src/taixable_copilot/data/`. Idempotent: re-running replaces documents.

Usage:
    export ELASTIC_URL=https://<your-project>.es.<region>.elastic.cloud
    export ELASTIC_API_KEY=<api-key>
    python scripts/ingest_elastic.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "taixable_copilot" / "data"
TREATY_INDEX = "treaty-articles"
RATES_INDEX = "withholding-rates"
LEGISLATION_INDEX = "tax-legislation"

TREATY_MAPPING = {
    "properties": {
        "country_pair": {"type": "keyword"},
        "income_types": {"type": "keyword"},
        "article_no": {"type": "keyword"},
        "topic": {"type": "text"},
        "text": {"type": "text"},
        "citation_id": {"type": "keyword"},
        "source": {"type": "text"},
    }
}

RATES_MAPPING = {
    "properties": {
        "country_pair": {"type": "keyword"},
        "income_type": {"type": "keyword"},
        "rate": {"type": "float"},
        "relief": {"type": "text"},
        "citation_id": {"type": "keyword"},
        "source": {"type": "text"},
    }
}

LEGISLATION_MAPPING = {
    "properties": {
        "citation_id": {"type": "keyword"},
        "jurisdiction": {"type": "keyword"},
        "article": {"type": "keyword"},
        "content_type": {"type": "keyword"},
        "package_version": {"type": "keyword"},
        "source_url": {"type": "keyword"},
        "title": {"type": "text"},
        "summary": {"type": "text"},
        "effective_date": {"type": "date"},
    }
}


def _recreate_index(es, name: str, mapping: dict) -> None:
    if es.indices.exists(index=name):
        es.indices.delete(index=name)
    es.indices.create(index=name, mappings=mapping)


def main() -> int:
    url = os.environ.get("ELASTIC_URL")
    api_key = os.environ.get("ELASTIC_API_KEY")
    if not url:
        print("ELASTIC_URL not set; aborting.", file=sys.stderr)
        return 1

    from elasticsearch import Elasticsearch, helpers

    es = Elasticsearch(url, api_key=api_key) if api_key else Elasticsearch(url)

    _recreate_index(es, TREATY_INDEX, TREATY_MAPPING)
    _recreate_index(es, RATES_INDEX, RATES_MAPPING)
    _recreate_index(es, LEGISLATION_INDEX, LEGISLATION_MAPPING)

    treaties = json.loads((DATA_DIR / "treaty_articles.json").read_text())["treaty_articles"]
    rates = json.loads((DATA_DIR / "withholding_rates.json").read_text())["withholding_rates"]
    legislation = json.loads((DATA_DIR / "legislation.json").read_text())["legislation"]

    helpers.bulk(
        es,
        ({"_index": TREATY_INDEX, "_id": t["citation_id"], "_source": t} for t in treaties),
    )
    helpers.bulk(
        es,
        ({"_index": RATES_INDEX, "_id": r["citation_id"], "_source": r} for r in rates),
    )
    helpers.bulk(
        es,
        ({"_index": LEGISLATION_INDEX, "_id": p["citation_id"], "_source": p} for p in legislation),
    )
    es.indices.refresh(index=TREATY_INDEX)
    es.indices.refresh(index=RATES_INDEX)
    es.indices.refresh(index=LEGISLATION_INDEX)

    print(
        f"Ingested {len(treaties)} treaty articles, {len(rates)} rate rows, "
        f"and {len(legislation)} legislation passages."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
