"""Central market data provider — fetch once, reuse everywhere."""

from __future__ import annotations

import hashlib
import json
import pickle
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd

from investment_market_data import config as cfg
from investment_market_data.diagnostics import (
    record_dedupe_wait,
    record_hit,
    record_miss,
    record_yahoo_request,
)
from investment_market_data import yahoo as yf_raw

T = TypeVar("T")

_SESSION_ROOT_KEY = "_inv_market_data_cache_v1"
_inflight_lock = threading.Lock()
_inflight_events: dict[str, threading.Event] = {}


@dataclass(frozen=True)
class EtfHoldingsBundle:
    holdings: pd.DataFrame
    sectors: pd.DataFrame
    meta: dict[str, Any]
    source: str


class MarketDataProvider:
    """Single entry point for Yahoo-backed investment market data."""

    def clear_all_caches(self) -> None:
        """Drop session, process, and disk cache entries (not Streamlit ``cache_data``)."""
        bucket = _session_bucket()
        if bucket is not None:
            bucket.clear()
        _process_session.clear()
        if cfg.DISK_CACHE_ENABLED and cfg.CACHE_ROOT.is_dir():
            for path in cfg.CACHE_ROOT.rglob("*"):
                if path.is_file():
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def get_price_history(
        self,
        tickers: list[str],
        start: str,
        end: str | None = None,
    ) -> pd.DataFrame:
        clean = tuple(yf_raw.normalize_symbol(t) for t in tickers if str(t).strip())
        if not clean:
            raise ValueError("At least one ticker is required.")
        cache_key = f"hist|{','.join(clean)}|{start}|{end or ''}"

        def _load() -> pd.DataFrame:
            hit = _session_get(cache_key, cfg.HISTORICAL_TTL_SECONDS)
            if hit is not None:
                record_hit(layer="session", kind="history", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL)
                return hit
            disk = _disk_load_history(cache_key)
            if disk is not None:
                _session_set(cache_key, disk, cfg.HISTORICAL_TTL_SECONDS)
                record_hit(layer="disk", kind="history", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL)
                return disk
            record_miss("history")
            frame = yf_raw.fetch_price_history_raw(list(clean), start, end)
            _session_set(cache_key, frame, cfg.HISTORICAL_TTL_SECONDS)
            _disk_save_history(cache_key, frame)
            return frame

        return _dedupe(cache_key, _load)

    def get_historical_prices(
        self,
        tickers: list[str],
        start: str,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Alias for ``get_price_history`` (stable name for future modules)."""
        return self.get_price_history(tickers, start, end)

    def get_latest_quote(self, symbol: str) -> tuple[float | None, str]:
        sym = yf_raw.normalize_symbol(symbol)
        if not sym or sym in yf_raw._SKIP_SPOT:
            return None, ""
        cache_key = f"spot|{sym}"

        def _load() -> tuple[float | None, str]:
            cached = _session_get(cache_key, cfg.SPOT_PRICE_TTL_SECONDS)
            if cached is not None:
                record_hit(layer="session", kind="spot", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL)
                return cached
            record_miss("spot")
            px, src = yf_raw.fetch_latest_quote_raw(sym)
            if px is None:
                simple = yf_raw.batch_spot_prices_raw([sym]).get(sym)
                if simple is not None and simple > 0:
                    px, src = float(simple), "yfinance_batch_close"
            pair = (px, src)
            _session_set(cache_key, pair, cfg.SPOT_PRICE_TTL_SECONDS)
            return pair

        return _dedupe(cache_key, _load)

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, tuple[float | None, str]]:
        syms = [yf_raw.normalize_symbol(s) for s in symbols if str(s).strip()]
        syms = [s for s in dict.fromkeys(syms) if s and s not in yf_raw._SKIP_SPOT]
        if not syms:
            return {}
        missing: list[str] = []
        out: dict[str, tuple[float | None, str]] = {}
        for sym in syms:
            key = f"spot|{sym}"
            cached = _session_get(key, cfg.SPOT_PRICE_TTL_SECONDS)
            if cached is not None:
                record_hit(layer="session", kind="spot", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL)
                out[sym] = cached
            else:
                missing.append(sym)
        if missing:
            batch = yf_raw.batch_spot_prices_raw(missing)
            for sym in missing:
                px = batch.get(sym)
                if px is not None and px > 0:
                    pair = (float(px), "yfinance_batch_close")
                else:
                    pair = yf_raw.fetch_latest_quote_raw(sym)
                _session_set(f"spot|{sym}", pair, cfg.SPOT_PRICE_TTL_SECONDS)
                out[sym] = pair
        return out

    def get_spot_price(self, symbol: str) -> float | None:
        """Simple spot price (ETF underlying column compatibility)."""
        px, _ = self.get_latest_quote(symbol)
        return px

    def get_trailing_pe(self, symbol: str) -> float | None:
        sym = yf_raw.normalize_symbol(symbol)
        cache_key = f"pe|{sym}"

        def _load() -> float | None:
            cached = _session_get(cache_key, cfg.TICKER_INFO_TTL_SECONDS)
            if cached is not None:
                record_hit(layer="session", kind="pe", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL)
                return cached
            record_miss("pe")
            val = yf_raw.fetch_trailing_pe_raw(sym)
            _session_set(cache_key, val, cfg.TICKER_INFO_TTL_SECONDS)
            return val

        return _dedupe(cache_key, _load)

    def get_etf_bundle(self, ticker: str) -> EtfHoldingsBundle:
        sym = yf_raw.normalize_symbol(ticker)
        if not sym:
            raise ValueError("Ticker required")
        cache_key = f"etf|{sym}"

        def _load() -> EtfHoldingsBundle:
            cached = _session_get(cache_key, cfg.ETF_HOLDINGS_TTL_SECONDS)
            if cached is not None:
                record_hit(layer="session", kind="etf", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL * 3)
                return cached
            disk = _disk_load_etf(sym)
            if disk is not None:
                _session_set(cache_key, disk, cfg.ETF_HOLDINGS_TTL_SECONDS)
                record_hit(layer="disk", kind="etf", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL * 3)
                return disk
            record_miss("etf")
            bundle = self._fetch_etf_bundle_live(sym)
            _session_set(cache_key, bundle, cfg.ETF_HOLDINGS_TTL_SECONDS)
            _disk_save_etf(sym, bundle)
            return bundle

        return _dedupe(cache_key, _load)

    def get_etf_bundles(self, tickers: list[str]) -> dict[str, EtfHoldingsBundle]:
        out: dict[str, EtfHoldingsBundle] = {}
        for t in tickers:
            sym = yf_raw.normalize_symbol(t)
            if sym:
                out[sym] = self.get_etf_bundle(sym)
        return out

    def get_stock_splits(self, symbol: str) -> pd.Series | None:
        sym = yf_raw.normalize_symbol(symbol)
        cache_key = f"splits|{sym}"

        def _load() -> pd.Series | None:
            cached = _session_get(cache_key, cfg.HISTORICAL_TTL_SECONDS)
            if cached is not None:
                record_hit(layer="session", kind="splits", bytes_saved=cfg.ESTIMATED_BYTES_PER_YAHOO_CALL)
                return cached
            record_miss("splits")
            splits = yf_raw.fetch_stock_splits_raw(sym)
            _session_set(cache_key, splits, cfg.HISTORICAL_TTL_SECONDS)
            return splits

        return _dedupe(cache_key, _load)

    def _fetch_etf_bundle_live(self, sym: str) -> EtfHoldingsBundle:
        import etf_holdings as eh

        try:
            meta, holdings_df, sectors_df = yf_raw.fetch_etf_fund_data_raw(sym)
            if not holdings_df.empty:
                symbols = [
                    str(r.get("symbol") or "")
                    for _, r in holdings_df.iterrows()
                    if str(r.get("symbol") or "")
                ]
                prices = yf_raw.batch_spot_prices_raw(symbols)
                holdings_df = holdings_df.copy()
                holdings_df["price"] = holdings_df["symbol"].map(
                    lambda s: prices.get(yf_raw.normalize_symbol(str(s)))
                )
                return EtfHoldingsBundle(
                    holdings=holdings_df,
                    sectors=sectors_df,
                    meta=meta,
                    source="live",
                )
        except Exception:
            pass

        static = eh._STATIC_HOLDINGS.get(sym)
        static_meta = eh._STATIC_META.get(sym, {})
        if static:
            meta = dict(static_meta)
            meta.setdefault("name", static_meta.get("name", sym))
            return EtfHoldingsBundle(
                holdings=pd.DataFrame(static),
                sectors=pd.DataFrame(),
                meta=meta,
                source="sample",
            )
        return EtfHoldingsBundle(
            holdings=pd.DataFrame(),
            sectors=pd.DataFrame(),
            meta={"name": sym},
            source="unavailable",
        )


_provider: MarketDataProvider | None = None


def get_market_data_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        _provider = MarketDataProvider()
    return _provider


def reset_market_data_provider_for_tests() -> None:
    global _provider
    _provider = None


def invalidate_all_market_data_caches() -> None:
    """
    Clear provider session, in-process, and disk caches.

    Streamlit ``@st.cache_data`` wrappers (e.g. in ``streamlit_app``) must be
    cleared separately — see ``refresh_market_data_sidebar``.
    """
    get_market_data_provider().clear_all_caches()


def _dedupe(key: str, fn: Callable[[], T]) -> T:
    with _inflight_lock:
        existing = _inflight_events.get(key)
        if existing is not None:
            event = existing
            owner = False
        else:
            event = threading.Event()
            _inflight_events[key] = event
            owner = True
    if not owner:
        record_dedupe_wait(key.split("|", 1)[0])
        event.wait(timeout=120.0)
        return fn()
    try:
        return fn()
    finally:
        with _inflight_lock:
            _inflight_events.pop(key, None)
            event.set()


def _session_bucket() -> dict[str, Any] | None:
    try:
        import streamlit as st

        raw = st.session_state.get(_SESSION_ROOT_KEY)
        if isinstance(raw, dict):
            return raw
        bucket: dict[str, Any] = {}
        st.session_state[_SESSION_ROOT_KEY] = bucket
        return bucket
    except Exception:
        return None


_process_session: dict[str, Any] = {}


def _fallback_bucket() -> dict[str, Any]:
    return _process_session


def _session_get(key: str, ttl_seconds: float) -> Any | None:
    now = time.time()
    for bucket in (_session_bucket(), _fallback_bucket()):
        if bucket is None:
            continue
        entry = bucket.get(key)
        if not isinstance(entry, dict):
            continue
        exp = float(entry.get("expires", 0))
        if exp >= now:
            return entry.get("value")
    return None


def _session_set(key: str, value: Any, ttl_seconds: float) -> None:
    entry = {"expires": time.time() + ttl_seconds, "value": value}
    bucket = _session_bucket()
    if bucket is not None:
        bucket[key] = entry
    _fallback_bucket()[key] = entry


def _disk_load_etf(sym: str) -> EtfHoldingsBundle | None:
    if not cfg.DISK_CACHE_ENABLED:
        return None
    path = cfg.CACHE_ROOT / "etf" / f"{sym}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cached_at = float(payload.get("cached_at", 0))
        if time.time() - cached_at > cfg.ETF_HOLDINGS_TTL_SECONDS:
            return None
        holdings = pd.DataFrame(payload.get("holdings") or [])
        sectors = pd.DataFrame(payload.get("sectors") or [])
        meta = dict(payload.get("meta") or {})
        source = str(payload.get("source") or "cache")
        return EtfHoldingsBundle(holdings=holdings, sectors=sectors, meta=meta, source=source)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _disk_save_etf(sym: str, bundle: EtfHoldingsBundle) -> None:
    if not cfg.DISK_CACHE_ENABLED:
        return
    try:
        out_dir = cfg.CACHE_ROOT / "etf"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "cached_at": time.time(),
            "source": bundle.source,
            "meta": bundle.meta,
            "holdings": bundle.holdings.to_dict(orient="records") if not bundle.holdings.empty else [],
            "sectors": bundle.sectors.to_dict(orient="records") if not bundle.sectors.empty else [],
        }
        (out_dir / f"{sym}.json").write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _history_disk_path(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:32]
    return cfg.CACHE_ROOT / "history" / f"{digest}.pkl"


def _disk_load_history(cache_key: str) -> pd.DataFrame | None:
    if not cfg.DISK_CACHE_ENABLED:
        return None
    path = _history_disk_path(cache_key)
    if not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            payload = pickle.load(fh)
        cached_at = float(payload.get("cached_at", 0))
        if time.time() - cached_at > cfg.HISTORICAL_TTL_SECONDS:
            return None
        frame = payload.get("frame")
        if isinstance(frame, pd.DataFrame):
            return frame
    except (OSError, pickle.PickleError, TypeError, ValueError):
        return None
    return None


def _disk_save_history(cache_key: str, frame: pd.DataFrame) -> None:
    if not cfg.DISK_CACHE_ENABLED:
        return
    try:
        path = _history_disk_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump({"cached_at": time.time(), "frame": frame}, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except OSError:
        pass

