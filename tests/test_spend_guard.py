"""Tests for the app-layer daily spend guard (fail-closed LLM cost cap)."""

from __future__ import annotations

import pytest

from taixable_copilot import spend_guard


@pytest.fixture(autouse=True)
def _reset_guard() -> None:
    spend_guard._reset_for_tests()
    yield
    spend_guard._reset_for_tests()


def test_disabled_when_cap_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_DAILY_USD_CAP", "0")
    assert spend_guard.is_enabled() is False
    # Always allowed when disabled, never accumulates spend.
    for _ in range(100):
        assert spend_guard.check_and_reserve() is True
    assert spend_guard.status()["spent_usd"] == 0.0


def test_blocks_once_cap_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_DAILY_USD_CAP", "0.10")
    monkeypatch.setenv("TAIXABLE_EST_USD_PER_CALL", "0.03")
    # 0.03 * 3 = 0.09 <= 0.10 (allowed); 4th would be 0.12 > 0.10 (blocked).
    assert spend_guard.check_and_reserve() is True
    assert spend_guard.check_and_reserve() is True
    assert spend_guard.check_and_reserve() is True
    assert spend_guard.check_and_reserve() is False
    # Stays closed on subsequent attempts.
    assert spend_guard.check_and_reserve() is False


def test_reserve_is_fail_closed_before_overspending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAIXABLE_DAILY_USD_CAP", "0.05")
    monkeypatch.setenv("TAIXABLE_EST_USD_PER_CALL", "0.03")
    # First call reserves 0.03; second would be 0.06 > 0.05 → blocked, no spend added.
    assert spend_guard.check_and_reserve() is True
    assert spend_guard.check_and_reserve() is False
    assert spend_guard.status()["spent_usd"] == pytest.approx(0.03)


def test_resets_on_new_utc_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_DAILY_USD_CAP", "0.03")
    monkeypatch.setenv("TAIXABLE_EST_USD_PER_CALL", "0.03")
    monkeypatch.setattr(spend_guard, "_today", lambda: "2026-06-01")
    assert spend_guard.check_and_reserve() is True
    assert spend_guard.check_and_reserve() is False
    # New day → budget refreshes.
    monkeypatch.setattr(spend_guard, "_today", lambda: "2026-06-02")
    assert spend_guard.check_and_reserve() is True


def test_status_reports_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_DAILY_USD_CAP", "1.00")
    monkeypatch.setenv("TAIXABLE_EST_USD_PER_CALL", "0.25")
    spend_guard.check_and_reserve()
    s = spend_guard.status()
    assert s["enabled"] is True
    assert s["daily_cap_usd"] == 1.0
    assert s["spent_usd"] == pytest.approx(0.25)
    assert s["remaining_usd"] == pytest.approx(0.75)


def test_invalid_env_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAIXABLE_DAILY_USD_CAP", "not-a-number")
    monkeypatch.setenv("TAIXABLE_EST_USD_PER_CALL", "")
    assert spend_guard.daily_cap_usd() == spend_guard._DEFAULT_DAILY_USD_CAP
    assert spend_guard.est_usd_per_call() == spend_guard._DEFAULT_EST_USD_PER_CALL
