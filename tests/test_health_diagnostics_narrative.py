"""Diagnostics / narrative consistency: Sharpe vs policy wiring + kind-aware copy."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core


class TestSharpeVsPolicyDiagnostic(unittest.TestCase):
    def test_policy_sharpe_uses_policy_series_not_sortino(self) -> None:
        idx = pd.date_range("2019-01-01", periods=260, freq="B")
        rng = np.random.default_rng(21)
        # Distinct drifts so Sharpe ≠ Sortino and port ≠ policy.
        port = pd.Series(rng.normal(0.0004, 0.012, size=len(idx)), index=idx)
        policy = pd.Series(rng.normal(0.00055, 0.009, size=len(idx)), index=idx)
        rf = 0.04
        d = core.compute_aligned_sharpe_sortino_diagnostics(port, policy, rf)

        aligned = pd.concat([port.rename("p"), policy.rename("pol")], axis=1, join="inner").dropna()
        expect_pol_sharpe = core.sharpe_ratio(
            core.annualized_return(aligned["pol"]),
            core.annualized_volatility(aligned["pol"]),
            rf,
        )
        expect_port_sortino = core.sortino_ratio(aligned["p"], rf)
        expect_pol_sortino = core.sortino_ratio(aligned["pol"], rf)

        self.assertAlmostEqual(d["policy_sharpe"], expect_pol_sharpe, places=10)
        self.assertAlmostEqual(d["sortino"], expect_port_sortino, places=10)
        self.assertAlmostEqual(d["policy_sortino"], expect_pol_sortino, places=10)
        # Guard: Sortino must not populate policy Sharpe.
        self.assertGreater(abs(d["policy_sharpe"] - d["sortino"]), 1e-4)
        display = core.format_sharpe_vs_policy_display(
            {
                "portfolio_sharpe": d["raw_sharpe"],
                "policy_benchmark_sharpe": d["policy_sharpe"],
                "sortino": d["sortino"],
                "policy_sortino": d["policy_sortino"],
            }
        )
        self.assertEqual(display, f"{d['raw_sharpe']:.3f} / {d['policy_sharpe']:.3f}")
        self.assertNotIn(f"{d['sortino']:.3f}", display.split(" / ")[1])

    def test_format_helper_never_falls_back_to_sortino_key(self) -> None:
        # Malicious / confused dict: only sortino present as a lookalike.
        bad = {"raw_sharpe": 0.284, "sortino": 0.407}
        self.assertEqual(core.format_sharpe_vs_policy_display(bad), "n/a")
        good = {
            "portfolio_sharpe": 0.284,
            "policy_benchmark_sharpe": 0.413,
            "sortino": 0.407,
        }
        self.assertEqual(core.format_sharpe_vs_policy_display(good), "0.284 / 0.413")

    def test_keyword_builder_rejects_positional_sortino_confusion(self) -> None:
        self.assertEqual(
            core.build_sharpe_vs_policy_metric_value(
                portfolio_sharpe=0.11, policy_benchmark_sharpe=0.22
            ),
            "0.110 / 0.220",
        )

    def test_ui_caller_render_sharpe_vs_policy_metric_sentinels(self) -> None:
        """Caller-level regression: UI path must use 0.11/0.22, never Sortino."""
        from streamlit_app import render_sharpe_vs_policy_metric

        diag = {
            "portfolio_sharpe": 0.11,
            "policy_benchmark_sharpe": 0.22,
            "sortino": 0.33,
            "policy_sortino": 0.44,
            "raw_sharpe": 0.11,
            "policy_sharpe": 0.22,
            # Poisoned legacy display string — must be ignored by UI caller.
            "sharpe_vs_policy_display": "0.110 / 0.330",
        }
        rendered = render_sharpe_vs_policy_metric(diag)
        self.assertEqual(rendered, "0.110 / 0.220")
        self.assertNotIn("0.33", rendered)
        self.assertNotIn("0.44", rendered)
        self.assertNotEqual(rendered, "0.110 / 0.330")
        self.assertNotEqual(rendered, "0.110 / 0.440")

    def test_ui_caller_detects_sortino_in_policy_slot(self) -> None:
        from streamlit_app import render_sharpe_vs_policy_metric

        poisoned = {
            "portfolio_sharpe": 0.284,
            "policy_benchmark_sharpe": 0.407,  # wrongly equals portfolio Sortino
            "sortino": 0.407,
            "policy_sortino": 0.575,
        }
        self.assertEqual(render_sharpe_vs_policy_metric(poisoned), "n/a")


class TestConcentrationNarrativeKindAware(unittest.TestCase):
    def test_broad_market_etf_within_bands_is_not_a_problem_warning(self) -> None:
        note = core.concentration_status_note(
            top_ticker="VTI",
            top_weight=0.40,
            kind="broad_market_etf",
            concentration_pillar_pts=15.0,
            conc_engine_pts=12.0,
        )
        self.assertIn("VTI", note)
        self.assertIn("40%", note)
        self.assertIn("broad-market ETF bands", note)
        self.assertNotIn("review concentration diagnostics", note)

    def test_individual_equity_elevated_still_flags_review(self) -> None:
        note = core.concentration_status_note(
            top_ticker="AAPL",
            top_weight=0.40,
            kind="individual_equity",
            concentration_pillar_pts=0.0,
            conc_engine_pts=0.0,
        )
        self.assertIn("AAPL", note)
        self.assertIn("40%", note)
        self.assertIn("review concentration diagnostics", note)


class TestStabilizerExposureWording(unittest.TestCase):
    def test_bonds_only_does_not_claim_tbills(self) -> None:
        phrase = core.stabilizer_exposure_phrase({"bonds": 0.30, "tbills": 0.0})
        self.assertEqual(phrase, "bond exposure")
        self.assertNotIn("T-bill", phrase)

    def test_absent_sleeves_return_none(self) -> None:
        self.assertIsNone(core.stabilizer_exposure_phrase({"bonds": 0.0, "tbills": 0.0}))

    def test_health_whats_working_uses_actual_exposure(self) -> None:
        idx = pd.date_range("2019-01-01", periods=120, freq="B")
        rng = np.random.default_rng(3)
        tickers = ["VTI", "VXUS", "BND", "VNQ"]
        w = np.array([0.40, 0.20, 0.30, 0.10])
        types = ["Equity", "Equity", "Bonds", "REIT"]
        rets = pd.DataFrame(rng.normal(0.0003, 0.01, size=(len(idx), 4)), index=idx, columns=tickers)
        # Force low beta via metrics object.
        metrics = core.ExtendedPortfolioMetrics(
            annual_return=0.07,
            volatility=0.12,
            sharpe_ratio=0.25,
            max_drawdown=-0.2,
            sortino_ratio=0.4,
            cagr=0.07,
            beta_spy=0.70,
            projected_value=10_000.0,
        )
        policy = pd.Series(rng.normal(0.0004, 0.009, size=len(idx)), index=idx)
        health = core.evaluate_portfolio_health(
            tickers,
            w,
            types,
            metrics,
            rets,
            rets.corr(),
            core.risk_contribution(rets, w, tickers=tickers),
            core.ForwardMacroAssumptions(
                "Stable Rates", "Moderate Inflation", 0.2, "Fair", "Expansion"
            ),
            "balanced growth",
            0.04,
            10_000.0,
            policy_benchmark_returns=policy,
            policy_benchmark_meta={"label": "test", "detail": "test"},
        )
        joined = " ".join(health.whats_working)
        if "market sensitivity" in joined.lower():
            self.assertIn("bond exposure", joined)
            self.assertNotIn("T-bill", joined)
        self.assertIn("broad-market ETF bands", health.status_message)
        self.assertNotIn("review concentration diagnostics", health.status_message)
        # Policy Sharpe diagnostic distinct from Sortino.
        self.assertIn("policy_benchmark_sharpe", health.health_diagnostics)
        self.assertNotAlmostEqual(
            health.health_diagnostics["policy_benchmark_sharpe"],
            health.health_diagnostics["sortino"],
            places=3,
        )
        from streamlit_app import render_sharpe_vs_policy_metric

        disp = render_sharpe_vs_policy_metric(health.health_diagnostics)
        self.assertEqual(
            disp,
            core.build_sharpe_vs_policy_metric_value(
                portfolio_sharpe=float(health.health_diagnostics["portfolio_sharpe"]),
                policy_benchmark_sharpe=float(
                    health.health_diagnostics["policy_benchmark_sharpe"]
                ),
            ),
        )
        right = disp.split(" / ")[1]
        self.assertAlmostEqual(
            float(right), health.health_diagnostics["policy_benchmark_sharpe"], places=3
        )


if __name__ == "__main__":
    unittest.main()
