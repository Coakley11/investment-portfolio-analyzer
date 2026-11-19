"""Deploy marker — the deployed commit, resolved at runtime (never hardcoded).

Same lookup order as the Command Center / Baseball Explorer copies of this module.
Already imported (optionally) by My Portfolio's caption, the AMI context and the
workspace diagnostics; it was missing from this repo, so they showed "unknown".
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DEPLOY_COMMIT_FILE = _ROOT / "deploy_commit.txt"

# Static label for this release; visible even where git metadata is unavailable.
INVESTMENT_DEPLOY_BUILD = "2026-11-19-account-isolation-sidebar"

_ENV_COMMIT_KEYS = (
    "STREAMLIT_CLOUD_COMMIT",
    "SOURCE_VERSION",
    "COMMIT_SHA",
    "GIT_COMMIT",
    "GITHUB_SHA",
)
_ENV_BRANCH_KEYS = ("STREAMLIT_CLOUD_BRANCH", "GITHUB_REF_NAME", "GIT_BRANCH")


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=_ROOT, stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
    except Exception:
        return ""


def _head_from_git_dir() -> str:
    """Read .git/HEAD directly when the git binary is not installed."""
    git_dir = _ROOT / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_file = git_dir / ref
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip()
            packed = git_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split(" ", 1)[0]
            return ""
        return head
    except Exception:
        return ""


@lru_cache(maxsize=1)
def resolve_git_commit_short() -> str:
    """Best-effort short SHA of the deployed revision."""
    if _DEPLOY_COMMIT_FILE.is_file():
        for line in _DEPLOY_COMMIT_FILE.read_text(encoding="utf-8").splitlines():
            token = line.strip().split("#", 1)[0].strip()
            if token and token.lower() != "unknown":
                return token[:7]
    for key in _ENV_COMMIT_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            return val[:7]
    sha = _git("rev-parse", "--short", "HEAD") or _head_from_git_dir()[:7]
    return sha or "unknown"


@lru_cache(maxsize=1)
def resolve_git_branch() -> str:
    for key in _ENV_BRANCH_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            return val.replace("refs/heads/", "")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    return branch or "unknown"
