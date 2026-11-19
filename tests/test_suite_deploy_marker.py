"""The deploy marker resolves a commit and is stamped (hidden) on the sign-in page."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import suite_deploy_marker as marker


def test_commit_prefers_env_and_is_short() -> None:
    marker.resolve_git_commit_short.cache_clear()
    try:
        with patch.dict("os.environ", {"GITHUB_SHA": "0123456789abcdef"}), patch.object(
            marker, "_DEPLOY_COMMIT_FILE", marker._ROOT / "no-such-deploy-file.txt"
        ):
            assert marker.resolve_git_commit_short() == "0123456"
    finally:
        marker.resolve_git_commit_short.cache_clear()


def test_sign_in_page_carries_hidden_build_and_commit() -> None:
    from suite_auth import _render_hidden_deploy_marker

    st = MagicMock()
    with patch("suite_deploy_marker.resolve_git_commit_short", return_value="abc1234"):
        _render_hidden_deploy_marker(st)
    html = st.markdown.call_args[0][0]
    assert html.startswith("<span hidden ")
    assert 'data-suite-deploy-commit="abc1234"' in html
    assert f'data-suite-deploy-build="{marker.INVESTMENT_DEPLOY_BUILD}"' in html
    assert st.markdown.call_args.kwargs.get("unsafe_allow_html") is True
