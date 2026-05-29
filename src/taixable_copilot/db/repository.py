"""System-of-record repository.

Tables are defined with SQLAlchemy Core so the same schema runs on SQLite
(local tests) and Cloud SQL for MySQL (production). All writes go through this
layer; `create_case` is only ever invoked after the human-approval gate in the
API.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
)
from sqlalchemy.pool import StaticPool

metadata = MetaData()

customers = Table(
    "customers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("customer_token", String(64), unique=True, nullable=False),
    Column("display_label", String(255)),  # synthetic, non-PII label for the UI
    Column("residence_country", String(2), nullable=False),
)

compliance_cases = Table(
    "compliance_cases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("customer_id", Integer, ForeignKey("customers.id"), nullable=False),
    Column("tax_year", Integer, nullable=False),
    Column("primary_residence", String(2), nullable=False),
    Column("summary", Text),
    Column("status", String(32), nullable=False, default="open"),
    Column("approved_by", String(255)),
    Column("created_at", DateTime, nullable=False),
)

case_deadlines = Table(
    "case_deadlines",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", Integer, ForeignKey("compliance_cases.id"), nullable=False),
    Column("jurisdiction", String(2), nullable=False),
    Column("description", String(512), nullable=False),
    Column("due_date", String(10), nullable=False),  # ISO date
    Column("citation_id", String(128)),
)

case_citations = Table(
    "case_citations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", Integer, ForeignKey("compliance_cases.id"), nullable=False),
    Column("citation_id", String(128), nullable=False),
)


def make_engine(url: str) -> Engine:
    """Create an engine and ensure the schema exists.

    For in-memory SQLite (tests) use a StaticPool so every checkout shares the
    single connection — otherwise each request would get an empty database.
    """
    if url == "sqlite:///:memory:" or url == "sqlite://":
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(url, future=True)
    metadata.create_all(engine)
    return engine


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_customer(
    engine: Engine, *, customer_token: str, residence_country: str, display_label: str = ""
) -> int:
    with engine.begin() as conn:
        existing = conn.execute(
            select(customers.c.id).where(customers.c.customer_token == customer_token)
        ).first()
        if existing:
            return int(existing[0])
        result = conn.execute(
            insert(customers).values(
                customer_token=customer_token,
                residence_country=residence_country,
                display_label=display_label,
            )
        )
        return int(result.inserted_primary_key[0])


def create_case(
    engine: Engine,
    *,
    customer_id: int,
    tax_year: int,
    primary_residence: str,
    summary: str,
    approved_by: str,
    deadlines: list[dict] | None = None,
    citation_ids: list[str] | None = None,
) -> int:
    """Persist an approved compliance case with its deadlines and citations."""
    with engine.begin() as conn:
        result = conn.execute(
            insert(compliance_cases).values(
                customer_id=customer_id,
                tax_year=tax_year,
                primary_residence=primary_residence,
                summary=summary,
                status="approved",
                approved_by=approved_by,
                created_at=_now(),
            )
        )
        case_id = int(result.inserted_primary_key[0])
        for d in deadlines or []:
            conn.execute(
                insert(case_deadlines).values(
                    case_id=case_id,
                    jurisdiction=d["jurisdiction"],
                    description=d["description"],
                    due_date=d["due_date"],
                    citation_id=d.get("citation_id"),
                )
            )
        for cid in citation_ids or []:
            conn.execute(insert(case_citations).values(case_id=case_id, citation_id=cid))
        return case_id


def get_case(engine: Engine, case_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(compliance_cases).where(compliance_cases.c.id == case_id)
        ).mappings().first()
        if not row:
            return None
        case = dict(row)
        case["deadlines"] = [
            dict(r)
            for r in conn.execute(
                select(case_deadlines).where(case_deadlines.c.case_id == case_id)
            ).mappings()
        ]
        case["citations"] = [
            r["citation_id"]
            for r in conn.execute(
                select(case_citations.c.citation_id).where(
                    case_citations.c.case_id == case_id
                )
            ).mappings()
        ]
        return case
