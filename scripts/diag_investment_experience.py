#!/usr/bin/env python3
"""
Read-only Investment experience-mode persistence diagnostics.

Prints local disk blob, Supabase metrics.full_session (if configured),
account ids, and the exact experience-related JSON keys.

Usage (from investment-portfolio-analyzer repo root):
  python scripts/diag_investment_experience.py

Requires [suite_activity] in .streamlit/secrets.toml or SUITE_SUPABASE_* env vars
to query cloud. Local disk is always read from data/investment_user_state.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP_ID = "investment"
FULL_SESSION_KEY = "full_session"
EXPERIENCE_KEYS = ("experience", "_suite_persisted_experience", "health_active_tab", "investment_active_tab")


def _pick_experience(blob: dict) -> dict[str, object]:
    return {k: blob.get(k) for k in EXPERIENCE_KEYS if k in blob}


def _load_local_disk() -> tuple[dict, str | None]:
    from suite_user_persistence import load_user_state

    state, _warn = load_user_state(APP_ID)
    path = ROOT / "data" / "investment_user_state.json"
    saved_at = None
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            saved_at = str(raw.get("saved_at") or "")
        except (OSError, json.JSONDecodeError):
            pass
    return state, saved_at


def main() -> int:
    from suite_cloud_state import FULL_SESSION_KEY as FS_KEY, load_cloud_full_session, pick_newer_session
    from suite_storage_config import cloud_storage_enabled, probe_secrets
    from suite_user import (
        account_mode,
        get_account_user_id,
        get_display_name,
        get_external_user_id,
        get_user_email,
    )

    print("=" * 72)
    print("Investment experience-mode persistence diagnostics (read-only)")
    print("=" * 72)

    print("\n--- Account / user scope ---")
    print(f"  suite_user_id (secrets):  {get_external_user_id()!r}")
    print(f"  suite_user_email:         {get_user_email()!r}")
    print(f"  display_name:             {get_display_name()!r}")
    print(f"  account_mode:             {account_mode()}")
    print(f"  account_user_id (UUID):   {get_account_user_id()!r}")
    print("  (Phone and Dell must resolve the SAME suite_user_id and account_user_id.)")

    probe = probe_secrets()
    print("\n--- Supabase config ---")
    print(f"  cloud enabled:            {cloud_storage_enabled()}")
    print(f"  secrets source:           {probe.resolved_source}")
    if probe.secrets_error:
        print(f"  secrets note:             {probe.secrets_error}")

    disk_state, disk_ts = _load_local_disk()
    print("\n--- Local disk blob (data/investment_user_state.json) ---")
    print(f"  saved_at:                 {disk_ts or '—'}")
    print(f"  disk experience fields:   {json.dumps(_pick_experience(disk_state), ensure_ascii=False)}")
    if disk_state:
        print(f"  disk experience:          {disk_state.get('experience')!r}")

    cloud_state: dict = {}
    cloud_ts: str | None = None
    cloud_err = ""
    if cloud_storage_enabled():
        try:
            cloud_state, cloud_ts = load_cloud_full_session(APP_ID)
        except Exception as exc:
            cloud_err = str(exc)
    else:
        cloud_err = "Cloud not configured in this environment."

    print("\n--- Supabase metrics.full_session (investment row) ---")
    if cloud_err:
        print(f"  error:                    {cloud_err}")
    else:
        print(f"  updated_at:               {cloud_ts or '—'}")
        if not cloud_state:
            print("  full_session:             EMPTY or missing")
        else:
            print(f"  full_session experience:  {cloud_state.get('experience')!r}")
            print(f"  experience keys:          {json.dumps(_pick_experience(cloud_state), ensure_ascii=False, indent=2)}")
            # Exact keys written by build_investment_disk_state
            snippet = {
                "experience": cloud_state.get("experience"),
                "_suite_persisted_experience": cloud_state.get("_suite_persisted_experience"),
            }
            print(f"  exact save JSON snippet:  {json.dumps(snippet, ensure_ascii=False)}")

        try:
            import suite_storage as storage

            row = storage.load_current_states().get("investment") or {}
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            has_fs = isinstance(metrics.get(FS_KEY), dict)
            print(f"  metrics.full_session present: {has_fs}")
            if has_fs:
                fs = metrics[FS_KEY]
                print(f"  metrics['full_session']['experience']: {fs.get('experience')!r}")
        except Exception as exc:
            print(f"  raw row load error:       {exc}")

    picked = pick_newer_session(cloud_state, cloud_ts, disk_state, disk_ts)
    picked_exp = picked.get("experience") if picked else None
    print("\n--- pick_newer_session (what restore uses) ---")
    print(f"  picked source:            {'cloud' if picked is cloud_state and cloud_state else 'disk' if picked is disk_state and disk_state else 'none'}")
    print(f"  picked experience:        {picked_exp!r}")

    print("\n--- In-app debug panel (on phone / Dell Streamlit UI) ---")
    print("  Sidebar -> 'Cloud persistence debug (after init)' -> Experience mode trace:")
    print("    cloud blob / disk blob / picked blob / after restore / saved to cloud / after init")
    print("  Copy those six lines from EACH device after your test and compare.")

    print("\n--- Compare Baseball/Music (same Supabase table) ---")
    if cloud_storage_enabled():
        try:
            import suite_storage as storage

            states = storage.load_current_states()
            for app in ("baseball", "music", "investment"):
                row = states.get(app) or {}
                fs = (row.get("metrics") or {}).get(FS_KEY) if isinstance(row.get("metrics"), dict) else None
                preview = ""
                if isinstance(fs, dict):
                    if app == "baseball":
                        preview = f"active_page={fs.get('active_page')!r}"
                    elif app == "music":
                        core = fs.get("core") if isinstance(fs.get("core"), dict) else fs
                        preview = f"studio_page={core.get('studio_page')!r}" if isinstance(core, dict) else "?"
                    else:
                        preview = f"experience={fs.get('experience')!r}"
                print(f"  {app}: updated={row.get('updated_at')!r} {preview}")
        except Exception as exc:
            print(f"  compare error: {exc}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
