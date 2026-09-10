"""Record a reviewed Contribution Advisor recommendation into the Real Portfolio ledger.

Pure helpers: build a simulated deposit + buys plan, validate freshness/idempotency,
and produce an atomic replacement transaction list. No Streamlit / cloud I/O here.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Mapping

import portfolio_engine as pe

SOURCE_CONTRIBUTION_ADVISOR = "contribution_advisor"
EXECUTION_POLICY_SIMULATED_MARK = "simulated_fill_at_current_mark"

STATUS_OK = "ok"
STATUS_ALREADY_APPLIED = "already_applied"
STATUS_STALE = "stale_recommendation"
STATUS_MISSING_QUOTES = "missing_or_invalid_quotes"
STATUS_INVALID = "invalid_plan"
STATUS_WORKSPACE_MISMATCH = "workspace_mismatch"
STATUS_BLOCKED = "blocked"

DOLLAR_TOLERANCE = 0.02
SHARE_DECIMALS = 6


@dataclass(frozen=True)
class PlannedPurchase:
    ticker: str
    recommended_dollars: float
    execution_price: float
    shares: float
    cost: float
    price_source: str
    asset_type: str = "etf"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContributionApplicationPlan:
    application_id: str
    contribution_amount: float
    trade_date: str
    execution_policy: str
    deposit_record: dict[str, Any]
    buy_records: tuple[dict[str, Any], ...]
    purchases: tuple[PlannedPurchase, ...]
    fingerprint: dict[str, Any]
    warnings: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_purchase_cost(self) -> float:
        return round(sum(float(p.cost) for p in self.purchases), 2)

    def all_records(self) -> list[dict[str, Any]]:
        return [dict(self.deposit_record), *[dict(r) for r in self.buy_records]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "contribution_amount": self.contribution_amount,
            "trade_date": self.trade_date,
            "execution_policy": self.execution_policy,
            "deposit_record": dict(self.deposit_record),
            "buy_records": [dict(r) for r in self.buy_records],
            "purchases": [p.to_dict() for p in self.purchases],
            "fingerprint": dict(self.fingerprint),
            "warnings": list(self.warnings),
            "meta": dict(self.meta),
            "total_purchase_cost": self.total_purchase_cost,
        }


@dataclass(frozen=True)
class ContributionApplyResult:
    ok: bool
    status: str
    message: str
    transactions: tuple[dict[str, Any], ...] = ()
    plan: ContributionApplicationPlan | None = None
    already_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "transactions": [dict(t) for t in self.transactions],
            "plan": self.plan.to_dict() if self.plan else None,
            "already_applied": self.already_applied,
        }


def new_application_id() -> str:
    return uuid.uuid4().hex


def ledger_state_fingerprint(records: list[dict[str, Any]] | None) -> str:
    """Stable fingerprint of authoritative ledger economics (not presentation)."""
    rows: list[tuple[Any, ...]] = []
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        rows.append(
            (
                str(raw.get("id") or ""),
                str(raw.get("action") or ""),
                str(raw.get("date") or ""),
                str(raw.get("ticker") or "").upper(),
                round(float(raw.get("quantity") or 0.0), 8),
                round(float(raw.get("execution_price") or 0.0), 8),
                str(raw.get("contribution_event_id") or ""),
            )
        )
    rows.sort()
    blob = json.dumps(rows, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def recommendation_fingerprint(
    *,
    ledger_fp: str,
    contribution_amount: float,
    target_source: str,
    targets: Mapping[str, float] | None,
    recommended_adds: Mapping[str, float],
    portfolio_value_before: float,
    workspace_token: str = "",
) -> dict[str, Any]:
    tgt = {
        str(k).strip().upper(): round(float(v), 6)
        for k, v in (targets or {}).items()
        if str(k).strip()
    }
    adds = {
        str(k).strip().upper(): round(float(v), 6)
        for k, v in (recommended_adds or {}).items()
        if str(k).strip() and float(v) > 0.0005
    }
    return {
        "ledger_fp": str(ledger_fp or ""),
        "contribution_amount": round(float(contribution_amount), 2),
        "target_source": str(target_source or ""),
        "targets": dict(sorted(tgt.items())),
        "recommended_adds": dict(sorted(adds.items())),
        "portfolio_value_before": round(float(portfolio_value_before), 2),
        "workspace_token": str(workspace_token or ""),
    }


def fingerprints_match(a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    keys = (
        "ledger_fp",
        "contribution_amount",
        "target_source",
        "targets",
        "recommended_adds",
        "portfolio_value_before",
        "workspace_token",
    )
    for k in keys:
        if a.get(k) != b.get(k):
            return False
    return True


def event_already_applied(records: list[dict[str, Any]] | None, application_id: str) -> bool:
    aid = str(application_id or "").strip()
    if not aid:
        return False
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("contribution_event_id") or "") == aid:
            return True
    return False


def _round_shares(shares: float) -> float:
    return math.floor(float(shares) * (10**SHARE_DECIMALS) + 1e-9) / (10**SHARE_DECIMALS)


def _allocate_simulated_fills(
    *,
    contribution_amount: float,
    recommended_adds: Mapping[str, float],
    quotes: Mapping[str, float],
    quote_sources: Mapping[str, str] | None = None,
    asset_types: Mapping[str, str] | None = None,
) -> tuple[list[PlannedPurchase] | None, str]:
    """Build share fills so purchase costs sum to contribution within cent tolerance."""
    c = round(float(contribution_amount), 2)
    if c <= 0:
        return None, "Contribution amount must be positive."

    sources = quote_sources or {}
    types = asset_types or {}
    tickers = sorted(
        str(k).strip().upper()
        for k, v in recommended_adds.items()
        if str(k).strip() and float(v) > 0.0005 and str(k).strip().upper() not in ("$CASH", "CASH")
    )
    if not tickers:
        return None, "No security purchases to record (all recommended adds were $0)."

    missing = [t for t in tickers if float(quotes.get(t) or 0.0) <= 0]
    if missing:
        return None, f"Missing or invalid market quotes for: {', '.join(missing)}."

    raw_dollars = {t: round(float(recommended_adds[t]), 6) for t in tickers}
    raw_sum = sum(raw_dollars.values())
    if raw_sum <= 0:
        return None, "Recommended purchase dollars sum to zero."
    # Scale tiny float drift so dollars target the contribution.
    scale = c / raw_sum if abs(raw_sum - c) > 1e-9 else 1.0
    dollars = {t: raw_dollars[t] * scale for t in tickers}

    purchases: list[PlannedPurchase] = []
    for t in tickers:
        px = float(quotes[t])
        d = dollars[t]
        shares = _round_shares(d / px)
        if shares <= 0:
            return None, f"Estimated shares for {t} rounded to zero; increase contribution or check quote."
        cost = round(shares * px, 2)
        purchases.append(
            PlannedPurchase(
                ticker=t,
                recommended_dollars=round(float(recommended_adds[t]), 2),
                execution_price=round(px, 6),
                shares=shares,
                cost=cost,
                price_source=str(sources.get(t) or "simulated_mark"),
                asset_type=str(types.get(t) or "etf"),
            )
        )

    cost_sum = round(sum(p.cost for p in purchases), 2)
    residual = round(c - cost_sum, 2)
    if abs(residual) > 0 and purchases:
        # Adjust the largest notional buy by residual cents via share tweak.
        idx = max(range(len(purchases)), key=lambda i: purchases[i].cost)
        p = purchases[idx]
        px = p.execution_price
        # Prefer spending the residual when positive; reduce when slightly over.
        target_cost = round(p.cost + residual, 2)
        if target_cost <= 0:
            return None, "Could not reconcile purchase costs to the contribution amount."
        new_shares = _round_shares(target_cost / px)
        # Nudge up one share quantum if still short after flooring.
        new_cost = round(new_shares * px, 2)
        quantum = 1.0 / (10**SHARE_DECIMALS)
        guard = 0
        while new_cost < target_cost - 0.001 and guard < 20:
            new_shares = round(new_shares + quantum, SHARE_DECIMALS)
            new_cost = round(new_shares * px, 2)
            guard += 1
        while new_cost > target_cost + 0.001 and new_shares > quantum and guard < 40:
            new_shares = round(new_shares - quantum, SHARE_DECIMALS)
            new_cost = round(new_shares * px, 2)
            guard += 1
        purchases[idx] = PlannedPurchase(
            ticker=p.ticker,
            recommended_dollars=p.recommended_dollars,
            execution_price=p.execution_price,
            shares=new_shares,
            cost=new_cost,
            price_source=p.price_source,
            asset_type=p.asset_type,
        )

    final_sum = round(sum(p.cost for p in purchases), 2)
    if abs(final_sum - c) > DOLLAR_TOLERANCE:
        return None, (
            f"Simulated purchase costs (${final_sum:,.2f}) do not match contribution "
            f"(${c:,.2f}) within tolerance."
        )
    return purchases, ""


def build_simulated_application_plan(
    *,
    application_id: str,
    contribution_amount: float,
    recommended_adds: Mapping[str, float],
    quotes: Mapping[str, float],
    fingerprint: Mapping[str, Any],
    quote_sources: Mapping[str, str] | None = None,
    asset_types: Mapping[str, str] | None = None,
    trade_date: str | None = None,
    notes_prefix: str = "Contribution Advisor",
) -> ContributionApplyResult:
    """
    Build an atomic deposit + simulated-fill buys plan.

    Execution policy: each buy uses the provided current market mark as execution
    price and estimated fractional shares = dollars / mark (clearly labeled simulated).
    """
    aid = str(application_id or "").strip() or new_application_id()
    c = round(float(contribution_amount), 2)
    day = str(trade_date or date.today().isoformat())[:10]
    purchases, err = _allocate_simulated_fills(
        contribution_amount=c,
        recommended_adds=recommended_adds,
        quotes=quotes,
        quote_sources=quote_sources,
        asset_types=asset_types,
    )
    if purchases is None:
        return ContributionApplyResult(ok=False, status=STATUS_MISSING_QUOTES, message=err)

    deposit = pe.PortfolioTransaction(
        id=pe._new_id(),
        action="cash_deposit",
        date=day,
        ticker="",
        quantity=c,
        execution_price=1.0,
        notes=f"{notes_prefix}: external contribution ${c:,.2f}",
        company_name="Cash",
        asset_type="cash",
        contribution_event_id=aid,
        source=SOURCE_CONTRIBUTION_ADVISOR,
    ).to_record()

    buy_records: list[dict[str, Any]] = []
    for p in purchases:
        buy_records.append(
            pe.PortfolioTransaction(
                id=pe._new_id(),
                action="buy",
                date=day,
                ticker=p.ticker,
                quantity=p.shares,
                execution_price=p.execution_price,
                notes=(
                    f"{notes_prefix}: simulated fill "
                    f"(${p.recommended_dollars:,.2f} rec @ {p.price_source})"
                ),
                company_name=pe.infer_company_name(p.ticker),
                asset_type=p.asset_type,
                contribution_event_id=aid,
                source=SOURCE_CONTRIBUTION_ADVISOR,
            ).to_record()
        )

    plan = ContributionApplicationPlan(
        application_id=aid,
        contribution_amount=c,
        trade_date=day,
        execution_policy=EXECUTION_POLICY_SIMULATED_MARK,
        deposit_record=deposit,
        buy_records=tuple(buy_records),
        purchases=tuple(purchases),
        fingerprint=dict(fingerprint),
        warnings=(
            "Simulated execution: fills use the current market quote as execution price "
            "and estimated fractional shares. This is not a brokerage order.",
        ),
        meta={"purchase_count": len(purchases)},
    )
    return ContributionApplyResult(
        ok=True,
        status=STATUS_OK,
        message="Plan ready for confirmation.",
        plan=plan,
    )


def apply_contribution_plan_to_records(
    existing_records: list[dict[str, Any]] | None,
    plan: ContributionApplicationPlan,
    *,
    current_fingerprint: Mapping[str, Any] | None = None,
    require_fingerprint_match: bool = True,
) -> ContributionApplyResult:
    """
    Validate then append deposit + buys atomically to a new list.

    On any failure returns ok=False with ``transactions=()`` (caller must write nothing).
    If the application_id is already present, returns already_applied with the
    unchanged existing list (idempotent).
    """
    existing = [dict(r) for r in (existing_records or []) if isinstance(r, dict)]
    if event_already_applied(existing, plan.application_id):
        return ContributionApplyResult(
            ok=True,
            status=STATUS_ALREADY_APPLIED,
            message="This contribution was already recorded; no duplicate transactions were added.",
            transactions=tuple(existing),
            plan=plan,
            already_applied=True,
        )

    if require_fingerprint_match:
        if not fingerprints_match(plan.fingerprint, current_fingerprint):
            return ContributionApplyResult(
                ok=False,
                status=STATUS_STALE,
                message=(
                    "The recommendation is out of date (portfolio, contribution amount, "
                    "or targets changed). Recalculate allocation before recording."
                ),
                plan=plan,
            )
        live_fp = ledger_state_fingerprint(existing)
        if live_fp != str(plan.fingerprint.get("ledger_fp") or ""):
            return ContributionApplyResult(
                ok=False,
                status=STATUS_STALE,
                message=(
                    "The transaction ledger changed since this recommendation was calculated. "
                    "Recalculate allocation before recording."
                ),
                plan=plan,
            )

    if abs(plan.total_purchase_cost - plan.contribution_amount) > DOLLAR_TOLERANCE:
        return ContributionApplyResult(
            ok=False,
            status=STATUS_INVALID,
            message="Purchase costs do not match the contribution amount.",
            plan=plan,
        )

    buy_cost_from_records = round(
        sum(
            float(r.get("quantity") or 0.0) * float(r.get("execution_price") or 0.0)
            for r in plan.buy_records
        ),
        2,
    )
    if abs(buy_cost_from_records - plan.contribution_amount) > DOLLAR_TOLERANCE:
        return ContributionApplyResult(
            ok=False,
            status=STATUS_INVALID,
            message="Buy transaction costs do not match the contribution amount.",
            plan=plan,
        )

    deposit_amt = float(plan.deposit_record.get("quantity") or 0.0)
    if abs(deposit_amt - plan.contribution_amount) > DOLLAR_TOLERANCE:
        return ContributionApplyResult(
            ok=False,
            status=STATUS_INVALID,
            message="Deposit amount does not match the contribution amount.",
            plan=plan,
        )

    # Validate records parse cleanly before committing.
    try:
        batch = plan.all_records()
        parsed = pe.transactions_from_records(batch)
        if len(parsed) != len(batch):
            return ContributionApplyResult(
                ok=False,
                status=STATUS_INVALID,
                message="Could not parse the planned contribution transactions.",
                plan=plan,
            )
        for txn in parsed:
            if str(txn.contribution_event_id or "") != plan.application_id:
                return ContributionApplyResult(
                    ok=False,
                    status=STATUS_INVALID,
                    message="Contribution event metadata missing on a planned transaction.",
                    plan=plan,
                )
    except Exception as exc:  # noqa: BLE001 — atomic guard
        return ContributionApplyResult(
            ok=False,
            status=STATUS_INVALID,
            message=f"Validation failed: {exc}",
            plan=plan,
        )

    merged = existing + batch
    return ContributionApplyResult(
        ok=True,
        status=STATUS_OK,
        message=(
            f"Recorded ${plan.contribution_amount:,.2f} external contribution and "
            f"{len(plan.purchases)} purchase(s)."
        ),
        transactions=tuple(merged),
        plan=plan,
    )


def plan_review_table_rows(plan: ContributionApplicationPlan | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a plan (object or dict) into review-table rows for UI/tests."""
    if isinstance(plan, ContributionApplicationPlan):
        purchases = plan.purchases
        deposit = float(plan.contribution_amount)
        aid = plan.application_id
        policy = plan.execution_policy
    else:
        purchases = plan.get("purchases") or []
        deposit = float(plan.get("contribution_amount") or 0.0)
        aid = str(plan.get("application_id") or "")
        policy = str(plan.get("execution_policy") or "")
    rows: list[dict[str, Any]] = [
        {
            "kind": "deposit",
            "ticker": "CASH",
            "label": "External cash deposit",
            "recommended_dollars": deposit,
            "execution_price": None,
            "estimated_shares": None,
            "cost": deposit,
            "price_source": "",
            "application_id": aid,
            "execution_policy": policy,
        }
    ]
    for p in purchases:
        if isinstance(p, PlannedPurchase):
            rows.append(
                {
                    "kind": "buy",
                    "ticker": p.ticker,
                    "label": f"Buy {p.ticker}",
                    "recommended_dollars": float(p.recommended_dollars),
                    "execution_price": float(p.execution_price),
                    "estimated_shares": float(p.shares),
                    "cost": float(p.cost),
                    "price_source": p.price_source,
                    "application_id": aid,
                    "execution_policy": policy,
                }
            )
        else:
            rows.append(
                {
                    "kind": "buy",
                    "ticker": str(p.get("ticker") or ""),
                    "label": f"Buy {p.get('ticker') or ''}",
                    "recommended_dollars": float(p.get("recommended_dollars") or 0.0),
                    "execution_price": float(p.get("execution_price") or 0.0),
                    "estimated_shares": float(p.get("shares") or 0.0),
                    "cost": float(p.get("cost") or 0.0),
                    "price_source": str(p.get("price_source") or ""),
                    "application_id": aid,
                    "execution_policy": policy,
                }
            )
    return rows


def attach_application_metadata_to_payload(
    payload: dict[str, Any],
    *,
    records: list[dict[str, Any]] | None,
    contribution_amount: float,
    target_source: str,
    targets: Mapping[str, float] | None,
    workspace_token: str = "",
) -> dict[str, Any]:
    """Stamp a Calculate result with application_id + freshness fingerprint (no ledger writes)."""
    out = dict(payload)
    rows = out.get("rows") or []
    adds = {
        str(r.get("ticker") or "").upper(): float(r.get("recommended_add") or 0.0)
        for r in rows
        if isinstance(r, dict)
    }
    aid = new_application_id()
    fp = recommendation_fingerprint(
        ledger_fp=ledger_state_fingerprint(records),
        contribution_amount=contribution_amount,
        target_source=target_source,
        targets=targets,
        recommended_adds=adds,
        portfolio_value_before=float(out.get("portfolio_value_before") or 0.0),
        workspace_token=workspace_token,
    )
    meta = dict(out.get("meta") or {})
    meta["application_id"] = aid
    meta["recommendation_fingerprint"] = fp
    meta["applied"] = False
    meta["execution_policy"] = EXECUTION_POLICY_SIMULATED_MARK
    out["meta"] = meta
    return out
