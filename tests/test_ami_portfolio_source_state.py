"""Test E: AMI source_state must carry portfolio payload; autosave must not clobber cloud."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from applied_math_context import (
    build_source_state,
    enrich_investment_source_state_holdings,
    investment_source_state_has_portfolio_payload,
)
from applied_math_return_insight import apply_return_source_state


class _FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


class TestAmiPortfolioSourceState(unittest.TestCase):
    def test_enrich_from_session_holdings_fingerprint_and_cloud_records(self) -> None:
        cloud_records = [
            {"Ticker": "BND", "Weight (%)": 50.0, "Asset Type": "Bonds"},
            {"Ticker": "VYM", "Weight (%)": 50.0, "Asset Type": "Dividend ETF"},
        ]
        session = {
            "investment_active_tab": "Portfolio Health",
            "holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF",
            "portfolio_built": True,
        }
        shell = {
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "entity_params": {"tab": "Portfolio Health"},
            "widget_params": {},
        }
        with patch(
            "suite_cloud_state.load_cloud_full_session",
            return_value=(
                {
                    "holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF",
                    "holdings_df": cloud_records,
                },
                "2026-06-11T12:00:00",
            ),
        ):
            enriched = enrich_investment_source_state_holdings(session, shell)
        ent = enriched["entity_params"]
        self.assertTrue(investment_source_state_has_portfolio_payload(enriched))
        self.assertEqual(len(ent["holdings_df"]), 2)
        self.assertIn("BND:50.0:Bonds", ent["holdings_fingerprint"])
        self.assertTrue(ent.get("portfolio_built"))

    def test_build_source_state_without_live_df_still_enriches_from_fingerprint(self) -> None:
        session = {
            "investment_active_tab": "Portfolio Health",
            "holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF",
        }
        shell = build_source_state("Portfolio Health", session)
        self.assertTrue(investment_source_state_has_portfolio_payload(shell))

    def test_apply_marks_partial_when_portfolio_payload_missing(self) -> None:
        st = _FakeSt()
        st.session_state["holdings_df"] = pd.DataFrame(
            {
                "Ticker": ["BND", "VYM"],
                "Weight (%)": [50.0, 50.0],
                "Asset Type": ["Bonds", "Dividend ETF"],
            }
        )
        source_state = {
            "source_app": "investment",
            "source_page": "Portfolio Health",
            "entity_params": {"tab": "Portfolio Health"},
            "widget_params": {},
        }
        apply_return_source_state(st, "investment", source_state)
        self.assertTrue(st.session_state.get("_ami_return_partial_source_state"))
        self.assertEqual(
            st.session_state.get("apply_source_state_skip_reason"),
            "source_state_missing_portfolio_payload",
        )

    def test_autosave_clobber_guard_blocks_empty_payload_vs_cloud(self) -> None:
        import investment_persistent_state as ips

        st = _FakeSt()
        cloud = {
            "holdings_fingerprint": "BND:50.0:Bonds|VYM:50.0:Dividend ETF",
            "holdings_df": [
                {"Ticker": "BND", "Weight (%)": 50.0, "Asset Type": "Bonds"},
                {"Ticker": "VYM", "Weight (%)": 50.0, "Asset Type": "Dividend ETF"},
            ],
        }
        with patch.object(ips, "_cloud_has_saved_portfolio", return_value=(cloud, "ts")):
            blocked, reason = ips._autosave_would_clobber_saved_portfolio(st, {})
        self.assertTrue(blocked)
        self.assertIn("empty_holdings", reason)


if __name__ == "__main__":
    unittest.main()
