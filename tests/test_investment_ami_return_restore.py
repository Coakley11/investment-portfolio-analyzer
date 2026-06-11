"""AMI return must not overwrite Test D portfolio state."""

from __future__ import annotations

import unittest

import pandas as pd

from applied_math_context import apply_source_state_to_session, build_source_state
from applied_math_return_insight import ami_return_navigation_active


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self, params: dict[str, str] | None = None) -> None:
        self.session_state = _FakeSessionState()
        self.query_params = dict(params or {})


class TestInvestmentAmiReturnRestore(unittest.TestCase):
    def test_ami_return_navigation_active_with_insight_query(self) -> None:
        st = _FakeSt({"suite_ami_insight": "abc123"})
        self.assertTrue(ami_return_navigation_active(st, "investment"))

    def test_build_source_state_includes_holdings_df_records(self) -> None:
        holdings = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        state = build_source_state(
            "Portfolio Health",
            {"investment_active_tab": "Portfolio Health", "holdings_df": holdings},
        )
        ent = state["entity_params"]
        self.assertIn("holdings_df", ent)
        self.assertEqual(len(ent["holdings_df"]), 2)
        self.assertIn("BND:50.0:Bonds", ent["holdings_fingerprint"])
        self.assertIn("VYM:50.0:Dividend ETF", ent["holdings_fingerprint"])

    def test_apply_deferred_restore_skips_stale_blob_holdings(self) -> None:
        import investment_persistent_state as ips

        st = _FakeSt()
        st.session_state["_skip_page_restore_for"] = "⑤ Portfolio Health"
        st.session_state["_suite_holdings_fp"] = "BND:50.0:Bonds|VYM:50.0:Dividend ETF"
        stale = {
            "investment_active_tab": "① Choose Goal",
            "holdings_fingerprint": "BND:30.0:Bonds|VNQ:10.0:REIT|VTI:40.0:Equity|VXUS:20.0:Equity",
            "holdings_df": [
                {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
                {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
                {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bonds"},
                {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
            ],
            "experience": "Beginner Mode",
            "portfolio_built": False,
        }
        good_state = build_source_state(
            "⑤ Portfolio Health",
            {
                "investment_active_tab": "⑤ Portfolio Health",
                "guide_goal_choice": "Income",
                "portfolio_built": True,
                "holdings_df": pd.DataFrame(
                    {
                        "Ticker": ["BND", "VYM"],
                        "Weight (%)": [50.0, 50.0],
                        "Asset Type": ["Bonds", "Dividend ETF"],
                    }
                ),
            },
        )
        apply_source_state_to_session(st.session_state, good_state)
        ips.apply_investment_disk_state(st, stale)
        df = st.session_state["holdings_df"]
        tickers = set(df["Ticker"].astype(str).str.upper())
        self.assertEqual(tickers, {"BND", "VYM"})
        self.assertEqual(st.session_state["investment_active_tab"], "⑤ Portfolio Health")
        self.assertEqual(
            st.session_state.get("_suite_page_overwrite_source"),
            "ami_return_deferred_holdings",
        )


if __name__ == "__main__":
    unittest.main()
