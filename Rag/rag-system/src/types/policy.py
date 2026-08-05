"""
Policy domain types.

`PolicyMeta` is the payload schema written to every chunk in the policy
collection — it is what makes deterministic Qdrant filtering possible, which
plain semantic similarity cannot guarantee on its own.
"""
from enum import Enum
from typing import Any

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyMeta(BaseModel):
    """
    Front-matter of a policy document, applied to every chunk derived from it.

    Authored by hand in the source document — never inferred by a model, so the
    tagging that drives access decisions stays auditable and version-controlled.
    """
    policy_id: str
    title: str = ""
    applies_to_tools: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    mandatory: bool = False          # always retrieved, regardless of similarity
    version: str = "1.0"
    effective_date: str | None = None
    jurisdiction: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Flat dict for the Qdrant point payload (filterable fields)."""
        return {
            "doc_type": "policy",
            "policy_id": self.policy_id,
            "title": self.title,
            "applies_to_tools": self.applies_to_tools,
            "risk_level": self.risk_level.value,
            "mandatory": self.mandatory,
            "version": self.version,
            "effective_date": self.effective_date,
            "jurisdiction": self.jurisdiction,
        }


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"                # escalate to a human


class PolicyVerdict(BaseModel):
    """Output of the policy gate. `allowed_tools` is consumed by the execution gate."""
    decision: PolicyDecision
    reason: str
    allowed_tools: list[str] = Field(default_factory=list)
    cited_policies: list[str] = Field(default_factory=list)   # policy_id@version

    @classmethod
    def denied(cls, reason: str) -> "PolicyVerdict":
        """Fail-closed constructor — used whenever the judge cannot be trusted."""
        return cls(decision=PolicyDecision.DENY, reason=reason)
