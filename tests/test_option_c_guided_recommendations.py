"""Option C: Guided primary issues must not be diagnostic-only Sharpe."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import portfolio_core as core
from components.guided_adjustment import _primary_issue


_SHADOW_TICKERS = ["VTI", "VXUS", "BND", "VNQ"]
_SHADOW_TYPES = ["Equity", "Equity", "Bonds", "REIT"]
_SHADOW_WEIGHTS = np.array([0.40, 0.20, 0.30, 0.10])


def _synthetic_returns(
    tickers: list[str],
    *,
    periods: int = 80,
    seed: int = 7,
    mu: float = 0.00015,
    sigma: float = 0.012,
) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=periods, freq="B")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(mu, sigma, size=(len(idx), len(tickers))),
        index=idx,
        columns=tickers,
    )


def _eval_shadow(*, low_sharpe: bool = True) -> core.PortfolioHealthResult:
    # High vol + modest drift → Sharpe often < 0.4 while Option C issues remain.
    mu = 0.00005 if low_sharpe else 0.0008
    sigma = 0.018 if low_sharpe else 0.008
    rets = _synthetic_returns(_SHADOW_TICKERS, mu=mu, sigma=sigma, seed=11)
    metrics = core.compute_extended_metrics(
        rets, _SHADOW_WEIGHTS, 0.04, 4250.0, tickers=_SHADOW_TICKERS
    )
    corr = rets.corr()
    risk = core.risk_contribution(rets, _SHADOW_WEIGHTS, tickers=_SHADOW_TICKERS)
    assumptions = core.ForwardMacroAssumptions(
        rate_environment="Stable Rates",
        inflation="Moderate Inflation",
        valuation="Fair",
        economic_regime="Expansion",
        recession_probability=0.20,
    )
    # Policy series slightly stronger than portfolio → performance pillar soft.
    policy = (
        0.60 * rets["VTI"] + 0.30 * rets["BND"] + 0.10 * rets["VXUS"]
    ).rename("policy") + 0.0002
    return core.evaluate_portfolio_health(
        tickers=_SHADOW_TICKERS,
        weights=_SHADOW_WEIGHTS,
        asset_types=_SHADOW_TYPES,
        metrics=metrics,
        asset_returns=rets,
        corr=corr,
        risk_contrib_df=risk,
        assumptions=assumptions,
        objective="balanced growth",
        risk_free_rate=0.04,
        initial_value=4250.0,
        benchmark_returns=rets["VTI"],
        optimizer_weights=None,
        recommended_type_mix=core.OBJECTIVE_ALLOCATIONS["balanced growth"],
        policy_benchmark_returns=policy,
        policy_benchmark_meta={
            "label": "60/30/10 test policy",
            "detail": "unit-test policy",
            "ok": True,
        },
    )


class TestOptionCGuidedPrimaryIssue(unittest.TestCase):
    def test_shadow_guided_targets_unchanged(self) -> None:
        health = _eval_shadow()
        by_ticker = {
            str(r["Ticker"]): float(r["Objective (%)"])
            for _, r in health.rebalance_df.iterrows()
        }
        self.assertAlmostEqual(by_ticker["VTI"], 20.0, places=1)
        self.assertAlmostEqual(by_ticker["VXUS"], 20.0, places=1)
        self.assertAlmostEqual(by_ticker["BND"], 30.0, places=1)
        self.assertAlmostEqual(by_ticker["VNQ"], 20.0, places=1)
        orphan = health.rebalance_df[health.rebalance_df["Orphan Sleeve"] == True]  # noqa: E712
        self.assertEqual(len(orphan), 1)
        self.assertAlmostEqual(float(orphan.iloc[0]["Objective (%)"]), 10.0, places=1)

    def test_mostly_on_plan_low_sharpe_not_primary_guided_issue(self) -> None:
        health = _eval_shadow(low_sharpe=True)
        sharpe = float(health.health_diagnostics.get("raw_sharpe", 0.0))
        self.assertLess(sharpe, 0.4)
        self.assertGreaterEqual(health.score, 70.0)

        sharpe_recs = [
            d
            for d in health.recommendation_details
            if "sharpe" in d.triggered_by.lower() or "Sharpe" in d.issue
        ]
        self.assertTrue(sharpe_recs)
        self.assertTrue(all(d.rec_class == core.REC_CLASS_DIAGNOSTIC for d in sharpe_recs))

        primary = core.select_primary_recommendation_detail(health.recommendation_details)
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertEqual(primary.rec_class, core.REC_CLASS_CORE)
        self.assertNotIn("Sharpe", primary.issue)
        self.assertNotIn("risk-adjusted return appears weak", primary.issue.lower())

        issue, _why, triggered = _primary_issue(health, beginner=False)
        self.assertNotIn("Sharpe", issue)
        self.assertNotIn("sharpe", triggered.lower())
        # Objective / missing sleeve should outrank diagnostic Sharpe.
        blob = f"{primary.issue} {primary.triggered_by} {issue}".lower()
        self.assertTrue(
            "not represented" in blob
            or "drift" in blob
            or "t-bill" in blob
            or "cash" in blob
            or "vti" in blob
            or "vnq" in blob
            or "objective" in blob,
            msg=f"unexpected primary: {primary.issue!r} / {triggered!r}",
        )

    def test_objective_drift_outranks_diagnostic_sharpe(self) -> None:
        health = _eval_shadow(low_sharpe=True)
        ordered = health.recommendation_details
        first_core = next(
            d for d in ordered if d.rec_class == core.REC_CLASS_CORE
        )
        first_diag = next(
            (d for d in ordered if d.rec_class == core.REC_CLASS_DIAGNOSTIC),
            None,
        )
        self.assertIsNotNone(first_diag)
        core_idx = ordered.index(first_core)
        diag_idx = ordered.index(first_diag)  # type: ignore[arg-type]
        self.assertLess(core_idx, diag_idx)
        self.assertIn("not represented", first_core.issue.lower())

    def test_diagnostics_still_present_as_context(self) -> None:
        health = _eval_shadow(low_sharpe=True)
        classes = {d.rec_class for d in health.recommendation_details}
        self.assertIn(core.REC_CLASS_CORE, classes)
        self.assertIn(core.REC_CLASS_DIAGNOSTIC, classes)
        self.assertTrue(
            any("Role" in d.evidence and "diagnostic" in d.evidence["Role"] for d in health.recommendation_details)
        )


class TestSelectPrimaryRecommendationDetail(unittest.TestCase):
    def test_skips_diagnostic_sharpe(self) -> None:
        details = [
            core._make_rec_detail(
                "Sharpe weak",
                issue="Risk-adjusted return appears weak in the model (diagnostic).",
                why_it_matters="context",
                triggered_by="Sharpe ratio = 0.28 (below 0.4 diagnostic threshold).",
                possible_benefit="n/a",
                evidence={"Sharpe ratio": "0.28"},
                rec_class=core.REC_CLASS_DIAGNOSTIC,
            ),
            core._make_rec_detail(
                "Missing T-Bills",
                issue="A category in your objective is not represented in current holdings.",
                why_it_matters="sleeve",
                triggered_by="Cash / T-Bills: objective 10.0% vs current 0%.",
                possible_benefit="add BIL",
                evidence={"Orphan sleeve": "yes"},
                rec_class=core.REC_CLASS_CORE,
            ),
        ]
        primary = core.select_primary_recommendation_detail(details)
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertIn("not represented", primary.issue.lower())


if __name__ == "__main__":
    unittest.main()
