from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agents.agent_universal import process_universal


def test_process_universal_normalizes_scalar_action_params():
    client = MagicMock()
    client.chat.return_value = SimpleNamespace(
        tool_calls=[],
        content='{"action": {"type": "finish", "params": "invalid"}}',
    )
    executor = MagicMock()
    executor.execute_action.return_value = SimpleNamespace(success=True, output="done", error="")

    with (
        patch("agents.agent_universal.analyze_intent", return_value="scan"),
        patch("agents.agent_universal.get_universal_executor", return_value=executor),
        patch("agents.agent_universal._build_bug_bounty_prompt", return_value="test prompt"),
    ):
        result = process_universal(
            user_input="run the next approved action",
            client=client,
            conversation_history=[],
            base_prompt="",
            governance=MagicMock(),
            target="example.com",
        )

    assert "Universal Agent Summary" in result
    executor.execute_action.assert_called_once_with({"type": "finish", "params": {}})
