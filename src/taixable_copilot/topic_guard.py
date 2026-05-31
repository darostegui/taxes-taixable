"""Deterministic topic guardrail: keep the advisor on tax & mobility.

Allow-by-default. A message is only refused when it carries a clear off-topic
signal (e.g. a request to write code, a poem or a recipe) AND contains no
tax/mobility keyword. This is a cheap, deterministic pre-filter that avoids
spending a Gemini call on obviously out-of-scope requests; the system
instruction is the second line of defence.

Design notes:
- Short messages (greetings, history-dependent follow-ups like "what about
  Spain?") are always allowed — they carry no off-topic signal and the
  conversation context disambiguates them.
- The blocklist is conservative and avoids bare tokens that legitimately appear
  in tax language (e.g. "tax code", "tax return") — it matches verbs of
  fabrication ("write me a script") rather than nouns alone.
"""

from __future__ import annotations

import re

# Tax / mobility vocabulary. If any of these appears, the message is on-topic.
_TAX_TERMS: tuple[str, ...] = (
    "tax", "taxes", "taxation", "taxable", "irpf", "vat", "gst", "paye",
    "hmrc", "agencia tributaria", "finanzamt", "fisc", "revenue",
    "residence", "residency", "resident", "domicile", "non-dom", "nondom",
    "expat", "expatriate", "relocat", "mobility", "immigration", "visa",
    "golden visa", "digital nomad", "nomad", "days present", "183",
    "treaty", "double taxation", "double-tax", "dta", "dtc", "withholding",
    "deduction", "allowance", "rebate", "credit", "exemption",
    "capital gain", "dividend", "interest income", "rental income", "rental",
    "pension", "retirement", "inheritance", "wealth tax", "exit tax",
    "social security", "payroll", "salary", "income", "self-employed",
    "filing", "deadline", "declaration", "return", "beckham", "impatriate",
    "nhr", "ificic", "ifici", "remittance", "territorial", "worldwide",
    "cross-border", "cross border", "familia numerosa", "regime", "band",
    "bracket", "rate", "euro", "eur", "gbp", "pound", "property tax",
    "stamp duty", "national insurance", "contribution", "estate",
)

# Off-topic signals: clear requests outside tax/mobility. Conservative on
# purpose — verbs of fabrication and unambiguous domains only.
_OFFTOPIC_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # Programming / software
        r"\b(write|generate|create|build|debug|fix|refactor|optimi[sz]e)\b[^.?!]*\b("
        r"code|script|program|programme|function|class|app|application|website|"
        r"webpage|api|endpoint|sql query|regex|algorithm|html|css|component)\b",
        r"\b(python|javascript|typescript|java|c\+\+|c#|golang|rust|kotlin|swift|"
        r"php|ruby on rails|react|angular|vue|node\.js|django|flask|kubernetes|"
        r"docker|terraform)\b",
        r"\b(stack trace|compile error|null pointer|segfault|leetcode|"
        r"unit test|merge conflict)\b",
        # Creative writing / entertainment
        r"\b(poem|haiku|sonnet|limerick|song|lyrics|short story|novel|"
        r"screenplay|fan ?fiction|joke|riddle|horoscope)\b",
        # Everyday-assistant domains clearly unrelated to tax/mobility
        r"\b(recipe|cook|bake|grocery list|workout|exercise plan|diet plan|"
        r"meal plan|dating advice|relationship advice)\b",
        # Misuse / jailbreak-ish
        r"\b(ignore (the |all )?(previous|above) instructions|system prompt|"
        r"hack into|sql injection|malware|keylogger)\b",
    )
)

_MIN_LEN = 16  # below this, treat as a greeting/short follow-up → allow


def _has_tax_term(text: str) -> bool:
    return any(term in text for term in _TAX_TERMS)


def _has_offtopic_signal(text: str) -> bool:
    return any(p.search(text) for p in _OFFTOPIC_PATTERNS)


def is_on_topic(message: str) -> bool:
    """Return True if the message is plausibly about tax / mobility.

    Allow-by-default: only an explicit off-topic signal with no tax/mobility
    keyword is refused.
    """
    text = (message or "").strip().lower()
    if len(text) < _MIN_LEN:
        return True
    if _has_tax_term(text):
        return True
    if _has_offtopic_signal(text):
        return False
    return True
