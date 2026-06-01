"""Fail-closed daily spend guard for the LLM advisor.

GCP Cloud Billing budgets only *alert*; they never stop spend. This module is the
actual enforcement: a lightweight, per-instance daily USD estimate that blocks
further model calls once a configurable cap is reached, so a runaway loop or abuse
cannot quietly burn the hackathon budget.

Design notes / limitations (intentional for a hackathon, no external dependency):
- The counter is **per process instance** and held in memory. With N Cloud Run
  instances the worst-case spend is ``N x cap``. We bound N by keeping Cloud Run
  ``max-instances`` low (≈4) and rely on the Cloud Billing budget as the financial
  backstop. A cross-instance hard cap would need Firestore/Redis — deliberately
  avoided here.
- The per-call cost is a conservative *estimate* (we charge before the call and do
  not refund), so the guard errs towards stopping early rather than overspending.
- The window resets on a UTC date change.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

_DEFAULT_DAILY_USD_CAP = 4.0
_DEFAULT_EST_USD_PER_CALL = 0.03

_lock = threading.Lock()
_state: dict[str, object] = {"date": None, "spent_usd": 0.0}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def daily_cap_usd() -> float:
    return _env_float("TAIXABLE_DAILY_USD_CAP", _DEFAULT_DAILY_USD_CAP)


def est_usd_per_call() -> float:
    return _env_float("TAIXABLE_EST_USD_PER_CALL", _DEFAULT_EST_USD_PER_CALL)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _reset_if_new_day_locked(today: str) -> None:
    if _state["date"] != today:
        _state["date"] = today
        _state["spent_usd"] = 0.0


def is_enabled() -> bool:
    """The guard is active unless the cap is explicitly set to 0 (disabled)."""
    return daily_cap_usd() > 0


def check_and_reserve() -> bool:
    """Reserve the cost of one model call.

    Returns ``True`` if the call is within today's budget (and records the
    reservation), ``False`` if it would exceed the cap (fail closed — caller must
    not call the model).
    """
    if not is_enabled():
        return True
    cap = daily_cap_usd()
    per_call = est_usd_per_call()
    today = _today()
    with _lock:
        _reset_if_new_day_locked(today)
        projected = float(_state["spent_usd"]) + per_call
        if projected > cap:
            return False
        _state["spent_usd"] = projected
        return True


def status() -> dict[str, object]:
    """Current guard state for observability (no secrets)."""
    cap = daily_cap_usd()
    today = _today()
    with _lock:
        _reset_if_new_day_locked(today)
        spent = float(_state["spent_usd"])
    return {
        "enabled": cap > 0,
        "date": today,
        "daily_cap_usd": cap,
        "est_usd_per_call": est_usd_per_call(),
        "spent_usd": round(spent, 4),
        "remaining_usd": round(max(0.0, cap - spent), 4),
    }


def _reset_for_tests() -> None:
    with _lock:
        _state["date"] = None
        _state["spent_usd"] = 0.0
