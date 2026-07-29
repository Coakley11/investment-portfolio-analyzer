"""Feature flag and configuration for Phase 4 analytical synthesis."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


SYNTHESIS_FLAG_ENV = "INVESTMENT_AMI_ANALYTICAL_SYNTHESIS"
SYNTHESIS_MODEL_ENV = "INVESTMENT_AMI_SYNTHESIS_MODEL"
SYNTHESIS_MOCK_ENV = "INVESTMENT_AMI_SYNTHESIS_MOCK"
DEFAULT_SYNTHESIS_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SEC = 90


@dataclass(frozen=True)
class SynthesisConfig:
    enabled: bool
    flag_source: str
    model: str
    mock_mode: bool
    timeout_sec: int = DEFAULT_TIMEOUT_SEC


def _secrets_openai_api_key() -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            block = st.secrets.get("openai")
            if isinstance(block, dict) and block.get("api_key"):
                return str(block["api_key"]).strip()
            direct = st.secrets.get("OPENAI_API_KEY")
            if direct:
                return str(direct).strip()
    except Exception:
        pass
    return ""


def openai_api_key() -> str:
    return str(os.environ.get("OPENAI_API_KEY") or _secrets_openai_api_key() or "").strip()


def analytical_synthesis_config() -> SynthesisConfig:
    mock = str(os.environ.get(SYNTHESIS_MOCK_ENV) or "").strip().lower() in ("1", "true", "yes")
    model = str(os.environ.get(SYNTHESIS_MODEL_ENV) or DEFAULT_SYNTHESIS_MODEL).strip()

    env_flag = str(os.environ.get(SYNTHESIS_FLAG_ENV) or "").strip().lower()
    if env_flag in ("1", "true", "yes", "on"):
        return SynthesisConfig(enabled=True, flag_source="env", model=model, mock_mode=mock)
    if env_flag in ("0", "false", "no", "off"):
        return SynthesisConfig(enabled=False, flag_source="env", model=model, mock_mode=mock)

    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            sec = st.secrets.get(SYNTHESIS_FLAG_ENV) or st.secrets.get("investment_ami_analytical_synthesis")
            if str(sec or "").strip().lower() in ("1", "true", "yes", "on"):
                return SynthesisConfig(enabled=True, flag_source="secrets", model=model, mock_mode=mock)
    except Exception:
        pass

    # Enabled when explicitly flagged and API key present (or mock).
    if mock:
        return SynthesisConfig(enabled=True, flag_source="mock_env", model=model, mock_mode=True)
    if openai_api_key() and env_flag == "":
        return SynthesisConfig(enabled=False, flag_source="default_off", model=model, mock_mode=False)

    return SynthesisConfig(enabled=False, flag_source="default_off", model=model, mock_mode=mock)


def analytical_synthesis_enabled() -> bool:
    return analytical_synthesis_config().enabled
