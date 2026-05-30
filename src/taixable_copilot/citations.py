"""Citation registry: maps every corpus citation id to a human label + source URL.

The domain layer stays pure and emits citation *ids* only. This module is the
single source of truth that resolves those ids into displayable evidence
(``label`` + ``url``) for the API responses and the rendered memo, so the agent
can surface real, clickable primary sources rather than opaque ids.

The index is built from the same four sources the guardrail validates against:
treaty articles, withholding rates, residency rules and filing deadlines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Citation:
    id: str
    label: str
    url: str | None = None
    category: str = "engine"


@lru_cache(maxsize=1)
def build_citation_index() -> dict[str, Citation]:
    """Build ``citation_id -> Citation`` from the curated corpus.

    Entries are de-duplicated by id (treaty entries that cover multiple income
    types share one id), and every id surfaced by the domain layer resolves
    here, including treaty ids (``ES-UK#art6``), rate ids (``ES-UK#art6-rate``),
    residency ids (``ES#residency-183``) and deadline ids (``UK#sa-deadline``).
    """
    index: dict[str, Citation] = {}

    treaty = json.loads((DATA_DIR / "treaty_articles.json").read_text())
    for entry in treaty["treaty_articles"]:
        cid = entry["citation_id"]
        index[cid] = Citation(cid, entry.get("source", cid), entry.get("url"))

    rates = json.loads((DATA_DIR / "withholding_rates.json").read_text())
    for entry in rates["withholding_rates"]:
        cid = entry["citation_id"]
        index[cid] = Citation(cid, entry.get("source", cid), entry.get("url"))

    import yaml

    rules = yaml.safe_load((DATA_DIR / "residency_rules.yaml").read_text()) or {}
    for rule in rules.values():
        cid = rule.get("citation_id")
        if cid:
            index[cid] = Citation(cid, rule.get("basis", cid), rule.get("url"))

    # Filing-deadline citation ids live in the obligations module.
    from taixable_copilot.obligations import FILING_DEADLINES

    for spec in FILING_DEADLINES.values():
        cid = spec["citation_id"]
        index[cid] = Citation(cid, spec.get("label", cid), spec.get("url"))

    # Progressive tax-band citation ids back the illustrative liability estimates.
    bands = json.loads((DATA_DIR / "tax_bands.json").read_text())
    for entry in bands["tax_bands"]:
        cid = entry["citation_id"]
        index[cid] = Citation(cid, entry.get("title", entry.get("source", cid)), entry.get("url"))

    # Expanded cited reference corpus (PwC Worldwide Tax Summaries + tax-authority
    # pointers). These are evidence-only: searchable, clickable, and verifiable at
    # source, but the deterministic engine does NOT compute these jurisdictions.
    # Curated engine entries above win on id collision (loaded first, not clobbered).
    legislation = json.loads((DATA_DIR / "legislation.json").read_text())
    for entry in legislation["legislation"]:
        cid = entry["citation_id"]
        if cid in index:
            continue
        content_type = entry.get("content_type")
        if content_type == "curated_reference":
            category = "curated_reference"
        elif content_type == "curated_regime":
            category = "curated_regime"
        else:
            category = "engine"
        index[cid] = Citation(
            cid, entry.get("title", cid), entry.get("source_url"), category
        )

    return index


def resolve_citations(
    ids: list[str], index: dict[str, Citation] | None = None
) -> list[Citation]:
    """Resolve citation ids to ``Citation`` objects, preserving input order.

    Unknown ids fall back to ``Citation(id, id, None)`` so evidence is never
    silently dropped from the response or memo.
    """
    idx = index if index is not None else build_citation_index()
    return [idx.get(cid, Citation(cid, cid, None)) for cid in ids]
