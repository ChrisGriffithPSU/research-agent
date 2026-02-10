"""Approval policy for Kimi Agent SDK tool actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Decision returned by the approval policy."""

    resolution: Literal["approve", "reject", "approve_for_session"]
    reason: str


class ApprovalPolicy:
    """Policy-based approval gate for Kimi approval requests."""

    _DEFAULT_ALLOWLIST = (
        r"\b(ls|dir|pwd|tree|type|cat|Get-Content|rg|grep)\b",
        r"\bpytest\b|\bpython\s+-m\s+pytest\b",
        r"\bpython\s+-m\s+jupyter\s+nbconvert\b",
        r"\bpapermill\b",
        r"\bpython\b.*\.py\b",
        r"\buv\s+sync\b",
        r"\buv\s+pip\s+install\b",
        r"(?:\.venv[\\/](?:bin|Scripts)[\\/])pip\s+install\b",
        r"\bgit\s+(status|diff|rev-parse|log)\b",
    )

    _DEFAULT_BLOCKLIST = (
        r"\bgit\s+push\b",
        r"\bssh\b|\bscp\b",
        r"\brm\s+-rf\b|\brmdir\s+/s\b|\bdel\s+/[sqf]\b",
        r"\bmkfs\b|\bformat\b",
        r"\bsudo\b|\brunas\b",
        r"\bapt(?:-get)?\s+install\b|\byum\s+install\b|\bbrew\s+install\b|\bchoco\s+install\b",
        r"~/.ssh|id_rsa|aws/credentials|\.npmrc|\.pypirc|\.env\b|credentials\.json",
        r"\bprintenv\b|\benv\s*$|\bset\s*$|\bGet-ChildItem\s+Env:\b",
    )

    _NETWORK_PATTERNS = (
        r"\bcurl\b",
        r"\bwget\b",
        r"\binvoke-webrequest\b",
        r"https?://",
    )

    def __init__(
        self,
        *,
        network_access: bool = False,
        yolo: bool = False,
        allowlist: tuple[str, ...] | None = None,
        blocklist: tuple[str, ...] | None = None,
    ) -> None:
        self.network_access = network_access
        self.yolo = yolo
        self._allowlist = [
            re.compile(p, re.IGNORECASE) for p in (allowlist or self._DEFAULT_ALLOWLIST)
        ]
        self._blocklist = [
            re.compile(p, re.IGNORECASE) for p in (blocklist or self._DEFAULT_BLOCKLIST)
        ]
        self._network = [re.compile(p, re.IGNORECASE) for p in self._NETWORK_PATTERNS]

    def evaluate_request(self, request: Any) -> ApprovalDecision:
        """Evaluate a Kimi `ApprovalRequest` and return a decision."""
        if self.yolo:
            return ApprovalDecision("approve", "YOLO mode enabled for this job")

        request_text = self._request_text(request)

        blocked = self._first_match(request_text, self._blocklist)
        if blocked:
            return ApprovalDecision("reject", f"blocked by policy rule: {blocked.pattern}")

        network_match = self._first_match(request_text, self._network)
        if network_match and not self.network_access:
            return ApprovalDecision(
                "reject",
                "network access is disabled for this job",
            )
        if network_match and self.network_access:
            return ApprovalDecision("approve", "network access explicitly enabled for this job")

        allowed = self._first_match(request_text, self._allowlist)
        if allowed:
            return ApprovalDecision("approve", f"allowlisted action matched: {allowed.pattern}")

        return ApprovalDecision(
            "reject",
            "command not on allowlist; propose a safer local alternative",
        )

    @staticmethod
    def denial_message(decision: ApprovalDecision) -> str:
        """Return a human-readable denial explanation for logs/prompts."""
        return (
            "Approval denied by worker policy: "
            f"{decision.reason}. "
            "Please propose an alternative that only uses local repo operations, "
            "tests, notebook/script execution, and safe git read-only commands."
        )

    @staticmethod
    def policy_text() -> str:
        """Short policy text injected into the task prompt."""
        return (
            "Approval policy: safe read/list commands, pytest, notebook/script execution, "
            "uv-based dependency installation, and git status/diff are approved. "
            "Commands like git push, ssh/scp, rm -rf, system package installs, "
            "secret exfiltration, and unauthorized network requests are rejected."
        )

    @staticmethod
    def _first_match(text: str, patterns: list[re.Pattern[str]]) -> re.Pattern[str] | None:
        for pattern in patterns:
            if pattern.search(text):
                return pattern
        return None

    @staticmethod
    def _request_text(request: Any) -> str:
        parts = [
            str(getattr(request, "action", "") or ""),
            str(getattr(request, "description", "") or ""),
            str(getattr(request, "sender", "") or ""),
        ]
        display = getattr(request, "display", None)
        if isinstance(display, list):
            for block in display:
                parts.append(str(block))
                parts.append(str(getattr(block, "command", "") or ""))
        return " | ".join(part for part in parts if part).lower()
