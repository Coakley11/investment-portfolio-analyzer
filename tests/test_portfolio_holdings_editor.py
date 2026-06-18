"""Tests for portfolio holdings editor helpers and auto asset-type detection."""

from __future__ import annotations

import unittest

import pandas as pd

import etf_holdings as eh
import portfolio_core as core
from components.portfolio_holdings_editor import (
    _enrich_for_mode,
    remove_holdings_row,
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


class TestPortfolioEditorHelpers(unittest.TestCase):
    def test_quick_loader_keys_map_to_presets(self) -> None:
        for label, preset_key in core.PORTFOLIO_QUICK_LOADERS.items():
            self.assertIn(preset_key, core.PORTFOLIO_PRESETS, msg=label)

    def test_remove_holdings_row(self) -> None:
        class _FakeSt:
            def __init__(self) -> None:
                self.session_state = {
                    "holdings_df": pd.DataFrame(
                        {
                            "Ticker": ["VTI", "BND"],
                            "Weight (%)": [60.0, 40.0],
                            "Asset Type": ["Equity", "Bonds"],
                        }
                    )
                }

        st_obj = _FakeSt()
        self.assertTrue(remove_holdings_row(st_obj, 0))
        self.assertEqual(len(st_obj.session_state["holdings_df"]), 1)
        self.assertEqual(st_obj.session_state["holdings_df"].iloc[0]["Ticker"], "BND")

    def test_beginner_enrich_preserves_asset_type_when_tickers_unchanged(self) -> None:
        class _FakeSt:
            def __init__(self) -> None:
                self.session_state: dict = {}

        st_obj = _FakeSt()
        df = pd.DataFrame(
            {
                "Ticker": ["VTI"],
                "Weight (%)": [100.0],
                "Asset Type": ["Bonds"],
            }
        )
        first = _enrich_for_mode(df, st_obj, beginner_mode=True)
        self.assertEqual(first.iloc[0]["Asset Type"], "Equity")
        df2 = df.copy()
        df2.at[0, "Asset Type"] = "Bonds"
        second = _enrich_for_mode(df2, st_obj, beginner_mode=True)
        self.assertEqual(second.iloc[0]["Asset Type"], "Bonds")


if __name__ == "__main__":
    unittest.main()
