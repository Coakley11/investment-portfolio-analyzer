"""Tests for live macro classification (no network)."""

from __future__ import annotations

from components.macro_data import (
    MacroSnapshot,
    classify_economic_regime,
    classify_inflation,
    classify_rate_environment,
    classify_recession_probability,
    map_snapshot_to_assumptions,
)


def _snap(**kwargs) -> MacroSnapshot:
    base = dict(
        federal_funds=5.0,
        treasury_10y=4.2,
        treasury_3m=4.5,
        cpi_yoy=2.5,
        core_cpi_yoy=2.8,
        unemployment=4.0,
        inflation_expectations_10y=2.2,
        as_of_date="2025-01-01",
        source="defaults",
    )
    base.update(kwargs)
    return MacroSnapshot(**base)


def test_classify_inflation_buckets():
    assert classify_inflation(-0.5) == "Deflation"
    assert classify_inflation(1.5) == "Low Inflation"
    assert classify_inflation(3.0) == "Moderate Inflation"
    assert classify_inflation(5.0) == "High Inflation"


def test_classify_rate_environment_trend():
    assert (
        classify_rate_environment(5.0, federal_funds_3m_ago=4.0, treasury_10y=4.0) == "Rising Rates"
    )
    assert (
        classify_rate_environment(4.5, federal_funds_3m_ago=5.2, treasury_10y=4.0) == "Falling Rates"
    )
    assert (
        classify_rate_environment(5.0, federal_funds_3m_ago=4.8, treasury_10y=4.5)
        == "High Rate Environment"
    )


def test_map_snapshot_produces_valid_assumptions():
    m = map_snapshot_to_assumptions(_snap())
    assert m.inflation in ("Low Inflation", "Moderate Inflation", "High Inflation", "Deflation")
    assert m.rate_environment in (
        "Falling Rates",
        "Stable Rates",
        "Rising Rates",
        "High Rate Environment",
    )
    assert 5 <= m.recession_probability <= 70


def test_inverted_yield_curve_raises_recession_prob():
    low = classify_recession_probability(4.0, yield_spread_10y_3m=1.0, unemployment_6m_ago=3.8)
    high = classify_recession_probability(4.0, yield_spread_10y_3m=-0.5, unemployment_6m_ago=3.8)
    assert high > low


def test_stagflation_regime():
    assert (
        classify_economic_regime(5.2, 4.5, yield_spread_10y_3m=0.2) == "Stagflation"
    )
