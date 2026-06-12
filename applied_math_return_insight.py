"""Return Applied Math insight to source apps — v1 display-only."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

INSIGHT_ITEM_TYPE = "applied_math_insight"
SESSION_PENDING_KEY = "_ami_pending_insight"
SESSION_RETURN_PAGE_KEY = "_ami_return_page"
SESSION_RETURN_CONTEXT_KEY = "_ami_return_context"
SESSION_INSIGHT_SOURCE_TAB_KEY = "insight_source_tab"
SESSION_SOURCE_INVESTMENT_TAB_KEY = "source_investment_tab"
INVESTMENT_INSIGHT_PANEL_TITLE = "Applied Investment Insight"

_INVESTMENT_TAB_CANONICAL: dict[str, str] = {
    "portfolio health": "Portfolio Health",
    "⑤ portfolio health": "Portfolio Health",
    "portfolio analytics": "Portfolio Analytics",
    "④ analyze portfolio": "Portfolio Analytics",
    "analyze portfolio": "Portfolio Analytics",
    "efficient frontier": "Efficient Frontier",
    "⑩ frontier (optional)": "Efficient Frontier",
    "frontier (optional)": "Efficient Frontier",
}

# Pages where the insight card may appear (display-only v1).
INSIGHT_ELIGIBLE_PAGES: dict[str, frozenset[str]] = {
    "baseball": frozenset({
        "Comparison Tool",
        "Trend Value",
        "Historical Explorer",
        "Draft Assistant Simulator",
        "Live Draft Room",
        "Draft Room Simulator",
        "Draft Simulation Test Mode",
    }),
    "nba": frozenset({
        "Matchup Intelligence",
        "Legacy Tracker",
        "Live Game Center",
    }),
    "investment": frozenset({
        "Portfolio Health",
        "⑤ Portfolio Health",
        "Portfolio Analytics",
        "④ Analyze Portfolio",
        "Efficient Frontier",
        "⑩ Frontier (Optional)",
    }),
}


def _normalize_insight_page(page: str) -> str:
    p = str(page or "").strip()
    if p.startswith("🔴 "):
        p = p.replace("🔴 ", "", 1)
    if p.startswith("🧠 "):
        p = p.replace("🧠 ", "", 1)
    if p.startswith("👑 "):
        p = p.replace("👑 ", "", 1)
    return p.strip()


def _normalize_investment_tab(page: str) -> str:
    """Canonical Investment tab label for insight page scoping."""
    p = _normalize_insight_page(page)
    if not p:
        return ""
    key = p.lower().strip()
    if key in _INVESTMENT_TAB_CANONICAL:
        return _INVESTMENT_TAB_CANONICAL[key]
    import re

    stripped = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩\d]+\s*", "", p).strip()
    alias = _INVESTMENT_TAB_CANONICAL.get(stripped.lower())
    if alias:
        return alias
    for label in _INVESTMENT_TAB_CANONICAL.values():
        if label.lower() == stripped.lower() or label.lower() == key:
            return label
    return p


def _investment_tabs_match(current_page: str, insight_page: str) -> bool:
    cur = _normalize_investment_tab(current_page)
    src = _normalize_investment_tab(insight_page)
    if not cur or not src:
        return False
    return cur == src or cur.lower() == src.lower()


def _resolve_insight_source_page(insight: dict[str, Any]) -> str:
    """Canonical originating Investment/source page for a pending insight."""
    raw = str(insight.get("source_page") or "").strip()
    page = _normalize_investment_tab(raw) if raw else _normalize_insight_page(raw)
    if page:
        return page
    for container_key in ("source_state", "return_context"):
        container = insight.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ("source_page", "page"):
            candidate = str(container.get(key) or "").strip()
            if candidate:
                normalized = _normalize_investment_tab(candidate)
                if normalized:
                    return normalized
        page_params = container.get("page_params")
        if isinstance(page_params, dict):
            candidate = str(page_params.get("page") or page_params.get("tab") or "").strip()
            if candidate:
                normalized = _normalize_investment_tab(candidate)
                if normalized:
                    return normalized
        ent = container.get("entity_params")
        if isinstance(ent, dict):
            candidate = str(ent.get("tab") or ent.get("page") or "").strip()
            if candidate:
                normalized = _normalize_investment_tab(candidate)
                if normalized:
                    return normalized
    return ""


def _query_param(st: Any, name: str) -> str:
    try:
        raw = st.query_params.get(name)
    except Exception:
        return ""
    if raw is None:
        return ""
    if isinstance(raw, list):
        return str(raw[0] or "").strip()
    return str(raw).strip()


def insight_return_query_id(st: Any) -> str:
    return _query_param(st, "suite_ami_insight")


def _active_ami_return_query_param_keys(st: Any) -> list[str]:
    """AMI return query params present on the current URL."""
    names = ("suite_ami_insight", "suite_page", "suite_holdings_fp", "suite_ai_question_id")
    return [name for name in names if _query_param(st, name)]


def _ami_return_url_active(st: Any) -> bool:
    """True when the current URL carries a live AMI insight return param."""
    return bool(insight_return_query_id(st))


def clear_ami_return_deferred_flags(st: Any, app_key: str) -> list[str]:
    """Drop deferred AMI tab/holdings restore flags (safe after return consumed or on normal reboot)."""
    ss = st.session_state
    cleared: list[str] = []
    for flag in (
        SESSION_RETURN_CONTEXT_KEY,
        SESSION_RETURN_PAGE_KEY,
        "_skip_page_restore_for",
        "_suite_holdings_fp",
        "_ami_hydrated_insight_id",
        "_navigate_to_page",
        "_suite_page_overwrite_source",
        "_suite_holdings_fp_mismatch",
        "_suite_holdings_fp_confirmed",
    ):
        if flag in ss:
            ss.pop(flag, None)
            cleared.append(flag)
    if str(app_key or "").strip().lower() == "investment" and not _ami_return_url_active(st):
        for flag in (SESSION_PENDING_KEY,):
            if flag in ss:
                ss.pop(flag, None)
                cleared.append(flag)
    return cleared


def reconcile_stale_page_navigation(st: Any, app_key: str) -> list[str]:
    """Clear stale AMI deferred-restore flags when not in a live AMI return URL."""
    if _ami_return_url_active(st):
        return []
    return clear_ami_return_deferred_flags(st, app_key)


def mark_ami_return_resume_consumed(st: Any, app_key: str) -> None:
    """Record that AMI return hydration/restore finished so startup may use cloud restore."""
    key = str(app_key or "").strip().lower()
    if key == "math":
        key = "applied_intelligence"
    try:
        from suite_cloud_state import _ami_resume_consumed_flag

        st.session_state[_ami_resume_consumed_flag(key)] = True
    except ImportError:
        st.session_state[f"_ami_resume_consumed_{key}"] = True


def ami_return_navigation_active(st: Any, app_key: str) -> bool:
    """True only when ``suite_ami_insight`` is on the URL (live AMI return), not stale session flags."""
    key = str(app_key or "").strip().lower()
    if key == "math":
        key = "applied_intelligence"
    if not insight_return_query_id(st):
        return False
    return key == "investment" or bool(st.session_state.get(SESSION_RETURN_CONTEXT_KEY))


def _session_holdings_fingerprint(session_state: Any) -> str:
    try:
        import pandas as pd

        from components.beginner_navigation import _holdings_fingerprint

        df = session_state.get("holdings_df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            return str(_holdings_fingerprint(df)).strip()
    except Exception:
        pass
    return ""


def ami_resume_consumed(st: Any, app_key: str) -> bool:
    try:
        from suite_cloud_state import ami_return_resume_consumed

        return ami_return_resume_consumed(st, app_key)
    except Exception:
        key = str(app_key or "").strip().lower()
        return bool(st.session_state.get(f"_ami_resume_consumed_{key}"))


def _sync_investment_insight_tab_keys(
    st: Any,
    app_key: str,
    *,
    insight: dict[str, Any] | None = None,
) -> None:
    if str(app_key or "").strip().lower() != "investment":
        return
    ss = st.session_state
    pending = insight if isinstance(insight, dict) else ss.get(SESSION_PENDING_KEY)
    source_tab = ""
    if isinstance(pending, dict):
        source_tab = _resolve_insight_source_page(pending)
    if not source_tab:
        source_tab = str(ss.get(SESSION_RETURN_PAGE_KEY) or "").strip()
    current = str(ss.get("investment_active_tab") or "").strip()
    if source_tab:
        ss[SESSION_INSIGHT_SOURCE_TAB_KEY] = source_tab
        ss[SESSION_SOURCE_INVESTMENT_TAB_KEY] = source_tab
    ss["current_investment_tab"] = current


def insight_page_scope_decision(
    source_app: str,
    current_page: str,
    insight: dict[str, Any],
) -> dict[str, Any]:
    """Strict page scope decision with skip reason (Investment uses tab equality)."""
    app = str(source_app or insight.get("source_app") or "").strip().lower()
    cur_raw = str(current_page or "").strip()
    insight_page = _resolve_insight_source_page(insight)
    if app == "investment":
        cur = _normalize_investment_tab(cur_raw)
        eligible = INSIGHT_ELIGIBLE_PAGES.get("investment", frozenset())
        cur_eligible = cur in eligible or any(
            _normalize_investment_tab(x) == cur for x in eligible
        )
        should_render = False
        skip_reason = ""
        if not cur_eligible:
            skip_reason = f"current_page_not_eligible ({cur_raw!r})"
        elif not insight_page:
            skip_reason = "missing_insight_source_tab"
        elif _investment_tabs_match(cur_raw, insight_page):
            should_render = True
        else:
            skip_reason = "source_tab_mismatch"
        return {
            "source_page_raw": str(insight.get("source_page") or "").strip() or None,
            "source_page_normalized": insight_page or None,
            "current_page_raw": cur_raw or None,
            "current_page_normalized": cur or None,
            "insight_source_tab": insight_page or None,
            "current_investment_tab": cur_raw or None,
            "should_render_insight_on_page": should_render,
            "render_skip_reason": skip_reason or None,
        }

    cur = _normalize_insight_page(current_page)
    eligible = INSIGHT_ELIGIBLE_PAGES.get(app, frozenset())
    if cur not in eligible and not any(_normalize_insight_page(x) == cur for x in eligible):
        return {
            "should_render_insight_on_page": False,
            "render_skip_reason": f"current_page_not_eligible ({cur!r})",
        }
    insight_page_norm = _normalize_insight_page(insight_page)
    if not insight_page_norm:
        return {
            "should_render_insight_on_page": False,
            "render_skip_reason": "missing_normalized_source_page",
        }
    if insight_page_norm == cur:
        return {"should_render_insight_on_page": True, "render_skip_reason": None}
    if "draft" in insight_page_norm.lower() and "draft" in cur.lower():
        return {"should_render_insight_on_page": True, "render_skip_reason": None}
    return {
        "should_render_insight_on_page": False,
        "render_skip_reason": f"normalized_page_mismatch (insight={insight_page_norm!r}, current={cur!r})",
    }


def should_render_insight_on_page(source_app: str, current_page: str, insight: dict[str, Any]) -> bool:
    """True when pending insight belongs on this page only (strict for Investment)."""
    return bool(
        insight_page_scope_decision(source_app, current_page, insight).get(
            "should_render_insight_on_page"
        )
    )


def _insight_panel_title(source_app: str, insight: dict[str, Any] | None = None) -> str:
    app = str(source_app or (insight or {}).get("source_app") or "").strip().lower()
    if app == "investment":
        return INVESTMENT_INSIGHT_PANEL_TITLE
    return "Applied Math Insight"


def _insight_from_persisted_full_session(app_key: str) -> dict[str, Any]:
    """Load pending insight embedded in Investment ``full_session`` (disk or cloud)."""
    app = str(app_key or "").strip().lower()
    if not app:
        return {}
    try:
        from suite_cloud_state import load_cloud_full_session
        from suite_user_persistence import load_user_state

        cloud_state, _cloud_ts = load_cloud_full_session(app)
        disk_state, _disk_warn = load_user_state(app)
        for state in (cloud_state, disk_state):
            if not isinstance(state, dict):
                continue
            pending = state.get(SESSION_PENDING_KEY)
            if isinstance(pending, dict) and (pending.get("conclusion") or pending.get("question")):
                out = dict(pending)
                out.setdefault("source_app", app)
                if not out.get("insight_id"):
                    out["insight_id"] = str(pending.get("insight_id") or "").strip()
                out["_hydrate_source_hint"] = "full_session_blob"
                return out
    except Exception as exc:
        log.warning("_insight_from_persisted_full_session failed: %s", exc)
    return {}


def load_latest_applied_math_insight_for_app(
    source_app: str,
    *,
    exclude_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Most recent cloud-stored insight for a source app (cross-device)."""
    app = str(source_app or "").strip().lower()
    if not app:
        return {}
    excluded = exclude_ids or set()
    try:
        from suite_account import load_saved_items

        store_keys = (app, "applied_intelligence")
        if app == "investment":
            store_keys = ("investment", "applied_intelligence")
        for app_key in store_keys:
            rows = load_saved_items(app=app_key, item_type=INSIGHT_ITEM_TYPE, limit=30)
            for row in rows:
                iid = str(row.get("item_key") or "").strip()
                if not iid or iid in excluded:
                    continue
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_app = str(payload.get("source_app") or "").strip().lower()
                if app == "investment" and payload_app and payload_app != "investment":
                    continue
                if payload_app and payload_app != app and app_key != app:
                    continue
                if payload.get("conclusion") or payload.get("question"):
                    out = dict(payload)
                    out.setdefault("insight_id", iid)
                    out.setdefault("source_app", app)
                    return out
    except Exception as exc:
        log.warning("load_latest_applied_math_insight_for_app failed: %s", exc)
    return _insight_from_persisted_full_session(app)


def _pending_insight_valid(st: Any) -> dict[str, Any]:
    pending = st.session_state.get(SESSION_PENDING_KEY)
    if not isinstance(pending, dict):
        return {}
    if pending.get("conclusion") or pending.get("question"):
        return pending
    return {}


def insight_exists_in_cloud(source_app: str) -> bool:
    return bool(load_latest_applied_math_insight_for_app(source_app))


def hydrate_applied_math_insight_for_session(st: Any, app_key: str) -> bool:
    """
    Load pending insight from URL, session, or cloud (cross-device phone refresh).

    Display-only — does not change Tests A–E persistence paths.
    """
    key = str(app_key or "").strip().lower()
    ss = st.session_state
    ss["_ami_insight_hydrate_attempted"] = True

    url_iid = insight_return_query_id(st)
    if url_iid:
        prev = str(ss.get("_ami_hydrated_insight_id") or "").strip()
        pending = _pending_insight_valid(st)
        if prev != url_iid or not pending:
            apply_ami_insight_from_query(st, key)
        pending = _pending_insight_valid(st)
        if pending:
            ss["_ami_insight_hydrate_success"] = True
            ss["_ami_insight_hydrate_source"] = "url"
            _sync_investment_insight_tab_keys(st, key, insight=pending)
            return True

    pending = _pending_insight_valid(st)
    if pending:
        ss["_ami_insight_hydrate_success"] = True
        ss["_ami_insight_hydrate_source"] = "session"
        _sync_investment_insight_tab_keys(st, key, insight=pending)
        return True

    latest = load_latest_applied_math_insight_for_app(key)
    if latest:
        ss[SESSION_PENDING_KEY] = latest
        source_page = _resolve_insight_source_page(latest)
        if source_page:
            ss[SESSION_RETURN_PAGE_KEY] = source_page
        _sync_investment_insight_tab_keys(st, key, insight=latest)
        ss["_ami_insight_hydrate_success"] = True
        hydrate_src = str(latest.get("_hydrate_source_hint") or "cloud_saved_items")
        ss["_ami_insight_hydrate_source"] = hydrate_src
        ss["_ami_hydrated_insight_id"] = str(latest.get("insight_id") or "").strip()
        if key == "investment" and hydrate_src == "cloud_saved_items":
            try:
                from investment_persistent_state import notify_pending_insight_change

                notify_pending_insight_change(st, source="insight_hydrate")
            except Exception:
                pass
        return True

    ss["_ami_insight_hydrate_success"] = False
    ss["_ami_insight_hydrate_source"] = "none"
    return False


@dataclass
class AppliedMathInsight:
    insight_id: str
    question_id: str
    question: str
    source_app: str
    source_page: str
    conclusion: str
    method: str
    model_name: str = ""
    math_summary: str = ""
    assumptions: list[str] = field(default_factory=list)
    confidence: str = "medium"
    confidence_pct: int | None = None
    key_numbers: dict[str, Any] = field(default_factory=dict)
    full_analysis_url: str = ""
    created_at: str = ""
    resume_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _confidence_word(pct: int | None) -> str:
    if pct is None:
        return "medium"
    if pct >= 75:
        return "high"
    if pct >= 50:
        return "medium"
    return "low"


def _insight_id(question_id: str, conclusion: str) -> str:
    blob = f"{question_id}|{conclusion}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_return_insight_payload(
    *,
    question: str,
    source_app: str,
    source_page: str = "",
    question_id: str = "",
    route: Any | None = None,
    result: Any | None = None,
    resume_key: str = "",
    full_analysis_url: str = "",
    context: dict[str, Any] | None = None,
) -> AppliedMathInsight:
    """Build display-only insight payload from a completed solve."""
    q = str(question or "").strip()
    app = str(source_app or "").strip().lower()
    page = str(source_page or "").strip()
    qid = str(question_id or "").strip()
    if not qid and q:
        try:
            from suite_analytical_question import question_id as make_qid

            qid = make_qid(q, source_app=app, source_page=page, context=context)
        except Exception:
            qid = hashlib.sha256(q.encode()).hexdigest()[:12]

    conclusion = ""
    method = ""
    model_name = ""
    math_summary = ""
    assumptions: list[str] = []
    confidence_pct: int | None = None
    key_numbers: dict[str, Any] = {}

    if result is not None:
        conclusion = str(getattr(result, "short_answer", "") or getattr(result, "conclusion", "") or "").strip()
        method = str(getattr(result, "math_idea", "") or getattr(result, "problem_type", "") or "").strip()
        model_name = str(getattr(result, "model_name", "") or "").strip()
        math_summary = str(getattr(result, "variables", "") or "").strip()[:400]
        assumptions = list(getattr(result, "assumptions", []) or [])[:6]
        confidence_pct = getattr(result, "confidence_pct", None)
        computed = getattr(result, "computed", None)
        live = getattr(result, "live_metrics", None)
        if isinstance(computed, dict):
            key_numbers.update({k: v for k, v in computed.items() if v is not None})
        if isinstance(live, dict):
            key_numbers.update({f"live_{k}": v for k, v in list(live.items())[:6]})

    if route is not None:
        if not model_name:
            model_name = str(getattr(route, "model_name", "") or getattr(route, "problem_type", "") or "").strip()
        if not method:
            method = str(getattr(route, "model_rationale", "") or method).strip()

    iid = _insight_id(qid, conclusion or q)
    return AppliedMathInsight(
        insight_id=iid,
        question_id=qid,
        question=q,
        source_app=app,
        source_page=page,
        conclusion=conclusion or "Analysis complete — open full analysis for details.",
        method=method or model_name or "Applied Math solver",
        model_name=model_name,
        math_summary=math_summary,
        assumptions=assumptions,
        confidence=_confidence_word(confidence_pct),
        confidence_pct=confidence_pct,
        key_numbers=key_numbers,
        full_analysis_url=full_analysis_url,
        created_at=datetime.now(timezone.utc).isoformat(),
        resume_key=str(resume_key or "").strip(),
    )


def build_applied_math_full_analysis_url(payload: dict[str, Any], *, base_url: str = "") -> str:
    """Deep link back into Applied Intelligence for the same question."""
    try:
        from suite_analytical_question import build_applied_math_resume_url

        return build_applied_math_resume_url(payload, base_url=base_url)
    except Exception:
        return ""


def metrics_for_source_app_return(insight: AppliedMathInsight | dict[str, Any]) -> dict[str, Any]:
    """Metrics bundle for return deep links."""
    data = insight.to_dict() if isinstance(insight, AppliedMathInsight) else dict(insight)
    ss = dict(data.get("source_state") or {})
    ctx = dict(data.get("return_context") or ss)
    ent = dict(ss.get("entity_params") or ctx.get("entity_params") or {})
    wp = dict(ss.get("widget_params") or ctx.get("widget_params") or {})
    chart = dict(ss.get("chart_params") or ctx.get("chart_params") or {})
    page = (
        data.get("source_page")
        or ss.get("source_page")
        or ctx.get("source_page")
        or ctx.get("page")
        or ss.get("page_params", {}).get("page")
        or ""
    )
    pa = (
        ent.get("player_a_label")
        or wp.get("sig_player_a_clean")
        or ctx.get("player_a")
        or ent.get("player_a")
    )
    pb = (
        ent.get("player_b_label")
        or wp.get("sig_player_b_clean")
        or ctx.get("player_b")
        or ent.get("player_b")
    )
    player = (
        ent.get("player_label")
        or wp.get("single_trend_dashboard_player")
        or ctx.get("player")
        or ent.get("player")
    )
    trend_players = ent.get("trend_players_multi") or chart.get("trend_players_multi")
    return {
        "page": page,
        "source_page": page,
        "player_a": pa,
        "player_b": pb,
        "player": player,
        "trend_players": trend_players,
        "team": ent.get("team") or ctx.get("team"),
        "opponent": ent.get("opponent") or ctx.get("opponent"),
        "tickers": ent.get("holdings") or ctx.get("holdings"),
        "holdings_fingerprint": ent.get("holdings_fingerprint") or ctx.get("holdings_fingerprint"),
        "ami_insight": data.get("insight_id") or "",
        "question_id": data.get("question_id") or "",
    }


def build_return_resume_key(
    insight: AppliedMathInsight | dict[str, Any],
    *,
    source_state: dict[str, Any] | None = None,
) -> str:
    """Prefer page-native resume keys (compare:/trend:) over ai:question: when possible."""
    data = insight.to_dict() if isinstance(insight, AppliedMathInsight) else dict(insight)
    app = str(data.get("source_app") or "").strip().lower()
    qid = str(data.get("question_id") or "").strip()
    ss = dict(source_state or data.get("source_state") or data.get("return_context") or {})
    page = str(ss.get("source_page") or data.get("source_page") or "").strip()
    ent = dict(ss.get("entity_params") or {})
    wp = dict(ss.get("widget_params") or {})

    if app == "baseball":
        if page == "Comparison Tool":
            pa = ent.get("player_a_label") or wp.get("sig_player_a_clean")
            pb = ent.get("player_b_label") or wp.get("sig_player_b_clean")
            if pa and pb:
                return f"compare:{pa}:{pb}"
        if page == "Trend Value":
            pl = ent.get("player_label") or wp.get("single_trend_dashboard_player")
            if pl:
                return f"trend:{pl}"
    if qid:
        return f"ai:question:{qid}"
    return str(data.get("resume_key") or "").strip()


def apply_return_source_state(st: Any, app_key: str, source_state: dict[str, Any] | None) -> None:
    """Apply stored page snapshot to source app session (pending keys + navigation)."""
    if not isinstance(source_state, dict) or not source_state:
        return
    ss = st.session_state
    ss[SESSION_RETURN_CONTEXT_KEY] = dict(source_state)
    page = str(
        source_state.get("source_page")
        or source_state.get("page_params", {}).get("page")
        or ""
    ).strip()
    app = str(app_key or source_state.get("source_app") or "").strip().lower()
    if page:
        ss[SESSION_RETURN_PAGE_KEY] = page
        if app == "investment":
            if insight_return_query_id(st):
                ss["_skip_page_restore_for"] = page
        else:
            ss["_skip_page_restore_for"] = page
    try:
        if app == "baseball":
            from applied_math_context import apply_source_state_to_session

            apply_source_state_to_session(ss, source_state)
        elif app == "nba":
            from applied_math_context import apply_source_state_to_session

            apply_source_state_to_session(ss, source_state)
        elif app == "investment":
            from applied_math_context import apply_source_state_to_session

            fp_before = _session_holdings_fingerprint(ss)
            apply_source_state_to_session(ss, source_state)
            fp_after = _session_holdings_fingerprint(ss)
            try:
                from investment_persistence_trace import record_ami_apply_trace

                record_ami_apply_trace(
                    st,
                    source_state=source_state,
                    success=True,
                    holdings_fp_before=fp_before,
                    holdings_fp_after=fp_after,
                )
            except Exception:
                pass
    except Exception as exc:
        if app == "investment":
            try:
                from investment_persistence_trace import record_ami_apply_trace

                record_ami_apply_trace(
                    st,
                    source_state=source_state,
                    success=False,
                    error=str(exc),
                    holdings_fp_before=_session_holdings_fingerprint(ss),
                    holdings_fp_after=_session_holdings_fingerprint(ss),
                )
            except Exception:
                pass
        log.warning("apply_return_source_state failed for %s: %s", app, exc)


def build_source_app_return_url(
    insight: AppliedMathInsight | dict[str, Any],
    *,
    resume_key: str = "",
    metrics: dict[str, Any] | None = None,
    base_url: str = "",
) -> str:
    """Build URL to return to source app with insight id in query params."""
    data = insight.to_dict() if isinstance(insight, AppliedMathInsight) else dict(insight)
    app = str(data.get("source_app") or "").strip().lower()
    if not app:
        return ""
    rk = str(resume_key or data.get("resume_key") or "").strip()
    m = dict(metrics or metrics_for_source_app_return(data))
    m["ami_insight"] = data.get("insight_id") or ""
    m["question_id"] = data.get("question_id") or ""
    m["page"] = data.get("source_page") or m.get("page") or ""
    try:
        from suite_deep_links import build_resume_action_url

        return build_resume_action_url(app, resume_key=rk, page=m.get("page", ""), metrics=m, base_url=base_url)
    except Exception as exc:
        log.warning("build_source_app_return_url failed: %s", exc)
        return ""


def store_applied_math_insight(
    insight: AppliedMathInsight | dict[str, Any],
    *,
    return_context: dict[str, Any] | None = None,
    source_state: dict[str, Any] | None = None,
) -> str:
    """Persist insight for retrieval on source app return."""
    data = insight.to_dict() if isinstance(insight, AppliedMathInsight) else dict(insight)
    iid = str(data.get("insight_id") or "").strip()
    if not iid:
        return ""
    blob = dict(data)
    rc = dict(return_context or source_state or data.get("return_context") or data.get("source_state") or {})
    ss = dict(source_state or data.get("source_state") or rc)
    if rc:
        blob["return_context"] = rc
    if ss:
        blob["source_state"] = ss
    try:
        from suite_account import remember_saved_item

        for store_app in (
            str(data.get("source_app") or "applied_intelligence"),
            "applied_intelligence",
            "investment",
        ):
            default_title = "Applied Math insight"
            if str(data.get("source_app") or "").strip().lower() == "investment":
                default_title = "Applied Investment Insight"
            remember_saved_item(
                store_app,
                INSIGHT_ITEM_TYPE,
                iid,
                title=str(data.get("conclusion") or default_title)[:120],
                payload=blob,
            )
    except Exception as exc:
        log.warning("remember_saved_item insight failed: %s", exc)
    try:
        from suite_activity_client import record_activity

        record_activity(
            str(data.get("source_app") or "unknown"),
            "applied_math_insight",
            page=str(data.get("source_page") or ""),
            metrics=blob,
            summary=str(data.get("conclusion") or "")[:200],
            resume_key=str(data.get("resume_key") or ""),
        )
    except Exception as exc:
        log.warning("record_activity insight failed: %s", exc)
    return iid


def load_applied_math_insight(insight_id: str, *, source_app: str = "") -> dict[str, Any]:
    """Load stored insight by id."""
    iid = str(insight_id or "").strip()
    if not iid:
        return {}
    app = str(source_app or "").strip()
    try:
        from suite_account import load_saved_items

        for app_key in ([app] if app else []) + [
            "applied_intelligence",
            "baseball",
            "nba",
            "investment",
        ]:
            rows = load_saved_items(app=app_key, item_type=INSIGHT_ITEM_TYPE, limit=80)
            for row in rows:
                if str(row.get("item_key") or "") == iid:
                    payload = row.get("payload")
                    if isinstance(payload, dict):
                        return dict(payload)
    except Exception as exc:
        log.warning("load_applied_math_insight failed: %s", exc)
    return {}


def _resolve_return_source_state(
    st: Any,
    app_key: str,
    insight: dict[str, Any],
    *,
    question_id_qp: str = "",
) -> dict[str, Any]:
    """Best-effort source_state from insight blob, return_context, or question send snapshot."""
    source_state = insight.get("source_state") or insight.get("return_context") or {}
    if isinstance(source_state, dict) and source_state.get("widget_params"):
        return dict(source_state)
    qid = str(insight.get("question_id") or question_id_qp or "").strip()
    if qid:
        try:
            from suite_analytical_question import load_analytical_question_source_state

            loaded = load_analytical_question_source_state(qid)
            if loaded:
                return dict(loaded)
        except Exception:
            pass
    return dict(source_state) if isinstance(source_state, dict) else {}


def commit_ami_return_page_restore(st: Any, app_key: str) -> bool:
    """
    After page navigation is committed, re-apply source_state once so widgets
    pick up pending_compare_players / trend labels before render.
    """
    flag = f"_ami_page_restore_committed_{app_key}"
    if st.session_state.get(flag):
        return False

    def _qp(name: str) -> str:
        try:
            raw = st.query_params.get(name)
        except Exception:
            return ""
        if raw is None:
            return ""
        if isinstance(raw, list):
            return str(raw[0] or "").strip()
        return str(raw).strip()

    iid = _qp("suite_ami_insight")
    if not iid:
        return False
    pending = st.session_state.get(SESSION_PENDING_KEY)

    insight = dict(pending) if isinstance(pending, dict) else {}
    if iid and not insight.get("insight_id"):
        loaded = load_applied_math_insight(iid, source_app=app_key)
        if loaded:
            insight = loaded
            st.session_state[SESSION_PENDING_KEY] = insight

    source_state = st.session_state.get(SESSION_RETURN_CONTEXT_KEY)
    if not isinstance(source_state, dict) or not source_state:
        source_state = _resolve_return_source_state(
            st,
            app_key,
            insight,
            question_id_qp=_qp("suite_ai_question_id"),
        )
    if isinstance(source_state, dict) and source_state:
        st.session_state[SESSION_RETURN_CONTEXT_KEY] = dict(source_state)
        apply_return_source_state(st, app_key, source_state)
        st.session_state[flag] = True
        mark_ami_return_resume_consumed(st, app_key)
        clear_ami_return_deferred_flags(st, app_key)
        return True
    return False


def stage_pending_insight(st: Any, insight: AppliedMathInsight | dict[str, Any], *, return_context: dict[str, Any] | None = None) -> None:
    """Write insight into Streamlit session for AMI return button."""
    data = insight.to_dict() if isinstance(insight, AppliedMathInsight) else dict(insight)
    st.session_state[SESSION_PENDING_KEY] = data
    source_page = _resolve_insight_source_page(data) or str(data.get("source_page") or "").strip()
    st.session_state[SESSION_RETURN_PAGE_KEY] = source_page
    if return_context:
        st.session_state[SESSION_RETURN_CONTEXT_KEY] = dict(return_context)
    app = str(data.get("source_app") or "").strip().lower()
    if app == "investment":
        _sync_investment_insight_tab_keys(st, app, insight=data)


def apply_ami_insight_from_query(st: Any, app_key: str) -> bool:
    """On source app load: hydrate pending insight from ?suite_ami_insight= (cloud-backed)."""

    def _qp(name: str) -> str:
        try:
            raw = st.query_params.get(name)
        except Exception:
            return ""
        if raw is None:
            return ""
        if isinstance(raw, list):
            return str(raw[0] or "").strip()
        return str(raw).strip()

    iid = _qp("suite_ami_insight")
    if not iid:
        return False

    prev = str(st.session_state.get("_ami_hydrated_insight_id") or "").strip()
    if prev == iid and isinstance(st.session_state.get(SESSION_PENDING_KEY), dict):
        return False

    insight = load_applied_math_insight(iid, source_app=app_key)
    if not insight:
        placeholder = (
            "Applied Investment Insight loaded."
            if str(app_key or "").strip().lower() == "investment"
            else "Applied Math insight loaded."
        )
        insight = {"insight_id": iid, "conclusion": placeholder, "question": "", "source_app": app_key}

    st.session_state[SESSION_PENDING_KEY] = insight
    st.session_state[SESSION_RETURN_PAGE_KEY] = (
        _query_param(st, "suite_page") or _resolve_insight_source_page(insight) or insight.get("source_page") or ""
    )

    source_state = _resolve_return_source_state(
        st,
        app_key,
        insight if isinstance(insight, dict) else {},
        question_id_qp=_qp("suite_ai_question_id"),
    )

    if isinstance(source_state, dict) and source_state:
        st.session_state[SESSION_RETURN_CONTEXT_KEY] = dict(source_state)
        apply_return_source_state(st, app_key, source_state)
        if str(app_key or "").strip().lower() == "investment":
            try:
                from investment_persistence_trace import record_ami_return_hydrate_trace

                record_ami_return_hydrate_trace(st, source_state=source_state, insight_id=iid)
            except Exception:
                pass
    elif st.session_state.get(SESSION_RETURN_PAGE_KEY):
        page = st.session_state[SESSION_RETURN_PAGE_KEY]
        st.session_state["_navigate_to_page"] = page
        if insight_return_query_id(st):
            st.session_state["_skip_page_restore_for"] = page

    st.session_state["_ami_hydrated_insight_id"] = iid
    if str(app_key or "").strip().lower() == "investment":
        _sync_investment_insight_tab_keys(st, app_key, insight=insight if isinstance(insight, dict) else {})
        try:
            from investment_persistent_state import notify_pending_insight_change

            notify_pending_insight_change(st, source="insight_hydrate")
        except Exception:
            pass
    return True


def clear_pending_insight(st: Any) -> None:
    st.session_state.pop(SESSION_PENDING_KEY, None)
    st.session_state.pop(SESSION_RETURN_PAGE_KEY, None)
    st.session_state.pop(SESSION_RETURN_CONTEXT_KEY, None)


def render_applied_math_insight_panel(
    st: Any,
    *,
    source_app: str = "",
    insight: dict[str, Any] | None = None,
) -> bool:
    """Display-only insight card on source app pages. Returns True if rendered."""
    data = insight if isinstance(insight, dict) else st.session_state.get(SESSION_PENDING_KEY)
    if not isinstance(data, dict) or not data.get("conclusion"):
        return False
    app = str(source_app or data.get("source_app") or "").strip().lower()

    with st.container(border=True):
        st.markdown(f"#### {_insight_panel_title(app, data)}")
        q = str(data.get("question") or "").strip()
        if q:
            st.markdown(f"**Question:** *{q}*")
        st.markdown(f"**Conclusion:** {data.get('conclusion')}")
        method = str(data.get("method") or data.get("model_name") or "").strip()
        if method:
            st.markdown(f"**Math used:** {method}")
        assumptions = data.get("assumptions") or []
        if assumptions:
            st.markdown("**Assumptions:**")
            for a in assumptions[:4]:
                st.markdown(f"- {a}")
        conf = data.get("confidence")
        if conf:
            extra = f" ({data.get('confidence_pct')}%)" if data.get("confidence_pct") else ""
            st.caption(f"Confidence: **{conf}**{extra}")
        url = str(data.get("full_analysis_url") or "").strip()
        c1, c2 = st.columns(2)
        with c1:
            if url:
                st.link_button("Open full analysis →", url, use_container_width=True)
        with c2:
            if st.button("Dismiss insight", key="ami_insight_dismiss", use_container_width=True):
                clear_pending_insight(st)
                st.rerun()
    return True


def render_suite_applied_math_insight_for_page(
    st: Any,
    *,
    source_app: str,
    source_page: str,
) -> bool:
    """Render insight card when pending insight matches this page (source apps)."""
    app = str(source_app or "").strip().lower()
    if app == "investment":
        hydrate_applied_math_insight_for_session(st, app)

    insight = st.session_state.get(SESSION_PENDING_KEY)
    pending_exists = isinstance(insight, dict) and bool(insight.get("conclusion") or insight.get("question"))
    cloud_exists = insight_exists_in_cloud(app) if app == "investment" else False
    scope = (
        insight_page_scope_decision(app, source_page, insight)
        if isinstance(insight, dict) and pending_exists
        else {"should_render_insight_on_page": False, "render_skip_reason": "no_pending_insight"}
    )
    should_render = bool(scope.get("should_render_insight_on_page"))
    skip_reason = str(scope.get("render_skip_reason") or "")

    if app == "investment":
        _sync_investment_insight_tab_keys(st, app, insight=insight if isinstance(insight, dict) else None)
        try:
            from investment_persistence_trace import record_insight_card_trace

            record_insight_card_trace(
                st,
                insight_exists_cloud=cloud_exists,
                pending_insight_exists=pending_exists,
                insight_card_rendered=should_render,
                insight_render_skipped_reason=skip_reason or None,
                insight_source_tab=scope.get("insight_source_tab")
                or st.session_state.get(SESSION_INSIGHT_SOURCE_TAB_KEY),
                current_investment_tab=str(st.session_state.get("investment_active_tab") or source_page),
                source_investment_tab=st.session_state.get(SESSION_SOURCE_INVESTMENT_TAB_KEY),
                insight_hydrate_attempted=bool(st.session_state.get("_ami_insight_hydrate_attempted")),
                insight_hydrate_success=bool(st.session_state.get("_ami_insight_hydrate_success")),
                insight_hydrate_source=st.session_state.get("_ami_insight_hydrate_source"),
            )
        except Exception:
            pass

    if not pending_exists:
        return False
    if not should_render:
        return False
    rendered = render_applied_math_insight_panel(st, source_app=app, insight=insight)
    if rendered and app == "investment":
        st.session_state["_ami_insight_card_rendered"] = True
        try:
            from suite_cloud_state import _ami_resume_consumed_flag

            st.session_state[_ami_resume_consumed_flag(app)] = True
        except Exception:
            pass
    return rendered


def render_return_to_source_button(
    st: Any,
    insight: AppliedMathInsight | dict[str, Any],
    *,
    resume_key: str = "",
    return_context: dict[str, Any] | None = None,
    source_state: dict[str, Any] | None = None,
) -> None:
    """AMI button: return insight to originating source app."""
    data = insight.to_dict() if isinstance(insight, AppliedMathInsight) else dict(insight)
    app = str(data.get("source_app") or "").strip().lower()
    if not app or app in ("unknown", "applied_intelligence", "math"):
        return

    try:
        from suite_analytical_question import source_app_label
    except Exception:
        source_app_label = lambda x: x  # noqa: E731

    label = source_app_label(app)

    ss = dict(source_state or {})
    if not ss:
        try:
            ss = dict(st.session_state.get("_suite_ai_source_state") or {})
        except Exception:
            ss = {}
    if not ss and return_context and isinstance(return_context.get("widget_params"), dict):
        ss = dict(return_context)
    if not ss and return_context:
        ss = {
            "source_app": app,
            "source_page": data.get("source_page") or return_context.get("page") or "",
            "entity_params": {
                k: v
                for k, v in return_context.items()
                if k in ("player_a", "player_b", "player", "team", "opponent", "holdings")
            },
            "widget_params": {},
            "page_params": {"page": data.get("source_page") or return_context.get("page") or ""},
        }
    qid = str(data.get("question_id") or "").strip()
    if qid and not ss:
        try:
            from suite_analytical_question import load_analytical_question_source_state

            ss = load_analytical_question_source_state(qid)
        except Exception:
            pass

    blob_data = dict(data)
    if ss:
        blob_data["source_state"] = ss
        blob_data["return_context"] = ss

    rk = str(resume_key or build_return_resume_key(blob_data, source_state=ss) or "").strip()
    store_applied_math_insight(blob_data, return_context=ss or return_context, source_state=ss)
    url = build_source_app_return_url(
        blob_data,
        resume_key=rk,
        metrics=metrics_for_source_app_return({**blob_data, "source_state": ss, "return_context": ss or {}}),
    )
    if not url:
        st.caption(f"Return link unavailable for {label}.")
        return

    st.link_button(
        f"Return to {label} with insight →",
        url,
        use_container_width=True,
        help="Restores your page context and shows this conclusion in the source app — display only, no auto-changes.",
    )
