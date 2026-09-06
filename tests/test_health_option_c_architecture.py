"""Option C Core Portfolio Health architecture acceptance tests."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core


_PILOT = ["VTI", "VXUS", "BND", "VNQ"]
_PILOT_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
_PILOT_T = ["Equity", "Equity", "Bonds", "REIT"]
_RF = 0.04


def _assumptions(**overrides) -> core.ForwardMacroAssumptions:
    base = dict(
        rate_environment="Stable Rates",
        inflation="Moderate Inflation",
        valuation="Fair",
        economic_regime="Expansion",
        recession_probability=0.25,
    )
    base.update(overrides)
    return core.ForwardMacroAssumptions(**base)


def _synthetic_pilot(seed: int = 0, columns: list[str] | None = None) -> pd.DataFrame:
    cols = columns or list(_PILOT)
    idx = pd.date_range("2019-01-01", periods=260, freq="B")
    data = {}
    specs = {
        "VTI": (0.00055, 0.010),
        "VXUS": (0.00035, 0.012),
        "BND": (0.00008, 0.003),
        "VNQ": (0.00040, 0.014),
        "AAPL": (0.0007, 0.018),
        "MSFT": (0.00065, 0.017),
        "BIL": (0.00005, 0.0004),
        "AGG": (0.0001, 0.003),
        "SPY": (0.0005, 0.01),
    }
    for c in cols:
        mu, sigma = specs.get(c, (0.0004, 0.01))
        # Per-ticker RNG so column order cannot change series identity.
        col_rng = np.random.default_rng(seed + hash(c) % 10_000)
        data[c] = col_rng.normal(mu, sigma, size=len(idx))
    return pd.DataFrame(data, index=idx)


def _policy_for(objective: str, idx: pd.DatetimeIndex, seed: int = 9):
    rng = np.random.default_rng(seed)
    proxy = pd.DataFrame(
        {
            "SPY": rng.normal(0.0005, 0.01, size=len(idx)),
            "AGG": rng.normal(0.0001, 0.003, size=len(idx)),
            "BIL": rng.normal(0.00005, 0.0004, size=len(idx)),
        },
        index=idx,
    )
    return core.build_policy_benchmark_returns(proxy, objective)


def _health(
    rets: pd.DataFrame,
    weights: np.ndarray,
    tickers: list[str],
    types: list[str],
    objective: str,
    assumptions: core.ForwardMacroAssumptions | None = None,
    policy=None,
    meta=None,
):
    if policy is None:
        policy, meta = _policy_for(objective, rets.index)
    metrics = core.compute_extended_metrics(rets, weights, _RF, 10_000.0, tickers=tickers)
    aligned, _, _ = core.align_returns_and_weights(rets, weights, tickers=tickers)
    return core.evaluate_portfolio_health(
        tickers=tickers,
        weights=weights,
        asset_types=types,
        metrics=metrics,
        asset_returns=rets,
        corr=aligned.corr(),
        risk_contrib_df=core.risk_contribution(rets, weights, tickers=tickers),
        assumptions=assumptions or _assumptions(),
        objective=objective,
        risk_free_rate=_RF,
        initial_value=10_000.0,
        policy_benchmark_returns=policy,
        policy_benchmark_meta=meta,
        recommended_type_mix=core.OBJECTIVE_ALLOCATIONS.get(
            objective.strip().lower(), core.OBJECTIVE_ALLOCATIONS["balanced growth"]
        ),
    )


class TestOptionCPillarArchitecture(unittest.TestCase):
    def test_A_four_pillar_maxima_sum_to_100(self) -> None:
        self.assertEqual(set(core.HEALTH_CORE_PILLAR_MAX), {
            "Policy / Objective Fit",
            "Portfolio Construction",
            "Risk Appropriateness",
            "Policy-Relative Performance",
        })
        self.assertAlmostEqual(sum(core.HEALTH_CORE_PILLAR_MAX.values()), 100.0, places=9)

    def test_B_sharpe_alone_cannot_change_core_health(self) -> None:
        rets = _synthetic_pilot(1)
        h1 = _health(rets, _PILOT_W, _PILOT, _PILOT_T, "balanced growth")
        # Plant extreme Sharpe via metrics object — Core breakdown must ignore it.
        bogus = core.ExtendedPortfolioMetrics(
            annual_return=h1.health_diagnostics["annual_return"],
            volatility=h1.health_diagnostics["annual_volatility"],
            sharpe_ratio=99.0,
            max_drawdown=h1.health_diagnostics["max_drawdown"],
            sortino_ratio=99.0,
            cagr=h1.health_diagnostics["annual_return"],
            beta_spy=1.0,
            projected_value=10_000.0,
        )
        policy, meta = _policy_for("balanced growth", rets.index)
        aligned, _, _ = core.align_returns_and_weights(rets, _PILOT_W, tickers=_PILOT)
        h2 = core.evaluate_portfolio_health(
            tickers=_PILOT,
            weights=_PILOT_W,
            asset_types=_PILOT_T,
            metrics=bogus,
            asset_returns=rets,
            corr=aligned.corr(),
            risk_contrib_df=core.risk_contribution(rets, _PILOT_W, tickers=_PILOT),
            assumptions=_assumptions(),
            objective="balanced growth",
            risk_free_rate=_RF,
            initial_value=10_000.0,
            policy_benchmark_returns=policy,
            policy_benchmark_meta=meta,
        )
        self.assertEqual(h1.score_breakdown, h2.score_breakdown)
        self.assertAlmostEqual(h1.score, h2.score, places=9)
        self.assertNotIn("Sharpe Score (pts)", h1.score_breakdown)
        self.assertIn("raw_sharpe", h1.health_diagnostics)

    def test_C_macro_alone_cannot_change_core_health(self) -> None:
        rets = _synthetic_pilot(2)
        calm = _assumptions(recession_probability=0.10, economic_regime="Expansion")
        stress = _assumptions(
            recession_probability=0.80,
            inflation="High Inflation",
            economic_regime="Credit Crisis",
            rate_environment="Rising Rates",
        )
        h1 = _health(rets, _PILOT_W, _PILOT, _PILOT_T, "balanced growth", assumptions=calm)
        h2 = _health(rets, _PILOT_W, _PILOT, _PILOT_T, "balanced growth", assumptions=stress)
        self.assertEqual(h1.score_breakdown, h2.score_breakdown)
        self.assertAlmostEqual(h1.score, h2.score, places=9)
        self.assertNotAlmostEqual(h1.macro_check_score, h2.macro_check_score)
        self.assertNotIn("Macro Regime Fit", h1.score_breakdown)

    def test_D_objectives_use_own_policy_definitions(self) -> None:
        idx = pd.date_range("2019-01-01", periods=80, freq="B")
        proxy = pd.DataFrame(
            {"SPY": np.ones(len(idx)) * 0.001, "AGG": np.ones(len(idx)) * 0.0002, "BIL": np.ones(len(idx)) * 0.00005},
            index=idx,
        )
        for obj, eq, bond, tb in (
            ("capital preservation", 0.20, 0.45, 0.35),
            ("balanced growth", 0.60, 0.30, 0.10),
            ("aggressive growth", 0.85, 0.10, 0.05),
        ):
            series, meta = core.build_policy_benchmark_returns(proxy, obj)
            self.assertTrue(meta["ok"])
            self.assertAlmostEqual(meta["weights"]["equity"], eq)
            self.assertAlmostEqual(meta["weights"]["bonds"], bond)
            self.assertAlmostEqual(meta["weights"]["tbills"], tb)
            assert series is not None
            expected = eq * 0.001 + bond * 0.0002 + tb * 0.00005
            self.assertAlmostEqual(float(series.iloc[0]), expected, places=10)

    def test_E_risk_appropriateness_is_policy_relative(self) -> None:
        idx = pd.date_range("2019-01-01", periods=200, freq="B")
        # Identical series → ratio 1 → full vol points.
        common = pd.Series(np.random.default_rng(0).normal(0.0004, 0.01, size=len(idx)), index=idx)
        pts, diag = core.score_risk_appropriateness(common, common)
        self.assertAlmostEqual(diag["vol_ratio"], 1.0, places=6)
        self.assertAlmostEqual(diag["vol_pts"], 16.0, places=6)
        self.assertGreaterEqual(pts, 16.0)

    def test_F_aggressive_not_penalized_for_higher_absolute_vol_vs_balanced(self) -> None:
        idx = pd.date_range("2019-01-01", periods=260, freq="B")
        rng = np.random.default_rng(11)
        # High-vol book matching aggressive policy risk.
        high = pd.Series(rng.normal(0.0006, 0.018, size=len(idx)), index=idx)
        # Aggressive policy ~ mostly SPY-like high vol.
        agg_policy = pd.Series(rng.normal(0.00055, 0.0175, size=len(idx)), index=idx)
        # Low-vol balanced policy.
        bal_policy = pd.Series(rng.normal(0.0003, 0.008, size=len(idx)), index=idx)

        pts_vs_agg, d_agg = core.score_risk_appropriateness(high, agg_policy)
        pts_vs_bal, d_bal = core.score_risk_appropriateness(high, bal_policy)
        self.assertGreater(d_agg["port_vol"], d_bal["policy_vol"])
        # Same absolute port vol: better when judged vs aggressive policy than vs balanced.
        self.assertGreater(pts_vs_agg, pts_vs_bal)

    def test_G_capital_preservation_penalized_when_risk_exceeds_policy(self) -> None:
        idx = pd.date_range("2019-01-01", periods=260, freq="B")
        rng = np.random.default_rng(12)
        risky = pd.Series(rng.normal(0.0006, 0.02, size=len(idx)), index=idx)
        conservative = pd.Series(rng.normal(0.00015, 0.004, size=len(idx)), index=idx)
        pts, diag = core.score_risk_appropriateness(risky, conservative)
        self.assertGreater(diag["vol_ratio"], 1.75)
        self.assertLessEqual(diag["vol_pts"], 4.0)
        self.assertLess(pts, 10.0)

    def test_H_construction_preserves_broad_etf_vs_stock_concentration(self) -> None:
        rets = _synthetic_pilot(3)
        # 70% VTI broad ETF vs 70% AAPL individual — kind-aware concentration.
        w_etf = np.array([0.70, 0.10, 0.10, 0.10])
        tickers_stock = ["AAPL", "VXUS", "BND", "VNQ"]
        w_stock = np.array([0.70, 0.10, 0.10, 0.10])
        types_stock = ["Equity", "Equity", "Bonds", "REIT"]
        rets_stock = rets.copy()
        rets_stock = rets_stock.rename(columns={"VTI": "AAPL"})
        # Rebuild AAPL series so column exists with distinct identity.
        rets_stock["AAPL"] = rets["VTI"] * 1.1

        _, d_etf = core.score_portfolio_construction(_PILOT, w_etf, _PILOT_T, rets[_PILOT].corr())
        _, d_stock = core.score_portfolio_construction(
            tickers_stock, w_stock, types_stock, rets_stock[tickers_stock].corr()
        )
        self.assertEqual(d_etf["conc_diag"]["kind"], "broad_market_etf")
        self.assertEqual(d_stock["conc_diag"]["kind"], "individual_equity")
        self.assertGreater(d_etf["concentration_pts"], d_stock["concentration_pts"])

    def test_I_column_permutation_does_not_change_pillars(self) -> None:
        orders = [
            ["VTI", "VXUS", "BND", "VNQ"],
            ["BND", "VNQ", "VTI", "VXUS"],
            ["VNQ", "VTI", "BND", "VXUS"],
        ]
        scores = []
        for cols in orders:
            rets = _synthetic_pilot(4, columns=cols)
            h = _health(rets, _PILOT_W, _PILOT, _PILOT_T, "balanced growth")
            scores.append((h.score, tuple(h.score_breakdown[k] for k in core.HEALTH_CORE_PILLAR_MAX)))
        for other in scores[1:]:
            self.assertAlmostEqual(scores[0][0], other[0], places=9)
            np.testing.assert_allclose(scores[0][1], other[1], rtol=1e-12, atol=1e-12)

    def test_J_policy_relative_performance_date_aligned(self) -> None:
        idx_a = pd.date_range("2020-01-01", periods=50, freq="B")
        idx_b = pd.date_range("2020-02-01", periods=50, freq="B")
        port = pd.Series(np.linspace(0.001, 0.002, len(idx_a)), index=idx_a)
        policy = pd.Series(np.linspace(0.0005, 0.001, len(idx_b)), index=idx_b)
        s_ret, _, _, n = core.score_policy_relative_performance(port, policy)
        self.assertGreater(n, 0)
        self.assertLess(n, len(idx_a))
        self.assertLess(n, len(idx_b))
        allowed = {0.0, 20.0, 16.0, 8.0 * 20 / 15, 4.0 * 20 / 15}
        self.assertTrue(any(abs(s_ret - a) < 1e-9 for a in allowed))

    def test_risk_formula_documented_splits(self) -> None:
        self.assertEqual(core.HEALTH_CONSTRUCTION_DIV_MAX, 15.0)
        self.assertEqual(core.HEALTH_CONSTRUCTION_CONC_MAX, 15.0)
        doc = core.score_risk_appropriateness.__doc__ or ""
        self.assertIn("0–16", doc.replace("0-16", "0–16"))
        self.assertIn("0–4", doc.replace("0-4", "0–4"))
        self.assertIn("port_vol / policy_vol", doc)


class TestOptionCLabels(unittest.TestCase):
    def test_labels_are_plan_aligned_not_watch_carefully(self) -> None:
        label, color = core._health_score_label(72)
        self.assertEqual(label, "Mostly On Plan")
        self.assertEqual(color, "green")
        label2, _ = core._health_score_label(50)
        self.assertEqual(label2, "Needs Attention")
        self.assertNotEqual(label2, "Watch Carefully")


if __name__ == "__main__":
    unittest.main()
