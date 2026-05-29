"""FastAPI tool service consumed by the Google Agent Builder agent.

Three tools:
  * POST /tools/assess_obligations — residency + cross-border obligations + deadlines
  * POST /tools/generate_memo      — cited markdown memo (tokenized identity only)
  * POST /tools/persist_case       — write to the system of record, gated on approval

The persist tool enforces the human-in-the-loop gate: it returns 409 unless the
caller passes approved=true, so the agent can never silently commit a case.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from taixable_copilot.api.deps import Deps, build_default_deps
from taixable_copilot.api.schemas import (
    AssessmentOut,
    AssessRequest,
    MemoRequest,
    MemoResponse,
    PersistRequest,
    PersistResponse,
)
from taixable_copilot.db import repository as repo
from taixable_copilot.memo import render_memo
from taixable_copilot.obligations import Assessment, assess_obligations

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def _serialize(assessment: Assessment) -> AssessmentOut:
    return AssessmentOut(
        primary_residence=str(assessment.primary_residence),
        residence_confidence=assessment.residence_confidence,
        obligations=[
            {
                "income_type": str(o.income_type),
                "source_country": str(o.source_country),
                "treaty_article": o.treaty_article,
                "rate": o.rate,
                "relief": o.relief,
                "citation_ids": o.citation_ids,
            }
            for o in assessment.obligations
        ],
        deadlines=[
            {
                "jurisdiction": str(d.jurisdiction),
                "description": d.description,
                "due_date": d.due_date,
                "citation_id": d.citation_id,
            }
            for d in assessment.deadlines
        ],
        citations=assessment.citations,
    )


def create_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="Cross-Border Tax Copilot — Tools", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_WEB_DIR / "index.html")

    @app.post("/tools/assess_obligations", response_model=AssessmentOut)
    def assess(req: AssessRequest) -> AssessmentOut:
        try:
            assessment = assess_obligations(
                req.profile,
                req.tax_year,
                deps.residency_rules,
                deps.treaty_retriever,
                deps.rate_lookup,
            )
        except LookupError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _serialize(assessment)

    @app.post("/tools/generate_memo", response_model=MemoResponse)
    def generate_memo(req: MemoRequest) -> MemoResponse:
        try:
            assessment = assess_obligations(
                req.profile,
                req.tax_year,
                deps.residency_rules,
                deps.treaty_retriever,
                deps.rate_lookup,
            )
        except LookupError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return MemoResponse(memo_markdown=render_memo(assessment, req.customer_token))

    @app.post("/tools/persist_case", response_model=PersistResponse)
    def persist_case(req: PersistRequest) -> PersistResponse:
        if not req.approved:
            raise HTTPException(
                status_code=409,
                detail="Case not persisted: human approval required (approved=true).",
            )
        customer_id = repo.create_customer(
            deps.engine,
            customer_token=req.customer_token,
            residence_country=str(req.residence_country),
            display_label=req.display_label,
        )
        case_id = repo.create_case(
            deps.engine,
            customer_id=customer_id,
            tax_year=req.tax_year,
            primary_residence=str(req.primary_residence),
            summary=req.summary,
            approved_by=req.approved_by,
            deadlines=[d.model_dump() for d in req.deadlines],
            citation_ids=req.citation_ids,
        )
        return PersistResponse(case_id=case_id)

    return app


# Default ASGI app for `uvicorn taixable_copilot.api.app:app`.
app = create_app(build_default_deps())
