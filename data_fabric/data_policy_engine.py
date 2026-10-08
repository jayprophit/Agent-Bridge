"""Aetherius Personal Data Policy Engine (§61).

Extends the existing privacy/permissions system with rules for
data classes. Allows defining what roles/projects can access
which data classes at what level.

Per §61: "Extend existing privacy/permissions with rules such as:
DATA_CLASS + ROLE + PROJECT + ACTION + LOCAL/CLOUD + READ/WRITE + RETENTION."

Examples:
    FINANCE + GENERAL_CODING_AGENT = DENY
    PROJECT_DOCUMENT + PROJECT_RESEARCHER = READ_SCOPED
    CREDENTIAL + CREDENTIAL_BROKER = BROKER_ONLY
"""
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from models.inference_contract import (
    PRIVACY_PUBLIC, PRIVACY_PROJECT, PRIVACY_CONFIDENTIAL,
    PRIVACY_SECRET_LOCAL_ONLY,
)
from data_fabric.data_service_registry import DataClass

logger = logging.getLogger("aetherius.data_policy")


class DataAction(Enum):
    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    EXPORT = "export"
    BACKUP = "backup"
    RESTORE = "restore"
    SYNC = "sync"
    DELETE = "delete"


class ExecutionLocation(Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"
    ANY = "any"


class AccessDecision(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    READ_SCOPED = "READ_SCOPED"
    WRITE_SCOPED = "WRITE_SCOPED"
    BROKER_ONLY = "BROKER_ONLY"
    REQUIRES_OWNER = "REQUIRES_OWNER"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class DataPolicyRule:
    """A single data policy rule (§61).

    Format: DATA_CLASS + ROLE + PROJECT + ACTION + LOCATION + DECISION + RETENTION
    """
    data_class: str
    role: str
    project: str = "*"  # * = all projects
    action: str = "*"
    location: str = "*"  # local, cloud, hybrid, any
    decision: str = "DENY"
    retention_days: Optional[int] = None
    justification: str = ""
    created_at: float = field(default_factory=time.time)

    def matches(self, data_class: str, role: str, project: str,
                action: str, location: str) -> bool:
        """Check if this rule applies to the given request."""
        if self.data_class != data_class and self.data_class != "*":
            return False
        if self.role != role and self.role != "*":
            return False
        if self.project != project and self.project != "*":
            return False
        if self.action != action and self.action != "*":
            return False
        if self.location != location and self.location != "*" and self.location != "any":
            return False
        return True


class DataPolicyEngine:
    """Policy engine for personal/business data access (§61, §41, §43).

    Evaluates requests against a rule set. DENY takes precedence (default-deny).
    """

    def __init__(self):
        self._rules: list[DataPolicyRule] = []
        self._decision_log: list = []
        self._defaults_applied = False

    def add_rule(self, rule: DataPolicyRule) -> None:
        """Add a policy rule (§61)."""
        self._rules.append(rule)
        logger.info(f"Added policy rule: {rule.data_class} + {rule.role} -> {rule.decision}")

    def apply_defaults(self) -> None:
        """Apply default policies (§61, §17, §43, §45)."""
        if self._defaults_applied:
            return
        self._defaults_applied = True

        # §8, §42: Credentials -> broker only
        self.add_rule(DataPolicyRule(
            data_class=DataClass.CREDENTIALS.value,
            role="*",
            action="*",
            location="*",
            decision=AccessDecision.BROKER_ONLY.value,
            justification="Credentials accessed only via Credential Broker",
        ))
        # §17, §43: Finance default DENY
        self.add_rule(DataPolicyRule(
            data_class=DataClass.FINANCE.value,
            role="*",
            action=DataAction.READ.value,
            location="*",
            decision=AccessDecision.DENY.value,
            justification="Finance data requires explicit FINANCE role",
        ))
        self.add_rule(DataPolicyRule(
            data_class=DataClass.FINANCE.value,
            role="finance_specialist",
            action=DataAction.READ.value,
            location="local",
            decision=AccessDecision.READ_SCOPED.value,
        ))
        self.add_rule(DataPolicyRule(
            data_class=DataClass.FINANCE.value,
            role="finance_specialist",
            action=DataAction.WRITE.value,
            location="local",
            decision=AccessDecision.WRITE_SCOPED.value,
        ))
        # §24, §43: Identity/Legal/Health -> local-only, no cloud
        for dc in [DataClass.IDENTITY.value, DataClass.LEGAL.value,
                   DataClass.HEALTH.value]:
            self.add_rule(DataPolicyRule(
                data_class=dc,
                role="*",
                action="*",
                location="cloud",
                decision=AccessDecision.DENY.value,
                justification="Identity/legal/health data never to cloud workers",
            ))
            self.add_rule(DataPolicyRule(
                data_class=dc,
                role="identity_specialist",
                action=DataAction.READ.value,
                location=ExecutionLocation.LOCAL.value,
                decision=AccessDecision.READ_SCOPED.value,
            ))
        # §12: Files -> local preferred, cloud denied for raw files
        self.add_rule(DataPolicyRule(
            data_class=DataClass.FILES.value,
            role="*",
            action=DataAction.READ.value,
            location=ExecutionLocation.CLOUD.value,
            decision=AccessDecision.DENY.value,
            justification="Raw files should be encrypted before cloud (§12)",
        ))
        # §35: Default for other data classes
        self.add_rule(DataPolicyRule(
            data_class=DataClass.NOTES.value,
            role="research_worker",
            action=DataAction.READ.value,
            location="local",
            decision=AccessDecision.READ_SCOPED.value,
        ))
        self.add_rule(DataPolicyRule(
            data_class=DataClass.DOCUMENTS.value,
            role="coding_worker",
            action=DataAction.READ.value,
            project="*",
            location="local",
            decision=AccessDecision.READ_SCOPED.value,
        ))
        self.add_rule(DataPolicyRule(
            data_class=DataClass.PROJECTS.value,
            role="project_researcher",
            action=DataAction.READ.value,
            location="local",
            decision=AccessDecision.READ_SCOPED.value,
        ))

    def evaluate(self, data_class: str, role: str, action: str,
                 project: str = "default",
                 location: str = "local") -> AccessDecision:
        """Evaluate a data access request (§61, §43)."""
        matching_rules = [r for r in self._rules
                          if r.matches(data_class, role, project, action, location)]

        log_entry = {
            "timestamp": time.time(),
            "data_class": data_class,
            "role": role,
            "action": action,
            "project": project if not project.startswith("CRED-") else "[REDACTED]",
            "location": location,
            "matching_rules": len(matching_rules),
            "decision": None,
            "justification": "",
        }

        if not matching_rules:
            log_entry["decision"] = AccessDecision.DENY.value
            log_entry["justification"] = "No matching policy rule"
            self._decision_log.append(log_entry)
            return AccessDecision.DENY

        # Select the best rule: most specific (fewest wildcards) wins.
        # Ties broken by precedence (DENY > BROKER_ONLY > others > ALLOW).
        precedence = {
            AccessDecision.ALLOW: 0,
            AccessDecision.NOT_APPLICABLE: 1,
            AccessDecision.READ_SCOPED: 2,
            AccessDecision.WRITE_SCOPED: 3,
            AccessDecision.REQUIRES_OWNER: 4,
            AccessDecision.BROKER_ONLY: 5,
            AccessDecision.DENY: 6,
        }

        def rule_specificity(r: DataPolicyRule) -> int:
            count = 0
            if r.data_class != "*": count += 1
            if r.role != "*": count += 1
            if r.project != "*": count += 1
            if r.action != "*": count += 1
            if r.location != "*" and r.location != "any": count += 1
            return count

        best = max(matching_rules,
                   key=lambda r: (rule_specificity(r),
                                  precedence.get(AccessDecision(r.decision), 0)))
        decision = AccessDecision(best.decision)
        log_entry["decision"] = decision.value
        log_entry["rule_justification"] = best.justification
        self._decision_log.append(log_entry)
        return decision

    def decision_log(self) -> list:
        """Return audit log of all policy decisions."""
        return list(self._decision_log)

    def rules(self) -> list:
        """Return all rules (without secrets)."""
        return [
            {"data_class": r.data_class, "role": r.role, "project": r.project,
             "action": r.action, "location": r.location,
             "decision": r.decision, "justification": r.justification,
             "retention_days": r.retention_days}
            for r in self._rules
        ]
