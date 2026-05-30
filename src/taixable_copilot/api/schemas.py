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


class EstimateOut(BaseModel):
    country: str
    role: str
    currency: str
    taxable_base: float
    gross_tax: float | None = None
    credit: float = 0.0
    net_tax: float | None = None
    method: str
    note: str
    citation_ids: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


class AssessmentOut(BaseModel):
    primary_residence: str
    residence_confidence: float
    obligations: list[ObligationOut]
    deadlines: list[DeadlineOut]
    estimates: list[EstimateOut] = Field(default_factory=list)
    citations: list[str]
    citation_details: list[CitationOut] = Field(default_factory=list)
    legislation: list[dict] = Field(default_factory=list)


class MemoRequest(BaseModel):
    profile: CustomerProfile
    tax_year: int = Field(ge=2000, le=2100)
    customer_token: str
    narrate: bool = True


class MemoResponse(BaseModel):
    memo_markdown: str
    narrative: str | None = None
    narrative_source: str = "deterministic"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    tax_year: int = Field(default=2025, ge=2000, le=2100)


class ChatResponse(BaseModel):
    reply: str
    available: bool = True
    used_tool: bool = False
    used_search: bool = False
    assessment: dict | None = None
    knowledge: list[dict] = Field(default_factory=list)
    search_meta: dict | None = None


class SearchRequest(BaseModel):
    query: str
    jurisdiction: str = ""
    k: int = Field(default=4, ge=1, le=20)


class SearchResponse(BaseModel):
    results: list[dict] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class HighlightResponse(BaseModel):
    found: bool
    citation_id: str
    title: str = ""
    jurisdiction: str = ""
    article: str = ""
    source_url: str = ""
    fragments: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class CoverageResponse(BaseModel):
    mode: str = "corpus"
    totals: dict = Field(default_factory=dict)
    by_jurisdiction: list[dict] = Field(default_factory=list)
    by_content_type: list[dict] = Field(default_factory=list)
    treaty_pairs: list[str] = Field(default_factory=list)
    rate_pairs: list[str] = Field(default_factory=list)


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
