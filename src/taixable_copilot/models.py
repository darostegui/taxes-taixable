"""Core domain models for the cross-border tax copilot.

Pure data structures with no cloud dependencies so the whole domain layer is
unit-testable in isolation. These models are intentionally small and explicit so
they map cleanly onto future MCP tool input/output schemas (see spec Appendix A).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Country(StrEnum):
    ES = "ES"
    UK = "UK"
    DE = "DE"

    @staticmethod
    def pair(a: "Country", b: "Country") -> str:
        """Return a canonical, order-independent country-pair key, e.g. 'ES-UK'."""
        return "-".join(sorted((str(a), str(b))))


class IncomeType(StrEnum):
    EMPLOYMENT = "employment"
    RENTAL = "rental"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    PENSION = "pension"
    CAPITAL_GAIN = "capital_gain"


class IncomeSource(BaseModel):
    type: IncomeType
    source_country: Country
    amount: float = Field(ge=0)


class CustomerProfile(BaseModel):
    """A tax-relevant, PII-free customer profile (identity is tokenized upstream)."""

    residence_country: Country
    days_present: dict[Country, int] = Field(default_factory=dict)
    income: list[IncomeSource] = Field(default_factory=list)
    customer_token: str | None = None

    def foreign_sourced(self) -> list[IncomeSource]:
        """Income whose source country differs from the residence country."""
        return [i for i in self.income if i.source_country != self.residence_country]
