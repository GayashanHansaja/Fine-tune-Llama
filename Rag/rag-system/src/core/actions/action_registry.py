"""
Action registry — the canonical vocabulary of everything this module can do.

This registry is a PUBLISHED CONTRACT, not an internal detail:

  • The data-transport layer tags each policy chunk with `applies_to_actions`
    drawn from these exact names.  A typo there means a policy silently stops
    applying, so the names must be treated as a stable, versioned interface.
  • Intent extraction is constrained to these names — the model cannot invent
    an action that isn't registered.
  • The execution gate checks the chosen name against this registry before any
    MCP tool is invoked.

Adding an action is a coordinated change: register it here, then have the
policy corpus re-tagged, or the new action runs with no policy coverage.
"""
from enum import Enum
from typing import Any

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

from src.types.policy import RiskLevel

REGISTRY_VERSION = "0.1.0"


class ActionName(str, Enum):
    """Canonical action identifiers. Values are what the policy corpus tags against."""

    # ── Compensation ──────────────────────────────────────────────────────────
    INCREASE_SALARY = "increase_salary"
    DECREASE_SALARY = "decrease_salary"
    ISSUE_BONUS = "issue_bonus"

    # ── Employment lifecycle ──────────────────────────────────────────────────
    PROMOTE_EMPLOYEE = "promote_employee"
    TRANSFER_DEPARTMENT = "transfer_department"
    TERMINATE_EMPLOYEE = "terminate_employee"

    # ── Leave ─────────────────────────────────────────────────────────────────
    APPROVE_LEAVE = "approve_leave"
    REJECT_LEAVE = "reject_leave"

    # ── Sensitive records ─────────────────────────────────────────────────────
    UPDATE_BANK_DETAILS = "update_bank_details"
    VIEW_SALARY_RECORD = "view_salary_record"


class ActionSpec(BaseModel):
    """
    One registered action.

    `params_schema` is JSON Schema and is enforced deterministically after intent
    extraction — the model proposes parameters, this schema decides whether they
    are even well-formed before any policy reasoning happens.
    """
    name: ActionName
    description: str
    params_schema: dict[str, Any]
    risk: RiskLevel
    financial: bool = False          # touches money → stricter thresholds apply
    mutates_pii: bool = False        # touches personal data → privacy policy applies
    self_target_forbidden: bool = True   # actor may not target themselves

    @property
    def is_mutation(self) -> bool:
        return self.name != ActionName.VIEW_SALARY_RECORD


def _employee_target() -> dict[str, Any]:
    return {
        "type": "string",
        "description": "Employee ID of the person the action applies to",
        "minLength": 1,
    }


_SPECS: dict[ActionName, ActionSpec] = {
    ActionName.INCREASE_SALARY: ActionSpec(
        name=ActionName.INCREASE_SALARY,
        description="Raise an employee's base salary by an absolute amount or a percentage.",
        risk=RiskLevel.HIGH,
        financial=True,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                # Exactly one of these must be supplied — an ambiguous
                # "increase from 50000" must not be silently coerced.
                "amount": {"type": "number", "exclusiveMinimum": 0},
                "percentage": {"type": "number", "exclusiveMinimum": 0, "maximum": 100},
                "effective_date": {"type": "string", "format": "date"},
                "reason": {"type": "string"},
            },
            "required": ["employee_id"],
            "oneOf": [{"required": ["amount"]}, {"required": ["percentage"]}],
            "additionalProperties": False,
        },
    ),
    ActionName.DECREASE_SALARY: ActionSpec(
        name=ActionName.DECREASE_SALARY,
        description="Reduce an employee's base salary.",
        risk=RiskLevel.CRITICAL,
        financial=True,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "amount": {"type": "number", "exclusiveMinimum": 0},
                "percentage": {"type": "number", "exclusiveMinimum": 0, "maximum": 100},
                "effective_date": {"type": "string", "format": "date"},
                "reason": {"type": "string"},
            },
            "required": ["employee_id", "reason"],
            "oneOf": [{"required": ["amount"]}, {"required": ["percentage"]}],
            "additionalProperties": False,
        },
    ),
    ActionName.ISSUE_BONUS: ActionSpec(
        name=ActionName.ISSUE_BONUS,
        description="Grant a one-time bonus payment to an employee.",
        risk=RiskLevel.HIGH,
        financial=True,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "amount": {"type": "number", "exclusiveMinimum": 0},
                "reason": {"type": "string"},
            },
            "required": ["employee_id", "amount"],
            "additionalProperties": False,
        },
    ),
    ActionName.PROMOTE_EMPLOYEE: ActionSpec(
        name=ActionName.PROMOTE_EMPLOYEE,
        description="Change an employee's job title or grade.",
        risk=RiskLevel.HIGH,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "new_title": {"type": "string", "minLength": 1},
                "new_grade": {"type": "string"},
                "effective_date": {"type": "string", "format": "date"},
            },
            "required": ["employee_id", "new_title"],
            "additionalProperties": False,
        },
    ),
    ActionName.TRANSFER_DEPARTMENT: ActionSpec(
        name=ActionName.TRANSFER_DEPARTMENT,
        description="Move an employee to a different department.",
        risk=RiskLevel.MEDIUM,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "target_department": {"type": "string", "minLength": 1},
                "effective_date": {"type": "string", "format": "date"},
            },
            "required": ["employee_id", "target_department"],
            "additionalProperties": False,
        },
    ),
    ActionName.TERMINATE_EMPLOYEE: ActionSpec(
        name=ActionName.TERMINATE_EMPLOYEE,
        description="End an employee's employment.",
        risk=RiskLevel.CRITICAL,
        financial=True,
        mutates_pii=True,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "termination_date": {"type": "string", "format": "date"},
                "reason": {"type": "string", "minLength": 1},
            },
            "required": ["employee_id", "termination_date", "reason"],
            "additionalProperties": False,
        },
    ),
    ActionName.APPROVE_LEAVE: ActionSpec(
        name=ActionName.APPROVE_LEAVE,
        description="Approve a pending leave request.",
        risk=RiskLevel.LOW,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "leave_request_id": {"type": "string", "minLength": 1},
            },
            "required": ["leave_request_id"],
            "additionalProperties": False,
        },
    ),
    ActionName.REJECT_LEAVE: ActionSpec(
        name=ActionName.REJECT_LEAVE,
        description="Reject a pending leave request.",
        risk=RiskLevel.LOW,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "leave_request_id": {"type": "string", "minLength": 1},
                "reason": {"type": "string"},
            },
            "required": ["leave_request_id"],
            "additionalProperties": False,
        },
    ),
    ActionName.UPDATE_BANK_DETAILS: ActionSpec(
        name=ActionName.UPDATE_BANK_DETAILS,
        description="Change the bank account salary is paid into.",
        risk=RiskLevel.CRITICAL,
        financial=True,
        mutates_pii=True,
        params_schema={
            "type": "object",
            "properties": {
                "employee_id": _employee_target(),
                "account_number": {"type": "string", "minLength": 1},
                "bank_code": {"type": "string"},
            },
            "required": ["employee_id", "account_number"],
            "additionalProperties": False,
        },
    ),
    ActionName.VIEW_SALARY_RECORD: ActionSpec(
        name=ActionName.VIEW_SALARY_RECORD,
        description="Read an employee's compensation record.",
        risk=RiskLevel.MEDIUM,
        mutates_pii=True,
        self_target_forbidden=False,   # viewing your own record is normal
        params_schema={
            "type": "object",
            "properties": {"employee_id": _employee_target()},
            "required": ["employee_id"],
            "additionalProperties": False,
        },
    ),
}


def get_action(name: str) -> ActionSpec | None:
    """Look up a registered action. Returns None for anything unregistered."""
    try:
        return _SPECS[ActionName(name)]
    except (ValueError, KeyError):
        return None


def all_actions() -> list[ActionSpec]:
    return list(_SPECS.values())


def action_names() -> list[str]:
    """The exact strings the policy corpus must tag against."""
    return [a.value for a in ActionName]
