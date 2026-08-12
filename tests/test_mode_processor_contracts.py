from unittest.mock import MagicMock, patch

from agents.agent_modes import ModeProcessor as LegacyModeProcessor
from securagentx.scanning.modes import ModeProcessor as CanonicalModeProcessor
from tools.governance import Governance


def test_legacy_mode_processor_preserves_optional_governance_until_execution():
    processor = LegacyModeProcessor(client=MagicMock())

    assert processor.governance is None
    assert isinstance(processor._effective_governance(), Governance)


def test_canonical_mode_processor_preserves_optional_governance_until_execution():
    processor = CanonicalModeProcessor(client=MagicMock())

    assert processor.governance is None
    assert isinstance(processor._effective_governance(), Governance)


def test_legacy_universal_mode_uses_its_public_context_overflow_contract():
    processor = LegacyModeProcessor(client=MagicMock())

    with patch("agents.agent_universal.process_universal", return_value="ok") as runner:
        assert processor.process_universal("scan", [], "base") == "ok"

    assert isinstance(runner.call_args.kwargs["governance"], Governance)
    assert runner.call_args.kwargs["check_context_overflow"] is None


def test_canonical_universal_mode_preserves_its_compatibility_contract():
    processor = CanonicalModeProcessor(client=MagicMock())

    with patch("securagentx.scanning.universal.process_universal", return_value="ok") as runner:
        assert processor.process_universal("scan", [], "base") == "ok"

    assert isinstance(runner.call_args.kwargs["governance"], Governance)
    assert runner.call_args.kwargs["_check_context_overflow"] is None
