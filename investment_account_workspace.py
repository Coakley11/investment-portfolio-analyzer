"""
Investment Account & Workspace — single sidebar entry point.

Copies Music/suite Account & Workspace conventions (label
``Account & Workspace · {label}``, expander key ``suite_account_workspace_expander``,
logout key, Saved Session reset confirm keys, Command Center URL helper) and nests
the Command Center logo + Saved Sessions + Log Out inside that one control so Investment
no longer shows redundant top-level suite chrome. Layout follows Baseball Explorer.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ("render_investment_account_workspace_control",)

_APP_ID = "investment"


def _signed_in_email(ctx: dict[str, Any], session_state: dict[str, Any]) -> str:
    """Mirror suite_account_settings._signed_in_email without importing a private helper."""
    try:
        from suite_auth import current_auth_email, is_auth_enabled, is_authenticated

        if is_auth_enabled() and is_authenticated(session_state):
            email = str(current_auth_email(session_state) or "").strip()
            if email:
                return email
    except ImportError:
        pass
    email = str(ctx.get("email_display") or "").strip()
    if email and email != "(not configured — set suite_user_email in secrets)":
        return email
    return ""


# Investment theme (.streamlit/config.toml): border on the dark sidebar, primary blue focus ring.
_CC_LOGO_BORDER = "#5b6b82"
_CC_LOGO_FOCUS = "#4da3ff"
LOG_OUT_ICON = ":material/logout:"


class _StyledMarkdown:
    """Markdown target that sends the logo's style with the logo in one element (no extra gap)."""

    def __init__(self, st: Any, css: str) -> None:
        self._st = st
        self._css = css

    def markdown(self, body: str, **kwargs: Any) -> Any:
        return self._st.markdown(self._css + body, **kwargs)


def _command_center_href(st: Any) -> str:
    try:
        from suite_command_center_link import command_center_url
        from suite_workspace import get_active_workspace_id

        return command_center_url(workspace_id=get_active_workspace_id(st))
    except Exception:
        try:
            from suite_command_center_link import command_center_url

            return command_center_url()
        except Exception:
            return ""


def _workspace_label(ctx: dict[str, Any]) -> str:
    return str(ctx.get("active_workspace_label") or "Workspace").strip() or "Workspace"


def _auth_session_active(session_state: dict[str, Any]) -> bool:
    try:
        from suite_auth import is_auth_enabled, is_authenticated

        return bool(is_auth_enabled() and is_authenticated(session_state))
    except ImportError:
        return False


def _render_command_center_entry(st: Any) -> None:
    """The approved Command Center logo as the control itself (Baseball Explorer parity).

    No heading or text label: the logo opens Command Center (same URL, new tab, as the
    former "← Command Center" button) and carries a tooltip and an accessible name.
    """
    url = _command_center_href(st)
    if not url:
        return
    shown = False
    try:
        from suite_brand_assets import command_center_logo_css, render_command_center_logo_link

        shown = render_command_center_logo_link(
            _StyledMarkdown(st, command_center_logo_css(border=_CC_LOGO_BORDER, focus=_CC_LOGO_FOCUS)),
            url,
            name="Open Command Center",
        )
    except ImportError:
        shown = False
    if not shown:
        # Artwork unavailable on this deploy: keep navigation working with a labelled button.
        st.link_button("Command Center", url, help="Open Command Center")


def _render_saved_sessions_section(
    st: Any,
    app_id: str,
    *,
    on_reset: Callable[[Any], None],
    label: str = "Reset to default",
    help_text: str = "Clears your saved session for this app only.",
) -> None:
    """Inline Saved Sessions controls (same keys/behavior as suite render_reset_controls)."""
    from suite_user_persistence import (
        clear_reset_confirm_state,
        execute_suite_reset,
        request_reset_confirm_state,
        reset_confirm_session_key,
    )

    pending = bool(st.session_state.get(reset_confirm_session_key(app_id)))
    st.markdown("**Saved Sessions**")
    st.caption("Your last page, filters, and inputs reload automatically.")
    if pending:
        st.warning("This clears saved preferences for this app. Continue?")
        c1, c2 = st.columns(2)
        with c1:
            st.button(
                "Yes, reset",
                key=f"suite_reset_yes::{app_id}",
                type="primary",
                on_click=execute_suite_reset,
                kwargs={
                    "st": st,
                    "app_id": app_id,
                    "on_reset": on_reset,
                },
            )
        with c2:
            st.button(
                "Cancel",
                key=f"suite_reset_no::{app_id}",
                on_click=clear_reset_confirm_state,
                kwargs={"session_state": st.session_state, "app_id": app_id},
            )
    else:
        st.button(
            label,
            key=f"suite_reset_btn::{app_id}",
            help=help_text,
            on_click=request_reset_confirm_state,
            kwargs={"session_state": st.session_state, "app_id": app_id},
        )


def _render_logout_entry(st: Any, session_state: dict[str, Any]) -> None:
    try:
        from suite_auth import is_auth_enabled, is_authenticated, logout

        if is_auth_enabled() and is_authenticated(session_state):
            if st.button(
                "Log out",
                key="suite_account_workspace_logout_btn",
                icon=LOG_OUT_ICON,
                use_container_width=True,
            ):
                logout(session_state, st=st)
                st.rerun()
    except ImportError:
        pass


def _render_consolidated_body(
    st: Any,
    session_state: dict[str, Any],
    ctx: dict[str, Any],
    *,
    app_id: str,
    on_reset: Callable[[Any], None],
    reset_label: str,
    reset_help: str,
) -> None:
    """Inside Account & Workspace (suite order, as Baseball Explorer / Music Practice Coach):
    Command Center logo → identity + workspace → Saved Sessions → Log out."""
    _render_command_center_entry(st)
    email = _signed_in_email(ctx, session_state)
    if email:
        st.markdown(f"Signed in as **{email}**")
    else:
        st.caption("Shared suite profile (no individual sign-in on this deploy).")
    st.caption(f"Workspace: **{_workspace_label(ctx)}**")
    st.divider()
    _render_saved_sessions_section(
        st,
        app_id,
        on_reset=on_reset,
        label=reset_label,
        help_text=reset_help,
    )
    # Log out sits in its own section below Saved Sessions so it never reads as part of
    # "Reset to default". The divider appears only when a Log out button follows it.
    if _auth_session_active(session_state):
        st.divider()
        _render_logout_entry(st, session_state)


def render_investment_account_workspace_control(
    st: Any,
    *,
    app_id: str = _APP_ID,
    on_reset: Callable[[Any], None] | None = None,
    reset_label: str = "Reset to default",
    reset_help: str = (
        "Clears saved portfolio, workflow progress, local disk, and cloud session for this app."
    ),
) -> None:
    """
    Single top-level Account & Workspace control for Investment.

    Reuses Music/suite naming, expander/logout/reset keys so auth and persistence
    behavior stay intact while consolidating previously separate top chrome.
    """
    try:
        from suite_workspace import bootstrap_suite_workspace

        bootstrap_suite_workspace(st)
    except ImportError:
        pass

    try:
        from suite_workspace import can_show_developer_tools

        if can_show_developer_tools(st=st):
            try:
                from suite_app_shell import render_suite_namespace_notices

                render_suite_namespace_notices(st)
            except ImportError:
                pass
    except ImportError:
        pass

    try:
        from suite_account_settings import (
            account_workspace_expander_label,
            build_account_settings_context,
            init_suite_workspace,
            render_account_settings_panel,
        )
    except ImportError:
        st.sidebar.caption("Account settings module unavailable on this deploy.")
        return

    if on_reset is None:

        def on_reset(_st: Any) -> None:
            return None

    init_suite_workspace(st)
    ctx = build_account_settings_context(st=st)

    try:
        from suite_auth import is_auth_enabled, is_authenticated, render_auth_panel

        auth_on = is_auth_enabled()
        signed_in = is_authenticated(st.session_state)
    except ImportError:
        auth_on = False
        signed_in = True

    if auth_on and not signed_in:
        st.sidebar.info("Sign in to sync your suite data across devices.")
        render_auth_panel(st, expanded=True)
        return

    dev_mode = False
    try:
        from suite_workspace import can_show_developer_tools

        dev_mode = can_show_developer_tools(st=st)
    except ImportError:
        pass

    if dev_mode:
        # Music uses the full diagnostics panel in developer mode; keep that parity,
        # then expose Command Center + Saved Sessions + Log out in one navigation block.
        render_account_settings_panel(st, expanded=True, show_title=True, sidebar=True)
        with st.sidebar.expander("Suite navigation (dev)", expanded=True):
            _render_consolidated_body(
                st,
                st.session_state,
                ctx,
                app_id=app_id,
                on_reset=on_reset,
                reset_label=reset_label,
                reset_help=reset_help,
            )
        return

    header = account_workspace_expander_label(ctx)
    with st.sidebar.expander(header, expanded=False, key="suite_account_workspace_expander"):
        _render_consolidated_body(
            st,
            st.session_state,
            ctx,
            app_id=app_id,
            on_reset=on_reset,
            reset_label=reset_label,
            reset_help=reset_help,
        )
