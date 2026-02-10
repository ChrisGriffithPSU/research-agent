"""Unit tests for Kimi approval policy."""

from __future__ import annotations

import types

from workers.kimi_worker.approvals import ApprovalPolicy


def _request(text: str):
    return types.SimpleNamespace(action=text, description=text, sender="agent", display=[])


def test_allowlisted_command_is_approved() -> None:
    policy = ApprovalPolicy(network_access=False, yolo=False)
    decision = policy.evaluate_request(_request("pytest -q"))
    assert decision.resolution == "approve"


def test_blocklisted_command_is_rejected() -> None:
    policy = ApprovalPolicy(network_access=False, yolo=False)
    decision = policy.evaluate_request(_request("git push origin main"))
    assert decision.resolution == "reject"
    assert "blocked" in decision.reason


def test_network_command_rejected_when_network_disabled() -> None:
    policy = ApprovalPolicy(network_access=False, yolo=False)
    decision = policy.evaluate_request(_request("curl https://example.com"))
    assert decision.resolution == "reject"


def test_network_command_approved_when_network_enabled() -> None:
    policy = ApprovalPolicy(network_access=True, yolo=False)
    decision = policy.evaluate_request(_request("curl https://example.com"))
    assert decision.resolution == "approve"


def test_yolo_mode_approves_everything() -> None:
    policy = ApprovalPolicy(yolo=True)
    decision = policy.evaluate_request(_request("rm -rf /"))
    assert decision.resolution == "approve"
