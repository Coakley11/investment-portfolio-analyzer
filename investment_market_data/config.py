"""TTL and path configuration for Investment market data caching."""

from __future__ import annotations

import os
from pathlib import Path

_TRUE = frozenset({"1", "true", "yes", "on"})


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in _TRUE


# TTLs (override via environment)
ETF_HOLDINGS_TTL_SECONDS = _env_float("INVESTMENT_MARKET_ETF_TTL_HOURS", 24.0) * 3600.0
SPOT_PRICE_TTL_SECONDS = _env_float("INVESTMENT_MARKET_SPOT_TTL_MINUTES", 15.0) * 60.0
HISTORICAL_TTL_SECONDS = _env_float("INVESTMENT_MARKET_HISTORICAL_TTL_HOURS", 24.0) * 3600.0
TICKER_INFO_TTL_SECONDS = _env_float("INVESTMENT_MARKET_INFO_TTL_HOURS", 6.0) * 3600.0

DISK_CACHE_ENABLED = _env_bool("INVESTMENT_MARKET_DISK_CACHE", True)
EGRESS_STRICT = _env_bool("INVESTMENT_EGRESS_STRICT", False)

CACHE_ROOT = Path(__file__).resolve().parents[1] / "data" / "market_data_cache"

# Rough bytes per avoided Yahoo quote/history call (for dev diagnostics only)
ESTIMATED_BYTES_PER_YAHOO_CALL = 12_000
