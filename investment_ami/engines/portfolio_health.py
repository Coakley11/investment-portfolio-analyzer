"""Core Portfolio Health interpretation engine (Option C–aware)."""

from __future__ import annotations

from typing import Any

from investment_ami_answer_format import build_analyst_sections
from investment_ami_instant_solver import InvestmentSolverResult

from investment_ami.engines.base import InstantEngineRequest


def _ctx_str(ctx: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        val = ctx.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def _mentions_sharpe(question: str) -> bool:
    q = str(question or "").lower()
    return "sharpe" in q


def _primary_issue_from_context(ctx: dict[str, Any]) -> str:
    """Infer the principal structural issue from live AMI context (not scoring math)."""
    drift = _ctx_str(ctx, "rebalance_drift", "total_drift")
    status = _ctx_str(ctx, "health_status_message")
    status_l = status.lower()
    if "t-bill" in status_l or "tbill" in status_l or "cash" in status_l:
        return (
            "objective alignment — missing or underweight Cash/T-Bill sleeve versus the Guided "
            "Balanced Growth target (policy includes ~10% T-Bills)."
        )
    if drift and drift not in ("0", "0%", "0.0", "0.0%"):
        return (
            "objective / Guided target alignment (category drift versus the stated portfolio objective)."
        )
    # Shadow #1 style: growth sleeves without T-Bills often show 0% tbills in weights.
    weights = ctx.get("current_weights") or {}
    if isinstance(weights, dict):
        def _pct(sym: str) -> float:
            raw = weights.get(sym) or weights.get(sym.upper()) or weights.get(sym.lower())
            try:
                return float(str(raw).replace("%", "").strip() or 0)
            except (TypeError, ValueError):
                return 0.0

        tbill_like = sum(_pct(t) for t in ("BIL", "SHV", "SGOV", "TBIL", "CASH"))
        if tbill_like < 1.0 and (_pct("VTI") + _pct("VXUS") + _pct("VNQ")) >= 50.0:
            return (
                "objective alignment — current mix is growth/bond sleeves with ~0% T-Bills, while "
                "Balanced Growth Guided targets include an unrepresented ~10% Cash/T-Bill sleeve."
            )
    return "objective fit / Guided alignment versus the stated portfolio goal (review Health pillars)."


class PortfolioHealthEngine:
    """Answer Health / Sharpe-diagnostic questions from canonical session context."""

    engine_id = "portfolio_health"

    def solve(self, request: InstantEngineRequest) -> InvestmentSolverResult:
        ctx = dict(request.context or {})
        beginner = bool(request.beginner)
        question = str(request.question or "")
        score = _ctx_str(ctx, "health_score", default="")
        label = _ctx_str(ctx, "health_score_label", default="")
        status = _ctx_str(ctx, "health_status_message", default="")
        sharpe = _ctx_str(ctx, "sharpe_ratio", default="")
        objective = _ctx_str(ctx, "objective", default="your selected objective")
        issue = _primary_issue_from_context(ctx)

        score_bit = f"**{score}/100**" if score else "the latest Core Health score"
        label_bit = f"**{label}**" if label else "the current Health label"
        if score and label:
            health_lead = f"Core Portfolio Health is {score_bit} — {label_bit}."
        elif label:
            health_lead = f"Core Portfolio Health label is {label_bit}."
        elif score:
            health_lead = f"Core Portfolio Health score is {score_bit}."
        else:
            health_lead = (
                "Run **Portfolio Health** first so AMI can cite the live Core Health score and label."
            )

        ask_sharpe = _mentions_sharpe(question)
        sharpe_bit = sharpe or "the reported historical Sharpe"
        sharpe_line = (
            f"Historical Sharpe (**{sharpe_bit}**) is a **risk-adjusted diagnostic** for the selected "
            "lookback — it is **not** a Core Health allocation trigger and does **not** by itself "
            "require an allocation change under Option C."
            if ask_sharpe
            else (
                "Absolute Sharpe/Sortino (when shown) are diagnostics outside Core Health scoring — "
                "not automatic allocation triggers."
            )
        )

        direct = (
            f"{health_lead} Principal structural issue: **{issue}** "
            + (sharpe_line if ask_sharpe else "")
        ).strip()

        analyst = (
            "Option C Core Health combines **objective fit**, **construction**, **risk appropriateness**, "
            "and **policy-relative performance**. "
            f"{sharpe_line} "
            "Guided Portfolio Adjustment follows your stated category objective; "
            "optimizer corner solutions are exploratory mean-variance math under a selected basis — "
            "not the primary allocation instruction."
        )
        if status:
            analyst += f" Health status note: {status[:280]}"

        key_vars = "\n".join(
            filter(
                None,
                [
                    f"- Core Health score: **{score}/100**" if score else None,
                    f"- Health label: **{label}**" if label else None,
                    f"- Historical Sharpe (diagnostic): **{sharpe}**" if sharpe else None,
                    f"- Objective: **{objective}**" if objective else None,
                    f"- Principal issue (context): {issue}",
                ],
            )
        ) or "— Run Portfolio Health to populate score/label diagnostics."

        tradeoffs = (
            "Improving objective alignment (e.g. adding the Guided T-Bill sleeve) can reduce modeled "
            "policy drift but may trim equity upside. Chasing a higher Sharpe via optimizer corners "
            "can produce extreme weights that fight your stated Balanced Growth policy."
        )
        what_if = (
            "If you change nothing: Core Health remains a policy-fit scorecard; a low historical Sharpe "
            "alone does not flip Mostly On Plan into Off Plan. If you apply Guided toward the objective "
            "(including the orphan Cash/T-Bill sleeve), objective-fit drift is the lever to watch."
        )
        actions = (
            "Focus first on **Guided / objective alignment** for the stated goal. "
            "Treat Sharpe ~diagnostic only — do not reallocate solely because Sharpe is low. "
            "Do not treat optimizer 100%-one-ticker solutions as the app recommendation. "
            "Ask separately if you want a single-holding valuation read."
        )
        if beginner:
            actions = (
                "Start with Guided Portfolio Adjustment toward your goal. "
                "A low Sharpe number is background context — not an automatic reason to sell. "
                "Ask separately if you want a holding's valuation."
            )

        sections = build_analyst_sections(
            direct_answer=direct,
            portfolio_analyst_view=analyst,
            key_variables=key_vars,
            tradeoffs=tradeoffs,
            what_if_scenarios=what_if,
            recommended_actions=actions,
            risk_notes=(
                "Educational model commentary only — not financial advice. "
                "Core Health ≠ market forecast; diagnostics ≠ allocation triggers."
            ),
            beginner=beginner,
        )
        return InvestmentSolverResult(
            short_answer=direct,
            analyst_sections=sections,
            math_idea="Option C Core Health interpretation + diagnostic Sharpe framing.",
            problem_type="portfolio_health",
            model_name="Portfolio Health interpreter",
            confidence_pct=88 if score and label else 70,
            computed={
                "ami_engine_id": self.engine_id,
                "health_score": score or None,
                "health_score_label": label or None,
                "sharpe_ratio": sharpe or None,
                "primary_issue": issue,
            },
        )


_DEFAULT = PortfolioHealthEngine()


def get_portfolio_health_engine() -> PortfolioHealthEngine:
    return _DEFAULT
