"""Regression tests for plan_total_cash coercion (cloud restore crash)."""

from __future__ import annotations

from components.investment_planning import (
    coerce_plan_integer,
    plan_integer_from_session,
    sanitize_plan_session_integers,
)


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_coerce_plan_integer_none_uses_fallback():
    assert coerce_plan_integer(None, 100_000) == 100_000


def test_coerce_plan_integer_empty_string():
    assert coerce_plan_integer("", 50_000) == 50_000


def test_coerce_plan_integer_formatted_currency():
    assert coerce_plan_integer("$125,500", 0) == 125_500


def test_coerce_plan_integer_float_string():
    assert coerce_plan_integer("75000.0", 0) == 75_000


def test_coerce_plan_integer_invalid():
    assert coerce_plan_integer("not-a-number", 42_000) == 42_000


def test_plan_integer_from_session_none_key_regression(monkeypatch):
    """Reproduces crash: key present with None from cloud full_session."""
    import components.investment_planning as ip

    ss = _FakeSessionState(plan_total_cash=None)

    class _St:
        session_state = ss

    monkeypatch.setattr(ip, "st", _St())
    assert ip.plan_integer_from_session("plan_total_cash", 100_000) == 100_000


def test_sanitize_plan_session_integers_clears_invalid():
    ss = _FakeSessionState(
        plan_total_cash=None,
        plan_emergency="20,500",
        plan_near_term="",
        plan_debt="bad",
    )
    defaults = {
        "plan_total_cash": 100_000,
        "plan_emergency": 20_000,
        "plan_near_term": 0,
        "plan_debt": 0,
        "plan_expenses": 0,
        "plan_monthly": 0,
    }
    sanitize_plan_session_integers(ss, defaults)
    assert ss["plan_total_cash"] == 100_000
    assert ss["plan_emergency"] == 20_500
    assert ss["plan_near_term"] == 0
    assert ss["plan_debt"] == 0
