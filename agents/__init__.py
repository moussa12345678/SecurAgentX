"""agents/ — SecurAgentX agent modules package (DEPRECATED).

This package now re-exports from securagentx.scanning for backward compatibility.
New code should import from securagentx.scanning directly.

Deprecated import:  from agents.scan_loop import ScanLoop   → from securagentx.scanning.scan_loop import ScanLoop
                    from agents.decision_engine import ...   → from securagentx.scanning.decision_engine import ...
                    from agents.scan_context import ...      → from securagentx.scanning.scan_context import ...
                    from agents.post_processor import ...    → from securagentx.scanning.post_processor import ...
                    from agents.prompt_builder import ...    → from securagentx.scanning.prompt_builder import ...
"""

import warnings

from securagentx.scanning.decision_engine import Decision, DecisionEngine
from securagentx.scanning.post_processor import PostExecutionProcessor
from securagentx.scanning.prompt_builder import PromptBuilder
from securagentx.scanning.scan_context import ScanContext
from securagentx.scanning.scan_loop import ScanLoop, ScanResult

warnings.warn(
    "agents/ is deprecated; import from securagentx.scanning instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "Decision",
    "DecisionEngine",
    "PostExecutionProcessor",
    "PromptBuilder",
    "ScanContext",
    "ScanLoop",
    "ScanResult",
]
