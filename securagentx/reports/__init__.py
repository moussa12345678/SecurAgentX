"""securagentx.reports — reporting subpackage.

Re-exports the public API of the reporting submodules:
    cvss, markdown, pdf, templates, export.

The CVSS calculator (``cvss``) is always available because it has no
third-party dependencies. The other submodules are imported defensively so
that a missing or partially-initialized submodule (e.g., ``pdf`` failing
because ``reportlab`` is not installed) does not break the rest of the
subpackage. Each guarded import is a no-op when its submodule has not yet
been landed by parallel development sub-tasks.

Direct submodule imports (e.g., ``from securagentx.reports.cvss import
CVSSVector``) always work regardless of this file's defensive behavior,
because Python imports the parent package (running this ``__init__``) before
descending into the submodule.
"""

from __future__ import annotations

# ── Always available — CVSS calculator (no third-party deps) ──────────

from .cvss import (
    AttackComplexity,
    AttackVector,
    CIAImpact,
    CVSSResult,
    CVSSVector,
    ExploitCodeMaturity,
    PrivilegesRequired,
    RemediationLevel,
    ReportConfidence,
    Scope,
    SecurityRequirement,
    UserInteraction,
    calculate_base_score,
    calculate_cvss_score,
    calculate_environmental_score,
    calculate_temporal_score,
    cvss_result,
    cvss_severity,
    format_cvss_vector,
    parse_cvss_vector,
)

# ── Optional submodules — guarded so incremental development by parallel ──
#    sub-tasks (markdown / pdf / templates / export) doesn't break this
#    package import if any of them aren't landed yet, or if their optional
#    third-party deps (e.g., reportlab) aren't installed.

try:  # pragma: no cover - import guard for incremental development
    from .markdown import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - import guard for incremental development
    pass

try:  # pragma: no cover - import guard for incremental development
    from .pdf import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - import guard for incremental development
    pass

try:  # pragma: no cover - import guard for incremental development
    from .templates import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - import guard for incremental development
    pass

try:  # pragma: no cover - import guard for incremental development
    from .export import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - import guard for incremental development
    pass


__all__ = [
    # cvss — enums
    "AttackComplexity",
    "AttackVector",
    "CIAImpact",
    "ExploitCodeMaturity",
    "PrivilegesRequired",
    "RemediationLevel",
    "ReportConfidence",
    "Scope",
    "SecurityRequirement",
    "UserInteraction",
    # cvss — classes
    "CVSSResult",
    "CVSSVector",
    # cvss — functions
    "calculate_base_score",
    "calculate_cvss_score",
    "calculate_environmental_score",
    "calculate_temporal_score",
    "cvss_result",
    "cvss_severity",
    "format_cvss_vector",
    "parse_cvss_vector",
]
