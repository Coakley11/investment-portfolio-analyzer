"""Tests for Phase 1 transparency helpers and health fingerprint lookback."""

from __future__ import annotations

import datetime as dt

from components.macro_engine import health_settings_fingerprint
from components.ui_helpers import format_historical_window_label, historical_window_years


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_format_historical_window_label():
    start = dt.date(2015, 1, 1)
    end = dt.date(2025, 6, 1)
    label = format_historical_window_label(start, end)
    assert "Jan 2015" in label
    assert "Jun 2025" in label
    assert "years" in label
    assert historical_window_years(start, end) > 10.0


def test_health_settings_fingerprint_includes_lookback(monkeypatch):
    import components.macro_engine as me

    fake = _FakeSessionState(
        {
            "health_rate_env": "Stable Rates",
            "health_recession": 25,
            "health_inflation": "Moderate Inflation",
            "health_valuation": "Fair Value",
            "health_regime": "Expansion",
            "health_objective": "balanced growth",
            "health_bond_min": 0,
            "analysis_start_date": dt.date(2020, 1, 1),
            "analysis_end_date": dt.date(2024, 12, 31),
        }
    )
    monkeypatch.setattr(me.st, "session_state", fake)
    fp1 = health_settings_fingerprint()
    fake["analysis_start_date"] = dt.date(2015, 1, 1)
    fp2 = health_settings_fingerprint()
    assert fp1 != fp2
    assert "2020-01-01" in fp1
    assert "2015-01-01" in fp2
