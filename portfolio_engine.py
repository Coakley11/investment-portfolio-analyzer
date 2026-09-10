"""
Real portfolio engine — transaction ledger, position derivation, and AMI-ready context.

Separate from the hypothetical weight-based ``holdings_df`` analytics path.
No brokerage integration; manual entry only.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd

import etf_holdings as eh

TransactionAction = Literal["buy", "sell", "cash_deposit", "cash_withdrawal"]
AssetType = Literal["stock", "etf", "bond", "cash", "other"]
RiskTolerance = Literal["Conservative", "Moderate", "Aggressive"]

# Trade tickers: letters/digits with optional Yahoo class separators (BRK.B, BF-B).
# Rejects punctuation such as ``!`` that cannot be quoted and was observed as ``VN!``.
_TRADE_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")

# Known ledger identity corruptions (not market-data aliases). Applied only via
# ``correct_transaction_ticker_identity`` / repair helpers — never as quote fallbacks.
KNOWN_TICKER_IDENTITY_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("VN!", "VNQ"),  # Shadow #1 REIT mistyped / unsanitized entry
)

POSITION_COLUMNS = [
    "Ticker",
    "Company Name",
    "Asset Type",
    "Shares Owned",
    "Avg Cost Basis",
    "Current Price",
    "Market Value",
    "Gain/Loss $",
    "Gain/Loss %",
    "Weight %",
]

TRANSACTION_COLUMNS = [
    "id",
    "action",
    "date",
    "ticker",
    "company_name",
    "asset_type",
    "quantity",
    "execution_price",
    "notes",
]

_KNOWN_ETF_TICKERS = frozenset(t.upper() for t in eh.POPULAR_ETF_TICKERS)


def format_currency(value: float, *, decimals: int = 2) -> str:
    """Format a dollar amount as $27,521.10."""
    amount = _safe_float(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.{decimals}f}"


def format_transaction_flow_amount(
    action: TransactionAction,
    amount: float,
) -> tuple[str, Literal["in", "out"]]:
    """
    Presentation-only signed cash flow label for transaction history.

    Does not affect ledger math — use raw ``quantity`` / ``execution_price`` for calculations.
    """
    magnitude = abs(_safe_float(amount))
    money = format_currency(magnitude)
    if action in ("buy", "cash_withdrawal"):
        return f"↓ −{money}", "out"
    if action in ("sell", "cash_deposit"):
        return f"↑ +{money}", "in"
    return money, "in"


# Readable on Streamlit light and dark dataframe backgrounds.
_TXN_FLOW_IN_COLOR = "#22c55e"
_TXN_FLOW_OUT_COLOR = "#f87171"


def style_transaction_history_dataframe(df: pd.DataFrame) -> Any:
    """Color Total / Amount cells green (inflow) or red (outflow)."""
    if df.empty:
        return df.style

    in_css = f"color: {_TXN_FLOW_IN_COLOR}; font-weight: 600;"
    out_css = f"color: {_TXN_FLOW_OUT_COLOR}; font-weight: 600;"
    _OUT_ACTIONS = frozenset({"Buy", "Cash Withdrawal"})
    _IN_ACTIONS = frozenset({"Sell", "Cash Deposit"})

    def _row_style(row: pd.Series) -> list[str]:
        action = str(row.get("Action", ""))
        flow_css = ""
        if action in _OUT_ACTIONS:
            flow_css = out_css
        elif action in _IN_ACTIONS:
            flow_css = in_css
        styles: list[str] = []
        for col in row.index:
            if col in ("Total", "Amount") and flow_css:
                styles.append(flow_css)
            else:
                styles.append("")
        return styles

    return df.style.apply(_row_style, axis=1)


def format_shares(value: float) -> str:
    """Human-readable share count — whole numbers without decimals when exact."""
    shares = _safe_float(value)
    if abs(shares) < 1e-9:
        return "0 shares"
    rounded = round(shares)
    if abs(shares - rounded) < 1e-6:
        count = int(rounded)
        word = "share" if count == 1 else "shares"
        return f"{count:,} {word}"
    text = f"{shares:,.4f}".rstrip("0").rstrip(".")
    return f"{text} shares"



@dataclass
class CashLedgerSummary:
    total_deposits: float
    total_withdrawals: float
    total_buy_cost: float
    total_sell_proceeds: float
    net_cash: float

    def to_dict(self) -> dict[str, float]:
        return {
            "total_deposits": self.total_deposits,
            "total_withdrawals": self.total_withdrawals,
            "total_buy_cost": self.total_buy_cost,
            "total_sell_proceeds": self.total_sell_proceeds,
            "net_cash": self.net_cash,
        }


def compute_cash_ledger_summary(transactions: list[PortfolioTransaction]) -> CashLedgerSummary:
    """Order-independent cash accounting identity for validation and UI."""
    deposits = withdrawals = buy_cost = sell_proceeds = 0.0
    for txn in transactions:
        action = txn.action
        qty = _safe_float(txn.quantity)
        price = _safe_float(txn.execution_price)
        if action == "cash_deposit":
            deposits += qty if qty > 0 else price
        elif action == "cash_withdrawal":
            withdrawals += qty if qty > 0 else price
        elif action == "buy":
            buy_cost += qty * price
        elif action == "sell":
            sell_proceeds += qty * price
    net = deposits - withdrawals - buy_cost + sell_proceeds
    return CashLedgerSummary(
        total_deposits=deposits,
        total_withdrawals=withdrawals,
        total_buy_cost=buy_cost,
        total_sell_proceeds=sell_proceeds,
        net_cash=net,
    )


def fetch_latest_price(symbol: str) -> tuple[float | None, str]:
    """
    Latest per-share market price for marking open positions.

    Uses actual last-traded / closing prices (not split-back-adjusted history) so
    marks align with brokerage share counts and execution prices.
    """
    from investment_market_data import get_market_data_provider

    sym = str(symbol or "").strip().upper()
    if not sym or sym in ("CASH", "US TREASURY", "MORTGAGE", "CORP BOND"):
        return None, ""
    px, src = get_market_data_provider().get_latest_quote(sym)
    if px is not None and px > 0:
        return float(px), src or "market_data_provider"
    return None, ""


def _stock_splits_for_symbol(symbol: str) -> list[tuple[dt.date, float]]:
    """Return (ex-date, ratio) stock splits for a ticker, oldest first."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return []
    try:
        from investment_market_data import get_market_data_provider

        splits = get_market_data_provider().get_stock_splits(sym)
        if splits is None or len(splits) == 0:
            return []
        out: list[tuple[dt.date, float]] = []
        for ts, ratio in splits.items():
            split_date = ts.date() if hasattr(ts, "date") else _parse_date(str(ts))
            r = _safe_float(ratio)
            if r > 1.0:
                out.append((split_date, r))
        out.sort(key=lambda x: x[0])
        return out
    except Exception:
        return []


def _apply_split_to_ledger(ledger: dict[str, dict[str, Any]], ticker: str, ratio: float) -> None:
    entry = ledger.get(ticker)
    if not entry:
        return
    shares = _safe_float(entry.get("shares"))
    if shares <= 0 or ratio <= 1.0:
        return
    entry["shares"] = shares * ratio
    splits_applied = int(entry.get("splits_applied", 0)) + 1
    entry["splits_applied"] = splits_applied

def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def normalize_trade_ticker(raw: Any) -> str:
    """Strip and uppercase a trade ticker; does not invent aliases."""
    return str(raw or "").strip().upper()


def validate_trade_ticker(raw: Any) -> tuple[bool, str, str]:
    """
    Validate a trade ticker for ledger entry.

    Returns ``(ok, normalized, error_message)``. Empty normalized when invalid.
    Blocks unsupported punctuation (e.g. ``VN!``) rather than auto-correcting.
    """
    normalized = normalize_trade_ticker(raw)
    if not normalized:
        return False, "", "Ticker is required."
    if not _TRADE_TICKER_RE.fullmatch(normalized):
        return (
            False,
            "",
            (
                f"Invalid ticker '{normalized}'. Use letters/numbers only "
                "(optional '.' or '-' for share classes, e.g. BRK.B). "
                "Punctuation such as '!' is not allowed."
            ),
        )
    return True, normalized, ""


def correct_transaction_ticker_identity(
    transactions: list[dict[str, Any]] | None,
    *,
    from_ticker: str,
    to_ticker: str,
) -> tuple[list[dict[str, Any]], int]:
    """
    Identity correction: rewrite ticker on existing trade rows only.

    Preserves date, action, quantity, price, notes, ids, and ownership fields.
    Does not insert sells/buys or change economics. Cash rows are left unchanged.
    """
    src = normalize_trade_ticker(from_ticker)
    ok, dst, err = validate_trade_ticker(to_ticker)
    if not src:
        raise ValueError("from_ticker is required")
    if not ok:
        raise ValueError(err or "to_ticker is invalid")

    out: list[dict[str, Any]] = []
    n_changed = 0
    for raw in transactions or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        action = str(row.get("action") or "").strip().lower()
        if action in ("buy", "sell"):
            cur = normalize_trade_ticker(row.get("ticker"))
            if cur == src:
                row["ticker"] = dst
                # Refresh display name when it was blank or mirrored the old symbol.
                prev_name = str(row.get("company_name") or "").strip()
                if (not prev_name) or prev_name.upper() == src:
                    row["company_name"] = infer_company_name(dst)
                n_changed += 1
        out.append(row)
    return out, n_changed


def apply_known_ticker_identity_corrections(
    transactions: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Apply documented ledger identity fixes (e.g. VN! → VNQ).

    Returns ``(transactions, human-readable change notes)``.
    """
    txs = [dict(t) for t in (transactions or []) if isinstance(t, dict)]
    notes: list[str] = []
    for src, dst in KNOWN_TICKER_IDENTITY_CORRECTIONS:
        txs, n = correct_transaction_ticker_identity(txs, from_ticker=src, to_ticker=dst)
        if n:
            notes.append(f"Corrected ticker identity on {n} transaction(s): {src} → {dst}")
    return txs, notes


def find_malformed_trade_tickers(
    transactions: list[dict[str, Any]] | None,
) -> list[str]:
    """Return sorted unique buy/sell tickers that fail ``validate_trade_ticker``."""
    bad: set[str] = set()
    for raw in transactions or []:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").strip().lower()
        if action not in ("buy", "sell"):
            continue
        sym = normalize_trade_ticker(raw.get("ticker"))
        if not sym:
            continue
        ok, _, _ = validate_trade_ticker(sym)
        if not ok:
            bad.add(sym)
    return sorted(bad)


def _parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return dt.date.today()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bond_fund_tickers() -> frozenset[str]:
    try:
        from investment_ami.decision_support.real_portfolio_security_types import BOND_FUND_TICKERS

        return BOND_FUND_TICKERS
    except ImportError:
        return frozenset({"BND", "AGG", "SCHZ", "GOVT", "VGIT", "TLT", "IEF", "SHY"})


def is_bond_fund_ticker(ticker: str) -> bool:
    """True for bond ETFs/funds (canonical Real Portfolio bond sleeve)."""
    sym = str(ticker or "").strip().upper()
    if not sym or sym in ("CASH", "$CASH"):
        return False
    if sym in _bond_fund_tickers():
        return True
    info = eh.infer_portfolio_fund_info(sym)
    asset_type = str(info.get("asset_type") or "").lower()
    return "bond" in asset_type


# User-facing / persisted instrument taxonomy (Dashboard Allocation cards).
# Once a label maps here, ticker-based economic classifiers must not override it.
_EXPLICIT_INSTRUMENT_ALIASES: dict[str, AssetType] = {
    "stock": "stock",
    "stocks": "stock",
    "etf": "etf",
    "etfs": "etf",
    "dividend etf": "etf",
    "reit": "etf",
    "bond": "bond",
    "bonds": "bond",
    "other": "other",
    "cash": "cash",
    "t-bills": "cash",
    "t bills": "cash",
}


def canonicalize_instrument_type(raw: str | None) -> AssetType | None:
    """Return a canonical instrument type if ``raw`` is an explicit instrument label.

    Does not consult tickers or market-data metadata. Returns ``None`` when the
    label is blank/unknown so callers may fall back to ticker inference.
    """
    label = str(raw or "").strip().lower()
    if not label:
        return None
    if label in _EXPLICIT_INSTRUMENT_ALIASES:
        return _EXPLICIT_INSTRUMENT_ALIASES[label]
    return None


def resolve_instrument_type(raw: str | None, ticker: str = "") -> AssetType:
    """Instrument type for ledger / Dashboard: explicit labels are frozen.

    Bond-fund ticker detection is used only when the stored/editor label is blank
    or not an instrument taxonomy value. This is the source of truth for
    Stocks/ETFs/Bonds/Cash/Other allocation cards.
    """
    explicit = canonicalize_instrument_type(raw)
    if explicit is not None:
        return explicit
    return normalize_asset_type(raw, ticker)


def normalize_asset_type(raw: str | None, ticker: str = "") -> AssetType:
    """Map labels to *instrument* types (Stock / ETF / Bond / Cash / Other).

    Explicit transaction/editor instrument labels win. Bond-fund ticker inference
    only fills gaps when the user did not choose an instrument type — it must not
    silently reclassify an ETF wrapper (e.g. BND entered as ETF) into Bond for
    Dashboard instrument-type allocation.
    """
    explicit = canonicalize_instrument_type(raw)
    if explicit is not None:
        return explicit

    sym = str(ticker or "").strip().upper()
    label = str(raw or "").strip().lower()
    if sym in ("CASH", "$CASH"):
        return "cash"
    # Non-canonical labels that still imply fixed income as an instrument.
    if "bond" in label:
        return "bond"
    if is_bond_fund_ticker(sym):
        return "bond"
    if sym in _KNOWN_ETF_TICKERS:
        return "etf"
    if label == "equity":
        if sym in _KNOWN_ETF_TICKERS:
            return "etf"
        return "stock"
    if sym and sym not in ("CASH",):
        info = eh.infer_portfolio_fund_info(sym)
        # Avoid infinite recursion: fund metadata may return the same blank/unknown label.
        inferred = str(info.get("asset_type") or "").strip().lower()
        if inferred and inferred != label:
            # Fund metadata often returns economic labels ("Bonds"); map via aliases
            # or recurse. Explicit instrument aliases (including "bonds"→bond) win.
            mapped = canonicalize_instrument_type(inferred)
            if mapped is not None:
                return mapped
            return normalize_asset_type(inferred, sym)
        if is_bond_fund_ticker(sym):
            return "bond"
        if sym in _KNOWN_ETF_TICKERS:
            return "etf"
        return "other"
    return "other"


def allocation_bucket(asset_type: AssetType) -> str:
    """Instrument-type allocation card labels (Dashboard Stocks/ETFs/Bonds/…)."""
    mapping = {
        "stock": "Stocks",
        "etf": "ETFs",
        "bond": "Bonds",
        "cash": "Cash",
        "other": "Other",
    }
    return mapping.get(asset_type, "Other")


def economic_exposure_bucket(asset_type: AssetType | str, ticker: str = "") -> str:
    """Economic sleeve for drift/AMI analysis (bond ETFs → Bonds / fixed income).

    Distinct from :func:`allocation_bucket`: an instrument typed as ETF can still
    contribute fixed-income exposure when the ticker is a known bond fund.
    """
    sym = str(ticker or "").strip().upper()
    if is_bond_fund_ticker(sym):
        return "Bonds"
    if asset_type in ("stock", "etf", "bond", "cash", "other"):
        return allocation_bucket(asset_type)  # type: ignore[arg-type]
    return allocation_bucket(normalize_asset_type(str(asset_type or ""), sym))

def infer_company_name(ticker: str) -> str:
    sym = str(ticker or "").strip().upper()
    if not sym or sym == "CASH":
        return "Cash"
    info = eh.infer_portfolio_fund_info(sym)
    return str(info.get("name") or sym)


@dataclass
class PortfolioTransaction:
    id: str
    action: TransactionAction
    date: str
    ticker: str
    quantity: float
    execution_price: float
    notes: str = ""
    company_name: str = ""
    asset_type: str = "stock"
    # Optional audit fields — empty for manual form entries.
    contribution_event_id: str = ""
    source: str = ""

    def to_record(self) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "id": self.id,
            "action": self.action,
            "date": self.date,
            "ticker": str(self.ticker or "").strip().upper(),
            "company_name": self.company_name,
            "asset_type": self.asset_type,
            "quantity": float(self.quantity),
            "execution_price": float(self.execution_price),
            "notes": self.notes,
        }
        if self.contribution_event_id:
            rec["contribution_event_id"] = str(self.contribution_event_id)
        if self.source:
            rec["source"] = str(self.source)
        return rec

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> PortfolioTransaction:
        ticker = str(record.get("ticker") or "").strip().upper()
        asset_raw = str(record.get("asset_type") or "")
        if asset_raw:
            # Preserve explicit persisted instrument type; do not reclassify by ticker.
            asset_resolved = resolve_instrument_type(asset_raw, "")
        elif ticker:
            asset_resolved = resolve_instrument_type("", ticker)
        else:
            asset_resolved = "stock"
        return cls(
            id=str(record.get("id") or _new_id()),
            action=str(record.get("action") or "buy"),  # type: ignore[arg-type]
            date=str(record.get("date") or dt.date.today().isoformat())[:10],
            ticker=ticker,
            quantity=_safe_float(record.get("quantity")),
            execution_price=_safe_float(record.get("execution_price")),
            notes=str(record.get("notes") or ""),
            company_name=str(record.get("company_name") or infer_company_name(ticker)),
            asset_type=str(asset_resolved),
            contribution_event_id=str(record.get("contribution_event_id") or ""),
            source=str(record.get("source") or ""),
        )


@dataclass
class PortfolioPosition:
    ticker: str
    company_name: str
    asset_type: AssetType
    shares_owned: float
    average_cost_basis: float
    current_price: float
    market_value: float
    gain_loss_dollar: float
    gain_loss_pct: float
    weight_pct: float
    stock_splits_applied: int = 0

    def to_row(self) -> dict[str, Any]:
        return {
            "Ticker": self.ticker,
            "Company Name": self.company_name,
            "Asset Type": self.asset_type,
            "Shares Owned": self.shares_owned,
            "Avg Cost Basis": self.average_cost_basis,
            "Current Price": self.current_price,
            "Market Value": self.market_value,
            "Gain/Loss $": self.gain_loss_dollar,
            "Gain/Loss %": self.gain_loss_pct,
            "Weight %": self.weight_pct,
        }


@dataclass
class PortfolioSummary:
    total_portfolio_value: float
    total_invested_capital: float
    total_gain_loss_dollar: float
    total_gain_loss_pct: float
    cash_balance: float
    num_holdings: int
    allocation_by_bucket: dict[str, float] = field(default_factory=dict)
    largest_position: PortfolioPosition | None = None
    smallest_position: PortfolioPosition | None = None
    top_gainers: list[PortfolioPosition] = field(default_factory=list)
    top_losers: list[PortfolioPosition] = field(default_factory=list)
    biggest_positions: list[PortfolioPosition] = field(default_factory=list)


@dataclass
class PositionSizingResult:
    suggested_dollar_amount: float
    suggested_allocation_pct: float
    projected_weight_pct: float
    concentration_warnings: list[str] = field(default_factory=list)
    allocation_bucket_preview: dict[str, float] = field(default_factory=dict)


def transactions_from_records(records: list[dict[str, Any]] | None) -> list[PortfolioTransaction]:
    if not records:
        return []
    out: list[PortfolioTransaction] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        out.append(PortfolioTransaction.from_record(rec))
    out.sort(key=lambda t: (_parse_date(t.date), t.id))
    return out


def transactions_to_records(transactions: list[PortfolioTransaction]) -> list[dict[str, Any]]:
    return [t.to_record() for t in transactions]


def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    from investment_market_data import get_market_data_provider

    syms = [str(s).strip().upper() for s in tickers if s and str(s).strip().upper() != "CASH"]
    quotes = get_market_data_provider().get_latest_quotes(syms)
    prices: dict[str, float] = {}
    for sym, (px, _src) in quotes.items():
        if px is not None and px > 0:
            prices[sym] = float(px)
    return prices


def fetch_price_sources(tickers: list[str]) -> dict[str, str]:
    """Map ticker → quote source label (for UI diagnostics)."""
    from investment_market_data import get_market_data_provider

    syms = [str(s).strip().upper() for s in tickers if s and str(s).strip().upper() != "CASH"]
    quotes = get_market_data_provider().get_latest_quotes(syms)
    out: dict[str, str] = {}
    for sym, (_px, src) in quotes.items():
        if src:
            out[sym] = src
    return out


def _ledger_from_transactions(
    transactions: list[PortfolioTransaction],
) -> tuple[dict[str, dict[str, Any]], float]:
    """
    Replay transactions into per-ticker ledger and cash balance.

    Cash uses an order-independent identity (deposits − withdrawals − buys + sells).
    Stock splits from yfinance are applied on their ex-dates to shares held.
    """
    ledger: dict[str, dict[str, Any]] = {}
    cash = compute_cash_ledger_summary(transactions).net_cash

    trade_tickers = {
        str(t.ticker or "").strip().upper()
        for t in transactions
        if t.action in ("buy", "sell") and str(t.ticker or "").strip()
    }
    split_events: list[tuple[dt.date, str, float]] = []
    for sym in trade_tickers:
        for split_date, ratio in _stock_splits_for_symbol(sym):
            split_events.append((split_date, sym, ratio))

    txn_events: list[tuple[dt.date, PortfolioTransaction]] = [
        (_parse_date(t.date), t)
        for t in transactions
        if t.action not in ("cash_deposit", "cash_withdrawal")
    ]

    timeline: list[tuple[dt.date, int, str, Any]] = []
    for split_date, sym, ratio in split_events:
        timeline.append((split_date, 0, "split", (sym, ratio)))
    for txn_date, txn in txn_events:
        timeline.append((txn_date, 1, "txn", txn))
    timeline.sort(key=lambda row: (row[0], row[1]))

    for _when, _order, kind, payload in timeline:
        if kind == "split":
            sym, ratio = payload
            _apply_split_to_ledger(ledger, sym, ratio)
            continue

        txn: PortfolioTransaction = payload
        action = txn.action
        qty = _safe_float(txn.quantity)
        price = _safe_float(txn.execution_price)
        ticker = str(txn.ticker or "").strip().upper()

        if action not in ("buy", "sell") or not ticker:
            continue

        entry = ledger.setdefault(
            ticker,
            {
                "shares": 0.0,
                "total_cost": 0.0,
                "company_name": txn.company_name or infer_company_name(ticker),
                "asset_type": resolve_instrument_type(txn.asset_type, ticker),
                "splits_applied": 0,
            },
        )
        if txn.company_name:
            entry["company_name"] = txn.company_name
        if txn.asset_type:
            # Explicit transaction instrument type wins; ticker must not override.
            entry["asset_type"] = resolve_instrument_type(txn.asset_type, ticker)

        if action == "buy":
            cost = qty * price
            entry["shares"] += qty
            entry["total_cost"] += cost
        elif action == "sell":
            shares_before = entry["shares"]
            if shares_before <= 0 or qty <= 0:
                continue
            sell_qty = min(qty, shares_before)
            avg_cost = entry["total_cost"] / shares_before if shares_before > 0 else 0.0
            entry["shares"] -= sell_qty
            entry["total_cost"] = max(0.0, entry["total_cost"] - avg_cost * sell_qty)

    ledger = {k: v for k, v in ledger.items() if _safe_float(v.get("shares")) > 1e-9}
    return ledger, cash


def build_positions(
    transactions: list[PortfolioTransaction],
    *,
    prices: dict[str, float] | None = None,
) -> tuple[list[PortfolioPosition], float]:
    ledger, cash_balance = _ledger_from_transactions(transactions)
    tickers = list(ledger.keys())
    live_prices = prices if prices is not None else _fetch_prices(tickers)

    positions: list[PortfolioPosition] = []
    for ticker, entry in ledger.items():
        shares = _safe_float(entry.get("shares"))
        total_cost = _safe_float(entry.get("total_cost"))
        avg_cost = total_cost / shares if shares > 0 else 0.0
        current_price = _safe_float(live_prices.get(ticker), avg_cost)
        market_value = shares * current_price
        cost_basis = shares * avg_cost
        gain_dollar = market_value - cost_basis
        gain_pct = (gain_dollar / cost_basis * 100.0) if cost_basis > 0 else 0.0
        positions.append(
            PortfolioPosition(
                ticker=ticker,
                company_name=str(entry.get("company_name") or ticker),
                asset_type=resolve_instrument_type(str(entry.get("asset_type")), ticker),
                shares_owned=shares,
                average_cost_basis=avg_cost,
                current_price=current_price,
                market_value=market_value,
                gain_loss_dollar=gain_dollar,
                gain_loss_pct=gain_pct,
                weight_pct=0.0,
                stock_splits_applied=int(entry.get("splits_applied") or 0),
            )
        )

    securities_value = sum(p.market_value for p in positions)
    # Holding weights use securities + non-negative cash only. Negative cash (buys
    # exceeding deposits) must not shrink the denominator and inflate weights past 100%.
    weight_denominator = securities_value + max(0.0, cash_balance)
    if weight_denominator > 0:
        for p in positions:
            p.weight_pct = p.market_value / weight_denominator * 100.0

    positions.sort(key=lambda p: p.market_value, reverse=True)
    return positions, cash_balance


def positions_to_dataframe(positions: list[PortfolioPosition]) -> pd.DataFrame:
    if not positions:
        return pd.DataFrame(columns=POSITION_COLUMNS)
    return pd.DataFrame([p.to_row() for p in positions])


def transactions_to_dataframe(transactions: list[PortfolioTransaction]) -> pd.DataFrame:
    if not transactions:
        return pd.DataFrame(columns=[c for c in TRANSACTION_COLUMNS if c != "company_name"])
    rows = []
    for t in reversed(transactions):
        rows.append(
            {
                "id": t.id,
                "Date": t.date,
                "Action": t.action.replace("_", " ").title(),
                "Ticker": t.ticker or "—",
                "Quantity": t.quantity,
                "Price": t.execution_price,
                "Total": t.quantity * t.execution_price,
                "Notes": t.notes,
            }
        )
    return pd.DataFrame(rows)


def transactions_display_dataframe(transactions: list[PortfolioTransaction]) -> pd.DataFrame:
    """Human-readable transaction table — cash rows omit share price."""
    if not transactions:
        return pd.DataFrame()
    rows: list[dict[str, str]] = []
    for t in reversed(transactions):
        action_label = t.action.replace("_", " ").title()
        if t.action in ("cash_deposit", "cash_withdrawal"):
            amount = t.quantity if t.quantity > 0 else t.execution_price
            flow_label, _flow = format_transaction_flow_amount(t.action, amount)
            rows.append(
                {
                    "Date": t.date,
                    "Action": action_label,
                    "Ticker": "—",
                    "Amount": flow_label,
                    "Notes": t.notes or "",
                }
            )
        else:
            total = t.quantity * t.execution_price
            flow_label, _flow = format_transaction_flow_amount(t.action, total)
            rows.append(
                {
                    "Date": t.date,
                    "Action": action_label,
                    "Ticker": t.ticker,
                    "Asset Type": resolve_instrument_type(t.asset_type, t.ticker),
                    "Shares": format_shares(t.quantity),
                    "Price/Share": format_currency(t.execution_price),
                    "Total": flow_label,
                    "Notes": t.notes or "",
                }
            )
    return pd.DataFrame(rows)


def compute_portfolio_summary(
    transactions: list[PortfolioTransaction],
    *,
    prices: dict[str, float] | None = None,
) -> PortfolioSummary:
    positions, cash_balance = build_positions(transactions, prices=prices)
    securities_value = sum(p.market_value for p in positions)
    total_value = securities_value + cash_balance
    invested = sum(p.shares_owned * p.average_cost_basis for p in positions)
    total_gain = sum(p.gain_loss_dollar for p in positions)
    total_gain_pct = (total_gain / invested * 100.0) if invested > 0 else 0.0

    bucket_totals: dict[str, float] = {
        "Stocks": 0.0,
        "ETFs": 0.0,
        "Bonds": 0.0,
        "Cash": 0.0,
        "Other": 0.0,
    }
    for p in positions:
        bucket = allocation_bucket(p.asset_type)
        bucket_totals[bucket] = bucket_totals.get(bucket, 0.0) + p.market_value
    # Negative cash is surfaced via cash_balance / warnings — not as a negative allocation %.
    cash_for_alloc = max(0.0, cash_balance)
    bucket_totals["Cash"] += cash_for_alloc
    alloc_denominator = securities_value + cash_for_alloc

    allocation_pct = {
        k: (v / alloc_denominator * 100.0 if alloc_denominator > 0 else 0.0)
        for k, v in bucket_totals.items()
    }

    sorted_by_gain = sorted(positions, key=lambda p: p.gain_loss_pct, reverse=True)
    sorted_by_loss = sorted(positions, key=lambda p: p.gain_loss_pct)
    sorted_by_size = sorted(positions, key=lambda p: p.market_value, reverse=True)

    return PortfolioSummary(
        total_portfolio_value=total_value,
        total_invested_capital=invested,
        total_gain_loss_dollar=total_gain,
        total_gain_loss_pct=total_gain_pct,
        cash_balance=cash_balance,
        num_holdings=len(positions),
        allocation_by_bucket=allocation_pct,
        largest_position=positions[0] if positions else None,
        smallest_position=positions[-1] if positions else None,
        top_gainers=sorted_by_gain[:5],
        top_losers=[p for p in sorted_by_loss[:5] if p.gain_loss_pct < 0],
        biggest_positions=sorted_by_size[:5],
    )


def _concentration_limit(risk_tolerance: RiskTolerance) -> float:
    if risk_tolerance == "Conservative":
        return 20.0
    if risk_tolerance == "Aggressive":
        return 35.0
    return 25.0


def _suggested_position_pct(risk_tolerance: RiskTolerance) -> float:
    if risk_tolerance == "Conservative":
        return 8.0
    if risk_tolerance == "Aggressive":
        return 15.0
    return 10.0


def compute_position_sizing(
    transactions: list[PortfolioTransaction],
    *,
    portfolio_size: float | None = None,
    cash_available: float | None = None,
    risk_tolerance: RiskTolerance = "Moderate",
    target_ticker: str = "",
    additional_investment: float = 0.0,
    prices: dict[str, float] | None = None,
) -> PositionSizingResult:
    summary = compute_portfolio_summary(transactions, prices=prices)
    positions, cash_balance = build_positions(transactions, prices=prices)

    port_size = portfolio_size if portfolio_size is not None else summary.total_portfolio_value
    cash = cash_available if cash_available is not None else cash_balance
    port_size = max(port_size, 1.0)

    target_pct = _suggested_position_pct(risk_tolerance)
    suggested_dollar = min(port_size * target_pct / 100.0, cash if cash > 0 else port_size * target_pct / 100.0)
    if additional_investment > 0:
        suggested_dollar = min(additional_investment, cash if cash > 0 else additional_investment)

    warnings: list[str] = []
    limit = _concentration_limit(risk_tolerance)
    sym = str(target_ticker or "").strip().upper()

    existing = next((p for p in positions if p.ticker == sym), None)
    existing_weight = existing.weight_pct if existing else 0.0
    add_weight = suggested_dollar / port_size * 100.0 if port_size > 0 else 0.0
    projected_weight = existing_weight + add_weight

    if sym:
        warnings.append(
            f"This position would become {projected_weight:.1f}% of your portfolio "
            f"({'currently ' + f'{existing_weight:.1f}%' if existing else 'new position'})."
        )
        if projected_weight > limit:
            warnings.append(
                f"This exceeds your preferred concentration limit ({limit:.0f}% for {risk_tolerance} risk)."
            )

    # Sector / bucket concentration (technology proxy via growth ETFs)
    tech_tickers = {"QQQ", "VGT", "XLK", "MGK", "VUG", "ARKK", "SMH", "SOXX"}
    tech_value = sum(p.market_value for p in positions if p.ticker in tech_tickers)
    if sym in tech_tickers:
        tech_value += suggested_dollar
    tech_pct = tech_value / port_size * 100.0 if port_size > 0 else 0.0
    if tech_pct >= 25.0:
        warnings.append(f"You already have {tech_pct:.0f}% in technology / growth exposure.")

    bucket_preview = dict(summary.allocation_by_bucket)
    if sym and suggested_dollar > 0:
        asset = normalize_asset_type("", sym)
        bucket = allocation_bucket(asset)
        add_pct = suggested_dollar / port_size * 100.0
        bucket_preview[bucket] = bucket_preview.get(bucket, 0.0) + add_pct

    return PositionSizingResult(
        suggested_dollar_amount=suggested_dollar,
        suggested_allocation_pct=target_pct,
        projected_weight_pct=projected_weight,
        concentration_warnings=warnings,
        allocation_bucket_preview=bucket_preview,
    )


def simulate_add_to_position(
    transactions: list[PortfolioTransaction],
    ticker: str,
    amount: float,
    *,
    prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """What-if: add ``amount`` dollars to ``ticker`` at current price."""
    sym = str(ticker or "").strip().upper()
    if not sym or amount <= 0:
        return {"ok": False, "message": "Enter a ticker and positive amount."}

    live_prices = prices if prices is not None else _fetch_prices([sym])
    price = _safe_float(live_prices.get(sym))
    if price <= 0:
        return {"ok": False, "message": f"Could not fetch a live price for {sym}."}

    qty = amount / price
    before = compute_portfolio_summary(transactions, prices=live_prices)
    before_pos = next((p for p in build_positions(transactions, prices=live_prices)[0] if p.ticker == sym), None)

    new_txn = PortfolioTransaction(
        id=_new_id(),
        action="buy",
        date=dt.date.today().isoformat(),
        ticker=sym,
        quantity=qty,
        execution_price=price,
        notes="What-if simulation",
        company_name=infer_company_name(sym),
        asset_type=normalize_asset_type("", sym),
    )
    after = compute_portfolio_summary(transactions + [new_txn], prices=live_prices)
    after_pos = next((p for p in build_positions(transactions + [new_txn], prices=live_prices)[0] if p.ticker == sym), None)

    return {
        "ok": True,
        "ticker": sym,
        "amount": amount,
        "shares_added": qty,
        "price": price,
        "portfolio_value_before": before.total_portfolio_value,
        "portfolio_value_after": after.total_portfolio_value,
        "position_weight_before": before_pos.weight_pct if before_pos else 0.0,
        "position_weight_after": after_pos.weight_pct if after_pos else add_weight_pct(amount, after.total_portfolio_value),
        "allocation_before": before.allocation_by_bucket,
        "allocation_after": after.allocation_by_bucket,
    }


def add_weight_pct(amount: float, total: float) -> float:
    return amount / total * 100.0 if total > 0 else 0.0


def build_ami_portfolio_context(
    transactions: list[PortfolioTransaction],
    *,
    prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Package real-portfolio state for future AMI instant solvers.

    Keeps hypothetical ``holdings_df`` analytics separate while exposing
    ownership, weights, concentration, and cash for decision-support questions.
    """
    summary = compute_portfolio_summary(transactions, prices=prices)
    positions, cash = build_positions(transactions, prices=prices)
    weights = {p.ticker: f"{p.weight_pct:.1f}%" for p in positions}
    return {
        "source": "real_portfolio_engine",
        "portfolio_value": summary.total_portfolio_value,
        "invested_capital": summary.total_invested_capital,
        "cash_balance": cash,
        "gain_loss_dollar": summary.total_gain_loss_dollar,
        "gain_loss_pct": summary.total_gain_loss_pct,
        "num_holdings": summary.num_holdings,
        "allocation_buckets": summary.allocation_by_bucket,
        "position_weights": weights,
        "positions": [asdict(p) for p in positions],
        "transactions_count": len(transactions),
        "largest_position": asdict(summary.largest_position) if summary.largest_position else None,
        "concentration_flags": [
            f"{p.ticker} is {p.weight_pct:.1f}% of portfolio"
            for p in positions
            if p.weight_pct >= 20.0
        ],
    }
