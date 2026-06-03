"""
Cloud storage shim for standalone Streamlit Cloud deploys.

The full ``suite_storage`` module (SQLite + cloud) lives in daniel-ai-command-center.
This app re-exports ``suite_storage_supabase`` so ``import suite_storage`` works without
a sibling monorepo checkout on the container filesystem.
"""

from __future__ import annotations

from suite_storage_supabase import *  # noqa: F403
