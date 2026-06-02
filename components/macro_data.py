"""Live U.S. macro data for Beginner Mode defaults — FRED public CSV + disk cache."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd

# FRED series (St. Louis Fed) — public graph CSV export, no API key required.
FRED_SERIES = {
    "federal_funds": "DFF",
    "treasury_10y": "DGS10",
    "treasury_3m": "DGS3MO",
    "cpi": "CPIAUCSL",
    "core_cpi": "CPILFESL",
    "unemployment": "UNRATE",
    "inflation_expectations_10y": "T10YIE",
}

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

_CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "macro_snapshot_cache.json"

# Sensible defaults when live data and cache are unavailable (approx. early-2025 U.S. levels).
_FALLBACK_VALUES: dict[str, float] = {
    "federal_funds": 5.25,
    "treasury_10y": 4.25,
    "treasury_3m": 4.35,
    "cpi_yoy": 2.8,
    "core_cpi_yoy": 3.0,
    "unemployment": 4.1,
    "inflation_expectations_10y": 2.3,
}


@dataclass(frozen=True)
class MacroSnapshot:
    federal_funds: float
    treasury_10y: float
    treasury_3m: float
    cpi_yoy: float
    core_cpi_yoy: float | None
    unemployment: float
    inflation_expectations_10y: float | None
    as_of_date: str
    source: str  # live | cache | defaults
    fetch_warnings: tuple[str, ...] = ()
    federal_funds_3m_ago: float | None = None
    unemployment_6m_ago: float | None = None

    @property
    def yield_curve_spread(self) -> float:
        """10Y minus 3M Treasury (percentage points). Negative = inverted."""
        return self.treasury_10y - self.treasury_3m

    @property
    def real_rate_proxy(self) -> float:
        """10Y Treasury minus CPI YoY (rough real-rate proxy)."""
        return self.treasury_10y - self.cpi_yoy


@dataclass(frozen=True)
class MacroAssumptionMapping:
    rate_environment: str
    inflation: str
    recession_probability: int
    valuation: str
    economic_regime: str


CUSTOM_SCENARIOS: dict[str, MacroAssumptionMapping] = {
    "high_inflation": MacroAssumptionMapping(
        rate_environment="High Rate Environment",
        inflation="High Inflation",
        recession_probability=30,
        valuation="Expensive",
        economic_regime="Stagflation",
    ),
    "recession": MacroAssumptionMapping(
        rate_environment="Falling Rates",
        inflation="Low Inflation",
        recession_probability=55,
        valuation="Cheap",
        economic_regime="Recession",
    ),
    "falling_rates": MacroAssumptionMapping(
        rate_environment="Falling Rates",
        inflation="Moderate Inflation",
        recession_probability=20,
        valuation="Fair Value",
        economic_regime="Recovery",
    ),
    "rising_rates": MacroAssumptionMapping(
        rate_environment="Rising Rates",
        inflation="Moderate Inflation",
        recession_probability=25,
        valuation="Fair Value",
        economic_regime="Slow Growth",
    ),
    "tech_boom": MacroAssumptionMapping(
        rate_environment="Stable Rates",
        inflation="Low Inflation",
        recession_probability=15,
        valuation="Expensive",
        economic_regime="AI / Tech Boom",
    ),
}

SCENARIO_LABELS: dict[str, str] = {
    "current": "Use Current Environment",
    "high_inflation": "High Inflation Scenario",
    "recession": "Recession Scenario",
    "falling_rates": "Falling Rates Scenario",
    "rising_rates": "Rising Rates Scenario",
    "tech_boom": "AI / Tech Boom Scenario",
}


def _fetch_fred_series(series_id: str, *, timeout: float = 12.0) -> pd.Series:
    url = FRED_CSV_URL.format(series_id=series_id)
    req = Request(url, headers={"User-Agent": "InvestmentPortfolioAnalyzer/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    frame = pd.read_csv(StringIO(raw))
    if frame.shape[1] < 2:
        raise ValueError(f"Unexpected FRED CSV for {series_id}")
    date_col, val_col = frame.columns[0], frame.columns[1]
    dates = pd.to_datetime(frame[date_col], errors="coerce")
    values = pd.to_numeric(frame[val_col], errors="coerce")
    series = pd.Series(values.values, index=dates).dropna()
    series = series[~series.index.isna()]
    if series.empty:
        raise ValueError(f"No observations for {series_id}")
    return series.sort_index()


def _latest_value(series: pd.Series) -> tuple[float, str]:
    val = float(series.iloc[-1])
    dt = series.index[-1]
    if hasattr(dt, "strftime"):
        as_of = dt.strftime("%Y-%m-%d")
    else:
        as_of = str(dt)[:10]
    return val, as_of


def _value_months_ago(series: pd.Series, months: int) -> float | None:
    if len(series) < 2:
        return None
    end = series.index[-1]
    try:
        target = end - pd.DateOffset(months=months)
    except Exception:
        return float(series.iloc[max(0, len(series) - months - 1)])
    prior = series[series.index <= target]
    if prior.empty:
        return float(series.iloc[0])
    return float(prior.iloc[-1])


def _cpi_yoy_percent(cpi_series: pd.Series) -> float:
    if len(cpi_series) < 13:
        raise ValueError("Need at least 13 monthly CPI observations for YoY")
    latest = float(cpi_series.iloc[-1])
    year_ago = float(cpi_series.iloc[-13])
    if year_ago <= 0:
        raise ValueError("Invalid CPI level")
    return (latest / year_ago - 1.0) * 100.0


def _read_disk_cache() -> dict[str, Any] | None:
    if not _CACHE_PATH.is_file():
        return None
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_disk_cache(payload: dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def _snapshot_from_dict(data: dict[str, Any], *, source: str) -> MacroSnapshot:
    return MacroSnapshot(
        federal_funds=float(data["federal_funds"]),
        treasury_10y=float(data["treasury_10y"]),
        treasury_3m=float(data["treasury_3m"]),
        cpi_yoy=float(data["cpi_yoy"]),
        core_cpi_yoy=float(data["core_cpi_yoy"]) if data.get("core_cpi_yoy") is not None else None,
        unemployment=float(data["unemployment"]),
        inflation_expectations_10y=(
            float(data["inflation_expectations_10y"])
            if data.get("inflation_expectations_10y") is not None
            else None
        ),
        as_of_date=str(data.get("as_of_date", "unknown")),
        source=source,
        fetch_warnings=tuple(data.get("fetch_warnings", ())),
        federal_funds_3m_ago=(
            float(data["federal_funds_3m_ago"]) if data.get("federal_funds_3m_ago") is not None else None
        ),
        unemployment_6m_ago=(
            float(data["unemployment_6m_ago"]) if data.get("unemployment_6m_ago") is not None else None
        ),
    )


def _fallback_snapshot(*, warnings: tuple[str, ...] = ()) -> MacroSnapshot:
    return MacroSnapshot(
        federal_funds=_FALLBACK_VALUES["federal_funds"],
        treasury_10y=_FALLBACK_VALUES["treasury_10y"],
        treasury_3m=_FALLBACK_VALUES["treasury_3m"],
        cpi_yoy=_FALLBACK_VALUES["cpi_yoy"],
        core_cpi_yoy=_FALLBACK_VALUES["core_cpi_yoy"],
        unemployment=_FALLBACK_VALUES["unemployment"],
        inflation_expectations_10y=_FALLBACK_VALUES["inflation_expectations_10y"],
        as_of_date="model default",
        source="defaults",
        fetch_warnings=warnings + ("Using built-in default macro values.",),
    )


def fetch_macro_snapshot_live() -> MacroSnapshot:
    """Download latest macro readings from FRED public CSV endpoints."""
    warnings: list[str] = []
    as_of_dates: list[str] = []
    values: dict[str, float] = {}
    optional: dict[str, float | None] = {"core_cpi_yoy": None, "inflation_expectations_10y": None}

    required_keys = ("federal_funds", "treasury_10y", "treasury_3m", "cpi", "unemployment")
    series_data: dict[str, pd.Series] = {}

    for key in required_keys:
        sid = FRED_SERIES[key]
        try:
            series_data[key] = _fetch_fred_series(sid)
            val, dt = _latest_value(series_data[key])
            values[key] = val
            as_of_dates.append(dt)
        except (URLError, OSError, ValueError, pd.errors.ParserError) as exc:
            warnings.append(f"Could not load {sid}: {exc}")

    if len(values) < len(required_keys):
        raise RuntimeError("Incomplete macro fetch")

    try:
        values["cpi_yoy"] = _cpi_yoy_percent(series_data["cpi"])
        _, cpi_dt = _latest_value(series_data["cpi"])
        as_of_dates.append(cpi_dt)
    except (ValueError, KeyError) as exc:
        raise RuntimeError(f"CPI YoY failed: {exc}") from exc

    for opt_key in ("core_cpi", "inflation_expectations_10y"):
        sid = FRED_SERIES[opt_key]
        try:
            s = _fetch_fred_series(sid)
            if opt_key == "core_cpi":
                optional["core_cpi_yoy"] = _cpi_yoy_percent(s)
            else:
                v, _ = _latest_value(s)
                optional["inflation_expectations_10y"] = v
        except (URLError, OSError, ValueError, pd.errors.ParserError):
            warnings.append(f"Optional series {sid} unavailable")

    as_of = max(as_of_dates) if as_of_dates else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fed_3m = _value_months_ago(series_data["federal_funds"], 3)
    unemp_6m = _value_months_ago(series_data["unemployment"], 6)
    snap = MacroSnapshot(
        federal_funds=values["federal_funds"],
        treasury_10y=values["treasury_10y"],
        treasury_3m=values["treasury_3m"],
        cpi_yoy=values["cpi_yoy"],
        core_cpi_yoy=optional["core_cpi_yoy"],
        unemployment=values["unemployment"],
        inflation_expectations_10y=optional["inflation_expectations_10y"],
        as_of_date=as_of,
        source="live",
        fetch_warnings=tuple(warnings),
        federal_funds_3m_ago=fed_3m,
        unemployment_6m_ago=unemp_6m,
    )
    _write_disk_cache({**asdict(snap), "cached_at": datetime.now(timezone.utc).isoformat()})
    return snap


def get_macro_snapshot(*, force_refresh: bool = False) -> MacroSnapshot:
    """Live FRED data with disk-cache and built-in fallback."""
    if not force_refresh:
        cached = _read_disk_cache()
        if cached and "federal_funds" in cached:
            try:
                return _snapshot_from_dict(cached, source="cache")
            except (KeyError, TypeError, ValueError):
                pass
    try:
        return fetch_macro_snapshot_live()
    except (RuntimeError, URLError, OSError) as exc:
        warnings = (f"Live macro data unavailable ({exc}).",)
        cached = _read_disk_cache()
        if cached and "federal_funds" in cached:
            try:
                snap = _snapshot_from_dict(cached, source="cache")
                return MacroSnapshot(
                    federal_funds=snap.federal_funds,
                    treasury_10y=snap.treasury_10y,
                    treasury_3m=snap.treasury_3m,
                    cpi_yoy=snap.cpi_yoy,
                    core_cpi_yoy=snap.core_cpi_yoy,
                    unemployment=snap.unemployment,
                    inflation_expectations_10y=snap.inflation_expectations_10y,
                    as_of_date=snap.as_of_date,
                    source="cache",
                    fetch_warnings=warnings + snap.fetch_warnings,
                    federal_funds_3m_ago=snap.federal_funds_3m_ago,
                    unemployment_6m_ago=snap.unemployment_6m_ago,
                )
            except (KeyError, TypeError, ValueError):
                pass
        return _fallback_snapshot(warnings=warnings)


def classify_inflation(cpi_yoy: float) -> str:
    if cpi_yoy < 0.0:
        return "Deflation"
    if cpi_yoy < 2.0:
        return "Low Inflation"
    if cpi_yoy < 4.0:
        return "Moderate Inflation"
    return "High Inflation"


def classify_rate_environment(
    federal_funds: float,
    *,
    federal_funds_3m_ago: float | None,
    treasury_10y: float,
) -> str:
    if federal_funds_3m_ago is not None:
        delta = federal_funds - federal_funds_3m_ago
        if delta >= 0.35:
            return "Rising Rates"
        if delta <= -0.35:
            return "Falling Rates"
    if federal_funds >= 4.25 and treasury_10y >= 3.75:
        return "High Rate Environment"
    return "Stable Rates"


def classify_recession_probability(
    unemployment: float,
    *,
    yield_spread_10y_3m: float,
    unemployment_6m_ago: float | None,
) -> int:
    prob = 22
    if yield_spread_10y_3m < 0:
        prob += 18
    elif yield_spread_10y_3m < 0.5:
        prob += 8
    if unemployment >= 5.5:
        prob += 15
    elif unemployment >= 4.8:
        prob += 8
    elif unemployment < 4.0:
        prob -= 5
    if unemployment_6m_ago is not None and unemployment - unemployment_6m_ago >= 0.4:
        prob += 12
    return int(max(5, min(70, prob)))


def classify_economic_regime(
    unemployment: float,
    cpi_yoy: float,
    *,
    yield_spread_10y_3m: float,
) -> str:
    if cpi_yoy >= 4.0 and unemployment >= 5.0:
        return "Stagflation"
    if unemployment >= 6.0:
        return "Recession"
    if unemployment >= 5.0 or yield_spread_10y_3m < -0.5:
        return "Slow Growth"
    if unemployment < 4.2 and cpi_yoy < 3.5:
        return "Expansion"
    return "Slow Growth"


def classify_valuation(cpi_yoy: float, treasury_10y: float) -> str:
    """Rough macro-only valuation hint — beginners default to Fair Value when unclear."""
    if treasury_10y <= 2.0 and cpi_yoy < 2.5:
        return "Expensive"
    if treasury_10y >= 4.5 and cpi_yoy > 3.5:
        return "Expensive"
    if treasury_10y >= 5.0:
        return "Cheap"
    return "Fair Value"


def map_snapshot_to_assumptions(snapshot: MacroSnapshot) -> MacroAssumptionMapping:
    spread = snapshot.yield_curve_spread

    return MacroAssumptionMapping(
        rate_environment=classify_rate_environment(
            snapshot.federal_funds,
            federal_funds_3m_ago=snapshot.federal_funds_3m_ago,
            treasury_10y=snapshot.treasury_10y,
        ),
        inflation=classify_inflation(snapshot.cpi_yoy),
        recession_probability=classify_recession_probability(
            snapshot.unemployment,
            yield_spread_10y_3m=spread,
            unemployment_6m_ago=snapshot.unemployment_6m_ago,
        ),
        valuation=classify_valuation(snapshot.cpi_yoy, snapshot.treasury_10y),
        economic_regime=classify_economic_regime(
            snapshot.unemployment,
            snapshot.cpi_yoy,
            yield_spread_10y_3m=spread,
        ),
    )


def beginner_friendly_labels(mapping: MacroAssumptionMapping, snapshot: MacroSnapshot) -> dict[str, str]:
    rate_label = {
        "Falling Rates": "Low",
        "Stable Rates": "Moderate",
        "Rising Rates": "Elevated",
        "High Rate Environment": "High",
    }.get(mapping.rate_environment, "Moderate")

    inflation_label = {
        "Deflation": "Very low",
        "Low Inflation": "Low",
        "Moderate Inflation": "Moderate",
        "High Inflation": "High",
    }.get(mapping.inflation, "Moderate")

    if snapshot.unemployment < 4.2:
        labor = "Strong"
    elif snapshot.unemployment < 5.0:
        labor = "Moderate"
    else:
        labor = "Soft"

    if mapping.economic_regime in ("Recession", "Credit Crisis") or mapping.recession_probability >= 45:
        overall = "Cautious — stress-test your portfolio for tougher times."
    elif mapping.inflation == "High Inflation" or mapping.rate_environment == "High Rate Environment":
        overall = "Mixed — inflation and rates matter; diversification helps."
    elif mapping.economic_regime == "Expansion" and mapping.recession_probability <= 25:
        overall = "Moderately favorable for long-term investing."
    else:
        overall = "Neutral — stay diversified and review regularly."

    return {
        "interest": rate_label,
        "inflation": inflation_label,
        "labor": labor,
        "overall": overall,
    }


def apply_assumptions_to_session(
    mapping: MacroAssumptionMapping,
    *,
    scenario_id: str = "current",
) -> None:
    """Set Portfolio Health macro session keys (safe in Beginner Mode — no macro widgets)."""
    import streamlit as st

    st.session_state["health_rate_env"] = mapping.rate_environment
    st.session_state["health_inflation"] = mapping.inflation
    st.session_state["health_recession"] = int(mapping.recession_probability)
    st.session_state["health_valuation"] = mapping.valuation
    st.session_state["health_regime"] = mapping.economic_regime
    st.session_state["macro_scenario_id"] = scenario_id
    st.session_state["macro_scenario_mode"] = "current" if scenario_id == "current" else "custom"
    st.session_state["macro_auto_initialized"] = True
    _invalidate_health_cache()


def _invalidate_health_cache() -> None:
    import streamlit as st

    st.session_state["run_health"] = False
    for key in (
        "health_result",
        "health_result_fingerprint",
        "health_settings_fingerprint",
        "health_summary",
    ):
        st.session_state.pop(key, None)


def apply_current_environment_from_live(*, force_refresh: bool = False) -> MacroSnapshot:
    import streamlit as st

    snapshot = get_macro_snapshot(force_refresh=force_refresh)
    mapping = map_snapshot_to_assumptions(snapshot)
    apply_assumptions_to_session(mapping, scenario_id="current")
    st.session_state["macro_live_snapshot"] = snapshot
    return snapshot


def apply_custom_scenario(scenario_id: str) -> None:
    if scenario_id not in CUSTOM_SCENARIOS:
        raise KeyError(scenario_id)
    apply_assumptions_to_session(CUSTOM_SCENARIOS[scenario_id], scenario_id=scenario_id)


def ensure_beginner_macro_defaults() -> MacroSnapshot | None:
    """On first Beginner visit, populate macro keys from live/cache data."""
    import streamlit as st

    if st.session_state.get("macro_auto_initialized"):
        return None
    has_health = all(
        k in st.session_state
        for k in ("health_rate_env", "health_inflation", "health_recession")
    )
    if has_health:
        st.session_state["macro_auto_initialized"] = True
        st.session_state.setdefault("macro_scenario_id", "current")
        st.session_state.setdefault("macro_scenario_mode", "current")
        return None
    return apply_current_environment_from_live()


def macro_data_source_note(snapshot: MacroSnapshot) -> str:
    if snapshot.source == "live":
        return "Federal Reserve Economic Data (FRED), U.S. Bureau of Labor Statistics via FRED."
    if snapshot.source == "cache":
        return "Most recent saved macro readings (live update temporarily unavailable)."
    return "Built-in default assumptions (connect to refresh live data)."
