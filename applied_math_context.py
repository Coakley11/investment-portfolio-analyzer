"""Page-specific Applied Math context extractors for Investment."""

from __future__ import annotations

import copy
from typing import Any


def cache_investment_context(session_state: dict[str, Any], ctx: dict[str, Any]) -> None:
    if ctx:
        session_state["_ami_investment_context"] = dict(ctx)


def _holdings_weight_column(df: Any) -> str | None:
    try:
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty:
            return None
        if "Weight (%)" in df.columns:
            return "Weight (%)"
        if "Weight" in df.columns:
            return "Weight"
    except Exception:
        pass
    return None


def current_weights_from_holdings_df(df: Any) -> dict[str, str]:
    """Build ticker → weight% map from the live portfolio editor dataframe."""
    try:
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty or "Ticker" not in df.columns:
            return {}
        weight_col = _holdings_weight_column(df)
        if not weight_col:
            return {}
        weights: dict[str, str] = {}
        for _, row in df.dropna(subset=["Ticker"]).iterrows():
            ticker = str(row.get("Ticker") or "").strip().upper()
            if not ticker:
                continue
            raw = row.get(weight_col)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                weights[ticker] = f"{float(raw):.1f}%"
            except (TypeError, ValueError):
                weights[ticker] = str(raw)
        return weights
    except Exception:
        return {}


def record_rebalance_from_health(session_state: dict[str, Any], health: Any) -> None:
    """Cache drift/target weights and rebalance recommendations for Applied Math."""
    if health is None:
        return
    drift: dict[str, str] = {}
    target_weights: dict[str, str] = {}
    current_weights: dict[str, str] = {}
    recommendations: list[str] = []

    reb = getattr(health, "rebalance_df", None)
    try:
        import pandas as pd

        if isinstance(reb, pd.DataFrame) and not reb.empty:
            for _, row in reb.iterrows():
                ticker = str(row.get("Ticker") or row.get("Asset") or "").strip()
                if not ticker:
                    continue
                cur = row.get("Current (%)")
                obj = row.get("Objective (%)")
                drift_val = row.get("Drift vs Objective (%)") or row.get("Change (pp)")
                if cur is not None:
                    try:
                        current_weights[ticker] = f"{float(cur):.1f}%"
                    except (TypeError, ValueError):
                        current_weights[ticker] = str(cur)
                if obj is not None:
                    try:
                        target_weights[ticker] = f"{float(obj):.1f}%"
                    except (TypeError, ValueError):
                        target_weights[ticker] = str(obj)
                if drift_val is not None:
                    try:
                        drift[ticker] = f"{float(drift_val):+.1f}pp"
                    except (TypeError, ValueError):
                        drift[ticker] = str(drift_val)
    except Exception:
        pass

    recs = getattr(health, "recommendations", None) or []
    if isinstance(recs, list):
        recommendations = [str(r).strip() for r in recs[:5] if str(r).strip()]

    avg_drift = getattr(health, "avg_drift", None)
    total_drift = f"{float(avg_drift) * 100:.1f}pp avg category drift" if avg_drift is not None else None

    ctx: dict[str, Any] = {}
    if drift:
        ctx["rebalance_drift"] = drift
        session_state["rebalance_drift"] = drift
        session_state["_ami_rebalance_drift"] = drift
    if target_weights:
        ctx["target_weights"] = target_weights
        session_state["target_weights"] = target_weights
    if current_weights:
        ctx["current_weights"] = current_weights
    if total_drift:
        ctx["total_drift"] = total_drift
    if recommendations:
        ctx["rebalance_recommendation"] = recommendations
    score = getattr(health, "score", None)
    if score is not None:
        ctx["health_score"] = round(float(score), 1)
    risk = getattr(health, "score_label", None) or getattr(health, "risk_level", None)
    if risk:
        ctx["risk_level"] = str(risk)

    if ctx:
        cache_investment_context(session_state, ctx)


def _merge_real_portfolio_ledger_into_ami_context(session_state: dict[str, Any], ctx: dict[str, Any]) -> None:
    """
    Copy canonical transaction ledger into AMI submit context.

    Real Portfolio Advisor reads ``portfolio_transactions`` from the merged context dict;
    session-only ledger without this copy yields ``no_real_ledger`` despite a populated UI tab.
    """
    try:
        from investment_persistent_state import (
            PORTFOLIO_TRANSACTIONS_KEY,
            REAL_PORTFOLIO_LEDGER_META_KEY,
            REAL_PORTFOLIO_LEDGER_RESTORED_FLAG,
            REAL_PORTFOLIO_LEDGER_TOUCHED_KEY,
        )
    except ImportError:
        PORTFOLIO_TRANSACTIONS_KEY = "portfolio_transactions"
        REAL_PORTFOLIO_LEDGER_META_KEY = "real_portfolio_ledger"
        REAL_PORTFOLIO_LEDGER_TOUCHED_KEY = "_real_portfolio_ledger_touched"
        REAL_PORTFOLIO_LEDGER_RESTORED_FLAG = "_suite_real_portfolio_ledger_restored"

    txn_records = session_state.get(PORTFOLIO_TRANSACTIONS_KEY)
    if isinstance(txn_records, list):
        ctx[PORTFOLIO_TRANSACTIONS_KEY] = copy.deepcopy(txn_records)
    meta = session_state.get(REAL_PORTFOLIO_LEDGER_META_KEY)
    if isinstance(meta, dict):
        ctx[REAL_PORTFOLIO_LEDGER_META_KEY] = copy.deepcopy(meta)
    if session_state.get(REAL_PORTFOLIO_LEDGER_TOUCHED_KEY):
        ctx[REAL_PORTFOLIO_LEDGER_TOUCHED_KEY] = True
    if session_state.get(REAL_PORTFOLIO_LEDGER_RESTORED_FLAG):
        ctx[REAL_PORTFOLIO_LEDGER_RESTORED_FLAG] = True


def real_portfolio_ami_ledger_diagnostics(
    session_state: dict[str, Any],
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Admin/support snapshot: session vs AMI context vs snapshot build."""
    try:
        from investment_persistent_state import PORTFOLIO_TRANSACTIONS_KEY, APP_ID, load_user_state
    except ImportError:
        PORTFOLIO_TRANSACTIONS_KEY = "portfolio_transactions"
        APP_ID = "investment"
        load_user_state = None  # type: ignore[assignment]

    ss_txns = session_state.get(PORTFOLIO_TRANSACTIONS_KEY)
    ctx = ctx or {}
    ctx_txns = ctx.get(PORTFOLIO_TRANSACTIONS_KEY)
    session_count = len(ss_txns) if isinstance(ss_txns, list) else 0
    ctx_count = len(ctx_txns) if isinstance(ctx_txns, list) else 0
    persisted_count: int | None = None
    if load_user_state is not None:
        try:
            disk_state, _ = load_user_state(APP_ID)
            if isinstance(disk_state, dict):
                disk_tx = disk_state.get(PORTFOLIO_TRANSACTIONS_KEY)
                persisted_count = len(disk_tx) if isinstance(disk_tx, list) else 0
        except Exception:
            persisted_count = None

    workspace_id = ""
    try:
        workspace_id = str(session_state.get("_suite_active_workspace_id") or "")
    except Exception:
        pass

    deploy_commit = "unknown"
    try:
        from suite_deploy_marker import resolve_git_commit_short

        deploy_commit = resolve_git_commit_short()
    except Exception:
        pass

    snapshot_source = "none"
    failure_code = ""
    try:
        from investment_ami.decision_support.real_portfolio_snapshot import build_real_portfolio_snapshot

        probe_ctx = dict(ctx) if ctx else {}
        if isinstance(ss_txns, list) and PORTFOLIO_TRANSACTIONS_KEY not in probe_ctx:
            probe_ctx[PORTFOLIO_TRANSACTIONS_KEY] = copy.deepcopy(ss_txns)
        build = build_real_portfolio_snapshot(session_state, context=probe_ctx if probe_ctx else None)
        if build.ok:
            snapshot_source = "portfolio_transactions"
        elif build.failure:
            failure_code = str(build.failure.code or "")
            if session_count > 0 and ctx_count == 0:
                snapshot_source = "session_only_context_missing_txns"
            elif session_count == 0:
                snapshot_source = "empty_session"
            else:
                snapshot_source = "build_failed"
    except Exception as exc:
        failure_code = f"exception:{exc}"

    positions_ok = False
    if isinstance(ss_txns, list) and ss_txns:
        try:
            import portfolio_engine as pe

            positions, _ = pe.build_positions(pe.transactions_from_records(ss_txns))
            positions_ok = bool(positions)
        except Exception:
            positions_ok = False

    no_ledger_reason = ""
    if failure_code == "no_real_ledger":
        if session_count > 0 and ctx_count == 0:
            no_ledger_reason = "ami_context_missing_portfolio_transactions"
        elif session_count == 0:
            no_ledger_reason = "session_portfolio_transactions_empty"
        elif not positions_ok:
            no_ledger_reason = "ledger_has_no_open_positions_or_cash_activity"
        else:
            no_ledger_reason = "snapshot_rejected_meaningful_ledger_check"

    return {
        "deploy_commit": deploy_commit,
        "active_workspace": workspace_id,
        "session_transaction_count": session_count,
        "ami_context_transaction_count": ctx_count,
        "persisted_transaction_count": persisted_count,
        "real_portfolio_ledger_touched": bool(session_state.get("_real_portfolio_ledger_touched")),
        "snapshot_build_source": snapshot_source,
        "snapshot_failure_code": failure_code,
        "no_real_ledger_reason": no_ledger_reason,
        "session_has_open_positions": positions_ok,
        "has_real_portfolio_context": bool(ctx.get("real_portfolio")),
    }


def build_investment_applied_math_context(page: str, session_state: dict[str, Any]) -> dict[str, Any]:
    tab = str(session_state.get("investment_active_tab") or page or "").strip()
    ctx: dict[str, Any] = {"page": tab}

    hr = session_state.get("health_result")
    if hr is not None and not session_state.get("_ami_rebalance_drift"):
        try:
            record_rebalance_from_health(session_state, hr)
        except Exception:
            pass

    exp = session_state.get("investment_experience") or session_state.get("experience_mode")
    if exp:
        ctx["experience_mode"] = str(exp)

    objective = str(
        session_state.get("portfolio_objective") or session_state.get("investment_objective") or ""
    ).strip()
    if objective:
        ctx["objective"] = objective

    pv = session_state.get("sidebar_portfolio_value")
    if pv:
        try:
            from planning_portfolio_value import effective_planning_portfolio_value_for_ami

            eff = effective_planning_portfolio_value_for_ami(session_state)
            display_pv = eff if eff is not None else float(pv)
            ctx["portfolio_value"] = f"${int(float(display_pv)):,}"
        except ImportError:
            try:
                ctx["portfolio_value"] = f"${int(float(pv)):,}"
            except (TypeError, ValueError):
                ctx["portfolio_value"] = str(pv)

    hr = session_state.get("health_result")
    if hr is not None:
        score = getattr(hr, "score", None) if not isinstance(hr, dict) else hr.get("score")
        if score is not None:
            ctx["health_score"] = round(float(score), 1) if isinstance(score, (int, float)) else score
        for attr, key, fmt in (
            ("expected_return", "expected_return", "{:.1f}%"),
            ("volatility", "volatility", "{:.1f}%"),
            ("sharpe", "sharpe_ratio", "{:.2f}"),
            ("max_drawdown", "max_drawdown", "{:.1f}%"),
            ("risk_level", "risk_level", "{}"),
        ):
            val = getattr(hr, attr, None) if not isinstance(hr, dict) else hr.get(attr)
            if val is not None and val != "":
                try:
                    ctx[key] = fmt.format(float(val)) if fmt != "{}" else str(val)
                except (TypeError, ValueError):
                    ctx[key] = str(val)
        ctx.setdefault(
            "context_note_historical",
            "expected_return/volatility/sharpe/max_drawdown are historical unless labeled forward",
        )

    df = session_state.get("holdings_df")
    try:
        import pandas as pd

        if isinstance(df, pd.DataFrame) and not df.empty and "Ticker" in df.columns:
            tickers = [str(t).strip() for t in df["Ticker"].dropna().tolist() if str(t).strip()]
            if tickers:
                ctx["holdings"] = tickers[:12]
    except Exception:
        pass

    target = session_state.get("target_weights") or session_state.get("portfolio_target_weights")
    if isinstance(target, dict) and target:
        ctx["target_weights"] = {str(k): str(v) for k, v in list(target.items())[:12]}

    drift = session_state.get("rebalance_drift") or session_state.get("_ami_rebalance_drift")
    if isinstance(drift, dict) and drift:
        ctx["rebalance_drift"] = drift

    if "macro" in tab.lower():
        ctx["workflow"] = "Macro analysis"
        try:
            from components.macro_engine import macro_assumption_summary

            macro = macro_assumption_summary()
            if macro:
                ctx["macro_summary"] = macro
                ctx["macro_outlook"] = macro
                ctx["context_note_forward"] = "Macro outlook affects forward projections and health recommendations, not historical return/volatility"
        except Exception:
            pass

    extra = session_state.get("_ami_investment_context")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None and v != "":
                ctx[k] = v

    try:
        from components.macro_engine import macro_assumption_summary

        macro = macro_assumption_summary()
        if macro:
            ctx.setdefault("macro_summary", macro)
            ctx.setdefault("macro_outlook", macro)
    except Exception:
        pass

    try:
        import pandas as pd

        df_ami = session_state.get("holdings_df")
        if isinstance(df_ami, pd.DataFrame) and not df_ami.empty:
            _enrich_investment_ami_analytics(ctx, df_ami, session_state)
    except Exception:
        pass

    # Live portfolio editor weights always win over cached health/rebalance snapshots.
    live_weights = current_weights_from_holdings_df(session_state.get("holdings_df"))
    if live_weights:
        ctx["current_weights"] = live_weights

    txn_records = session_state.get("portfolio_transactions")
    if isinstance(txn_records, list) and txn_records:
        try:
            import portfolio_engine as pe

            real_ctx = pe.build_ami_portfolio_context(pe.transactions_from_records(txn_records))
            ctx["real_portfolio"] = real_ctx
            if real_ctx.get("position_weights"):
                ctx.setdefault("current_weights_real", real_ctx["position_weights"])
        except Exception:
            pass

    _merge_real_portfolio_ledger_into_ami_context(session_state, ctx)
    _merge_investment_plan_into_context(session_state, ctx)
    return ctx


def _merge_investment_plan_into_context(session_state: dict[str, Any], ctx: dict[str, Any]) -> None:
    """Expose How Much Should I Invest session inputs to AMI decision support."""
    try:
        from components.investment_planning import PLAN_MONTHLY_PROVIDED_KEY
    except ImportError:
        PLAN_MONTHLY_PROVIDED_KEY = "plan_monthly_provided"  # noqa: N806
    for key in (
        "plan_total_cash",
        "plan_emergency",
        "plan_near_term",
        "plan_debt",
        "plan_expenses",
        "plan_horizon",
        "plan_risk",
    ):
        if key in session_state and session_state.get(key) is not None:
            ctx[key] = session_state[key]
    if session_state.get("sidebar_portfolio_value") is not None:
        try:
            from planning_portfolio_value import effective_planning_portfolio_value_for_ami

            eff = effective_planning_portfolio_value_for_ami(session_state)
            if eff is not None:
                ctx["applied_plan_portfolio_value"] = int(round(eff))
                ctx["sidebar_portfolio_value"] = int(round(eff))
            else:
                ctx["sidebar_portfolio_value"] = session_state["sidebar_portfolio_value"]
        except ImportError:
            ctx["sidebar_portfolio_value"] = session_state["sidebar_portfolio_value"]
    if session_state.get("investment_plan_generated"):
        ctx["investment_plan_generated"] = True
    if session_state.get(PLAN_MONTHLY_PROVIDED_KEY) is not None:
        ctx["plan_monthly_provided"] = bool(session_state.get(PLAN_MONTHLY_PROVIDED_KEY))
    if session_state.get(PLAN_MONTHLY_PROVIDED_KEY):
        ctx["plan_monthly"] = session_state.get("plan_monthly")
    for key in (
        "monthly_income",
        "monthly_expenses",
        "job_stability",
        "plan_employer_match",
        "plan_retirement_goal",
    ):
        val = session_state.get(key)
        if val is not None and val != "":
            ctx[key] = val
    plan = session_state.get("investment_plan")
    if plan is not None:
        try:
            from json_safe import investment_plan_result_to_dict

            ctx["investment_plan"] = investment_plan_result_to_dict(plan)
        except TypeError:
            ctx.pop("investment_plan", None)


def _enrich_investment_ami_analytics(
    ctx: dict[str, Any],
    holdings_df: Any,
    session_state: dict[str, Any],
) -> None:
    """Add overlap, asset-class, and scenario params for Investment AMI Phase 2."""
    import pandas as pd

    if not isinstance(holdings_df, pd.DataFrame) or holdings_df.empty:
        return

    if "Asset Type" in holdings_df.columns and "Weight (%)" in holdings_df.columns:
        breakdown: dict[str, float] = {}
        for _, row in holdings_df.dropna(subset=["Ticker"]).iterrows():
            at = str(row.get("Asset Type") or "Equity").strip() or "Equity"
            try:
                w = float(row.get("Weight (%)") or 0)
            except (TypeError, ValueError):
                w = 0.0
            if w > 0:
                breakdown[at] = breakdown.get(at, 0.0) + w
        if breakdown:
            ctx["asset_class_breakdown"] = {k: round(v, 1) for k, v in breakdown.items()}

    try:
        import etf_holdings as eh

        etf_list = [t for t, _ in eh.portfolio_etf_tickers(holdings_df)]
        if len(etf_list) >= 2:
            holdings_map: dict[str, pd.DataFrame] = {}
            try:
                batch = eh.lookup_etfs(etf_list[:6])
                for t in etf_list[:6]:
                    result = batch.get(t.upper())
                    holdings_map[t] = result.holdings if result is not None else pd.DataFrame()
            except Exception:
                for t in etf_list[:6]:
                    try:
                        holdings_map[t] = eh.lookup_etf(t).holdings
                    except Exception:
                        holdings_map[t] = pd.DataFrame()
            pairs: list[dict[str, Any]] = []
            for i, t1 in enumerate(etf_list[:6]):
                for t2 in etf_list[i + 1 : 6]:
                    ov = eh.pairwise_etf_overlap(
                        holdings_map.get(t1, pd.DataFrame()),
                        holdings_map.get(t2, pd.DataFrame()),
                    )
                    if ov > 0:
                        pairs.append({"pair": f"{t1}/{t2}", "overlap_pct": round(ov * 100, 1)})
            if pairs:
                pairs.sort(key=lambda p: float(p.get("overlap_pct") or 0), reverse=True)
                ctx["etf_overlap_pairs"] = pairs[:8]
    except Exception:
        pass

    scenario: dict[str, Any] = dict(session_state.get("_ami_scenario_params") or {})
    rate = session_state.get("health_rate_env")
    if rate not in (None, "") and "rate_shock" not in scenario:
        scenario["rate_shock"] = str(rate)
    recession = session_state.get("health_recession")
    if recession not in (None, "") and "recession_scenario" not in scenario:
        scenario["recession_scenario"] = str(recession)
    if scenario:
        ctx["scenario_params"] = scenario

    valuation = session_state.get("health_valuation")
    if valuation not in (None, ""):
        ctx["health_valuation"] = str(valuation)
        scenario.setdefault("valuation_environment", str(valuation))
        ctx["scenario_params"] = scenario

    try:
        from investment_ami_exposure import build_tech_exposure_from_weights

        weights: dict[str, float] = {}
        if "Weight (%)" in holdings_df.columns and "Ticker" in holdings_df.columns:
            for _, row in holdings_df.dropna(subset=["Ticker"]).iterrows():
                t = str(row.get("Ticker") or "").strip().upper()
                try:
                    w = float(row.get("Weight (%)") or 0)
                except (TypeError, ValueError):
                    w = 0.0
                if t and w > 0:
                    weights[t] = w
        if weights:
            ctx["tech_exposure"] = build_tech_exposure_from_weights(weights)
    except Exception:
        pass


_INVESTMENT_SOURCE_FILTER_KEYS: tuple[str, ...] = (
    "overview_subtab",
    "mc_assumption_mode",
    "health_run_optimizer",
    "health_bond_min",
    "frontier_points",
    "macro_scenario_id",
    "macro_scenario_mode",
    "health_rate_env",
    "health_inflation",
    "health_recession",
    "health_valuation",
    "health_regime",
)

def _holdings_records_from_session(session_state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = session_state.get("holdings_df")
    try:
        import pandas as pd

        if isinstance(raw, pd.DataFrame) and not raw.empty and "Ticker" in raw.columns:
            return raw.to_dict(orient="records")
    except Exception:
        pass
    if isinstance(raw, list) and raw:
        return [dict(row) for row in raw if isinstance(row, dict)]
    return []


def enrich_investment_entity_params_holdings(
    session_state: dict[str, Any],
    entity_params: dict[str, Any],
) -> dict[str, Any]:
    """Ensure AMI entity_params carry portfolio rows/fingerprint when session or cloud has them."""
    ent = dict(entity_params or {})
    if ent.get("holdings_df"):
        return ent

    records = _holdings_records_from_session(session_state)
    if records:
        ent["holdings_df"] = records
        try:
            import pandas as pd

            from components.beginner_navigation import _holdings_fingerprint

            hfp = str(_holdings_fingerprint(pd.DataFrame(records))).strip()
            if hfp:
                ent["holdings_fingerprint"] = hfp
        except Exception:
            pass
    elif not str(ent.get("holdings_fingerprint") or "").strip():
        hfp = str(session_state.get("holdings_fingerprint") or "").strip()
        if not hfp:
            try:
                from investment_persistent_state import portfolio_fingerprint_from_session

                hfp = str(portfolio_fingerprint_from_session(session_state)).strip()
            except Exception:
                pass
        if hfp:
            ent["holdings_fingerprint"] = hfp

    if not ent.get("holdings_df"):
        try:
            from suite_analytical_question import peek_investment_portfolio_entity_params

            peek = peek_investment_portfolio_entity_params()
            if peek.get("holdings_df"):
                ent["holdings_df"] = peek["holdings_df"]
            if not str(ent.get("holdings_fingerprint") or "").strip() and peek.get("holdings_fingerprint"):
                ent["holdings_fingerprint"] = peek["holdings_fingerprint"]
            if peek.get("portfolio_built"):
                ent["portfolio_built"] = True
        except Exception:
            pass

    if session_state.get("portfolio_built"):
        ent["portfolio_built"] = True
    for key in (
        "preset_applied",
        "selected_portfolio",
        "beginner_goal_card",
        "guide_goal_choice",
        "health_objective",
    ):
        val = session_state.get(key)
        if val is not None and val != "" and key not in ent:
            ent[key] = val
    return ent


def enrich_investment_source_state_holdings(
    session_state: dict[str, Any],
    source_state: dict[str, Any],
) -> dict[str, Any]:
    state = dict(source_state or {})
    state["entity_params"] = enrich_investment_entity_params_holdings(
        session_state,
        dict(state.get("entity_params") or {}),
    )
    return state


def investment_source_state_has_portfolio_payload(source_state: dict[str, Any] | None) -> bool:
    if not isinstance(source_state, dict):
        return False
    ent = source_state.get("entity_params")
    if not isinstance(ent, dict):
        return False
    if ent.get("holdings_df"):
        return True
    return bool(str(ent.get("holdings_fingerprint") or "").strip())


_INVESTMENT_SOURCE_GLOBAL_KEYS: tuple[str, ...] = (
    "experience",
    "_suite_persisted_experience",
    "sidebar_portfolio_value",
    "analysis_start_date",
    "analysis_end_date",
    "risk_free_pct",
    "portfolio_preset",
)


def build_source_state(page: str, session_state: dict[str, Any]) -> dict[str, Any]:
    """Serializable snapshot for AMI launch + return restore (tab, portfolio, globals, filters)."""
    from datetime import datetime, timezone

    tab = str(session_state.get("investment_active_tab") or page or "").strip()
    widget_params: dict[str, Any] = {}
    entity_params: dict[str, Any] = {"tab": tab, "page": tab}
    filter_params: dict[str, Any] = {}

    objective = str(
        session_state.get("health_objective")
        or session_state.get("portfolio_objective")
        or session_state.get("investment_objective")
        or ""
    ).strip()
    if objective:
        entity_params["objective"] = objective
        widget_params["health_objective"] = objective

    for key in _INVESTMENT_SOURCE_GLOBAL_KEYS:
        val = session_state.get(key)
        if key == "sidebar_portfolio_value":
            try:
                from planning_portfolio_value import effective_planning_portfolio_value_for_ami

                eff = effective_planning_portfolio_value_for_ami(session_state)
                if eff is not None:
                    val = int(round(eff))
            except ImportError:
                pass
        if val is not None and val != "":
            filter_params[key] = val

    exp = session_state.get("investment_experience") or session_state.get("experience_mode")
    if exp:
        filter_params["experience_mode"] = str(exp)

    for key in _INVESTMENT_SOURCE_FILTER_KEYS:
        val = session_state.get(key)
        if val is not None and val != "":
            filter_params[key] = val

    preset = session_state.get("preset_applied")
    if preset:
        entity_params["preset_applied"] = str(preset)
    if session_state.get("portfolio_built"):
        entity_params["portfolio_built"] = True
    for goal_key in ("beginner_goal_card", "guide_goal_choice", "health_objective"):
        val = session_state.get(goal_key)
        if val is not None and val != "":
            entity_params[goal_key] = val

    df = session_state.get("holdings_df")
    tickers: list[str] = []
    try:
        import pandas as pd

        from components.beginner_navigation import _holdings_fingerprint

        if isinstance(df, pd.DataFrame) and not df.empty and "Ticker" in df.columns:
            tickers = [str(t).strip() for t in df["Ticker"].dropna().tolist() if str(t).strip()]
            if tickers:
                entity_params["holdings"] = tickers[:12]
            hfp = str(_holdings_fingerprint(df)).strip()
            if hfp:
                entity_params["holdings_fingerprint"] = hfp
            entity_params["holdings_df"] = df.to_dict(orient="records")
    except Exception:
        pass
    entity_params = enrich_investment_entity_params_holdings(session_state, entity_params)

    hr = session_state.get("health_result")
    if hr is not None:
        score = getattr(hr, "score", None) if not isinstance(hr, dict) else hr.get("score")
        if score is not None:
            entity_params["health_score"] = score
    summary = session_state.get("health_summary")
    if isinstance(summary, dict) and summary.get("score") is not None:
        entity_params.setdefault("health_score", summary.get("score"))

    return enrich_investment_source_state_holdings(
        session_state,
        {
            "source_app": "investment",
            "source_page": tab,
            "page_params": {"page": tab, "tab": tab},
            "entity_params": entity_params,
            "widget_params": widget_params,
            "filter_params": filter_params,
            "chart_params": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def ensure_investment_source_state(page: str, session_state: dict[str, Any]) -> dict[str, Any]:
    """Build source_state for AMI launch; always returns an investment snapshot dict."""
    try:
        state = build_source_state(page, session_state)
        if isinstance(state, dict) and state.get("source_app"):
            return enrich_investment_source_state_holdings(session_state, state)
    except Exception:
        pass
    tab = str(session_state.get("investment_active_tab") or page or "").strip()
    return enrich_investment_source_state_holdings(
        session_state,
        {
            "source_app": "investment",
            "source_page": tab,
            "page_params": {"page": tab, "tab": tab},
            "entity_params": {"tab": tab, "page": tab},
            "widget_params": {},
            "filter_params": {},
            "chart_params": {},
        },
    )


def _apply_holdings_df_from_entity(session_state: dict[str, Any], ent: dict[str, Any]) -> bool:
    """Restore ``holdings_df`` from AMI source_state entity_params when present."""
    raw = ent.get("holdings_df")
    if not raw:
        return False
    try:
        import pandas as pd

        df = pd.DataFrame(raw)
        if df.empty or "Ticker" not in df.columns:
            return False
        session_state["holdings_df"] = df
        return True
    except Exception:
        return False


def apply_source_state_to_session(session_state: dict[str, Any], source_state: dict[str, Any]) -> None:
    """Map stored source_state into Investment session restore keys."""
    if not source_state:
        return
    ent = dict(source_state.get("entity_params") or {})
    wp = dict(source_state.get("widget_params") or {})
    fp = dict(source_state.get("filter_params") or {})
    tab = str(
        source_state.get("source_page")
        or source_state.get("page_params", {}).get("tab")
        or source_state.get("page_params", {}).get("page")
        or ""
    ).strip()
    if tab:
        session_state["_suite_investment_page"] = tab
        session_state["investment_active_tab"] = tab
        # Deferred tab restore is set only from live AMI return URL handlers.
    hfp = ent.get("holdings_fingerprint")
    if hfp:
        session_state["_suite_holdings_fp"] = str(hfp)
    _apply_holdings_df_from_entity(session_state, ent)
    for key in ("beginner_goal_card", "guide_goal_choice", "preset_applied", "health_objective", "portfolio_built"):
        if key in ent and ent[key] is not None and ent[key] != "":
            session_state[key] = ent[key]
    for k, v in wp.items():
        if v is not None:
            try:
                from planning_portfolio_value import should_block_portfolio_value_restore

                if should_block_portfolio_value_restore(session_state, k):
                    continue
            except ImportError:
                pass
            session_state[k] = v
    for k, v in fp.items():
        if v is not None and v != "":
            try:
                from planning_portfolio_value import should_block_portfolio_value_restore

                if should_block_portfolio_value_restore(session_state, k):
                    continue
            except ImportError:
                pass
            session_state[k] = v

