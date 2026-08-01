"""securagentx/governance.py - Governance & Safety System"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Callable
import yaml

from .types import (
    RiskLevel, AIAction, RiskAssessment
)

logger = logging.getLogger("securagentx.governance")


class GovernanceDecision(Enum):
    """Governance Decision"""
    ALLOW = "allow"                    # อนุญาตให้ดำเนินการ
    NEEDS_APPROVAL = "needs_approval"  # ต้องขออนุมัติ
    DENY = "deny"                      # ปฏิเสธ


@dataclass
class GateResult:
    """ผลการตัดสินใจของ Governance"""
    decision: GovernanceDecision
    rationale: str
    risk_level: str
    requires_human: bool = False
    auto_approve_conditions: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)


@dataclass
class GovernancePolicy:
    """นโยบายการกำกับดูแล"""
    name: str
    description: str
    risk_levels: List[str]
    allowed_actions: List[str]
    blocked_actions: List[str]
    requires_approval: List[str]
    auto_approve_conditions: List[str] = field(default_factory=list)
    max_concurrent: int = 5
    rate_limit_rps: float = 10.0


class GovernanceGate:
    """
    Governance Gate - ประตูควบคุมการกระทำ
    ประเมินความเสี่ยงและตัดสินใจอนุญาต/ปฏิเสธ/ขออนุมัติ
    """

    def __init__(self, config_path: Optional[str] = None):
        self.policies: Dict[str, GovernancePolicy] = {}
        self.auto_approve_enabled = True
        self.approval_callbacks: Dict[str, Callable] = {}
        self.audit_log: List[Dict] = []
        # VULN-03: lazy-instantiate ScopeManager on first _check_scope call.
        self._scope_manager: Optional[Any] = None
        # VULN-03: simple in-memory sliding-window rate limiter.
        self._rate_limiter: Dict[str, List[float]] = {}
        self._rate_limit_max_actions: int = 10
        self._rate_limit_window_s: float = 60.0
        self._load_default_policies()
        if config_path:
            self.load_config(config_path)

    def _load_default_policies(self):
        """โหลดนโยบายเริ่มต้น"""
        self.policies = {
            "recon": GovernancePolicy(
                name="reconnaissance",
                description="Passive reconnaissance activities",
                risk_levels=["safe"],
                allowed_actions=["dns_lookup", "ssl_cert_check", "whois", "passive_dns"],
                blocked_actions=[],
                requires_approval=[],
                auto_approve_conditions=["passive_only", "no_auth_required"]
            ),
            "scan": GovernancePolicy(
                name="vulnerability_scanning",
                description="Active vulnerability scanning",
                risk_levels=["safe", "privileged"],
                allowed_actions=["port_scan", "service_detection", "vuln_scan", "fuzzing"],
                blocked_actions=["dos", "brute_force", "exploitation"],
                requires_approval=["intrusive_scan", "auth_bypass"],
                auto_approve_conditions=["safe_scan", "rate_limited"],
                max_concurrent=10,
                rate_limit_rps=5.0
            ),
            "exploit": GovernancePolicy(
                name="exploitation",
                description="Vulnerability exploitation",
                risk_levels=["privileged", "destructive"],
                allowed_actions=["poc_exploit", "proof_of_concept"],
                blocked_actions=["data_exfiltration", "persistence", "lateral_movement", "ransomware"],
                requires_approval=["exploit_execution", "data_access", "shell_access"],
                auto_approve_conditions=["poc_only", "read_only", "no_data_access"],
                max_concurrent=3,
                rate_limit_rps=1.0
            ),
            "post_exploit": GovernancePolicy(
                name="post_exploitation",
                description="Post-exploitation activities",
                risk_levels=["destructive", "existential"],
                allowed_actions=["privilege_escalation_poc", "lateral_movement_poc"],
                blocked_actions=["data_destruction", "ransomware", "backdoor_installation", "credential_theft"],
                requires_approval=["all_actions"],
                auto_approve_conditions=[],
                max_concurrent=1,
                rate_limit_rps=0.5
            ),
        }

    def load_config(self, config_path: str):
        """โหลดคอนฟิกจาก YAML"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            # Parse custom policies
            for name, policy_data in config.get("policies", {}).items():
                self.policies[name] = GovernancePolicy(**policy_data)
        except Exception as e:
            logger.warning(f"Could not load governance config: {e}")

    def gate(
        self,
        mission_id: str,
        target: str,
        action: AIAction,
        callback: Optional[Callable] = None
    ) -> GateResult:
        """
        ประเมินการกระทำผ่านประตูควบคุม
        Returns GovernanceGate decision
        """
        # 1. Determine policy
        policy_name = self._get_policy_for_action(action)
        _policy = self.policies.get(policy_name, self.policies.get("scan"))

        # 2. Risk Assessment
        risk_assessment = self._assess_risk(action)

        # 3. Check Scope (advisory only — does not block, just logs)
        if not self._check_scope(action):
            logger.info(
                "Scope notice: target %r not in scope.txt — proceeding (advisory).",
                action.target,
            )

        # 4. Check Policy
        policy_decision = self._check_policy(action, risk_assessment)
        if policy_decision != GovernanceDecision.ALLOW:
            action_type_str = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)
            return GateResult(
                decision=policy_decision,
                rationale=f"Policy violation: {action_type_str}",
                risk_level=risk_assessment.level,
                requires_human=(policy_decision == GovernanceDecision.DENY)
            )

        # 5. Constitutional Check
        # (Done separately by ConstitutionalAIEngine)

        # 6. Rate Limiting
        if not self._check_rate_limit(action):
            return GateResult(
                decision=GovernanceDecision.DENY,
                rationale="Rate limit exceeded",
                risk_level="medium"
            )

        # 7. Final Decision
        if risk_assessment.level in ["critical", "existential"]:
            return GateResult(
                decision=GovernanceDecision.DENY,
                rationale=f"Risk level {risk_assessment.level} exceeds threshold",
                risk_level=risk_assessment.level,
                requires_human=True
            )

        return GateResult(
            decision=GovernanceDecision.ALLOW,
            rationale="Action approved by governance gate",
            risk_level=risk_assessment.level,
            requires_human=False
        )

    def _get_policy_for_action(self, action: AIAction) -> str:
        """กำหนดนโยบายตามประเภทการกระทำ"""
        action_type = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)
        mapping = {
            "recon": "recon",
            "reconnaissance": "recon",
            "scan": "scan",
            "scanning": "scan",
            "exploit": "exploit",
            "exploitation": "exploit",
            "post_exploit": "post_exploit",
            "post_exploitation": "post_exploit",
        }
        return mapping.get(action_type, "scan")

    def _assess_risk(self, action: AIAction) -> "RiskAssessment":
        """ประเมินความเสี่ยง"""
        risk = action.risk_level.value if hasattr(action.risk_level, 'value') else str(action.risk_level)

        # Enhance with action-specific assessment
        tool_risk = {
            "sqlmap": "high",
            "nmap": "low",
            "nuclei": "medium",
            "ffuf": "low",
            "metasploit": "critical",
        }.get(action.tool.lower(), "medium")

        # Determine overall risk
        risk_order = ["safe", "privileged", "destructive", "critical", "existential"]
        risk_idx = max(risk_order.index(risk) if risk in risk_order else 1,
                       risk_order.index(tool_risk) if tool_risk in risk_order else 1)

        return RiskAssessment(
            level=risk_order[risk_idx],
            factors={"action_risk": risk, "tool_risk": tool_risk}
        )

    def _check_scope(self, action: AIAction) -> bool:
        """Check scope — delegate to securagentx.scope.ScopeManager (VULN-03)."""
        target = (action.target or "").strip()
        if not target:
            return False
        try:
            if self._scope_manager is None:
                from .scope import ScopeManager
                self._scope_manager = ScopeManager()
            return self._scope_manager.is_in_scope(target)
        except Exception as e:
            logger.warning("Scope check failed for target=%r: %s — failing open.", target, e)
            return True

    def _check_policy(self, action: AIAction, risk: "RiskAssessment") -> GovernanceDecision:
        """ตรวจสอบนโยบาย"""
        policy_name = self._get_policy_for_action(action)
        policy = self.policies.get(policy_name, self.policies.get("scan"))

        action_name = action.tool or action.action_type.value  # type: ignore[attr-defined]

        # Check blocked
        if action_name in policy.blocked_actions:  # type: ignore[union-attr]
            return GovernanceDecision.DENY

        # Check if needs approval
        if action_name in policy.requires_approval:  # type: ignore[union-attr]
            return GovernanceDecision.NEEDS_APPROVAL

        # Check auto-approve conditions
        if self.auto_approve_enabled:
            for condition in policy.auto_approve_conditions:  # type: ignore[union-attr]
                if self._check_condition(condition, action):
                    return GovernanceDecision.ALLOW

        # Check allowed
        if policy.allowed_actions and action_name not in policy.allowed_actions:  # type: ignore[union-attr]
            return GovernanceDecision.NEEDS_APPROVAL

        return GovernanceDecision.ALLOW

    def _check_condition(self, condition: str, action: AIAction) -> bool:
        """ตรวจสอบเงื่อนไข Auto-approve"""
        conditions = {
            "passive_only": lambda a: (a.action_type.value if hasattr(a.action_type, 'value') else str(a.action_type)) in ["recon", "reconnaissance"],
            "safe_scan": lambda a: a.risk_level == RiskLevel.SAFE,
            "rate_limited": lambda a: True,  # Checked separately
            "poc_only": lambda a: "poc" in (a.parameters.get("mode", "") if isinstance(a.parameters, dict) else ""),
            "read_only": lambda a: "read" in (a.parameters.get("mode", "") if isinstance(a.parameters, dict) else ""),
            "no_data_access": lambda a: "data" not in (a.parameters.get("access", "") if isinstance(a.parameters, dict) else ""),
            "no_auth_required": lambda a: "auth" not in (a.parameters.get("type", "") if isinstance(a.parameters, dict) else ""),
        }
        check = conditions.get(condition)
        return check(action) if check else False

    def _check_rate_limit(self, action: AIAction) -> bool:
        """Check rate limit — simple in-memory sliding window (VULN-03)."""
        target = (action.target or "_unknown_").strip() or "_unknown_"
        now = time.time()
        window = self._rate_limit_window_s
        max_actions = self._rate_limit_max_actions
        recent = [t for t in self._rate_limiter.get(target, []) if now - t < window]
        if len(recent) >= max_actions:
            self._rate_limiter[target] = recent
            logger.info("Rate limit hit for target=%r: %d actions in last %.0fs.", target, len(recent), window)
            return False
        recent.append(now)
        self._rate_limiter[target] = recent
        return True

    def audit(self, action: AIAction, decision: GovernanceGate):
        """บันทึก Audit Log"""
        action_type_str = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type_str,
            "action_id": action.action_id,
            "tool": action.tool,
            "target": action.target,
            "decision": decision.decision.value,  # type: ignore[attr-defined]
            "rationale": decision.rationale,  # type: ignore[attr-defined]
            "risk_level": decision.risk_level  # type: ignore[attr-defined]
        }
        self.audit_log.append(entry)
        logger.info(f"Governance: {decision.decision.value} - {action.tool} on {action.target} - {decision.rationale}")  # type: ignore[attr-defined]


# Export
__all__ = [
    "RiskLevel",
    "GovernanceDecision",
    "GovernanceGate",
    "GovernancePolicy",
    "RiskAssessment",
]