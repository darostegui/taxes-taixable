"""Approximate progressive-tax liability estimation.

Deterministic, corpus-backed: given the engine's residence determination and the
person's income, produce an *illustrative* tax estimate per taxing jurisdiction
from published, cited progressive tax bands in ``data/tax_bands.json``. No figure
here comes from the LLM — they are pure arithmetic over the curated bands, so this
module can never become a hallucination channel.

Honesty rules baked in:
  * Profile amounts carry no currency; the UI collects EUR, so we assume EUR. The
    residence progressive estimate is computed only when the residence bands are
    EUR-denominated; otherwise the number is *withheld* with an explicit note (we
    never apply GBP statutory thresholds to EUR amounts — that would be a fabricated
    figure).
  * Source-state taxes are a percentage of the line amount, so they are
    currency-agnostic and always shown, reusing the engine's already-cited rates.
  * Every estimate is labelled illustrative, lists its calculation trace, and
    carries a method note describing what the simplified model excludes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from taixable_copilot.crossborder import resolve_cross_border
from taixable_copilot.models import Country, CustomerProfile
from taixable_copilot.rates import RateLookup, get_withholding_rate
from taixable_copilot.treaty import Retriever

DATA_DIR = Path(__file__).resolve().parent / "data"

# Profile amounts are bare floats with no currency; the UI collects EUR.
ASSUMED_CURRENCY = "EUR"


@dataclass
class CountryEstimate:
    """An illustrative, cited tax estimate for one jurisdiction.

    ``gross_tax``/``net_tax`` are ``None`` when the estimate is withheld (e.g. the
    residence bands are in a different currency than the assumed input currency).
    """

    country: Country
    role: str  # "residence" | "source"
    currency: str
    taxable_base: float
    gross_tax: float | None
    credit: float | None
    net_tax: float | None
    method: str
    note: str
    citation_ids: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_tax_bands() -> dict[str, dict]:
    """Load the curated progressive-band corpus keyed by country code."""
    raw = json.loads((DATA_DIR / "tax_bands.json").read_text(encoding="utf-8"))
    return {e["country"]: e for e in raw["tax_bands"]}


def progressive_tax(taxable: float, bands: list[dict]) -> float:
    """Tax on ``taxable`` (already net of any allowance) through marginal bands.

    Each band is ``{"up_to": threshold | None, "rate": fraction}`` with thresholds
    measured from 0; the final band uses ``up_to=None`` for "and above".
    """
    if taxable <= 0:
        return 0.0
    tax = 0.0
    lower = 0.0
    for band in bands:
        up = band.get("up_to")
        upper = float(up) if up is not None else float("inf")
        if taxable <= lower:
            break
        slice_top = min(taxable, upper)
        tax += (slice_top - lower) * float(band["rate"])
        lower = upper
    return round(tax, 2)


def _dedupe(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid in ids:
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def estimate_liabilities(
    profile: CustomerProfile,
    primary: Country,
    rate_lookup: RateLookup,
    tax_bands: dict[str, dict] | None,
    *,
    treaty_retriever: Retriever | None = None,
    tax_base_scope: str | None = None,
    known_citation_ids: set[str] | None = None,
) -> list[CountryEstimate]:
    """Estimate per-jurisdiction tax for the engine's residence determination.

    Returns an empty list when no bands are supplied (estimates are opt-in so the
    pure unit tests that exercise the obligation engine stay unaffected).

    When ``treaty_retriever`` is provided, foreign income lines are resolved through
    the fail-closed cross-border resolver: an uncurated country pair is flagged as
    *not modelled* (no fabricated rate) and the residence net figure is then withheld
    (a missing foreign-tax credit would overstate the residence tax). When it is not
    provided the legacy direct-rate path is used (curated pairs only).

    ``tax_base_scope`` (from the residency finding) gates the residence estimate:
    a ``no_personal_income_tax`` jurisdiction never produces a positive amount.
    """
    if not tax_bands:
        return []

    estimates: list[CountryEstimate] = []
    worldwide = sum(inc.amount for inc in profile.income)
    foreign = [inc for inc in profile.income if inc.source_country != primary]

    # --- Source-country taxes: a percentage of the line amount (currency-agnostic),
    # reusing the engine's already-cited withholding rate. A line is taxed at source
    # iff its rate > 0 (rental/dividend); employment/interest/pension are 0. ---
    source_tax_by_country: dict[Country, float] = {}
    source_base_by_country: dict[Country, float] = {}
    source_trace_by_country: dict[Country, list[str]] = {}
    source_cites_by_country: dict[Country, list[str]] = {}
    credited_income = 0.0
    has_unmodelled_foreign = False
    for inc in foreign:
        if treaty_retriever is not None:
            treatment = resolve_cross_border(
                primary,
                inc.source_country,
                inc.type,
                treaty_retriever,
                rate_lookup,
                known_ids=known_citation_ids,
            )
            if not treatment.modelled:
                has_unmodelled_foreign = True
                continue
            line_rate = treatment.rate or 0.0
            line_cite = treatment.citation_ids
        else:
            rate = get_withholding_rate(primary, inc.source_country, inc.type, rate_lookup)
            line_rate = rate.rate
            line_cite = [rate.citation_id]
        if line_rate <= 0:
            continue
        amt = round(inc.amount * line_rate, 2)
        c = inc.source_country
        source_tax_by_country[c] = round(source_tax_by_country.get(c, 0.0) + amt, 2)
        source_base_by_country[c] = round(source_base_by_country.get(c, 0.0) + inc.amount, 2)
        source_trace_by_country.setdefault(c, []).append(
            f"{inc.type} {inc.amount:,.0f} × {line_rate * 100:.0f}% = {amt:,.0f} {ASSUMED_CURRENCY}"
        )
        source_cites_by_country.setdefault(c, []).extend(line_cite)
        credited_income += inc.amount

    total_source_tax = round(sum(source_tax_by_country.values()), 2)

    # --- Residence progressive estimate on worldwide income. ---
    spec = tax_bands.get(str(primary))
    if spec and tax_base_scope != "no_personal_income_tax":
        currency = spec["currency"]
        allowance = float(spec.get("personal_allowance", 0))
        taxable = max(0.0, worldwide - allowance)
        band_cite = spec["citation_id"]
        if currency != ASSUMED_CURRENCY:
            estimates.append(
                CountryEstimate(
                    country=primary,
                    role="residence",
                    currency=currency,
                    taxable_base=round(taxable, 2),
                    gross_tax=None,
                    credit=None,
                    net_tax=None,
                    method=spec.get("method", ""),
                    note=(
                        f"Residence estimate withheld: income was entered without a "
                        f"currency (treated as {ASSUMED_CURRENCY}) but {primary} tax bands "
                        f"are in {currency}. Provide {currency} figures for an estimate — "
                        f"no FX conversion is applied."
                    ),
                    citation_ids=[band_cite],
                    trace=[
                        f"Worldwide income (assumed {ASSUMED_CURRENCY}) {worldwide:,.0f}",
                        f"{primary} bands are denominated in {currency}; no FX conversion applied",
                    ],
                )
            )
        else:
            gross = progressive_tax(taxable, spec["bands"])
            trace = [
                f"Worldwide income (assumed {ASSUMED_CURRENCY}) {worldwide:,.0f}",
                f"− personal allowance {allowance:,.0f} → taxable {taxable:,.0f}",
                f"Progressive bands → gross tax {gross:,.0f} {currency}",
            ]
            cites = [band_cite]
            if has_unmodelled_foreign:
                # A foreign line could not be modelled (uncurated treaty pair), so the
                # foreign-tax credit is unknown. Show the gross residence figure but
                # withhold the net — omitting the credit would overstate the liability.
                credit: float | None = None
                net: float | None = None
                trace.append(
                    "Foreign-tax credit not computed: a foreign income line falls on an "
                    "uncurated treaty pair (flagged for review), so the net residence "
                    "figure is withheld to avoid overstating tax."
                )
                note = (
                    "Net withheld — one or more foreign income lines are on a country "
                    "pair not yet modelled, so the foreign-tax credit cannot be computed. "
                    + spec.get("note", "")
                ).strip()
            else:
                cap = round(gross * (credited_income / worldwide), 2) if worldwide > 0 else 0.0
                credit = round(min(total_source_tax, cap), 2)
                net = round(gross - credit, 2)
                if total_source_tax > 0:
                    trace.append(
                        f"Foreign tax credit = min(source tax {total_source_tax:,.0f}, "
                        f"proportional cap {cap:,.0f}) = {credit:,.0f}"
                    )
                    cites += [c for cl in source_cites_by_country.values() for c in cl]
                trace.append(f"Net residence tax ≈ {net:,.0f} {currency}")
                note = spec.get("note", "")
            estimates.append(
                CountryEstimate(
                    country=primary,
                    role="residence",
                    currency=currency,
                    taxable_base=round(taxable, 2),
                    gross_tax=gross,
                    credit=credit,
                    net_tax=net,
                    method=spec.get("method", ""),
                    note=note,
                    citation_ids=_dedupe(cites),
                    trace=trace,
                )
            )

    # --- Source-country estimates (one per taxing jurisdiction). ---
    for country, tax in source_tax_by_country.items():
        estimates.append(
            CountryEstimate(
                country=country,
                role="source",
                currency=ASSUMED_CURRENCY,
                taxable_base=source_base_by_country[country],
                gross_tax=tax,
                credit=0.0,
                net_tax=tax,
                method="Flat treaty-capped rate applied to the income arising in this country.",
                note="Tax levied where the income arises; credited against residence-country tax.",
                citation_ids=_dedupe(source_cites_by_country[country]),
                trace=source_trace_by_country[country],
            )
        )

    return estimates
