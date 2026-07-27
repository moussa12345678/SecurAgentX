"""
core/agent.py — get_agent() compatibility shim (DEPRECATED).

Recreates the singleton factory that cli/textual.py depends on.
Import from tools/ or agents/ directly for new code.
"""

import logging

from core.brain import SecurAgentXAgent

logger = logging.getLogger(__name__)

_agent_instance = None


def get_agent() -> SecurAgentXAgent:
    """Return the singleton SecurAgentXAgent instance.

    Part of the ``core.agent`` compatibility layer that was deleted
    during the architecture consolidation.  Recreated as a thin shim
    to keep cli/textual.py working without changes.
    """
    global _agent_instance
    if _agent_instance is None:
        logger.info("Initialising SecurAgentXAgent (compatibility shim)")
        _agent_instance = SecurAgentXAgent()
    return _agent_instance
