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
    ChatRequest,
    ChatResponse,
    MemoRequest,
    MemoResponse,
    PersistRequest,
    PersistResponse,
    SearchRequest,
    SearchResponse,
)
from taixable_copilot.chat import chat as run_chat
from taixable_copilot.citations import resolve_citations
from taixable_copilot.db import repository as repo
from taixable_copilot.guardrails import validate_citations
from taixable_copilot.llm import narrate_assessment
from taixable_copilot.memo import render_memo
from taixable_copilot.obligations import Assessment, assess_obligations

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def _reject_unknown_citations(deps: Deps, cited: list[str]) -> None:
    if deps.known_citation_ids is None:
        return
    ok, invalid = validate_citations(cited, deps.known_citation_ids)
    if not ok:
        raise HTTPException(
            status_code=422, detail=f"Unknown/hallucinated citation ids: {invalid}"
        )


def _serialize(assessment: Assessment, deps: Deps) -> AssessmentOut:
    details = resolve_citations(assessment.citations, deps.citation_index)
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
        estimates=[
            {
                "country": str(e.country),
                "role": e.role,
                "currency": e.currency,
                "taxable_base": e.taxable_base,
                "gross_tax": e.gross_tax,
                "credit": e.credit,
                "net_tax": e.net_tax,
                "method": e.method,
                "note": e.note,
                "citation_ids": e.citation_ids,
                "trace": e.trace,
            }
            for e in assessment.estimates
        ],
        citations=assessment.citations,
        citation_details=[
            {"id": c.id, "label": c.label, "url": c.url} for c in details
        ],
        legislation=(
            deps.legislation_lookup(assessment.citations)
            if deps.legislation_lookup
            else []
        ),
    )


def create_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="Cross-Border Tax Copilot — Tools", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/health/search")
    def health_search() -> dict:
        """Probe the Elasticsearch knowledge backend for the demo dashboard.

        Reports the active mode and whether a representative query returns
        grounded passages, so the hosted demo can show Elastic is live.
        """
        if deps.knowledge_search is None:
            return {"status": "disabled", "elastic": False}
        try:
            probe = deps.knowledge_search("183 day tax residency rule", jurisdiction=None)
        except Exception as exc:  # noqa: BLE001 - surface the failure, don't crash
            return {"status": "error", "elastic": False, "detail": str(exc)}
        meta = probe.get("meta", {})
        results = probe.get("results", [])
        mode = meta.get("mode", "unknown")
        return {
            "status": "ok" if results else "empty",
            "elastic": mode in {"elastic", "corpus_fallback"},
            "mode": mode,
            "retrieval": meta.get("retrieval"),
            "hits": len(results),
        }

    @app.post("/tools/search_knowledge", response_model=SearchResponse)
    def search_knowledge(req: SearchRequest) -> SearchResponse:
        if deps.knowledge_search is None:
            return SearchResponse(results=[], meta={"mode": "disabled"})
        out = deps.knowledge_search(
            req.query, k=req.k, jurisdiction=(req.jurisdiction or None)
        )
        _reject_unknown_citations(
            deps, [r["citation_id"] for r in out.get("results", []) if r.get("citation_id")]
        )
        return SearchResponse(results=out.get("results", []), meta=out.get("meta", {}))

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
                deps.tax_bands,
            )
        except LookupError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _reject_unknown_citations(deps, assessment.citations)
        return _serialize(assessment, deps)

    @app.post("/tools/generate_memo", response_model=MemoResponse)
    def generate_memo(req: MemoRequest) -> MemoResponse:
        try:
            assessment = assess_obligations(
                req.profile,
                req.tax_year,
                deps.residency_rules,
                deps.treaty_retriever,
                deps.rate_lookup,
                deps.tax_bands,
            )
        except LookupError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _reject_unknown_citations(deps, assessment.citations)
        markdown = render_memo(assessment, req.customer_token, deps.citation_index)
        narrative = None
        if req.narrate:
            narrative = narrate_assessment(
                assessment, req.customer_token, deps.citation_index
            )
        return MemoResponse(
            memo_markdown=markdown,
            narrative=narrative,
            narrative_source="gemini" if narrative else "deterministic",
        )

    @app.post("/chat", response_model=ChatResponse)
    def chat_endpoint(req: ChatRequest) -> ChatResponse:
        result = run_chat(
            deps,
            history=[m.model_dump() for m in req.history],
            message=req.message,
            tax_year=req.tax_year,
        )
        # Defensive: a tool-produced assessment can only contain engine citations,
        # but re-validate before returning to honour the no-hallucination contract.
        assessment = result.get("assessment")
        if assessment:
            cited = [s["id"] for s in assessment.get("sources", []) if s.get("id")]
            _reject_unknown_citations(deps, cited)
        # Knowledge passages are returned by the curated, allowlisted search; still
        # re-validate their ids against the known-citation guardrail.
        knowledge = result.get("knowledge") or []
        _reject_unknown_citations(
            deps, [p["citation_id"] for p in knowledge if p.get("citation_id")]
        )
        return ChatResponse(**result)

    @app.post("/tools/persist_case", response_model=PersistResponse)
    def persist_case(req: PersistRequest) -> PersistResponse:
        if not req.approved:
            raise HTTPException(
                status_code=409,
                detail="Case not persisted: human approval required (approved=true).",
            )
        cited = list(req.citation_ids) + [d.citation_id for d in req.deadlines if d.citation_id]
        _reject_unknown_citations(deps, cited)
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
