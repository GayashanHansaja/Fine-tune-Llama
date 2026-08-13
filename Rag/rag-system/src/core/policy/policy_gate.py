"""
PolicyGate — the orchestrator behind POST /api/policy/evaluate.

    prompt + actor
        ↓  classify + extract     (LLM, bounded by the action registry)
        ↓  validate parameters    (JSON Schema, deterministic)
        ↓  retrieve               (three-query union over Qdrant)
        ↓  rule engine            (thresholds / roles / segregation, deterministic)
        ↓  judge                  (narrative clauses only, must cite)
    verdict + action + conditions + citations

The caller executes; this module never does. Its whole output is a
recommendation with the authority attached.

FAILURE POSTURE
Every stage that cannot complete produces a denial, not an exception and not a
default-allow. Concretely: an unreachable Qdrant denies, an unreachable judge
denies, an unparseable model reply denies, an action with no policy coverage
denies. The one thing this module must never do is return an executable verdict
derived from rules it did not actually read.
"""
import logging
import uuid

from src.core.actions.action_registry import REGISTRY_VERSION, get_action
from src.core.intent import intent_extractor
from src.core.policy import judge as judge_module
from src.core.policy import rule_engine
from src.core.policy.policy_retriever import RetrievalResult, get_policy_retriever
from src.types.gateway import (
    AuditRecord,
    EvaluateRequest,
    EvaluateResponse,
    ProposedAction,
    RequestType,
    RetrievalStats,
)
from src.types.policy import Condition, PolicyDecision

logger = logging.getLogger(__name__)


def _stats(result: RetrievalResult | None) -> RetrievalStats:
    if result is None:
        return RetrievalStats()
    return RetrievalStats(
        mandatory=result.counts["mandatory"],
        action_filtered=result.counts["action"],
        semantic=result.counts["semantic"],
        total_unique=result.total_unique,
    )


def _refuse(
    request_id: str,
    reason: str,
    request_type: RequestType = RequestType.UNCLEAR,
    **kw,
) -> EvaluateResponse:
    # A caller that has already built an audit record (one that knows which
    # policies were seen) keeps it; only a refusal with no history gets the bare one.
    kw.setdefault("audit", AuditRecord(registry_version=REGISTRY_VERSION))
    return EvaluateResponse(
        request_id=request_id,
        request_type=request_type,
        decision=PolicyDecision.DENY,
        reason=reason,
        **kw,
    )


async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    """
    Decide one request. Never raises — a failure is a denial with a reason.

    The guard is here, around everything, rather than only on the steps we
    currently expect to fail. Each stage below handles its own known failures
    and phrases them usefully; this catches the rest. An unforeseen exception
    escaping to the caller would surface as a transport error, and a caller
    holding a pending payment and an HTTP 500 is exactly the state the gate
    exists to prevent — the answer to "we don't know" must be a denial, not
    an absence of one.
    """
    try:
        return await _evaluate(request)
    except Exception as exc:  # noqa: BLE001 — every unhandled failure is one failure
        logger.exception("policy gate failed")
        return _refuse(
            str(uuid.uuid4()),
            f"The policy gate could not complete this decision "
            f"({type(exc).__name__}); the action is not authorized.",
        )


async def _evaluate(request: EvaluateRequest) -> EvaluateResponse:
    request_id = str(uuid.uuid4())
    prompt = request.prompt.strip()
    actor = request.actor

    logger.info(f"[{request_id}] evaluate | actor={actor.user_id}/{actor.role} | {prompt[:80]!r}")

    # ── 1. Classify and extract ───────────────────────────────────────────────
    try:
        intent = await intent_extractor.extract(prompt)
    except intent_extractor.IntentError as exc:
        return _refuse(request_id, f"Could not interpret the request: {exc}")
    except Exception as exc:  # noqa: BLE001 — model/transport failures look alike
        logger.exception("intent extraction failed")
        return _refuse(
            request_id,
            f"Language model unavailable ({type(exc).__name__}); the request "
            f"cannot be interpreted.",
        )

    if intent.request_type == "question":
        return await _answer_question(request_id, prompt, request)

    if intent.request_type != "action" or not intent.action:
        return _refuse(
            request_id,
            intent.note
            or "The request does not correspond to any action this system can perform.",
        )

    spec = get_action(intent.action)
    if spec is None:
        # Belt and braces: extractor already rejects unregistered names.
        return _refuse(request_id, f"'{intent.action}' is not a registered action.")

    # ── 2. Validate parameters ────────────────────────────────────────────────
    problems = intent_extractor.validate_parameters(spec, intent.parameters)
    if problems:
        return _refuse(
            request_id,
            "The request is missing information needed to act on it: "
            + "; ".join(problems),
            request_type=RequestType.ACTION,
            action=ProposedAction(
                name=spec.name.value,
                parameters=intent.parameters,
                confidence=intent.confidence,
            ),
        )

    proposed = ProposedAction(
        name=spec.name.value,
        parameters=intent.parameters,
        confidence=intent.confidence,
    )

    # ── 3. Retrieve governing rules ───────────────────────────────────────────
    try:
        retrieved = get_policy_retriever().retrieve(spec.name.value, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("policy retrieval failed")
        return _refuse(
            request_id,
            f"Policy store unavailable ({type(exc).__name__}); no action can be "
            f"authorized without reading the rules that govern it.",
            request_type=RequestType.ACTION,
            action=proposed,
        )

    if retrieved.counts["action"] == 0:
        return _refuse(
            request_id,
            f"No current policy governs '{spec.name.value}'. An action with no "
            f"governing rule cannot be authorized.",
            request_type=RequestType.ACTION,
            action=proposed,
            retrieval=_stats(retrieved),
            audit=AuditRecord(
                registry_version=REGISTRY_VERSION, policies_seen=retrieved.policy_refs
            ),
        )

    # ── 4. Deterministic checks ───────────────────────────────────────────────
    outcome = rule_engine.evaluate(spec, retrieved.chunks, actor, request.context)

    if outcome.hard_denials:
        reason, source = outcome.hard_denials[0]
        return EvaluateResponse(
            request_id=request_id,
            request_type=RequestType.ACTION,
            decision=PolicyDecision.DENY,
            reason=reason,
            action=proposed,
            conditions=outcome.conditions,
            citations=_citations_for(source, retrieved),
            retrieval=_stats(retrieved),
            audit=AuditRecord(
                registry_version=REGISTRY_VERSION, policies_seen=retrieved.policy_refs
            ),
        )

    # ── 5. Judge the rest ─────────────────────────────────────────────────────
    verdict = await judge_module.judge(
        action=spec.name.value,
        parameters=intent.parameters,
        prompt=prompt,
        actor=actor,
        chunks=retrieved.chunks,
        established_facts=_facts(outcome.conditions),
    )

    decision = verdict.decision

    # The judge may only narrow. Where it allows but conditions remain unmet, the
    # result is conditional — never a bare allow, because "we could not check the
    # amount" and "the amount is within the limit" are different answers.
    if decision == PolicyDecision.ALLOW and outcome.unmet:
        decision = PolicyDecision.ALLOW_WITH_CONDITIONS

    reason = verdict.reason
    if decision == PolicyDecision.ALLOW_WITH_CONDITIONS and outcome.unmet:
        reason = f"{reason} {len(outcome.unmet)} condition(s) must be satisfied before executing."

    citations = verdict.citations
    if not citations and decision != PolicyDecision.ALLOW:
        # A refusal has to say which rule refused. The judge sometimes names a
        # policy in its prose without emitting it as a structured reference, which
        # leaves the requester told "no" with nothing to look up and the audit
        # trail with nothing to check. Fall back to the rules whose conditions did
        # not pass — those are the grounds, whether or not the judge listed them.
        citations = _citations_for_unmet(outcome, retrieved)

    return EvaluateResponse(
        request_id=request_id,
        request_type=RequestType.ACTION,
        decision=decision,
        reason=reason,
        action=proposed,
        conditions=outcome.conditions,
        citations=citations,
        knowledge=_knowledge(retrieved),
        retrieval=_stats(retrieved),
        audit=AuditRecord(
            judge_model=verdict.model,
            registry_version=REGISTRY_VERSION,
            policies_seen=retrieved.policy_refs,
        ),
    )


def _facts(conditions: list[Condition]) -> list[str]:
    """
    Settled numeric results, phrased for the judge.

    Only conditions we actually checked are passed on. An unchecked condition is
    withheld deliberately — telling the judge "the limit is 1,000,000" without
    telling it the amount invites it to do the arithmetic we removed from it.
    """
    facts = []
    for condition in conditions:
        if condition.satisfied is None:
            continue
        state = "SATISFIED" if condition.satisfied else "NOT SATISFIED"
        facts.append(f"{condition.description} [{state}, per {condition.source}]")
    return facts


def _citations_for(source: str, retrieved: RetrievalResult):
    """Build a citation for a deterministic denial from the chunk it came from."""
    from src.types.policy import Citation

    for chunk in retrieved.chunks:
        if chunk.meta.citation == source or chunk.meta.policy_id == source.split("@")[0]:
            return [
                Citation(
                    policy_id=chunk.meta.policy_id,
                    version=chunk.meta.version,
                    section=chunk.meta.section,
                    title=chunk.meta.title,
                    quote=chunk.text[:300],
                )
            ]
    return []


def _citations_for_unmet(outcome, retrieved: RetrievalResult):
    """Citations for every rule whose condition did not pass, in condition order."""
    citations = []
    seen: set[str] = set()
    for condition in outcome.unmet:
        if condition.source in seen or condition.source == "unattributed":
            continue
        seen.add(condition.source)
        citations.extend(_citations_for(condition.source, retrieved))
    return citations


def _knowledge(retrieved: RetrievalResult) -> str:
    """
    The rules relied upon, named for the end user.

    Headings only, and only for chunks retrieved by filter. This is a reference
    list, not an explanation — the explanation is `reason`, and the clause text
    itself may be subject to the disclosure limits in the privacy policy.
    """
    lines = []
    seen: set[str] = set()
    for chunk in retrieved.chunks:
        if chunk.via == "semantic" or chunk.meta.policy_id in seen:
            continue
        seen.add(chunk.meta.policy_id)
        lines.append(f"{chunk.meta.policy_id}@{chunk.meta.version} — {chunk.meta.title}")
    return "\n".join(lines[:8])


# ── Question path ────────────────────────────────────────────────────────────


async def _answer_question(
    request_id: str, prompt: str, request: EvaluateRequest
) -> EvaluateResponse:
    """
    Answer a policy question from the policy collection.

    Retrieval here is semantic — there is no action to filter on — but it stays
    inside `policy_docs` with the same doc_type and is_current filters, so a
    question can never be answered out of company data or a superseded rule.
    """
    try:
        chunks = get_policy_retriever().search_semantic(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("question retrieval failed")
        return _refuse(
            request_id,
            f"Policy store unavailable ({type(exc).__name__}).",
            request_type=RequestType.QUESTION,
        )

    if not chunks:
        return EvaluateResponse(
            request_id=request_id,
            request_type=RequestType.QUESTION,
            decision=PolicyDecision.ANSWER,
            reason="No policy in the knowledge base addresses this question.",
            audit=AuditRecord(registry_version=REGISTRY_VERSION),
        )

    from src.types.policy import Citation

    return EvaluateResponse(
        request_id=request_id,
        request_type=RequestType.QUESTION,
        decision=PolicyDecision.ANSWER,
        reason="Informational answer — no action was requested, so nothing is authorized.",
        knowledge="\n\n".join(f"{c.meta.citation}: {c.text}" for c in chunks[:4]),
        citations=[
            Citation(
                policy_id=c.meta.policy_id,
                version=c.meta.version,
                section=c.meta.section,
                title=c.meta.title,
                quote=c.text[:300],
            )
            for c in chunks[:4]
        ],
        retrieval=RetrievalStats(semantic=len(chunks), total_unique=len(chunks)),
        audit=AuditRecord(registry_version=REGISTRY_VERSION),
    )
