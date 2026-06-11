"""Defensive historical lookback helpers — startup crash hotfix."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from components.ui_helpers import (
    format_historical_window_label,
    historical_window_years,
    normalize_historical_date,
)


def test_historical_window_years_mixed_string_and_date() -> None:
    years = historical_window_years("2020-01-01", dt.date(2025, 12, 31))
    assert years is not None
    assert years > 5.0


def test_historical_window_years_none_start_does_not_crash() -> None:
    assert historical_window_years(None, dt.date(2025, 12, 31)) is None
    assert format_historical_window_label(None, dt.date(2025, 12, 31)) == "unavailable"


def test_historical_window_years_end_before_start_normalized() -> None:
    assert historical_window_years("2025-01-01", dt.date(2020, 1, 1)) == 0.0
    assert historical_window_years(dt.date(2025, 6, 1), "2020-01-01") == 0.0


def test_normalize_historical_date_accepts_pandas_timestamp() -> None:
    ts = pd.Timestamp("2021-06-15")
    assert normalize_historical_date(ts) == dt.date(2021, 6, 15)


def test_normalize_historical_date_accepts_iso_string() -> None:
    assert normalize_historical_date("2019-03-01T00:00:00") == dt.date(2019, 3, 1)
