"""Tests for portfolio holdings editor helpers and auto asset-type detection."""

from __future__ import annotations

import unittest

import pandas as pd

import etf_holdings as eh
import portfolio_core as core
from components.portfolio_holdings_editor import (
    add_holding_ticker,
    load_portfolio_preset,
    remove_holding_ticker,
)


class TestPortfolioFundInference(unittest.TestCase):
    def test_qqq_metadata(self) -> None:
        info = eh.infer_portfolio_fund_info("QQQ")
        self.assertEqual(info["ticker"], "QQQ")
        self.assertEqual(info["asset_type"], "Equity")
        self.assertIn("Technology", info["category_label"])

    def test_bnd_metadata(self) -> None:
        info = eh.infer_portfolio_fund_info("BND")
        self.assertEqual(info["asset_type"], "Bonds")
        self.assertIn("Bond", info["category_label"])

    def test_schd_dividend_type(self) -> None:
        info = eh.infer_portfolio_fund_info("SCHD")
        self.assertEqual(info["asset_type"], "Dividend ETF")

    def test_vnq_reit_type(self) -> None:
        info = eh.infer_portfolio_fund_info("VNQ")
        self.assertEqual(info["asset_type"], "REIT")

    def test_enrich_holdings_asset_types(self) -> None:
        df = pd.DataFrame(
            {
                "Ticker": ["QQQ", "BND", "VNQ"],
                "Weight (%)": [50.0, 30.0, 20.0],
                "Asset Type": ["Equity", "Equity", "Equity"],
            }
        )
        out = eh.enrich_holdings_asset_types(df)
        self.assertEqual(out.loc[0, "Asset Type"], "Equity")
        self.assertEqual(out.loc[1, "Asset Type"], "Bonds")
        self.assertEqual(out.loc[2, "Asset Type"], "REIT")

    def test_holdings_metadata_table(self) -> None:
        df = pd.DataFrame(
            {"Ticker": ["BND"], "Weight (%)": [100.0], "Asset Type": ["Bonds"]}
        )
        meta = eh.holdings_metadata_table(df)
        self.assertEqual(len(meta), 1)
        self.assertEqual(meta.iloc[0]["Ticker"], "BND")
        self.assertIn("Bond", meta.iloc[0]["Category"])


class TestPortfolioQuickLoaders(unittest.TestCase):
    def test_quick_loader_keys_map_to_presets(self) -> None:
        for label, preset_key in core.PORTFOLIO_QUICK_LOADERS.items():
            self.assertIn(preset_key, core.PORTFOLIO_PRESETS, msg=label)

    def test_add_and_remove_holding(self) -> None:
        class _FakeSt:
            def __init__(self) -> None:
                self.session_state = {
                    "holdings_df": pd.DataFrame(columns=["Ticker", "Weight (%)", "Asset Type"])
                }

        st_obj = _FakeSt()
        self.assertTrue(add_holding_ticker(st_obj, "VTI"))
        self.assertIn("VTI", st_obj.session_state["holdings_df"]["Ticker"].astype(str).tolist())
        self.assertFalse(add_holding_ticker(st_obj, "VTI"))
        self.assertTrue(remove_holding_ticker(st_obj, "VTI"))
        self.assertTrue(st_obj.session_state["holdings_df"].empty)

    def test_load_balanced_preset(self) -> None:
        class _FakeSt:
            def __init__(self) -> None:
                self.session_state = {"holdings_df": pd.DataFrame()}

        st_obj = _FakeSt()
        self.assertTrue(load_portfolio_preset(st_obj, "Balanced"))
        tickers = set(st_obj.session_state["holdings_df"]["Ticker"].astype(str).str.upper())
        self.assertIn("VTI", tickers)
        self.assertIn("BND", tickers)


if __name__ == "__main__":
    unittest.main()
