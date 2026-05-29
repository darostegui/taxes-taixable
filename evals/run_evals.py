#!/usr/bin/env python3
"""Run the golden-case evals against the corpus-backed tool service.

Checks, for each scenario: correct primary residence, expected number of
cross-border obligations, that all required citations appear, that deadlines land
in the right jurisdiction, and — critically — that EVERY citation the agent emits
resolves to a known corpus id (no hallucinated sources).

Usage:
    python evals/run_evals.py
Exit code is non-zero if any case fails (suitable for CI).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from taixable_copilot.api.app import create_app
from taixable_copilot.api.deps import Deps, _load_residency_rules
from taixable_copilot.db.repository import make_engine
from taixable_copilot.guardrails import validate_citations
from taixable_copilot.search import all_citation_ids, corpus_retrievers

CASES = Path(__file__).resolve().parent / "golden_cases.json"


def _client() -> TestClient:
    treaty, rate = corpus_retrievers()
    deps = Deps(
        residency_rules=_load_residency_rules(),
        treaty_retriever=treaty,
        rate_lookup=rate,
        engine=make_engine("sqlite:///:memory:"),
    )
    return TestClient(create_app(deps))


def run() -> int:
    client = _client()
    known = all_citation_ids()
    cases = json.loads(CASES.read_text())["cases"]
    failures: list[str] = []

    for case in cases:
        cid = case["id"]
        exp = case["expect"]
        r = client.post(
            "/tools/assess_obligations",
            json={"profile": case["profile"], "tax_year": case["tax_year"]},
        )
        if r.status_code != 200:
            failures.append(f"[{cid}] HTTP {r.status_code}: {r.text}")
            continue
        body = r.json()

        if body["primary_residence"] != exp["primary_residence"]:
            failures.append(
                f"[{cid}] residence {body['primary_residence']} != {exp['primary_residence']}"
            )
        if len(body["obligations"]) != exp["num_obligations"]:
            failures.append(
                f"[{cid}] obligations {len(body['obligations'])} != {exp['num_obligations']}"
            )
        missing = [c for c in exp["must_cite"] if c not in body["citations"]]
        if missing:
            failures.append(f"[{cid}] missing citations {missing}")
        juris = {d["jurisdiction"] for d in body["deadlines"]}
        if set(exp["deadline_jurisdictions"]) - juris:
            failures.append(
                f"[{cid}] deadline jurisdictions {juris} missing "
                f"{set(exp['deadline_jurisdictions']) - juris}"
            )
        ok, invalid = validate_citations(body["citations"], known)
        if not ok:
            failures.append(f"[{cid}] hallucinated citations {invalid}")

        status = "FAIL" if any(cid in f for f in failures) else "PASS"
        print(f"  {status}  {cid} — {case['description']}")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"All {len(cases)} golden cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
