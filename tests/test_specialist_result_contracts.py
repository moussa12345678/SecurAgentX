from unittest.mock import MagicMock, patch

from agents.specialist_agent import SpecialistAgent as LegacySpecialistAgent
from securagentx.scanning.specialist import SpecialistAgent as CanonicalSpecialistAgent


def _assert_normalized_result(agent):
    with patch(
        "tools.safe_exec.execute_safely",
        return_value={"success": 1, "stdout": 42, "stderr": None, "error": None},
    ):
        result = agent._run_shell({"command": "echo harmless"}, "example.test", "test")

    assert result.success is False
    assert result.output == "42"
    assert result.error == ""


def test_legacy_specialist_normalizes_safe_exec_result_values():
    _assert_normalized_result(LegacySpecialistAgent(client=MagicMock()))


def test_canonical_specialist_normalizes_safe_exec_result_values():
    _assert_normalized_result(CanonicalSpecialistAgent(client=MagicMock()))
