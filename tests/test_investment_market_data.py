"""Tests for centralized market data provider (no live network)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

import etf_holdings as eh
from investment_market_data import (
    get_market_data_diagnostics,
    get_market_data_provider,
    reset_market_data_diagnostics,
    reset_market_data_provider_for_tests,
)
from investment_market_data.provider import EtfHoldingsBundle


class TestMarketDataProvider(unittest.TestCase):
    def setUp(self) -> None:
        reset_market_data_provider_for_tests()
        reset_market_data_diagnostics()
        get_market_data_provider().clear_all_caches()

    def tearDown(self) -> None:
        reset_market_data_provider_for_tests()
        reset_market_data_diagnostics()

    def test_etf_sample_bundle_uses_session_cache(self) -> None:
        provider = get_market_data_provider()
        with patch.object(
            provider,
            "_fetch_etf_bundle_live",
            wraps=provider._fetch_etf_bundle_live,
        ) as live:
            b1 = provider.get_etf_bundle("VOO")
            b2 = provider.get_etf_bundle("VOO")
            self.assertIn(b1.source, ("live", "sample"))
            self.assertFalse(b1.holdings.empty)
            self.assertEqual(len(b1.holdings), len(b2.holdings))

        diag = get_market_data_diagnostics()
        self.assertGreaterEqual(diag.cache_hits_session, 1)

    def test_dedupe_concurrent_etf_requests(self) -> None:
        provider = get_market_data_provider()
        calls = {"n": 0}

        def _fake(sym: str) -> EtfHoldingsBundle:
            calls["n"] += 1
            static = eh._STATIC_HOLDINGS["VOO"]
            return EtfHoldingsBundle(
                holdings=pd.DataFrame(static),
                sectors=pd.DataFrame(),
                meta={"name": "VOO"},
                source="sample",
            )

        with patch.object(provider, "_fetch_etf_bundle_live", side_effect=_fake):
            a = provider.get_etf_bundle("VOO")
            b = provider.get_etf_bundle("VOO")
            self.assertEqual(a.source, b.source)
            self.assertEqual(calls["n"], 1)

    def test_batch_spot_quotes_single_download(self) -> None:
        provider = get_market_data_provider()
        with patch("investment_market_data.yahoo.batch_spot_prices_raw", return_value={"AAPL": 190.0, "MSFT": 420.0}) as batch:
            quotes = provider.get_latest_quotes(["AAPL", "MSFT"])
            self.assertEqual(quotes["AAPL"][0], 190.0)
            self.assertEqual(quotes["MSFT"][0], 420.0)
            batch.assert_called_once()

    def test_clear_all_caches_drops_process_fallback(self) -> None:
        provider = get_market_data_provider()
        provider.get_etf_bundle("VOO")
        provider.clear_all_caches()
        with patch.object(provider, "_fetch_etf_bundle_live") as live:
            live.return_value = EtfHoldingsBundle(
                holdings=pd.DataFrame([{"symbol": "X", "weight": 1.0}]),
                sectors=pd.DataFrame(),
                meta={"name": "X"},
                source="sample",
            )
            bundle = provider.get_etf_bundle("VOO")
            live.assert_called_once()
            self.assertEqual(bundle.holdings.iloc[0]["symbol"], "X")

    def test_lookup_etfs_batch(self) -> None:
        with patch(
            "investment_market_data.provider.MarketDataProvider._fetch_etf_bundle_live",
            return_value=EtfHoldingsBundle(
                holdings=pd.DataFrame([{"symbol": "AAPL", "weight": 0.1}]),
                sectors=pd.DataFrame(),
                meta={"name": "Test"},
                source="sample",
            ),
        ):
            out = eh.lookup_etfs(["VOO", "VTI"])
            self.assertIn("VOO", out)
            self.assertIn("VTI", out)


class TestYahooHistoryEmptyResponses(unittest.TestCase):
    def setUp(self) -> None:
        reset_market_data_diagnostics()

    def tearDown(self) -> None:
        reset_market_data_diagnostics()

    def test_empty_batch_raises_market_data_fetch_error_with_context(self) -> None:
        from investment_market_data.yahoo import MarketDataFetchError, fetch_price_history_raw

        empty = pd.DataFrame()

        class _Ticker:
            def history(self, **_kwargs):
                return empty

        with (
            patch("investment_market_data.yahoo.time.sleep", return_value=None),
            patch("yfinance.download", return_value=empty),
            patch("yfinance.Ticker", return_value=_Ticker()),
        ):
            with self.assertRaises(MarketDataFetchError) as ctx:
                fetch_price_history_raw(["SPY", "VTI"], "2024-01-01", "2024-06-01")

        err = ctx.exception
        msg = str(err)
        self.assertIn("SPY", msg)
        self.assertIn("2024-01-01", msg)
        self.assertIn("market-data fetch failure", msg.lower())
        self.assertNotIn("Check tickers and date range", msg)
        self.assertEqual(err.details.get("provider"), "yfinance")
        self.assertIn("batch_download", err.details.get("attempts") or [])
        diag = get_market_data_diagnostics().last_fetch
        self.assertFalse(diag.get("ok"))
        self.assertEqual(diag.get("symbols"), ["SPY", "VTI"])
        self.assertIn("MarketDataFetchError", str(diag.get("error_class")))

    def test_batch_empty_then_ticker_history_fallback_succeeds(self) -> None:
        from investment_market_data.yahoo import fetch_price_history_raw

        idx = pd.date_range("2024-01-02", periods=5, freq="B")
        hist = pd.DataFrame({"Close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=idx)

        class _Ticker:
            def history(self, **_kwargs):
                return hist.copy()

        with (
            patch("investment_market_data.yahoo.time.sleep", return_value=None),
            patch("yfinance.download", return_value=pd.DataFrame()),
            patch("yfinance.Ticker", return_value=_Ticker()),
        ):
            prices = fetch_price_history_raw(["SPY"], "2024-01-01", "2024-02-01")

        self.assertFalse(prices.empty)
        self.assertIn("SPY", prices.columns)
        self.assertTrue(get_market_data_diagnostics().last_fetch.get("ok"))

    def test_provider_surfaces_fetch_error_message(self) -> None:
        from investment_market_data.yahoo import MarketDataFetchError

        reset_market_data_provider_for_tests()
        provider = get_market_data_provider()
        provider.clear_all_caches()
        with patch(
            "investment_market_data.yahoo.fetch_price_history_raw",
            side_effect=MarketDataFetchError(
                "No Yahoo price history for [SPY] from 2024-01-01 to 2024-06-01. "
                "Yahoo Finance likely rate-limited or blocked this host "
                "(common on Streamlit Cloud shared IPs). "
                "Attempts: batch_download. "
                "This is a market-data fetch failure, not a portfolio-math error.",
                details={"provider": "yfinance", "symbols": ["SPY"]},
            ),
        ):
            with self.assertRaises(MarketDataFetchError) as ctx:
                provider.get_price_history(["SPY"], "2024-01-01", "2024-06-01")
        self.assertIn("rate-limited", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
