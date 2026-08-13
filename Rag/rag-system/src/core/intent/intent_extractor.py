"""
IntentExtractor — natural language in, one registered action name out.

Two jobs, in order:

  1. CLASSIFY   is this prompt asking a question, or asking for something to be done?
                "what is our payment limit?"  → question, answered from policy text
                "pay invoice 8842"            → action, gated

  2. EXTRACT    map the request to exactly one name from the action registry and
                pull its parameters out of the text.

The model's freedom is bounded on both sides. It may only choose a registered
name — an unregistered name is a refusal, not a new capability — and the
parameters it produces are validated against that action's JSON Schema before
any policy work begins. A malformed request is rejected without ever reaching
the rule store.

Nothing here touches Qdrant. If this stage refuses, no retrieval happens at all.
"""
import json
import logging
import re

from src.core.actions.action_registry import ActionSpec, action_names, all_actions, get_action
from src.core.llm.llm_service import get_llm

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class IntentError(Exception):
    """Extraction failed. Always fatal to the request — never retried loosely."""


class Intent:
    def __init__(
        self,
        request_type: str,
        action: str | None = None,
        parameters: dict | None = None,
        confidence: str = "high",
        note: str = "",
    ) -> None:
        self.request_type = request_type      # "action" | "question" | "unclear"
        self.action = action
        self.parameters = parameters or {}
        self.confidence = confidence
        self.note = note

    @property
    def spec(self) -> ActionSpec | None:
        return get_action(self.action) if self.action else None


def _catalogue() -> str:
    lines = []
    for spec in all_actions():
        params = ", ".join(spec.params_schema.get("properties", {}))
        lines.append(f"  {spec.name.value}: {spec.description} (params: {params})")
    return "\n".join(lines)


_PROMPT = """\
You classify requests for an ERP finance system. Reply with JSON only, no prose.

Available actions:
{catalogue}

Decide:
- "question" if the user is asking for information, policy, or an explanation.
- "action" if the user is asking for something to be done or changed.
- "unclear" if you cannot tell, or if the request does not correspond to any
  action listed above. Never invent an action name that is not in the list.

Extract parameters only where the user actually stated them. Do not guess an
invoice number, an amount, or a vendor that is not present in the request.

Reply exactly:
{{"request_type": "action|question|unclear",
  "action": "<name from the list, or null>",
  "parameters": {{}},
  "confidence": "high|low"}}

Request: {prompt}
"""


def _parse(raw: str) -> dict:
    match = _JSON_BLOCK.search(raw)
    if not match:
        raise IntentError(f"model returned no JSON object: {raw[:200]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise IntentError(f"model returned malformed JSON: {exc}") from exc


# Placeholders models emit for "the user didn't say". They must be stripped, not
# passed on: the caller executes with these parameters, and a vendor_id of the
# string "None" is a value that looks supplied and is not — worse than absent,
# because a missing field is caught by the schema and this one isn't.
_EMPTY_VALUES = {"none", "null", "n/a", "na", "unknown", "unspecified", "", "-"}


def _drop_empty(params: dict) -> dict:
    return {
        k: v
        for k, v in params.items()
        if v is not None and not (isinstance(v, str) and v.strip().lower() in _EMPTY_VALUES)
    }


def validate_parameters(spec: ActionSpec, params: dict) -> list[str]:
    """
    Check extracted parameters against the action's JSON Schema.

    Deliberately a small hand-rolled subset (required / oneOf / type /
    additionalProperties) rather than a schema library: these are the constraints
    the registry actually uses, and a failure here must be a clear message the
    caller can act on, not a nested validator trace.
    """
    problems: list[str] = []
    schema = spec.params_schema
    properties: dict = schema.get("properties", {})

    for key in params:
        if key not in properties and schema.get("additionalProperties") is False:
            problems.append(f"unknown parameter '{key}'")

    for key in schema.get("required", []):
        if key not in params or params[key] in (None, ""):
            problems.append(f"missing required parameter '{key}'")

    one_of = schema.get("oneOf")
    if one_of:
        matched = [
            branch for branch in one_of
            if all(r in params and params[r] not in (None, "") for r in branch.get("required", []))
        ]
        if len(matched) != 1:
            options = " or ".join(
                "+".join(b.get("required", [])) for b in one_of
            )
            problems.append(
                f"exactly one of ({options}) must be supplied, got {len(matched)}"
            )

    for key, value in params.items():
        expected = properties.get(key, {}).get("type")
        if expected == "number" and isinstance(value, str):
            # The model often returns "1450000" for a number field; accept it if
            # it is unambiguously numeric, reject anything needing interpretation.
            try:
                params[key] = float(value.replace(",", ""))
            except ValueError:
                problems.append(f"parameter '{key}' must be a number, got {value!r}")
        elif expected == "string" and not isinstance(value, str):
            params[key] = str(value)

    return problems


async def extract(prompt: str) -> Intent:
    """
    Classify and extract. Raises IntentError when the model output is unusable.

    A prompt naming no registered action returns request_type="unclear" rather
    than a best guess: executing the nearest-sounding action is how an assistant
    pays the wrong invoice.
    """
    llm = get_llm()
    message = _PROMPT.format(catalogue=_catalogue(), prompt=prompt)
    response = await llm.ainvoke(message)
    data = _parse(getattr(response, "content", str(response)))

    request_type = str(data.get("request_type", "unclear")).lower().strip()
    if request_type not in ("action", "question", "unclear"):
        request_type = "unclear"

    action = data.get("action")
    action = str(action).strip() if action else None

    if request_type == "action":
        if not action or action not in action_names():
            logger.warning(
                f"model proposed unregistered action {action!r} — treating as unclear"
            )
            return Intent(
                request_type="unclear",
                note=f"'{action}' is not a registered action",
            )

    params = data.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}
    params = _drop_empty(params)

    confidence = "low" if str(data.get("confidence", "")).lower() == "low" else "high"

    logger.info(
        f"intent: type={request_type} action={action} "
        f"params={list(params)} confidence={confidence}"
    )
    return Intent(request_type, action, params, confidence)
