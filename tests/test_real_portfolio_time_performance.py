"""Deterministic Real Portfolio TWR / XIRR / NAV reconstruction tests (no live Yahoo)."""

from __future__ import annotations

import copy
import unittest
from datetime import date

import pandas as pd

import portfolio_engine as pe
from investment_ami.decision_support.real_portfolio_time_performance import (
    XIRR_ANNUALIZE_MIN_DAYS,
    analyze_real_portfolio_time_performance,
    benchmark_total_return,
    build_nav_series,
    compute_modified_dietz,
    compute_twr,
    reconstruct_holdings_and_cash,
)


def _dep(amount: float, day: str, *, txn_id: str = "") -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=txn_id or pe._new_id(),
        action="cash_deposit",
        date=day,
        ticker="",
        quantity=amount,
        execution_price=1.0,
    )


def _wd(amount: float, day: str, *, txn_id: str = "") -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=txn_id or pe._new_id(),
        action="cash_withdrawal",
        date=day,
        ticker="",
        quantity=amount,
        execution_price=1.0,
    )


def _buy(ticker: str, qty: float, price: float, day: str, *, txn_id: str = "") -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=txn_id or pe._new_id(),
        action="buy",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        asset_type="etf",
    )


def _sell(ticker: str, qty: float, price: float, day: str, *, txn_id: str = "") -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=txn_id or pe._new_id(),
        action="sell",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        asset_type="etf",
    )


def _prices(rows: dict[str, dict[str, float]]) -> pd.DataFrame:
    """rows: date_iso -> {ticker: price}"""
    idx = sorted(rows.keys())
    tickers = sorted({t for day in rows.values() for t in day})
    data = {t: [rows[d].get(t) for d in idx] for t in tickers}
    df = pd.DataFrame(data, index=pd.to_datetime(idx))
    return df


class TestReconstructionAndFlows(unittest.TestCase):
    def test_buy_sell_are_internal_cash_moves(self) -> None:
        txns = [
            _dep(1000.0, "2024-01-02", txn_id="d1"),
            _buy("VTI", 5, 100.0, "2024-01-02", txn_id="b1"),
            _sell("VTI", 2, 100.0, "2024-01-03", txn_id="s1"),
        ]
        shares, cash, contrib = reconstruct_holdings_and_cash(txns, as_of=date(2024, 1, 3))
        self.assertAlmostEqual(shares["VTI"], 3.0)
        self.assertAlmostEqual(cash, 1000.0 - 500.0 + 200.0)
        self.assertAlmostEqual(contrib, 1000.0)  # sell is not external

    def test_deposit_increases_contrib_not_implied_by_buy(self) -> None:
        txns = [_dep(500.0, "2024-01-02"), _buy("VTI", 2, 100.0, "2024-01-02")]
        _, _, contrib = reconstruct_holdings_and_cash(txns, as_of=date(2024, 1, 2))
        self.assertAlmostEqual(contrib, 500.0)

    def test_no_ledger_mutation(self) -> None:
        txns = [_dep(1000.0, "2024-01-02"), _buy("VTI", 10, 100.0, "2024-01-02")]
        before = copy.deepcopy([t.to_record() for t in txns])
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 50.0},
                "2024-01-03": {"VTI": 100.0, "BENCH": 50.0},
            }
        )
        analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 3),
            benchmark_symbol="BENCH",
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3)],
        )
        self.assertEqual([t.to_record() for t in txns], before)


class TestTWRCashFlowAwareness(unittest.TestCase):
    def test_flat_prices_plus_deposit_twr_near_zero(self) -> None:
        # Day1: deposit 1000, buy 10 @ 100 → NAV 1000
        # Day2: flat
        # Day3: deposit 1000, buy 10 @ 100 → NAV 2000, prices flat → TWR ~ 0
        txns = [
            _dep(1000.0, "2024-01-02", txn_id="d1"),
            _buy("VTI", 10, 100.0, "2024-01-02", txn_id="b1"),
            _dep(1000.0, "2024-01-04", txn_id="d2"),
            _buy("VTI", 10, 100.0, "2024-01-04", txn_id="b2"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 10.0},
                "2024-01-03": {"VTI": 100.0, "BENCH": 10.0},
                "2024-01-04": {"VTI": 100.0, "BENCH": 10.0},
            }
        )
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 4),
            benchmark_symbol="BENCH",
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        )
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.twr_since_inception or 0.0, 0.0, places=6)
        # NAV jumped with deposit, but TWR index should stay ~100
        self.assertAlmostEqual(result.twr_index[-1][1], 100.0, places=4)
        self.assertGreater(result.nav_series[-1].nav, result.nav_series[0].nav)

    def test_rising_prices_with_later_deposit_correct_twr(self) -> None:
        # Start: 10 shares @ 100, NAV=1000
        # Mid: price 110, NAV=1100 → +10%
        # Then deposit 1000 + buy 10 @ 110, NAV=2200
        # End: price 121, NAV=2420
        # Subperiod2: (2420 - 1000) / 1100 - 1 = 29.09%? 
        # r2 = (2420 - 1000)/1100 - 1 = 0.290909 on the second step if only 2 points after deposit day...
        # Daily: 
        # d1 NAV=1000 CF=1000 (deposit day) — first point, no return yet
        # d2 NAV=1100 CF=0 → r=(1100-0)/1000-1=0.10
        # d3 NAV=2200 CF=1000 → r=(2200-1000)/1100-1=0.090909? Wait buy at 110: 10*110=1100 + 10*110 from new = 2200, CF=1000
        # r = (2200-1000)/1100 - 1 = 0.090909 — but prices didn't move on deposit day; should be ~0
        # Actually on deposit day price still 110, old 10 sh = 1100, +1000 cash then buy → still 2200. 
        # (2200-1000)/1100 - 1 = 0.0909 which is WRONG (should be 0).
        #
        # Problem: end-of-day CF convention assumes CF is added to ending NAV without return.
        # (NAV_t - CF)/NAV_{t-1} - 1 should be 0 when prices flat: (2200-1000)/1100 - 1 = 0.0909 ≠ 0.
        #
        # The issue is that on deposit day we also bought, but more importantly:
        # Before deposit NAV should be 1100. After deposit+buy NAV=2200. CF=1000.
        # (2200-1000)=1200 / 1100 - 1 = 9% — still wrong.
        #
        # Why? Because we're comparing to previous day. On deposit day prices unchanged,
        # pre-flow NAV = 1100, post-flow NAV = 2200, CF = 1000.
        # Correct: r = pre_flow_end / prev - 1 = 1100/1100 - 1 = 0
        # Or: r = (NAV_t - CF_t) / NAV_{t-1} - 1 only works if NAV_t = pre_flow + CF exactly.
        # Here NAV_t = 2200, CF = 1000, NAV_t - CF = 1200 ≠ 1100.
        #
        # Root cause: cash after deposit before buy is 1000 (from prior cash 0 + deposit), 
        # then buy spends 1100 but we only had 1000 cash from deposit + 0 leftover...
        # Let's recalculate:
        # After day1: 10 sh, cash 0, contrib 1000
        # Day2 mark @110: NAV=1100
        # Day3: deposit 1100 (not 1000!) buy 10 @ 110
        #
        # Fix fixture: deposit exactly the buy amount with flat mark that day.

        txns = [
            _dep(1000.0, "2024-01-02", txn_id="d1"),
            _buy("VTI", 10, 100.0, "2024-01-02", txn_id="b1"),
            _dep(1100.0, "2024-01-04", txn_id="d2"),
            _buy("VTI", 10, 110.0, "2024-01-04", txn_id="b2"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 100.0},
                "2024-01-03": {"VTI": 110.0, "BENCH": 110.0},
                "2024-01-04": {"VTI": 110.0, "BENCH": 110.0},
                "2024-01-05": {"VTI": 121.0, "BENCH": 121.0},
            }
        )
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 5),
            benchmark_symbol="BENCH",
            valuation_dates=[
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
            ],
        )
        self.assertTrue(result.ok)
        # Subreturns: +10%, ~0% on deposit day, +10% → 1.1*1.0*1.1 - 1 = 21%
        self.assertAlmostEqual(result.twr_since_inception or 0.0, 0.21, places=4)

    def test_withdrawal_does_not_create_fake_negative_return_when_flat(self) -> None:
        txns = [
            _dep(2000.0, "2024-01-02", txn_id="d1"),
            _buy("VTI", 10, 100.0, "2024-01-02", txn_id="b1"),
            # leave 1000 cash
            _wd(500.0, "2024-01-03", txn_id="w1"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 1.0},
                "2024-01-03": {"VTI": 100.0, "BENCH": 1.0},
            }
        )
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 3),
            benchmark_symbol="BENCH",
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3)],
        )
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.twr_since_inception or 0.0, 0.0, places=6)

    def test_contribution_between_dates_does_not_distort_twr(self) -> None:
        # Same as flat+deposit test — explicit alias for requirement wording.
        self.test_flat_prices_plus_deposit_twr_near_zero()


class TestMissingMarksAndPeriods(unittest.TestCase):
    def test_missing_historical_marks_omit_days(self) -> None:
        txns = [
            _dep(1000.0, "2024-01-02"),
            _buy("VTI", 10, 100.0, "2024-01-02"),
            _buy("MISSING", 5, 50.0, "2024-01-02"),
        ]
        # MISSING never appears in the price panel → every day with that holding is omitted.
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 1.0},
                "2024-01-03": {"VTI": 101.0, "BENCH": 1.0},
                "2024-01-04": {"VTI": 102.0, "BENCH": 1.0},
            }
        )
        series, warnings = build_nav_series(
            txns,
            prices,
            as_of=date(2024, 1, 4),
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        )
        self.assertEqual(len(series), 0)
        self.assertTrue(any("omitted_valuation_days" in w for w in warnings))

    def test_weekend_lookback_allows_prior_close(self) -> None:
        txns = [
            _dep(1000.0, "2024-01-02"),
            _buy("VTI", 10, 100.0, "2024-01-02"),
        ]
        prices = _prices({"2024-01-02": {"VTI": 100.0, "BENCH": 1.0}})
        series, _ = build_nav_series(
            txns,
            prices,
            as_of=date(2024, 1, 3),
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3)],
        )
        # Jan 3 can mark via lookback to Jan 2 close.
        self.assertEqual([p.as_of for p in series], [date(2024, 1, 2), date(2024, 1, 3)])
        self.assertAlmostEqual(series[1].nav, 1000.0, places=2)

    def test_short_history_period_insufficient(self) -> None:
        txns = [
            _dep(1000.0, "2024-01-02"),
            _buy("VTI", 10, 100.0, "2024-01-02"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 10.0},
                "2024-01-03": {"VTI": 101.0, "BENCH": 10.1},
                "2024-01-04": {"VTI": 102.0, "BENCH": 10.2},
            }
        )
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 4),
            benchmark_symbol="BENCH",
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        )
        by = {p.period: p for p in result.periods}
        self.assertTrue(by["since_inception"].available)
        self.assertFalse(by["1m"].available)
        self.assertFalse(by["1y"].available)
        self.assertIn("Insufficient", by["1m"].message)

    def test_xirr_suppressed_for_short_span(self) -> None:
        self.assertEqual(XIRR_ANNUALIZE_MIN_DAYS, 90)
        txns = [
            _dep(1000.0, "2024-01-02"),
            _buy("VTI", 10, 100.0, "2024-01-02"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 1.0},
                "2024-01-09": {"VTI": 105.0, "BENCH": 1.0},
            }
        )
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 9),
            benchmark_symbol="BENCH",
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 9)],
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.xirr_shown)
        self.assertIsNone(result.xirr_annualized)
        self.assertTrue(result.meta.get("xirr_suppressed"))


class TestBenchmarkAlignment(unittest.TestCase):
    def test_benchmark_same_dates(self) -> None:
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 200.0},
                "2024-01-10": {"VTI": 110.0, "BENCH": 220.0},
            }
        )
        br = benchmark_total_return(prices, "BENCH", date(2024, 1, 2), date(2024, 1, 10))
        self.assertAlmostEqual(br or 0.0, 0.10, places=6)

    def test_period_excess_uses_aligned_window(self) -> None:
        txns = [
            _dep(1000.0, "2024-01-02"),
            _buy("VTI", 10, 100.0, "2024-01-02"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0, "BENCH": 50.0},
                "2024-01-03": {"VTI": 110.0, "BENCH": 55.0},
            }
        )
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 1, 3),
            benchmark_symbol="BENCH",
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3)],
        )
        p = next(x for x in result.periods if x.period == "since_inception")
        self.assertTrue(p.available)
        self.assertAlmostEqual(p.twr or 0.0, 0.10, places=4)
        self.assertAlmostEqual(p.benchmark_return or 0.0, 0.10, places=4)
        self.assertAlmostEqual(p.excess_twr_vs_benchmark or 0.0, 0.0, places=4)


class TestShadowLikeScenario(unittest.TestCase):
    def test_sept_funding_and_later_contribution(self) -> None:
        """Sept 3 fund + Sept 10 $1000 contribution must not create fake TWR from the deposit."""
        txns = [
            _dep(4250.0, "2024-09-03", txn_id="d0"),
            _buy("VTI", 14.875, 100.0, "2024-09-03", txn_id="b1"),  # 1487.5
            _buy("VXUS", 10.625, 100.0, "2024-09-03", txn_id="b2"),  # 1062.5
            _buy("BND", 12.75, 100.0, "2024-09-03", txn_id="b3"),  # 1275
            _buy("VNQ", 4.25, 100.0, "2024-09-03", txn_id="b4"),  # 425
            _dep(1000.0, "2024-09-10", txn_id="d1"),
            _buy("VTI", 3.5, 100.0, "2024-09-10", txn_id="b5"),
            _buy("VXUS", 2.5, 100.0, "2024-09-10", txn_id="b6"),
            _buy("BND", 3.0, 100.0, "2024-09-10", txn_id="b7"),
            _buy("VNQ", 1.0, 100.0, "2024-09-10", txn_id="b8"),
        ]
        # Flat marks → TWR ~ 0 despite NAV rising by ~1000
        days = [
            "2024-09-03",
            "2024-09-04",
            "2024-09-05",
            "2024-09-06",
            "2024-09-09",
            "2024-09-10",
            "2024-09-11",
        ]
        rows = {
            d: {"VTI": 100.0, "VXUS": 100.0, "BND": 100.0, "VNQ": 100.0, "BENCH": 100.0}
            for d in days
        }
        prices = _prices(rows)
        result = analyze_real_portfolio_time_performance(
            txns,
            prices,
            as_of=date(2024, 9, 11),
            benchmark_symbol="BENCH",
            valuation_dates=[date.fromisoformat(d) for d in days],
        )
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.twr_since_inception or 0.0, 0.0, places=5)
        self.assertAlmostEqual(result.nav_series[0].cumulative_net_contributions, 4250.0, places=2)
        self.assertAlmostEqual(result.nav_series[-1].cumulative_net_contributions, 5250.0, places=2)
        self.assertAlmostEqual(
            result.nav_series[-1].nav - result.nav_series[0].nav,
            1000.0,
            delta=1.0,
        )


class TestDietzAndHelpers(unittest.TestCase):
    def test_modified_dietz_flat_with_flow(self) -> None:
        txns = [
            _dep(1000.0, "2024-01-02"),
            _buy("VTI", 10, 100.0, "2024-01-02"),
            _dep(1000.0, "2024-01-04"),
            _buy("VTI", 10, 100.0, "2024-01-04"),
        ]
        prices = _prices(
            {
                "2024-01-02": {"VTI": 100.0},
                "2024-01-03": {"VTI": 100.0},
                "2024-01-04": {"VTI": 100.0},
            }
        )
        series, _ = build_nav_series(
            txns,
            prices,
            valuation_dates=[date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
        )
        diet = compute_modified_dietz(series)
        self.assertIsNotNone(diet)
        self.assertAlmostEqual(diet or 0.0, 0.0, places=5)
        twr, _ = compute_twr(series)
        self.assertAlmostEqual(twr or 0.0, 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
