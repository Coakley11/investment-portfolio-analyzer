"""Resilient loader for ``components.macro_engine`` (Streamlit Cloud safe).

Streamlit Cloud partial reloads can leave a stale ``components.macro_engine`` in
``sys.modules`` that predates newly added exports. A plain

    from components.macro_engine import ensure_shared_macro_session_defaults

then raises ``ImportError: cannot import name '...'`` even though the file on
disk defines the symbol. Always load via ``load_macro_engine()`` from app entry.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

# Symbols imported by streamlit_app.py — keep in sync with that entrypoint.
STREAMLIT_APP_MACRO_ENGINE_EXPORTS: tuple[str, ...] = (
    "get_forward_projection",
    "health_settings_fingerprint",
    "macro_assumption_summary",
    "macro_assumptions_from_session",
    "ensure_shared_macro_session_defaults",
    "render_shared_macro_assumption_controls",
)

_MODULE_NAME = "components.macro_engine"


def load_macro_engine(
    required_exports: tuple[str, ...] = STREAMLIT_APP_MACRO_ENGINE_EXPORTS,
) -> ModuleType:
    """Import macro_engine, reloading if required exports are missing from a stale module."""
    mod = sys.modules.get(_MODULE_NAME)
    if mod is None:
        mod = importlib.import_module(_MODULE_NAME)
    if any(not hasattr(mod, name) for name in required_exports):
        mod = importlib.reload(mod)
    missing = [name for name in required_exports if not hasattr(mod, name)]
    if missing:
        raise ImportError(
            f"cannot import name {missing[0]!r} from {_MODULE_NAME} "
            f"(missing after reload: {missing})"
        )
    return mod
