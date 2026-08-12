from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.venom_control_server import ACTION_BY_NAME, VenomController


TARGET = "https://8340b19dbdf7ed78addd601459980939.ctf.hacker101.com/"
HOST = "8340b19dbdf7ed78addd601459980939.ctf.hacker101.com"


def test_controller_exposes_only_registered_actions():
    controller = VenomController({HOST})

    result = controller.execute("tool_catalog")

    assert result["ok"] is True
    assert result["result"]["summary"] == f"{len(ACTION_BY_NAME)} registered Venom actions"
    assert {entry["name"] for entry in result["result"]["actions"]} == set(ACTION_BY_NAME)
    assert "audit_log" in ACTION_BY_NAME


def test_controller_rejects_unregistered_action():
    controller = VenomController({HOST})

    with pytest.raises(ValueError, match="not registered"):
        controller.execute("shell", TARGET)


@pytest.mark.parametrize(
    "target",
    [
        "ftp://" + HOST + "/",
        "https://example.com/",
        "https://user:pass@" + HOST + "/",
        "https://" + HOST + ":8443/",
        "not a url",
    ],
)
def test_controller_rejects_target_outside_constrained_scope(target: str):
    controller = VenomController({HOST})

    with pytest.raises(ValueError):
        controller.normalize_target(target)


def test_scope_validation_returns_canonical_target():
    controller = VenomController({HOST})

    result = controller.execute("scope_validate", TARGET + "#fragment")

    assert result["ok"] is True
    assert result["target"] == TARGET
    assert result["audit"]["target"] == TARGET


@patch("tools.venom_control_server._open_scope_bound")
def test_header_action_uses_head_with_bounded_timeout(mock_open):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers.items.return_value = [("Server", "test")]
    mock_open.return_value = response
    controller = VenomController({HOST})

    result = controller.execute("http_headers", TARGET)

    assert result["ok"] is True
    assert result["result"]["status"] == 200
    request = mock_open.call_args.args[0]
    assert request.get_method() == "HEAD"


@patch("tools.venom_control_server._open_scope_bound", side_effect=OSError("network unavailable"))
def test_execution_failure_is_recorded_without_leaking_traceback(_mock_open):
    controller = VenomController({HOST})

    result = controller.execute("http_headers", TARGET)

    assert result["ok"] is False
    assert result["audit"]["ok"] is False
    assert "traceback" not in result["result"].get("error", "").lower()


def test_control_plane_excludes_free_shell_and_high_impact_tool_actions():
    forbidden = {"shell", "nmap", "masscan", "ffuf", "gobuster", "sqlmap", "hydra", "metasploit"}

    assert forbidden.isdisjoint(ACTION_BY_NAME)
    assert "project_venom_tests" in ACTION_BY_NAME
