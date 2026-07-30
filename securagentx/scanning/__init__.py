"""securagentx/scanning/ — Scanning pipeline (consolidated from agents/).

This subpackage contains the scanning pipeline: context management,
decision engine, scan loop, prompt building, post processing, and
specialized agent roles (critic, specialist, strategist).

All symbols are re-exported through the agents/ package for backward
compatibility. New code should import from scanning.scanning directly.
"""

from securagentx.scanning.scan_loop import ScanLoop, ScanResult
from securagentx.scanning.scan_context import ScanContext
from securagentx.scanning.decision_engine import Decision, DecisionEngine, Reflection
from securagentx.scanning.vuln_reasoning_phase import run_reasoning_phase, _hypothesis_to_finding
from securagentx.scanning.hypothesis_boost import HypothesisBoost, build_stuck_guidance
from securagentx.scanning.post_processor import PostExecutionProcessor
from securagentx.scanning.prompt_builder import PromptBuilder

__all__ = [
    "ScanLoop", "ScanResult",
    "ScanContext",
    "Decision", "DecisionEngine", "Reflection",
    "run_reasoning_phase", "_hypothesis_to_finding",
    "HypothesisBoost", "build_stuck_guidance",
    "PostExecutionProcessor",
    "PromptBuilder",
]
