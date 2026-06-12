"""Tests for ETF holdings lookup and portfolio exposure."""

from __future__ import annotations

import unittest

import pandas as pd

import etf_holdings as eh


class TestEtfHoldings(unittest.TestCase):
    def test_lookup_sample_fallback(self) -> None:
        result = eh.lookup_etf("VOO")
        self.assertEqual(result.ticker, "VOO")
        self.assertIn(result.data_source, ("live", "sample"))
        self.assertFalse(result.holdings.empty)
        self.assertIn("symbol", result.holdings.columns)
        self.assertIn("weight", result.holdings.columns)

    def test_portfolio_etf_tickers(self) -> None:
        df = pd.DataFrame(
            {
                "Ticker": ["VTI", "BND", "AAPL"],
                "Weight (%)": [60.0, 30.0, 10.0],
                "Asset Type": ["Equity", "Bonds", "Equity"],
            }
        )
        etfs = eh.portfolio_etf_tickers(df)
        tickers = {t for t, _ in etfs}
        self.assertIn("VTI", tickers)
        self.assertIn("BND", tickers)
        self.assertNotIn("AAPL", tickers)

    def test_aggregate_underlying_exposure(self) -> None:
        holdings = pd.DataFrame(
            [
                {"symbol": "AAPL", "name": "Apple", "weight": 0.5, "sector": "Technology"},
                {"symbol": "MSFT", "name": "Microsoft", "weight": 0.3, "sector": "Technology"},
            ]
        )
        exposure = eh.aggregate_underlying_exposure(
            [("ETF1", 0.6), ("ETF2", 0.4)],
            holdings_by_etf={"ETF1": holdings, "ETF2": holdings},
        )
        self.assertFalse(exposure.empty)
        aapl = exposure[exposure["symbol"] == "AAPL"].iloc[0]
        self.assertAlmostEqual(float(aapl["portfolio_weight"]), 0.6 * 0.5 + 0.4 * 0.5, places=4)

    def test_concentration_hhi(self) -> None:
        hhi = eh.concentration_hhi(pd.Series([0.5, 0.3, 0.2]))
        self.assertGreater(hhi, 0.3)

    def test_pairwise_overlap(self) -> None:
        h1 = pd.DataFrame([{"symbol": "AAPL", "weight": 0.1}, {"symbol": "MSFT", "weight": 0.08}])
        h2 = pd.DataFrame([{"symbol": "AAPL", "weight": 0.12}, {"symbol": "GOOG", "weight": 0.05}])
        ov = eh.pairwise_etf_overlap(h1, h2)
        self.assertAlmostEqual(ov, 0.1, places=4)

    def test_overlap_warnings(self) -> None:
        holdings = pd.DataFrame([{"symbol": "AAPL", "weight": 0.5}, {"symbol": "MSFT", "weight": 0.4}])
        warnings = eh.overlap_warnings(["A", "B"], {"A": holdings, "B": holdings}, threshold=0.35)
        self.assertTrue(any("A" in w and "B" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
