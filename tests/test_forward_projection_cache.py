"""Forward projection cache fingerprint includes historical window."""

from components.macro_engine import (
    forward_projection_cache_fingerprint,
    historical_window_fingerprint,
)

import portfolio_core as core


def test_historical_window_fingerprint_changes_with_dates():
    a = historical_window_fingerprint("2015-01-01", "2019-12-31")
    b = historical_window_fingerprint("2022-01-01", "2025-12-31")
    assert a != b


def test_forward_cache_fingerprint_includes_dates_and_macro():
    assumptions = core.ForwardMacroAssumptions(
        rate_environment="Stable Rates",
        inflation="Moderate Inflation",
        recession_probability=0.25,
        valuation="Fair Value",
        economic_regime="Expansion",
    )
    fp_old = forward_projection_cache_fingerprint(
        "2015-01-01", "2019-12-31", assumptions, years=5.0, n_assets=4
    )
    fp_new = forward_projection_cache_fingerprint(
        "2022-01-01", "2025-12-31", assumptions, years=5.0, n_assets=4
    )
    assert fp_old != fp_new
