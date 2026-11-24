"""Load the current auth modules after an in-place Streamlit Cloud pull (security hotfix 2026-11-23).

Streamlit Community Cloud pulls a push into the running container without restarting Python. The main
script is re-read from disk on the next run, but modules it already imported stay loaded from the
previous release (``sys.modules``). The suite_sid fix lives in ``suite_auth_browser`` and
``suite_storage_supabase``, so a process that loaded them before the fix would keep the old behaviour
until a reboot.

``refresh_pre_fix_modules()`` runs first in the entry script. When the loaded ``suite_auth_browser`` is
a pre-fix copy (it has no ``url_auth_restore_enabled``), every module loaded from this app's directory
is dropped from ``sys.modules`` so the following imports load the files on disk, as a restart would.
Otherwise it does nothing. It never raises.
"""

from __future__ import annotations

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FIX_MARKER = ("suite_auth_browser", "url_auth_restore_enabled")
DROPPED: list[str] = []  # names dropped in this process (diagnostics)


def pre_fix_auth_loaded() -> bool:
    """True when the process holds a ``suite_auth_browser`` loaded before the fix."""
    module = sys.modules.get(FIX_MARKER[0])
    return module is not None and not hasattr(module, FIX_MARKER[1])


def app_module_names(app_dir: str = APP_DIR) -> list[str]:
    """Loaded modules whose file is inside ``app_dir`` (never third-party packages)."""
    root = os.path.abspath(app_dir) + os.sep
    out: list[str] = []
    for name, module in list(sys.modules.items()):
        if name in ("__main__", __name__) or module is None:
            continue
        path = getattr(module, "__file__", None)
        if not path or not str(path).endswith(".py"):
            continue
        path = os.path.abspath(str(path))
        if path.startswith(root) and "site-packages" not in path:
            out.append(name)
    return out


def refresh_pre_fix_modules(app_dir: str = APP_DIR) -> list[str]:
    """Drop this app's modules when a pre-fix auth module is loaded; returns the dropped names."""
    try:
        if not pre_fix_auth_loaded():
            return []
        names = app_module_names(app_dir)
        for name in names:
            sys.modules.pop(name, None)
        DROPPED.extend(names)
        return names
    except Exception:
        return []
