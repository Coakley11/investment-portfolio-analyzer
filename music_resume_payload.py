"""
Music Continue resume envelope helpers (suite-wide).

Used by ``suite_deep_links.build_music_continue_url`` for base64url JSON payloads.
Investment and other apps import this module only indirectly via ``suite_deep_links``;
it must live on the Python path alongside suite modules.
"""

from __future__ import annotations

import base64
import json
from typing import Any

_KNOWN_KINDS = frozenset(
    {
        "practice",
        "backing",
        "creative",
        "multitrack",
        "tone",
        "analysis",
        "recording",
        "openai",
    }
)

_KIND_ALIASES: dict[str, str] = {
    "backing_track": "backing",
    "backing track": "backing",
    "song": "practice",
    "practice_studio": "practice",
    "recording_analysis": "analysis",
    "upload_analysis": "analysis",
}


def normalize_resume_kind(raw: str) -> str:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return "practice"
    text = _KIND_ALIASES.get(text, text)
    if text in _KNOWN_KINDS:
        return text
    return "practice"


def legacy_resume_key_for_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    explicit = str(payload.get("resume_key") or payload.get("suite_resume") or "").strip()
    if explicit:
        return explicit
    pick = str(payload.get("pick_key") or "").strip()
    kind = normalize_resume_kind(str(payload.get("resume_kind") or ""))
    if kind == "backing":
        return f"backing:{pick}" if pick else "backing:"
    if pick:
        return f"song:{pick}"
    return ""


def encode_payload_b64(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def decode_payload_b64(encoded: str) -> dict[str, Any]:
    text = str(encoded or "").strip()
    if not text:
        return {}
    padding = "=" * (-len(text) % 4)
    try:
        raw = base64.urlsafe_b64decode(text + padding)
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}
