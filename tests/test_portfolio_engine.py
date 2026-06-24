"""Tests for the real portfolio engine (Phase 1)."""

from __future__ import annotations

import datetime as dt

import portfolio_engine as pe


def _buy(ticker: str, qty: float, price: float, *, day: str = "2024-01-15") -> pe.PortfolioTransaction:
    return pe.PortfolioTransaction(
        id=pe._new_id(),
        action="buy",
        date=day,
        ticker=ticker,
        quantity=qty,
        execution_price=price,
        company_name=ticker,
        asset_type="etf",
    )


def test_ledger_builds_position_and_average_cost():
    txns = [
        _buy("VOO", 10, 400.0),
        _buy("VOO", 5, 430.0),
    ]
    prices = {"VOO": 450.0}
    positions, cash = pe.build_positions(txns, prices=prices)
    assert len(positions) == 1
    pos = positions[0]
    assert pos.ticker == "VOO"
    assert pos.shares_owned == 15
    assert abs(pos.average_cost_basis - (10 * 400 + 5 * 430) / 15) < 0.01
    assert abs(pos.market_value - 15 * 450) < 0.01
    assert abs(cash - (-(10 * 400 + 5 * 430))) < 0.01


def test_sell_reduces_shares_and_updates_cash():
    txns = [
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="cash_deposit",
            date="2024-01-01",
            ticker="",
            quantity=10_000.0,
            execution_price=1.0,
        ),
        _buy("VTI", 20, 200.0),
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="sell",
            date="2024-02-01",
            ticker="VTI",
            quantity=5,
            execution_price=210.0,
            asset_type="etf",
        ),
    ]
    prices = {"VTI": 205.0}
    positions, cash = pe.build_positions(txns, prices=prices)
    assert len(positions) == 1
    assert positions[0].shares_owned == 15
    assert abs(cash - (10_000.0 - 20 * 200.0 + 5 * 210.0)) < 0.01


def test_cash_deposit_increases_cash_balance():
    txns = [
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="cash_deposit",
            date="2024-01-01",
            ticker="",
            quantity=5000.0,
            execution_price=1.0,
        ),
        _buy("BND", 10, 80.0),
    ]
    prices = {"BND": 82.0}
    positions, cash = pe.build_positions(txns, prices=prices)
    assert len(positions) == 1
    assert abs(cash - (5000.0 - 10 * 80.0)) < 0.01


def test_buy_before_deposit_uses_order_independent_cash():
    """Regression: buys entered before deposits must still reduce cash."""
    txns = [
        _buy("VOO", 100, 485.46),
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="cash_deposit",
            date="2024-01-02",
            ticker="",
            quantity=10_000.0,
            execution_price=1.0,
        ),
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="cash_deposit",
            date="2024-01-03",
            ticker="",
            quantity=50_000.0,
            execution_price=1.0,
        ),
    ]
    _positions, cash = pe.build_positions(txns, prices={"VOO": 500.0})
    expected = 60_000.0 - 48_546.0
    assert abs(cash - expected) < 0.01
    ledger = pe.compute_cash_ledger_summary(txns)
    assert abs(ledger.net_cash - expected) < 0.01


def test_format_currency_and_shares():
    assert pe.format_currency(27521.1) == "$27,521.10"
    assert pe.format_currency(-12.5) == "-$12.50"
    assert pe.format_shares(40) == "40 shares"
    assert pe.format_shares(10.25) == "10.25 shares"
    assert pe.format_shares(40.0) == "40 shares"


def test_stock_split_adjusts_shares_and_market_value(monkeypatch):
    """SCHD 3:1 split (Oct 2024): pre-split lots should triple in share count."""
    monkeypatch.setattr(
        pe,
        "_stock_splits_for_symbol",
        lambda sym: [(dt.date(2024, 10, 11), 3.0)] if sym == "SCHD" else [],
    )
    txns = [_buy("SCHD", 25, 85.0, day="2024-06-01")]
    positions, _cash = pe.build_positions(txns, prices={"SCHD": 32.02})
    assert len(positions) == 1
    pos = positions[0]
    assert pos.ticker == "SCHD"
    assert abs(pos.shares_owned - 75.0) < 0.01
    assert abs(pos.average_cost_basis - 85.0 / 3.0) < 0.01
    assert abs(pos.market_value - 75.0 * 32.02) < 0.05
    assert pos.stock_splits_applied == 1


def test_cash_transaction_display_omits_share_price():
    txns = [
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="cash_deposit",
            date="2024-01-01",
            ticker="",
            quantity=50_000.0,
            execution_price=1.0,
        ),
        _buy("VOO", 10, 688.11),
    ]
    df = pe.transactions_display_dataframe(txns)
    cash_row = df.iloc[1]
    assert "Price" not in df.columns
    assert "Amount" in df.columns
    assert cash_row["Amount"] == "$50,000.00"
    assert cash_row["Ticker"] == "—"
    sec_row = df.iloc[0]
    assert sec_row["Price/Share"] == "$688.11"
    assert sec_row["Shares"] == "10 shares"


def test_portfolio_summary_allocation_buckets():
    txns = [
        pe.PortfolioTransaction(
            id=pe._new_id(),
            action="cash_deposit",
            date="2024-01-01",
            ticker="",
            quantity=1000.0,
            execution_price=1.0,
        ),
        _buy("VOO", 1, 400.0),
        _buy("AAPL", 2, 150.0, day="2024-01-16"),
    ]
    prices = {"VOO": 420.0, "AAPL": 160.0}
    summary = pe.compute_portfolio_summary(txns, prices=prices)
    assert summary.num_holdings == 2
    assert summary.total_portfolio_value > 0
    assert "ETFs" in summary.allocation_by_bucket
    assert "Stocks" in summary.allocation_by_bucket
    assert summary.allocation_by_bucket["Cash"] >= 0


def test_position_sizing_warnings():
    txns = [_buy("QQQ", 50, 300.0)]
    prices = {"QQQ": 350.0}
    result = pe.compute_position_sizing(
        txns,
        portfolio_size=20_000.0,
        cash_available=2000.0,
        risk_tolerance="Conservative",
        target_ticker="QQQ",
    )
    assert result.suggested_dollar_amount > 0
    assert result.concentration_warnings


def test_ami_context_structure():
    txns = [_buy("VOO", 5, 400.0)]
    ctx = pe.build_ami_portfolio_context(txns, prices={"VOO": 410.0})
    assert ctx["source"] == "real_portfolio_engine"
    assert "VOO" in ctx["position_weights"]
    assert ctx["transactions_count"] == 1


def test_transactions_round_trip_records():
    txn = _buy("SPY", 3, 500.0)
    records = pe.transactions_to_records([txn])
    restored = pe.transactions_from_records(records)
    assert len(restored) == 1
    assert restored[0].ticker == "SPY"
    assert restored[0].quantity == 3
