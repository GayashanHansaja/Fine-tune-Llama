"""
Policy domain types.

`PolicyMeta` is the *internal* normalised view of a policy chunk's metadata.
It is deliberately decoupled from whatever the data-transport layer actually
writes into Qdrant — that external shape is not finalised yet, so all mapping
from their payload into this model happens in one place:
`src/core/policy/payload_adapter.py`.

Nothing outside that adapter should reference their raw field names.
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


class DocType(str, Enum):
    """
    Distinguishes governing rules from ordinary company data.

    Without this, an employee's own salary record could be retrieved and handed
    to the judge as if it were policy authority.
    """
    POLICY = "policy"
    RULE = "rule"
    PRIVACY_POLICY = "privacy_policy"
    COMPANY_DATA = "company_data"
    UNKNOWN = "unknown"

    @property
    def is_governing(self) -> bool:
        """True for chunks that may be used as authority in a decision."""
        return self in (DocType.POLICY, DocType.RULE, DocType.PRIVACY_POLICY)


class ThresholdUnit(str, Enum):
    PERCENT = "percent"
    ABSOLUTE = "absolute"
    DAYS = "days"


class PolicyMeta(BaseModel):
    """
    Normalised metadata for one retrieved policy chunk.

    `applies_to_actions` holds names from `core.actions.action_registry` and is
    what makes deterministic retrieval possible: the governing rules for an
    action are fetched by database predicate, not by hoping similarity ranked
    them into the top-k.
    """
    policy_id: str
    doc_type: DocType = DocType.UNKNOWN
    title: str = ""
    applies_to_actions: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    mandatory: bool = False              # always retrieved, ignores similarity
    version: str = "1.0"
    effective_date: str | None = None
    expires_date: str | None = None
    is_current: bool = True              # False ⇒ superseded, must not decide
    section: str | None = None           # clause ref, e.g. "2.4", for citation
    source_document: str | None = None

    # Optional structured conditions. When present these are evaluated in Python
    # rather than by the judge — a model comparing 15% against a 20% threshold is
    # unreliable in a way that an arithmetic comparison is not.
    threshold_value: float | None = None
    threshold_unit: ThresholdUnit | None = None
    requires_role: list[str] = Field(default_factory=list)

    # Reject unknown keys: front-matter is built with **kwargs, and a misspelled
    # tag (`applies_to_tools` for `applies_to_actions`) would otherwise be dropped
    # silently — leaving a policy that never matches anything, with no error.
    model_config = {"extra": "forbid"}

    @property
    def citation(self) -> str:
        """Stable reference for the audit trail."""
        base = f"{self.policy_id}@{self.version}"
        return f"{base}#{self.section}" if self.section else base

    @property
    def has_structured_condition(self) -> bool:
        return self.threshold_value is not None or bool(self.requires_role)

    def to_payload(self) -> dict[str, Any]:
        """
        Flat dict for a Qdrant point payload.

        Used only by the offline fixture generator — production ingestion is
        owned by the data-transport layer, not by this module.
        """
        return {
            "doc_type": self.doc_type.value,
            "policy_id": self.policy_id,
            "title": self.title,
            "applies_to_actions": self.applies_to_actions,
            "risk_level": self.risk_level.value,
            "mandatory": self.mandatory,
            "version": self.version,
            "effective_date": self.effective_date,
            "expires_date": self.expires_date,
            "is_current": self.is_current,
            "section": self.section,
            "source_document": self.source_document,
            "threshold_value": self.threshold_value,
            "threshold_unit": self.threshold_unit.value if self.threshold_unit else None,
            "requires_role": self.requires_role,
        }


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"                    # escalate to a human


class PolicyVerdict(BaseModel):
    """
    Outcome of the policy gate.

    `allowed_actions` is consumed by the execution gate: approving an intent is
    not the same as authorising whichever action the model then selected.
    """
    decision: PolicyDecision
    reason: str
    allowed_actions: list[str] = Field(default_factory=list)
    cited_policies: list[str] = Field(default_factory=list)   # policy_id@version#section
    retrieved_count: int = 0             # how many chunks the judge actually saw
    judge_model: str | None = None       # recorded for audit reproducibility

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    @classmethod
    def denied(cls, reason: str, **kw: Any) -> "PolicyVerdict":
        """Fail-closed constructor — used whenever the judge cannot be trusted."""
        return cls(decision=PolicyDecision.DENY, reason=reason, **kw)
