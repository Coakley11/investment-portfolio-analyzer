"""AMI Forward metrics cold-start: resolve via canonical helper without visiting Forward UI."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
import pandas as pd

import portfolio_core as core
from applied_math_context import (
    build_investment_applied_math_context,
    ensure_ami_forward_scenario_metrics,
)
from components.macro_engine import (
    FORWARD_ENGINE_INPUTS_KEY,
    FORWARD_HORIZON_PERSIST_KEY,
    FORWARD_PROJECTION_FP_KEY,
    FORWARD_PROJECTION_KEY,
    SHARED_MACRO_DEFAULTS,
    build_canonical_forward_fingerprint,
    macro_assumptions_from_session,
    peek_valid_forward_projection,
    resolve_canonical_forward_projection,
    store_forward_engine_inputs,
)
from investment_ami.integration.instant_solver_facade import solve_instant_insight
from investment_ami_context import detect_investment_send_intent
from investment_ami_instant_solver import _rebalance_answer
from investment_ami_macro import _macro_environment_solve


_TICKERS = ["VTI", "VXUS", "BND", "VNQ"]
_W = np.array([0.40, 0.20, 0.30, 0.10], dtype=float)
_TYPES = ["Equity", "Equity", "Bonds", "REIT"]
_RF = 0.04
_IV = 10_000.0
_START = "2018-01-01"
_END = "2024-12-31"
_ORIG = (
    "How does my current macro environment affect my portfolio, "
    "and should I change my allocation because of it?"
)


def _synthetic_returns(seed: int = 21) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=900, freq="B")
    specs = {
        "VTI": (0.00055, 0.010),
        "VXUS": (0.00035, 0.012),
        "BND": (0.00008, 0.003),
        "VNQ": (0.00040, 0.014),
    }
    return pd.DataFrame(
        {t: rng.normal(mu, sig, size=len(idx)) for t, (mu, sig) in specs.items()},
        index=idx,
    )


def _engine_bundle():
    rets = _synthetic_returns()
    mean_rets, cov, aligned = core.annualized_mean_and_cov(rets, tickers=_TICKERS, weights=_W)
    metrics = core.compute_extended_metrics(aligned, _W, _RF, _IV, tickers=_TICKERS)
    return metrics, mean_rets, cov


def _frozen_macros(ss: dict) -> None:
    ss["health_rate_env"] = "Rising Rates"
    ss["health_inflation"] = "High Inflation"
    ss["health_recession"] = 60
    ss["health_valuation"] = "Expensive"
    ss["health_regime"] = "Recession"


def _sync_streamlit_session(ss: dict) -> None:
    """Populate Streamlit session for ensure/resolve (never embed proxy on AMI ctx)."""
    import streamlit as st

    for key in list(st.session_state.keys()):
        del st.session_state[key]
    for key, val in ss.items():
        st.session_state[key] = val


def _fresh_session(**extra) -> dict:
    ss = dict(SHARED_MACRO_DEFAULTS)
    _frozen_macros(ss)
    ss[FORWARD_HORIZON_PERSIST_KEY] = 10
    ss["holdings_df"] = pd.DataFrame(
        [
            {"Ticker": "VTI", "Weight (%)": 40.0, "Asset Type": "Equity"},
            {"Ticker": "VXUS", "Weight (%)": 20.0, "Asset Type": "Equity"},
            {"Ticker": "BND", "Weight (%)": 30.0, "Asset Type": "Bond"},
            {"Ticker": "VNQ", "Weight (%)": 10.0, "Asset Type": "REIT"},
        ]
    )
    ss["investment_active_tab"] = "Portfolio Health"
    ss["portfolio_objective"] = "balanced growth"
    ss["risk_free_pct"] = 4.0
    metrics, mean_rets, cov = _engine_bundle()
    store_forward_engine_inputs(
        ss,
        metrics=metrics,
        mean_returns=mean_rets,
        cov=cov,
        tickers=_TICKERS,
        weights=_W,
        asset_types=_TYPES,
        start=_START,
        end=_END,
        initial_value=_IV,
        risk_free_rate=_RF,
    )
    # Explicitly no prior Forward UI visit.
    ss.pop(FORWARD_PROJECTION_KEY, None)
    ss.pop(FORWARD_PROJECTION_FP_KEY, None)
    ss.update(extra)
    _sync_streamlit_session(ss)
    return ss


class TestAmiForwardColdStart(unittest.TestCase):
    def test_01_fresh_session_macro_ami_gets_forward_metrics(self) -> None:
        ss = _fresh_session()
        self.assertNotIn(FORWARD_PROJECTION_KEY, ss)
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        # Context attach must not require Forward page, but may not compute yet.
        ok = ensure_ami_forward_scenario_metrics(ctx, ss)
        self.assertTrue(ok)
        self.assertIsNotNone(ctx.get("forward_modeled_return"))
        self.assertIsNotNone(ctx.get("forward_modeled_volatility"))
        self.assertIsNotNone(ctx.get("forward_modeled_sharpe"))

    def test_02_forward_page_never_visited_metrics_available(self) -> None:
        ss = _fresh_session()
        self.assertIsNone(ss.get(FORWARD_PROJECTION_KEY))
        result = _macro_environment_solve(
            build_investment_applied_math_context("Portfolio Health", ss),
            beginner=False,
            question=_ORIG,
        )
        text = (result.short_answer or "") + str(result.analyst_sections or {})
        self.assertIn("Forward modeled", text)
        self.assertIn("forward_modeled_return", result.computed or {})
        import streamlit as st

        self.assertIsNotNone(st.session_state.get(FORWARD_PROJECTION_KEY))

    def test_03_existing_valid_projection_reused(self) -> None:
        ss = _fresh_session()
        first = resolve_canonical_forward_projection(ss)
        assert first is not None
        with mock.patch(
            "portfolio_core.compute_forward_projection_with_profile",
            side_effect=AssertionError("must reuse cache"),
        ):
            second = resolve_canonical_forward_projection(ss)
        self.assertIs(second, first)

    def test_04_macro_change_rejects_stale_projection(self) -> None:
        ss = _fresh_session()
        first = resolve_canonical_forward_projection(ss)
        assert first is not None
        old_fp = ss[FORWARD_PROJECTION_FP_KEY]
        ss["health_valuation"] = "Cheap"
        second = resolve_canonical_forward_projection(ss)
        assert second is not None
        self.assertNotEqual(ss[FORWARD_PROJECTION_FP_KEY], old_fp)
        self.assertNotAlmostEqual(first.adjusted_return, second.adjusted_return, places=6)

    def test_05_holdings_change_rejects_stale(self) -> None:
        ss = _fresh_session()
        first = resolve_canonical_forward_projection(ss)
        assert first is not None
        old_fp = ss[FORWARD_PROJECTION_FP_KEY]
        inputs = dict(ss[FORWARD_ENGINE_INPUTS_KEY])
        inputs["tickers"] = ["VTI", "BND", "VXUS", "VNQ"]  # order change
        inputs["weights"] = np.array([0.40, 0.30, 0.20, 0.10])
        ss[FORWARD_ENGINE_INPUTS_KEY] = inputs
        # Keep stale projection+fp deliberately.
        peeked = peek_valid_forward_projection(ss)
        self.assertIsNone(peeked)
        second = resolve_canonical_forward_projection(ss)
        assert second is not None
        self.assertNotEqual(ss[FORWARD_PROJECTION_FP_KEY], old_fp)

    def test_06_weights_change_rejects_stale(self) -> None:
        ss = _fresh_session()
        resolve_canonical_forward_projection(ss)
        old_fp = ss[FORWARD_PROJECTION_FP_KEY]
        inputs = dict(ss[FORWARD_ENGINE_INPUTS_KEY])
        inputs["weights"] = np.array([0.50, 0.10, 0.30, 0.10])
        ss[FORWARD_ENGINE_INPUTS_KEY] = inputs
        self.assertIsNone(peek_valid_forward_projection(ss))
        resolve_canonical_forward_projection(ss)
        self.assertNotEqual(ss[FORWARD_PROJECTION_FP_KEY], old_fp)

    def test_07_risk_free_change_invalidates(self) -> None:
        ss = _fresh_session()
        resolve_canonical_forward_projection(ss)
        old_fp = ss[FORWARD_PROJECTION_FP_KEY]
        inputs = dict(ss[FORWARD_ENGINE_INPUTS_KEY])
        inputs["risk_free_rate"] = 0.055
        ss[FORWARD_ENGINE_INPUTS_KEY] = inputs
        self.assertIsNone(peek_valid_forward_projection(ss))
        resolve_canonical_forward_projection(ss)
        self.assertNotEqual(ss[FORWARD_PROJECTION_FP_KEY], old_fp)

    def test_08_ami_matches_canonical_helper(self) -> None:
        ss = _fresh_session()
        canonical = resolve_canonical_forward_projection(ss)
        assert canonical is not None
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        # Clear ctx forward fields; ensure re-reads same cache.
        ctx.pop("forward_modeled_return", None)
        ensure_ami_forward_scenario_metrics(ctx, ss)
        self.assertAlmostEqual(
            float(ctx["forward_modeled_return"]), float(canonical.adjusted_return), places=8
        )
        self.assertAlmostEqual(
            float(ctx["forward_modeled_volatility"]), float(canonical.adjusted_volatility), places=8
        )
        self.assertAlmostEqual(
            float(ctx["forward_modeled_sharpe"]), float(canonical.adjusted_sharpe), places=8
        )

    def test_09_no_duplicate_forward_formula_in_ami(self) -> None:
        ss = _fresh_session()
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        with mock.patch(
            "components.macro_engine.resolve_canonical_forward_projection",
            wraps=resolve_canonical_forward_projection,
        ) as resolve_mock:
            with mock.patch(
                "portfolio_core.compute_forward_projection_with_profile",
                wraps=core.compute_forward_projection_with_profile,
            ) as compute_mock:
                ensure_ami_forward_scenario_metrics(ctx, ss)
                self.assertTrue(resolve_mock.called)
                self.assertTrue(compute_mock.called)
                # Ensure AMI did not invent a parallel return formula.
                self.assertNotIn("forward_return_shift", ctx)

    def test_10_historical_health_metrics_remain_distinct(self) -> None:
        ss = _fresh_session()
        ss["health_result"] = type(
            "HR",
            (),
            {
                "score": 70,
                "score_label": "OK",
                "status_message": "ok",
                "health_diagnostics": {
                    "annual_return": 0.08,
                    "annual_volatility": 0.15,
                    "portfolio_sharpe": 0.40,
                    "max_drawdown": -0.2,
                },
                "expected_return": 0.08,
                "volatility": 0.15,
                "sharpe": 0.40,
                "max_drawdown": -0.2,
                "risk_level": "Moderate",
            },
        )()
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        ensure_ami_forward_scenario_metrics(ctx, ss)
        self.assertEqual(ctx.get("expected_return"), "8.0%")
        self.assertNotEqual(
            float(ctx["forward_modeled_return"]),
            0.08,
        )

    def test_11_scenario_disclaimer_remains(self) -> None:
        ss = _fresh_session()
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        ensure_ami_forward_scenario_metrics(ctx, ss)
        disc = str(ctx.get("forward_metrics_disclaimer") or "").lower()
        self.assertIn("scenario", disc)
        result = _macro_environment_solve(ctx, beginner=False, question=_ORIG)
        text = (result.short_answer or "").lower()
        self.assertTrue("scenario" in text or "model output" in text)

    def test_12_non_macro_does_not_require_forward_compute(self) -> None:
        ss = _fresh_session()
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        with mock.patch(
            "portfolio_core.compute_forward_projection_with_profile",
            side_effect=AssertionError("rebalance must not compute Forward"),
        ):
            # Attach path: no compute.
            self.assertIsNone(ctx.get("forward_modeled_return"))
            _rebalance_answer(ctx, beginner=False)

    def test_13_sleeve_70_30_10_still_green(self) -> None:
        ss = _fresh_session()
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        result = _macro_environment_solve(ctx, beginner=False, question=_ORIG)
        computed = result.computed or {}
        self.assertAlmostEqual(float(computed["sleeve_equity_pct"]), 70.0, places=1)
        self.assertAlmostEqual(float(computed["sleeve_bonds_pct"]), 30.0, places=1)
        self.assertAlmostEqual(float(computed["sleeve_reit_pct"]), 10.0, places=1)

    def test_14_pure_rebalance_routing_unchanged(self) -> None:
        self.assertEqual(detect_investment_send_intent("Explain my allocation.", ""), "rebalance_allocation")
        self.assertEqual(detect_investment_send_intent("Should I rebalance?", ""), "allocation_recommendation")
        self.assertEqual(detect_investment_send_intent(_ORIG, ""), "macro_environment")

    def test_15_forward_helper_matches_direct_core_call(self) -> None:
        """Forward UI/helper results remain the same as direct core compute for identical inputs."""
        ss = _fresh_session()
        assumptions = macro_assumptions_from_session(ss)
        inputs = ss[FORWARD_ENGINE_INPUTS_KEY]
        direct = core.compute_forward_projection_with_profile(
            metrics=inputs["metrics"],
            mean_returns=np.asarray(inputs["mean_returns"]).copy(),
            cov=np.asarray(inputs["cov"]).copy(),
            tickers=list(inputs["tickers"]),
            weights=np.asarray(inputs["weights"]),
            asset_types=list(inputs["asset_types"]),
            assumptions=assumptions,
            initial_value=float(inputs["initial_value"]),
            years=float(ss[FORWARD_HORIZON_PERSIST_KEY]),
            risk_free_rate=float(inputs["risk_free_rate"]),
        )
        via_helper = resolve_canonical_forward_projection(ss)
        assert via_helper is not None
        self.assertAlmostEqual(via_helper.adjusted_return, direct.adjusted_return, places=10)
        self.assertAlmostEqual(via_helper.adjusted_volatility, direct.adjusted_volatility, places=10)
        self.assertAlmostEqual(via_helper.adjusted_sharpe, direct.adjusted_sharpe, places=10)
        # Fingerprint includes macros + holdings + RF.
        fp = build_canonical_forward_fingerprint(
            assumptions,
            start=_START,
            end=_END,
            years=10.0,
            tickers=_TICKERS,
            weights=_W,
            risk_free_rate=_RF,
            initial_value=_IV,
        )
        self.assertEqual(ss[FORWARD_PROJECTION_FP_KEY], fp)

    def test_end_to_end_macro_question_cold_start(self) -> None:
        ss = _fresh_session()
        ctx = build_investment_applied_math_context("Portfolio Health", ss)
        pair = solve_instant_insight(_ORIG, ctx)
        assert pair is not None
        _, result = pair
        text = (result.short_answer or "").lower()
        self.assertIn("high inflation", text)
        self.assertIn("forward modeled", text)
        self.assertIn("-", text)  # negative return under stress

    def test_16_context_json_safe_with_streamlit_session_proxy(self) -> None:
        """Regression: never embed SessionStateProxy on AMI ctx (live TypeError)."""
        import json

        import streamlit as st
        from json_safe import json_safe_context

        ss = _fresh_session()
        # Live path passes Streamlit session into context builder.
        ctx = build_investment_applied_math_context("Portfolio Health", st.session_state)
        self.assertNotIn("_ami_session_ref", ctx)
        self.assertNotIn("_ami_session_dict", ctx)
        # Must not raise TypeError: SessionStateProxy is not JSON serializable
        safe = json_safe_context(ctx)
        json.dumps(safe, ensure_ascii=False)
        ensure_ami_forward_scenario_metrics(ctx)  # uses st.session_state
        self.assertIsNotNone(ctx.get("forward_modeled_return"))
        safe2 = json_safe_context(ctx)
        json.dumps(safe2, ensure_ascii=False)

    def test_17_fingerprint_uses_primitives_not_session_proxy(self) -> None:
        import streamlit as st

        ss = _fresh_session()
        assumptions = macro_assumptions_from_session(st.session_state)
        fp = build_canonical_forward_fingerprint(
            assumptions,
            start=_START,
            end=_END,
            years=10.0,
            tickers=_TICKERS,
            weights=_W,
            risk_free_rate=_RF,
            initial_value=_IV,
        )
        self.assertIsInstance(fp, str)
        self.assertNotIn("SessionState", fp)
        self.assertIn("Rising Rates", fp)
        self.assertIn("High Inflation", fp)
        # Mutating via proxy updates fingerprint inputs the same as a plain dict.
        st.session_state["health_valuation"] = "Cheap"
        assumptions2 = macro_assumptions_from_session(st.session_state)
        fp2 = build_canonical_forward_fingerprint(
            assumptions2,
            start=_START,
            end=_END,
            years=10.0,
            tickers=_TICKERS,
            weights=_W,
            risk_free_rate=_RF,
            initial_value=_IV,
        )
        self.assertNotEqual(fp, fp2)
        self.assertIn("Cheap", fp2)


if __name__ == "__main__":
    unittest.main()
