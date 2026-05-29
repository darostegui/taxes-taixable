"""Request/response schemas for the tool endpoints.

These map closely onto the future MCP tool I/O schemas (spec Appendix A).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from taixable_copilot.models import Country, CustomerProfile


class AssessRequest(BaseModel):
    profile: CustomerProfile
    tax_year: int = Field(ge=2000, le=2100)


class ObligationOut(BaseModel):
    income_type: str
    source_country: str
    treaty_article: str
    rate: float
    relief: str
    citation_ids: list[str]


class DeadlineOut(BaseModel):
    jurisdiction: str
    description: str
    due_date: str
    citation_id: str | None = None


class CitationOut(BaseModel):
    id: str
    label: str
    url: str | None = None


class AssessmentOut(BaseModel):
    primary_residence: str
    residence_confidence: float
    obligations: list[ObligationOut]
    deadlines: list[DeadlineOut]
    citations: list[str]
    citation_details: list[CitationOut] = Field(default_factory=list)


class MemoRequest(BaseModel):
    profile: CustomerProfile
    tax_year: int = Field(ge=2000, le=2100)
    customer_token: str
    narrate: bool = True


class MemoResponse(BaseModel):
    memo_markdown: str
    narrative: str | None = None
    narrative_source: str = "deterministic"


class PersistDeadline(BaseModel):
    jurisdiction: str
    description: str
    due_date: str
    citation_id: str | None = None


class PersistRequest(BaseModel):
    approved: bool
    approved_by: str
    customer_token: str
    residence_country: Country
    display_label: str = ""
    tax_year: int = Field(ge=2000, le=2100)
    primary_residence: Country
    summary: str = ""
    deadlines: list[PersistDeadline] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)


class PersistResponse(BaseModel):
    case_id: int
