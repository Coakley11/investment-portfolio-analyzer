"""Format decision-support responses for AMI instant answers (internal/diagnostics only)."""

from __future__ import annotations

from investment_ami.decision_support.models import DecisionSupportResponse

DECISION_SUPPORT_VERSION = "ds-v1"


def format_decision_support_markdown(response: DecisionSupportResponse) -> str:
    """Legacy markdown blob — prefer structured analyst sections for UI."""
    return response.assessment or ""
