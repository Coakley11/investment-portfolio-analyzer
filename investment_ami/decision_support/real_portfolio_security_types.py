"""Security-type classification for real portfolio holdings (Phase B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from investment_ami.decision_support.real_portfolio_models import RealHoldingSnapshot

SecurityKind = Literal[
    "individual_equity",
    "broad_market_etf",
    "diversified_sector_or_factor_etf",
    "bond_etf_or_bond_fund",
    "narrow_or_thematic_etf",
    "cash",
    "other",
    "unknown",
]

# Product decision-support lists — not universal investment rules.
BROAD_MARKET_ETF_TICKERS: frozenset[str] = frozenset(
    {
        "VTI",
        "VOO",
        "SPY",
        "IVV",
        "VXUS",
        "VEA",
        "VWO",
        "IEFA",
        "IEMG",
        "ITOT",
        "SCHB",
        "SPTM",
        "ACWI",
    }
)
BOND_FUND_TICKERS: frozenset[str] = frozenset(
    {
        "BND",
        "AGG",
        "SCHZ",
        "GOVT",
        "VGIT",
        "VGLT",
        "TLT",
        "IEF",
        "SHY",
        "BIL",
        "SGOV",
        "VCIT",
        "VCSH",
        "SPTS",
        "SPTI",
        "MUB",
        "LQD",
        "TIP",
        "VTIP",
        "BNDX",
        "IAGG",
    }
)
NARROW_OR_THEMATIC_ETF_TICKERS: frozenset[str] = frozenset(
    {
        "QQQ",
        "VGT",
        "XLK",
        "FTEC",
        "IGV",
        "SMH",
        "SOXX",
        "ARKK",
        "TQQQ",
        "TECL",
        "MGK",
        "VUG",
        "XLE",
        "XLF",
        "XLV",
        "VNQ",
    }
)


@dataclass(frozen=True)
class SecurityClassification:
    ticker: str
    kind: SecurityKind
    source: str
    asset_type_label: str = ""
    category_label: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


def _fund_info_for(ticker: str, metadata: dict[str, dict[str, str]] | None) -> dict[str, str]:
    sym = str(ticker or "").strip().upper()
    if metadata and sym in metadata:
        return dict(metadata[sym])
    try:
        import etf_holdings as eh

        return dict(eh.infer_portfolio_fund_info(sym))
    except Exception:
        return {}


def classify_holding_security(
    holding: RealHoldingSnapshot,
    *,
    security_metadata: dict[str, dict[str, str]] | None = None,
) -> SecurityClassification:
    """Classify a holding using engine asset class plus fund metadata when available."""
    sym = str(holding.ticker or "").strip().upper()
    if not sym:
        return SecurityClassification(sym, "unknown", "empty_ticker", confidence="low")

    info = _fund_info_for(sym, security_metadata)
    asset_type_label = str(info.get("asset_type") or holding.asset_class or "")
    category_label = str(info.get("category_label") or "")
    cat_lower = category_label.lower()
    engine_class = str(holding.asset_class or "")

    if engine_class == "Stocks":
        return SecurityClassification(
            sym,
            "individual_equity",
            "engine_asset_class",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="high",
        )

    if sym in BROAD_MARKET_ETF_TICKERS or (
        engine_class == "ETFs" and "broad equity" in cat_lower
    ):
        return SecurityClassification(
            sym,
            "broad_market_etf",
            "ticker_or_category",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="high" if sym in BROAD_MARKET_ETF_TICKERS else "medium",
        )
    if sym in BOND_FUND_TICKERS or engine_class == "Bonds" or asset_type_label == "Bonds" or "bond" in cat_lower:
        return SecurityClassification(
            sym,
            "bond_etf_or_bond_fund",
            "ticker_or_asset_type",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="high" if sym in BOND_FUND_TICKERS else "medium",
        )
    if sym in NARROW_OR_THEMATIC_ETF_TICKERS or (
        engine_class == "ETFs" and "technology / growth" in cat_lower
    ):
        return SecurityClassification(
            sym,
            "narrow_or_thematic_etf",
            "ticker_or_category",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="high" if sym in NARROW_OR_THEMATIC_ETF_TICKERS else "medium",
        )

    if engine_class == "ETFs" or asset_type_label in ("Equity", "Dividend ETF", "REIT"):
        if asset_type_label == "Dividend ETF":
            return SecurityClassification(
                sym,
                "diversified_sector_or_factor_etf",
                "asset_type",
                asset_type_label=asset_type_label,
                category_label=category_label,
                confidence="medium",
            )
        if "sector" in cat_lower or "factor" in cat_lower:
            return SecurityClassification(
                sym,
                "diversified_sector_or_factor_etf",
                "category_label",
                asset_type_label=asset_type_label,
                category_label=category_label,
                confidence="medium",
            )
        if info:
            return SecurityClassification(
                sym,
                "other",
                "fund_metadata_without_broad_narrow_match",
                asset_type_label=asset_type_label,
                category_label=category_label,
                confidence="medium",
            )
        return SecurityClassification(
            sym,
            "unknown",
            "etf_without_metadata",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="low",
        )

    if engine_class == "Other":
        return SecurityClassification(
            sym,
            "other",
            "engine_asset_class",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="medium",
        )

    if not info and engine_class not in ("Stocks", "ETFs"):
        return SecurityClassification(
            sym,
            "unknown",
            "insufficient_metadata",
            asset_type_label=asset_type_label,
            category_label=category_label,
            confidence="low",
        )

    return SecurityClassification(
        sym,
        "other",
        "fallback",
        asset_type_label=asset_type_label,
        category_label=category_label,
        confidence="medium",
    )


def classify_snapshot_holdings(
    holdings: tuple[RealHoldingSnapshot, ...],
    *,
    security_metadata: dict[str, dict[str, str]] | None = None,
) -> dict[str, SecurityClassification]:
    return {h.ticker: classify_holding_security(h, security_metadata=security_metadata) for h in holdings}
