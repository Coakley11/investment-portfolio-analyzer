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


if __name__ == "__main__":
    unittest.main()
