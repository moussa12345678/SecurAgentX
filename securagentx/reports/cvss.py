"""securagentx/reports/cvss.py — CVSS v3.1 vector parser & base-score calculator.

Implements the CVSS v3.1 specification per the FIRST.org specification document
(https://www.first.org/cvss/v3.1/specification-document). Base, Temporal, and
Environmental score formulas are implemented per §7.1, §7.2, and §7.3 of the spec.

Public API
----------
Enums:
    AttackVector, AttackComplexity, PrivilegesRequired, UserInteraction, Scope,
    CIAImpact, ExploitCodeMaturity, RemediationLevel, ReportConfidence,
    SecurityRequirement

Classes:
    CVSSVector — frozen dataclass of the 8 CVSS v3.1 base metrics
    CVSSResult — frozen dataclass holding score, severity, subscores, vector string

Functions:
    parse_cvss_vector(s)              -> CVSSVector
    format_cvss_vector(v)             -> str
    calculate_base_score(v)           -> float
    calculate_cvss_score(v)           -> float   (alias of calculate_base_score)
    calculate_temporal_score(...)     -> float
    calculate_environmental_score(...) -> float
    cvss_severity(score)              -> str
    cvss_result(v)                    -> CVSSResult

All scoring functions are pure (no I/O, no shared mutable state) and safe to
call concurrently from multiple threads.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Optional


# ── 1. Metric enumerations (CVSS v3.1 spec §2, Tables 23–26) ──────────


class AttackVector(enum.Enum):
    """AV — Attack Vector (spec Table 23)."""

    NETWORK = "N"
    ADJACENT = "A"
    LOCAL = "L"
    PHYSICAL = "P"


class AttackComplexity(enum.Enum):
    """AC — Attack Complexity (spec Table 24)."""

    LOW = "L"
    HIGH = "H"


class PrivilegesRequired(enum.Enum):
    """PR — Privileges Required (spec Table 25).

    The numeric weight depends on Scope; see ``_PR_VALUES`` below.
    """

    NONE = "N"
    LOW = "L"
    HIGH = "H"


class UserInteraction(enum.Enum):
    """UI — User Interaction (spec Table 26)."""

    NONE = "N"
    REQUIRED = "R"


class Scope(enum.Enum):
    """S — Scope (spec §2.2)."""

    UNCHANGED = "U"
    CHANGED = "C"


class CIAImpact(enum.Enum):
    """C/I/A — Confidentiality / Integrity / Availability Impact (spec Table 27)."""

    NONE = "N"
    LOW = "L"
    HIGH = "H"


class ExploitCodeMaturity(enum.Enum):
    """E — Exploit Code Maturity (temporal, spec Table 14)."""

    NOT_DEFINED = "X"
    UNPROVEN = "U"
    PROOF_OF_CONCEPT = "P"
    FUNCTIONAL = "F"
    HIGH = "H"


class RemediationLevel(enum.Enum):
    """RL — Remediation Level (temporal, spec Table 15)."""

    NOT_DEFINED = "X"
    OFFICIAL_FIX = "O"
    TEMPORARY_FIX = "T"
    WORKAROUND = "W"
    UNAVAILABLE = "U"


class ReportConfidence(enum.Enum):
    """RC — Report Confidence (temporal, spec Table 16)."""

    NOT_DEFINED = "X"
    CONFIRMED = "C"
    REASONABLE = "R"
    UNKNOWN = "U"


class SecurityRequirement(enum.Enum):
    """CR/IR/AR — Confidentiality / Integrity / Availability Requirements.

    Environmental metric (spec Table 18).
    """

    NOT_DEFINED = "X"
    LOW = "L"
    MEDIUM = "M"
    HIGH = "H"


# ── 2. Numeric lookup tables ──────────────────────────────────────────


_AV_VALUES: dict[AttackVector, float] = {
    AttackVector.NETWORK: 0.85,
    AttackVector.ADJACENT: 0.62,
    AttackVector.LOCAL: 0.55,
    AttackVector.PHYSICAL: 0.20,
}

_AC_VALUES: dict[AttackComplexity, float] = {
    AttackComplexity.LOW: 0.77,
    AttackComplexity.HIGH: 0.44,
}

# PR value depends on Scope (spec Table 25):
#   Scope=Unchanged: N=0.85, L=0.62, H=0.27
#   Scope=Changed:   N=0.85, L=0.68, H=0.50
_PR_VALUES: dict[tuple[PrivilegesRequired, Scope], float] = {
    (PrivilegesRequired.NONE, Scope.UNCHANGED): 0.85,
    (PrivilegesRequired.NONE, Scope.CHANGED): 0.85,
    (PrivilegesRequired.LOW, Scope.UNCHANGED): 0.62,
    (PrivilegesRequired.LOW, Scope.CHANGED): 0.68,
    (PrivilegesRequired.HIGH, Scope.UNCHANGED): 0.27,
    (PrivilegesRequired.HIGH, Scope.CHANGED): 0.50,
}

_UI_VALUES: dict[UserInteraction, float] = {
    UserInteraction.NONE: 0.85,
    UserInteraction.REQUIRED: 0.62,
}

_CIA_VALUES: dict[CIAImpact, float] = {
    CIAImpact.HIGH: 0.56,
    CIAImpact.LOW: 0.22,
    CIAImpact.NONE: 0.00,
}

_E_VALUES: dict[ExploitCodeMaturity, float] = {
    ExploitCodeMaturity.NOT_DEFINED: 1.0,
    ExploitCodeMaturity.UNPROVEN: 0.91,
    ExploitCodeMaturity.PROOF_OF_CONCEPT: 0.94,
    ExploitCodeMaturity.FUNCTIONAL: 1.0,
    ExploitCodeMaturity.HIGH: 1.0,
}

_RL_VALUES: dict[RemediationLevel, float] = {
    RemediationLevel.NOT_DEFINED: 1.0,
    RemediationLevel.OFFICIAL_FIX: 1.0,
    RemediationLevel.TEMPORARY_FIX: 0.97,
    RemediationLevel.WORKAROUND: 0.96,
    RemediationLevel.UNAVAILABLE: 0.95,
}

_RC_VALUES: dict[ReportConfidence, float] = {
    ReportConfidence.NOT_DEFINED: 1.0,
    ReportConfidence.CONFIRMED: 1.0,
    ReportConfidence.REASONABLE: 0.92,
    ReportConfidence.UNKNOWN: 0.92,
}

_SR_VALUES: dict[SecurityRequirement, float] = {
    SecurityRequirement.NOT_DEFINED: 1.0,
    SecurityRequirement.LOW: 0.5,
    SecurityRequirement.MEDIUM: 1.0,
    SecurityRequirement.HIGH: 1.5,
}

# Reverse-lookups (string code → enum) for parsing vector strings.
_AV_BY_CODE: dict[str, AttackVector] = {e.value: e for e in AttackVector}
_AC_BY_CODE: dict[str, AttackComplexity] = {e.value: e for e in AttackComplexity}
_PR_BY_CODE: dict[str, PrivilegesRequired] = {e.value: e for e in PrivilegesRequired}
_UI_BY_CODE: dict[str, UserInteraction] = {e.value: e for e in UserInteraction}
_SCOPE_BY_CODE: dict[str, Scope] = {e.value: e for e in Scope}
_CIA_BY_CODE: dict[str, CIAImpact] = {e.value: e for e in CIAImpact}


# ── 3. Data classes ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CVSSVector:
    """CVSS v3.1 base-metric vector (8 mandatory base metrics).

    Defaults match the no-impact vector ``AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N``
    which scores 0.0. Frozen so it is hashable and safe to share between
    threads.
    """

    attack_vector: AttackVector = AttackVector.NETWORK
    attack_complexity: AttackComplexity = AttackComplexity.LOW
    privileges_required: PrivilegesRequired = PrivilegesRequired.NONE
    user_interaction: UserInteraction = UserInteraction.NONE
    scope: Scope = Scope.UNCHANGED
    confidentiality_impact: CIAImpact = CIAImpact.NONE
    integrity_impact: CIAImpact = CIAImpact.NONE
    availability_impact: CIAImpact = CIAImpact.NONE


@dataclass(frozen=True)
class CVSSResult:
    """Scored CVSS result.

    Attributes:
        base_score:              CVSS v3.1 Base Score (rounded to 1 dp).
        severity:                Info / Low / Medium / High / Critical.
        vector_string:           Canonical ``CVSS:3.1/...`` string.
        impact_subscore:         Impact Sub-Score (raw, unrounded).
        exploitability_subscore: Exploitability Sub-Score (raw, unrounded).
    """

    base_score: float
    severity: str
    vector_string: str
    impact_subscore: float
    exploitability_subscore: float


# ── 4. Spec primitives ────────────────────────────────────────────────


def _roundup(value: float) -> float:
    """CVSS v3.1 Roundup function (spec §7.1, Appendix A).

    Returns the smallest number, specified to one decimal place, that is equal
    to or higher than its input. Implemented per the spec's integer-based
    algorithm to avoid floating-point rounding drift.
    """
    int_input = int(round(value * 100_000))
    if int_input % 10_000 == 0:
        return int_input / 100_000.0
    return (math.floor(int_input / 10_000) + 1) / 10.0


def _isc_base(v: CVSSVector) -> float:
    """Impact Sub-Score (ISC) base — ``1 − [(1−C)(1−I)(1−A)]`` (spec §7.1)."""
    c = _CIA_VALUES[v.confidentiality_impact]
    i = _CIA_VALUES[v.integrity_impact]
    a = _CIA_VALUES[v.availability_impact]
    return 1 - ((1 - c) * (1 - i) * (1 - a))


def _impact_subscore(v: CVSSVector) -> float:
    """Impact Sub-Score (spec §7.1).

    Returns ``0.0`` when ISC base ≤ 0; otherwise ``6.42 × ISC`` for
    Scope=Unchanged, or ``7.52 × (ISC − 0.029) − 3.25 × (ISC − 0.02)^15``
    for Scope=Changed.
    """
    isc_base = _isc_base(v)
    if isc_base <= 0:
        return 0.0
    if v.scope == Scope.UNCHANGED:
        return 6.42 * isc_base
    return 7.52 * (isc_base - 0.029) - 3.25 * (isc_base - 0.02) ** 15


def _exploitability_subscore(v: CVSSVector) -> float:
    """Exploitability Sub-Score = ``8.22 × AV × AC × PR × UI`` (spec §7.1).

    Note: PR's numeric weight depends on Scope (see ``_PR_VALUES``).
    """
    av = _AV_VALUES[v.attack_vector]
    ac = _AC_VALUES[v.attack_complexity]
    pr = _PR_VALUES[(v.privileges_required, v.scope)]
    ui = _UI_VALUES[v.user_interaction]
    return 8.22 * av * ac * pr * ui


# ── 5. Scoring functions ──────────────────────────────────────────────


def calculate_base_score(v: CVSSVector) -> float:
    """CVSS v3.1 Base Score (spec §7.1).

    Returns ``0.0`` when Impact ≤ 0; otherwise ``Roundup(min(Impact+Exploit, 10))``
    for Scope=Unchanged, or ``Roundup(min(1.08 × (Impact+Exploit), 10))`` for
    Scope=Changed.
    """
    impact = _impact_subscore(v)
    if impact <= 0:
        return 0.0
    exploit = _exploitability_subscore(v)
    if v.scope == Scope.UNCHANGED:
        return _roundup(min(impact + exploit, 10.0))
    return _roundup(min(1.08 * (impact + exploit), 10.0))


# Canonical alias used throughout SecurAgentX + the brutal test suite.
calculate_cvss_score = calculate_base_score


def calculate_temporal_score(
    v: CVSSVector,
    exploit_code_maturity: ExploitCodeMaturity = ExploitCodeMaturity.NOT_DEFINED,
    remediation_level: RemediationLevel = RemediationLevel.NOT_DEFINED,
    report_confidence: ReportConfidence = ReportConfidence.NOT_DEFINED,
) -> float:
    """CVSS v3.1 Temporal Score (spec §7.2).

    ``TemporalScore = Roundup(BaseScore × E × RL × RC)``. NOT_DEFINED metrics
    default to a multiplier of 1.0, so a vector without temporal metrics returns
    the Base Score unchanged.
    """
    base = calculate_base_score(v)
    e = _E_VALUES[exploit_code_maturity]
    rl = _RL_VALUES[remediation_level]
    rc = _RC_VALUES[report_confidence]
    return _roundup(base * e * rl * rc)


def calculate_environmental_score(
    v: CVSSVector,
    *,
    exploit_code_maturity: ExploitCodeMaturity = ExploitCodeMaturity.NOT_DEFINED,
    remediation_level: RemediationLevel = RemediationLevel.NOT_DEFINED,
    report_confidence: ReportConfidence = ReportConfidence.NOT_DEFINED,
    confidentiality_requirement: SecurityRequirement = SecurityRequirement.NOT_DEFINED,
    integrity_requirement: SecurityRequirement = SecurityRequirement.NOT_DEFINED,
    availability_requirement: SecurityRequirement = SecurityRequirement.NOT_DEFINED,
    modified_attack_vector: Optional[AttackVector] = None,
    modified_attack_complexity: Optional[AttackComplexity] = None,
    modified_privileges_required: Optional[PrivilegesRequired] = None,
    modified_user_interaction: Optional[UserInteraction] = None,
    modified_scope: Optional[Scope] = None,
    modified_confidentiality_impact: Optional[CIAImpact] = None,
    modified_integrity_impact: Optional[CIAImpact] = None,
    modified_availability_impact: Optional[CIAImpact] = None,
) -> float:
    """CVSS v3.1 Environmental Score (spec §7.3).

    Uses the modified base metrics (defaulting to the base vector's values when
    ``None``) and security requirements (CR/IR/AR) to compute Modified Impact &
    Exploitability, then applies the temporal multipliers (E, RL, RC).
    """
    # Resolve modified metrics: fall back to the base vector when None.
    mav = modified_attack_vector or v.attack_vector
    mac = modified_attack_complexity or v.attack_complexity
    mpr = modified_privileges_required or v.privileges_required
    mui = modified_user_interaction or v.user_interaction
    ms = modified_scope or v.scope
    mc = modified_confidentiality_impact or v.confidentiality_impact
    mi = modified_integrity_impact or v.integrity_impact
    ma = modified_availability_impact or v.availability_impact

    cr = _SR_VALUES[confidentiality_requirement]
    ir = _SR_VALUES[integrity_requirement]
    ar = _SR_VALUES[availability_requirement]

    # Modified Impact Sub-Score (spec §7.3, MIT formula).
    c_v = _CIA_VALUES[mc]
    i_v = _CIA_VALUES[mi]
    a_v = _CIA_VALUES[ma]
    mit = min(1 - ((1 - cr * c_v) * (1 - ir * i_v) * (1 - ar * a_v)), 0.915)
    if mit <= 0:
        modified_impact = 0.0
    elif ms == Scope.UNCHANGED:
        modified_impact = 6.42 * mit
    else:
        modified_impact = 7.52 * (mit - 0.029) - 3.25 * (mit - 0.02) ** 15

    if modified_impact <= 0:
        return 0.0

    # Modified Exploitability (PR's numeric weight depends on the modified scope).
    av_v = _AV_VALUES[mav]
    ac_v = _AC_VALUES[mac]
    pr_v = _PR_VALUES[(mpr, ms)]
    ui_v = _UI_VALUES[mui]
    modified_exploitability = 8.22 * av_v * ac_v * pr_v * ui_v

    if ms == Scope.UNCHANGED:
        score = min(modified_impact + modified_exploitability, 10.0)
    else:
        score = min(1.08 * (modified_impact + modified_exploitability), 10.0)
    score = _roundup(score)

    # Apply temporal multipliers.
    e = _E_VALUES[exploit_code_maturity]
    rl = _RL_VALUES[remediation_level]
    rc = _RC_VALUES[report_confidence]
    return _roundup(score * e * rl * rc)


def cvss_severity(score: float) -> str:
    """Severity bucket for a CVSS score (spec §4.1, Table 13).

    Returns:
        - ``"Info"``     for score == 0.0
        - ``"Low"``      for 0.0 < score < 4.0
        - ``"Medium"``   for 4.0 ≤ score < 7.0
        - ``"High"``     for 7.0 ≤ score < 9.0
        - ``"Critical"`` for 9.0 ≤ score ≤ 10.0
    """
    if score <= 0.0:
        return "Info"
    if score < 4.0:
        return "Low"
    if score < 7.0:
        return "Medium"
    if score < 9.0:
        return "High"
    return "Critical"


def cvss_result(v: CVSSVector) -> CVSSResult:
    """Compute the full :class:`CVSSResult` for a base vector."""
    base = calculate_base_score(v)
    return CVSSResult(
        base_score=base,
        severity=cvss_severity(base),
        vector_string=format_cvss_vector(v),
        impact_subscore=_impact_subscore(v),
        exploitability_subscore=_exploitability_subscore(v),
    )


# ── 6. Parsing / formatting ───────────────────────────────────────────

# Required base-metric keys and their value-code → enum resolver.
_REQUIRED_BASE_KEYS: frozenset[str] = frozenset({"AV", "AC", "PR", "UI", "S", "C", "I", "A"})
_BASE_METRIC_RESOLVERS: dict[str, dict[str, enum.Enum]] = {
    "AV": _AV_BY_CODE,
    "AC": _AC_BY_CODE,
    "PR": _PR_BY_CODE,
    "UI": _UI_BY_CODE,
    "S": _SCOPE_BY_CODE,
    "C": _CIA_BY_CODE,
    "I": _CIA_BY_CODE,
    "A": _CIA_BY_CODE,
}


def parse_cvss_vector(vector: str) -> CVSSVector:
    """Parse a CVSS v3.1 vector string into a :class:`CVSSVector`.

    Accepts both the canonical form (``"CVSS:3.1/AV:N/..."``) and the bare
    form (``"AV:N/..."`` without the prefix). Raises ``ValueError`` on any
    malformed, incomplete, or out-of-spec input — including non-string input,
    empty strings, unknown metric keys, unknown metric values, and missing
    required base metrics.
    """
    if not isinstance(vector, str):
        raise ValueError(
            f"CVSS vector must be a string, got {type(vector).__name__}"
        )
    s = vector.strip()
    if not s:
        raise ValueError("CVSS vector string is empty")

    # Strip optional "CVSS:3.1/" prefix.
    if s.startswith("CVSS:"):
        slash = s.find("/")
        if slash == -1:
            raise ValueError(
                f"Malformed CVSS vector (no '/' after prefix): {vector!r}"
            )
        version_token = s[:slash]
        if version_token != "CVSS:3.1":
            raise ValueError(
                f"Unsupported CVSS version (only 3.1 is supported): {version_token}"
            )
        s = s[slash + 1:]

    # Parse "AV:N/AC:L/..." segments into a {KEY: VALUE} dict.
    metrics: dict[str, str] = {}
    for seg in s.split("/"):
        seg = seg.strip()
        if not seg:
            continue
        if ":" not in seg:
            raise ValueError(
                f"Malformed CVSS metric segment (no ':'): {seg!r}"
            )
        key, _, val = seg.partition(":")
        key = key.strip().upper()
        val = val.strip().upper()
        if not key or not val:
            raise ValueError(
                f"Empty key or value in CVSS segment: {seg!r}"
            )
        metrics[key] = val

    # All 8 base metrics are required.
    missing = _REQUIRED_BASE_KEYS - set(metrics.keys())
    if missing:
        raise ValueError(
            f"Missing required CVSS base metrics: {sorted(missing)}"
        )

    # Reject unknown metric keys (e.g., temporal/env metrics — not supported
    # by the base-only CVSSVector model).
    unknown = set(metrics.keys()) - _REQUIRED_BASE_KEYS
    if unknown:
        raise ValueError(
            f"Unknown/unsupported CVSS metric keys: {sorted(unknown)}"
        )

    # Resolve each metric value to its enum.
    try:
        av = _AV_BY_CODE[metrics["AV"]]
        ac = _AC_BY_CODE[metrics["AC"]]
        pr = _PR_BY_CODE[metrics["PR"]]
        ui = _UI_BY_CODE[metrics["UI"]]
        scope = _SCOPE_BY_CODE[metrics["S"]]
        c = _CIA_BY_CODE[metrics["C"]]
        i = _CIA_BY_CODE[metrics["I"]]
        a = _CIA_BY_CODE[metrics["A"]]
    except KeyError as exc:
        raise ValueError(
            f"Invalid CVSS metric value in vector {vector!r}: {exc}"
        ) from exc

    return CVSSVector(
        attack_vector=av,
        attack_complexity=ac,
        privileges_required=pr,
        user_interaction=ui,
        scope=scope,
        confidentiality_impact=c,
        integrity_impact=i,
        availability_impact=a,
    )


def format_cvss_vector(v: CVSSVector) -> str:
    """Format a :class:`CVSSVector` as a canonical ``CVSS:3.1/...`` string."""
    return (
        f"CVSS:3.1/"
        f"AV:{v.attack_vector.value}/"
        f"AC:{v.attack_complexity.value}/"
        f"PR:{v.privileges_required.value}/"
        f"UI:{v.user_interaction.value}/"
        f"S:{v.scope.value}/"
        f"C:{v.confidentiality_impact.value}/"
        f"I:{v.integrity_impact.value}/"
        f"A:{v.availability_impact.value}"
    )


__all__ = [
    # Enums
    "AttackVector",
    "AttackComplexity",
    "PrivilegesRequired",
    "UserInteraction",
    "Scope",
    "CIAImpact",
    "ExploitCodeMaturity",
    "RemediationLevel",
    "ReportConfidence",
    "SecurityRequirement",
    # Classes
    "CVSSVector",
    "CVSSResult",
    # Functions
    "parse_cvss_vector",
    "format_cvss_vector",
    "calculate_base_score",
    "calculate_cvss_score",
    "calculate_temporal_score",
    "calculate_environmental_score",
    "cvss_severity",
    "cvss_result",
]
