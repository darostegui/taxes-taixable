"""Generate the expanded *cited reference corpus* into ``legislation.json``.

This tool turns the project's "no-hallucination" promise into a build step.
Rather than inventing statute text or guessing citation URLs for ~150 countries,
it programmatically *verifies* every source link against a real authority — PwC
Worldwide Tax Summaries — and emits **reference-only** corpus entries:

  * Every URL is fetched; an entry is emitted ONLY when the page returns HTTP 200.
  * Each entry pins provenance: ``retrieved_at`` (UTC date) and
    ``source_content_hash`` (sha256 of the fetched page body).
  * Summaries are deliberately reference-only. They assert **no** legal rule, day
    count or article number — they point at the authoritative source and state
    plainly that Taixable's deterministic engine does not compute that
    jurisdiction. The engine stays anchored on ES / UK / DE.

Run from the repo root::

    .venv/bin/python scripts/build_reference_corpus.py

It rewrites ``src/taixable_copilot/data/legislation.json`` in place, preserving
every existing curated entry and refusing to clobber an existing citation id.

The country map (slug -> ISO-3166 alpha-2 -> display name) is verified, embedded
and asserted unique below; ``spain``/``germany``/``united-kingdom`` are excluded
because they are the curated, *computable* jurisdictions.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "src/taixable_copilot/data/legislation.json"
PWC = "https://taxsummaries.pwc.com/{slug}/individual/{leaf}"
PACKAGE_VERSION = "2025.1"
GENERATOR_VERSION = "reference-corpus/1.0"
USER_AGENT = "Mozilla/5.0 (taixable reference-corpus builder)"

# Verified slug -> (ISO 3166-1 alpha-2, display name). Each slug has a live
# /individual/residence AND /individual/taxes-on-personal-income page on PwC
# Worldwide Tax Summaries (confirmed via sitemap.xml + per-URL fetch). ES/DE/GB
# are intentionally absent: they are the engine's computable jurisdictions.
TERRITORIES: dict[str, tuple[str, str]] = {
    "albania": ("AL", "Albania"),
    "algeria": ("DZ", "Algeria"),
    "angola": ("AO", "Angola"),
    "argentina": ("AR", "Argentina"),
    "armenia": ("AM", "Armenia"),
    "australia": ("AU", "Australia"),
    "austria": ("AT", "Austria"),
    "azerbaijan": ("AZ", "Azerbaijan"),
    "bahrain": ("BH", "Bahrain"),
    "bangladesh": ("BD", "Bangladesh"),
    "barbados": ("BB", "Barbados"),
    "belgium": ("BE", "Belgium"),
    "bermuda": ("BM", "Bermuda"),
    "bosnia-and-herzegovina": ("BA", "Bosnia and Herzegovina"),
    "botswana": ("BW", "Botswana"),
    "brazil": ("BR", "Brazil"),
    "brunei-darussalam": ("BN", "Brunei"),
    "bulgaria": ("BG", "Bulgaria"),
    "cabo-verde": ("CV", "Cabo Verde"),
    "cambodia": ("KH", "Cambodia"),
    "canada": ("CA", "Canada"),
    "cayman-islands": ("KY", "Cayman Islands"),
    "chad": ("TD", "Chad"),
    "chile": ("CL", "Chile"),
    "colombia": ("CO", "Colombia"),
    "costa-rica": ("CR", "Costa Rica"),
    "croatia": ("HR", "Croatia"),
    "cyprus": ("CY", "Cyprus"),
    "czech-republic": ("CZ", "Czech Republic"),
    "democratic-republic-of-the-congo": ("CD", "DR Congo"),
    "denmark": ("DK", "Denmark"),
    "dominican-republic": ("DO", "Dominican Republic"),
    "ecuador": ("EC", "Ecuador"),
    "egypt": ("EG", "Egypt"),
    "el-salvador": ("SV", "El Salvador"),
    "equatorial-guinea": ("GQ", "Equatorial Guinea"),
    "estonia": ("EE", "Estonia"),
    "eswatini": ("SZ", "Eswatini"),
    "ethiopia": ("ET", "Ethiopia"),
    "finland": ("FI", "Finland"),
    "france": ("FR", "France"),
    "gabon": ("GA", "Gabon"),
    "georgia": ("GE", "Georgia"),
    "ghana": ("GH", "Ghana"),
    "gibraltar": ("GI", "Gibraltar"),
    "greece": ("GR", "Greece"),
    "greenland": ("GL", "Greenland"),
    "guatemala": ("GT", "Guatemala"),
    "guernsey": ("GG", "Guernsey"),
    "guyana": ("GY", "Guyana"),
    "honduras": ("HN", "Honduras"),
    "hong-kong-sar": ("HK", "Hong Kong SAR"),
    "hungary": ("HU", "Hungary"),
    "iceland": ("IS", "Iceland"),
    "india": ("IN", "India"),
    "indonesia": ("ID", "Indonesia"),
    "iraq": ("IQ", "Iraq"),
    "ireland": ("IE", "Ireland"),
    "isle-of-man": ("IM", "Isle of Man"),
    "israel": ("IL", "Israel"),
    "italy": ("IT", "Italy"),
    "ivory-coast": ("CI", "Côte d'Ivoire"),
    "jamaica": ("JM", "Jamaica"),
    "japan": ("JP", "Japan"),
    "jersey": ("JE", "Jersey"),
    "jordan": ("JO", "Jordan"),
    "kazakhstan": ("KZ", "Kazakhstan"),
    "kenya": ("KE", "Kenya"),
    "kosovo": ("XK", "Kosovo"),
    "kuwait": ("KW", "Kuwait"),
    "lao-pdr": ("LA", "Laos"),
    "latvia": ("LV", "Latvia"),
    "lebanon": ("LB", "Lebanon"),
    "liechtenstein": ("LI", "Liechtenstein"),
    "lithuania": ("LT", "Lithuania"),
    "luxembourg": ("LU", "Luxembourg"),
    "macau-sar": ("MO", "Macau SAR"),
    "madagascar": ("MG", "Madagascar"),
    "malaysia": ("MY", "Malaysia"),
    "malta": ("MT", "Malta"),
    "mauritania": ("MR", "Mauritania"),
    "mauritius": ("MU", "Mauritius"),
    "mexico": ("MX", "Mexico"),
    "moldova": ("MD", "Moldova"),
    "mongolia": ("MN", "Mongolia"),
    "montenegro": ("ME", "Montenegro"),
    "morocco": ("MA", "Morocco"),
    "mozambique": ("MZ", "Mozambique"),
    "myanmar": ("MM", "Myanmar"),
    "netherlands": ("NL", "Netherlands"),
    "new-caledonia": ("NC", "New Caledonia"),
    "new-zealand": ("NZ", "New Zealand"),
    "nicaragua": ("NI", "Nicaragua"),
    "nigeria": ("NG", "Nigeria"),
    "north-macedonia": ("MK", "North Macedonia"),
    "norway": ("NO", "Norway"),
    "oman": ("OM", "Oman"),
    "pakistan": ("PK", "Pakistan"),
    "palestinian-territories": ("PS", "Palestinian Territories"),
    "panama": ("PA", "Panama"),
    "papua-new-guinea": ("PG", "Papua New Guinea"),
    "paraguay": ("PY", "Paraguay"),
    "peoples-republic-of-china": ("CN", "China"),
    "peru": ("PE", "Peru"),
    "philippines": ("PH", "Philippines"),
    "poland": ("PL", "Poland"),
    "portugal": ("PT", "Portugal"),
    "puerto-rico": ("PR", "Puerto Rico"),
    "qatar": ("QA", "Qatar"),
    "republic-of-cameroon": ("CM", "Cameroon"),
    "republic-of-congo": ("CG", "Republic of the Congo"),
    "republic-of-korea": ("KR", "South Korea"),
    "republic-of-liberia": ("LR", "Liberia"),
    "republic-of-namibia": ("NA", "Namibia"),
    "republic-of-uzbekistan": ("UZ", "Uzbekistan"),
    "romania": ("RO", "Romania"),
    "rwanda": ("RW", "Rwanda"),
    "saint-lucia": ("LC", "Saint Lucia"),
    "saudi-arabia": ("SA", "Saudi Arabia"),
    "senegal": ("SN", "Senegal"),
    "serbia": ("RS", "Serbia"),
    "singapore": ("SG", "Singapore"),
    "slovak-republic": ("SK", "Slovakia"),
    "slovenia": ("SI", "Slovenia"),
    "south-africa": ("ZA", "South Africa"),
    "sweden": ("SE", "Sweden"),
    "switzerland": ("CH", "Switzerland"),
    "taiwan": ("TW", "Taiwan"),
    "tanzania": ("TZ", "Tanzania"),
    "thailand": ("TH", "Thailand"),
    "the-bahamas": ("BS", "The Bahamas"),
    "timor-leste": ("TL", "Timor-Leste"),
    "trinidad-and-tobago": ("TT", "Trinidad and Tobago"),
    "tunisia": ("TN", "Tunisia"),
    "turkey": ("TR", "Türkiye"),
    "uganda": ("UG", "Uganda"),
    "ukraine": ("UA", "Ukraine"),
    "united-arab-emirates": ("AE", "United Arab Emirates"),
    "united-states": ("US", "United States"),
    "uruguay": ("UY", "Uruguay"),
    "venezuela": ("VE", "Venezuela"),
    "vietnam": ("VN", "Vietnam"),
    "zambia": ("ZM", "Zambia"),
}

# Authorities with no PwC page. Single, manually verified pointer entry each.
SPECIAL = {
    "RU": {
        "name": "Russia",
        "title": "Russia — Federal Tax Service (official portal)",
        "url": "https://www.nalog.gov.ru/eng/",
        "note": (
            "PwC Worldwide Tax Summaries withdrew its Russia coverage in 2022, so "
            "this points at the Federal Tax Service of Russia's official English "
            "portal instead."
        ),
        "leaf": "tax-authority",
    },
}

# Reference-only summaries. NO legal generalisation, NO day counts, NO articles.
LEAVES = {
    "residence": {
        "leaf": "residence",
        "id": "residence",
        "article": "Residence",
        "title": "{name} — individual tax residence (PwC Worldwide Tax Summaries)",
        "summary": (
            "Cited reference card for individual tax-residence rules in {name}, "
            "published by PwC Worldwide Tax Summaries. Reference-only: Taixable's "
            "deterministic engine does not model {name}'s residence tests — open "
            "the linked source for the authoritative, current rules."
        ),
    },
    "income-tax": {
        "leaf": "taxes-on-personal-income",
        "id": "income-tax",
        "article": "Personal income tax",
        "title": "{name} — personal income tax (PwC Worldwide Tax Summaries)",
        "summary": (
            "Cited reference card for personal income tax in {name}, published by "
            "PwC Worldwide Tax Summaries. Reference-only: Taixable's deterministic "
            "engine does not compute {name} tax — open the linked source for "
            "current rates, bands and reliefs."
        ),
    },
}


def _validate_map() -> None:
    isos = [iso for iso, _ in TERRITORIES.values()]
    dups = {i for i in isos if isos.count(i) > 1}
    if dups:
        raise SystemExit(f"duplicate ISO codes in TERRITORIES: {sorted(dups)}")
    for iso, name in TERRITORIES.values():
        if len(iso) != 2 or not iso.isalpha() or not iso.isupper():
            raise SystemExit(f"bad ISO code: {iso!r}")
        if not name:
            raise SystemExit(f"empty display name for {iso}")


def _fetch(url: str) -> str | None:
    """Return the page body if HTTP 200, else ``None`` (entry is skipped)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed host
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - network failure -> skip, never invent
        print(f"  skip ({exc}): {url}", file=sys.stderr)
        return None


def _entry(citation_id, jurisdiction, title, article, summary, url, body, today):
    return {
        "citation_id": citation_id,
        "jurisdiction": jurisdiction,
        "title": title,
        "article": article,
        "summary": summary,
        "content_type": "curated_reference",
        "effective_date": today,
        "source_url": url,
        "package_version": PACKAGE_VERSION,
        "generator_version": GENERATOR_VERSION,
        "retrieved_at": today,
        "source_content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    _validate_map()
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    existing = {e["citation_id"] for e in doc["legislation"]}
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")

    added: list[dict] = []
    territories_ok = 0
    for slug, (iso, name) in sorted(TERRITORIES.items()):
        leaf_ok = 0
        for spec in LEAVES.values():
            cid = f"{iso}#{spec['id']}"
            if cid in existing:
                continue
            url = PWC.format(slug=slug, leaf=spec["leaf"])
            body = _fetch(url)
            if body is None:
                continue
            added.append(
                _entry(
                    cid,
                    iso,
                    spec["title"].format(name=name),
                    spec["article"],
                    spec["summary"].format(name=name),
                    url,
                    body,
                    today,
                )
            )
            existing.add(cid)
            leaf_ok += 1
        if leaf_ok:
            territories_ok += 1
        print(f"  {iso} {name}: {leaf_ok}/2 pages")

    for iso, spec in SPECIAL.items():
        cid = f"{iso}#{spec['leaf']}"
        if cid in existing:
            continue
        body = _fetch(spec["url"])
        if body is None:
            print(f"  skip special {iso}: source unreachable", file=sys.stderr)
            continue
        e = _entry(
            cid,
            iso,
            spec["title"],
            "Tax authority",
            f"Official tax-authority reference for {spec['name']}. {spec['note']} "
            "Reference-only: Taixable's deterministic engine does not compute "
            f"{spec['name']} tax.",
            spec["url"],
            body,
            today,
        )
        added.append(e)
        existing.add(cid)
        territories_ok += 1
        print(f"  {iso} {spec['name']}: special pointer")

    doc["legislation"].extend(added)
    DATA.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nAdded {len(added)} entries across {territories_ok} territories.")
    print(f"Total corpus entries now: {len(doc['legislation'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
