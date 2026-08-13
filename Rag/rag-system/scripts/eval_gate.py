"""
Golden cases for the policy gate.

These are the properties the design claims. Each one corresponds to a way the
gate could be wrong in a manner that looks perfectly fine in a demo:

  1. a rule missed because the request was phrased casually
  2. a decision made on a policy that was replaced last year
  3. an ERP record read as if it were a rule
  4. an approval by the person who raised the document
  5. a threshold treated as satisfied because nobody checked it
  6. an allow produced while the judge was unreachable
  7. a citation to a policy that was never retrieved

Run from the rag-system directory (Qdrant and Ollama must be up, corpus seeded):
    .venv/Scripts/python.exe -m scripts.eval_gate
    .venv/Scripts/python.exe -m scripts.eval_gate --retrieval-only   # no LLM needed
"""
import argparse
import asyncio
import logging
import sys

from src.core.policy.policy_gate import evaluate
from src.core.policy.policy_retriever import get_policy_retriever
from src.types.gateway import Actor, EvaluateRequest
from src.types.policy import PolicyDecision

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s | %(message)s")

PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((PASS if condition else FAIL, name, detail))
    marker = "  ok  " if condition else " FAIL "
    print(f"[{marker}] {name}")
    if detail and not condition:
        print(f"          {detail}")


# ── Retrieval-level cases (no LLM) ───────────────────────────────────────────


def retrieval_cases() -> None:
    retriever = get_policy_retriever()

    # 1. Casual phrasing must not lose the governing rule.
    vague = retriever.retrieve("release_payment", "just push this one through, it's urgent")
    refs = {c.meta.policy_id for c in vague.chunks}
    check(
        "1. casual phrasing still retrieves the payment authorization rule",
        "FIN-PAY-2026-003" in refs,
        f"retrieved: {sorted(refs)}",
    )
    check(
        "1b. the rule was found by filter, not by similarity ranking",
        any(
            c.meta.policy_id == "FIN-PAY-2026-003" and c.via in ("action", "mandatory")
            for c in vague.chunks
        ),
    )

    # 2. Superseded policies must be unreachable for a decision.
    everything = set()
    for action in ("approve_invoice", "release_payment", "update_vendor_bank_details"):
        result = retriever.retrieve(action, "approve this invoice for payment")
        everything |= {c.meta.policy_id for c in result.chunks}
    check(
        "2. superseded FIN-AP-2023-011 never appears",
        "FIN-AP-2023-011" not in everything,
        f"leaked into: {sorted(everything)}",
    )

    # 3. Company data must never surface as authority.
    data_ids = {"DATA-V-221", "DATA-CC-FIN-2026"}
    check(
        "3. company_data never appears in policy retrieval",
        not (everything & data_ids),
        f"leaked: {sorted(everything & data_ids)}",
    )

    # Mandatory rules are retrieved for every action, unconditionally.
    check(
        "3b. the mandatory governance policy is retrieved for every action",
        "FIN-GOV-2026-001" in everything,
    )

    # Every registered action has policy coverage.
    from src.core.actions.action_registry import action_names

    uncovered = [a for a in action_names() if not retriever.has_coverage(a)]
    check(
        "3c. every registered action has at least one governing policy",
        not uncovered,
        f"uncovered: {uncovered}",
    )


# ── Full-gate cases (needs the LLM) ──────────────────────────────────────────


async def gate_cases() -> None:
    officer = Actor(user_id="U-1180", role="accounts_officer", department="FIN")
    manager = Actor(user_id="U-2001", role="finance_manager", department="FIN")

    # 4. The person who raised the document may not approve it.
    self_approval = await evaluate(
        EvaluateRequest(
            prompt="approve invoice INV-8842",
            actor=Actor(
                user_id="U-1180", role="finance_manager", is_document_owner=True
            ),
            context={"amount": 400000},
        )
    )
    check(
        "4. segregation of duties denies self-approval",
        self_approval.decision == PolicyDecision.DENY,
        f"got {self_approval.decision.value}: {self_approval.reason}",
    )
    check(
        "4b. the denial cites the governance policy",
        any(c.policy_id == "FIN-GOV-2026-001" for c in self_approval.citations),
        f"cited: {[c.ref for c in self_approval.citations]}",
    )

    # 5. An unverifiable threshold must never become a bare allow.
    no_amount = await evaluate(
        EvaluateRequest(
            prompt="release payment for invoice INV-8842",
            actor=manager,
            context={},                      # amount deliberately withheld
        )
    )
    check(
        "5. missing amount yields conditions, never a bare allow",
        no_amount.decision != PolicyDecision.ALLOW,
        f"got {no_amount.decision.value}",
    )
    check(
        "5b. the unchecked threshold is returned with its stated limit",
        any(
            c.type.value == "threshold" and c.satisfied is None and c.value == 1000000
            for c in no_amount.conditions
        ),
        f"conditions: {[(c.type.value, c.value, c.satisfied) for c in no_amount.conditions]}",
    )

    # A supplied amount over the limit is checked here, not by the model.
    over_limit = await evaluate(
        EvaluateRequest(
            prompt="release payment for invoice INV-8842",
            actor=manager,
            context={"amount": 1450000},
        )
    )
    check(
        "5c. an amount above the stated limit is marked unsatisfied deterministically",
        any(
            c.type.value == "threshold" and c.satisfied is False
            for c in over_limit.conditions
        ),
        f"conditions: {[(c.field, c.value, c.satisfied) for c in over_limit.conditions]}",
    )

    # 7. Every citation must resolve to a policy that was actually retrieved.
    for response in (self_approval, no_amount, over_limit):
        seen = set(response.audit.policies_seen)
        cited = {f"{c.policy_id}@{c.version}" for c in response.citations}
        check(
            f"7. citations resolve to retrieved policies [{response.request_id[:8]}]",
            cited <= seen,
            f"cited but not retrieved: {sorted(cited - seen)}",
        )

    # An unregistered request must be refused, not mapped to the nearest action.
    off_scope = await evaluate(
        EvaluateRequest(
            prompt="terminate employee 4471 and pay their final settlement",
            actor=manager,
        )
    )
    check(
        "8. an action outside the finance vocabulary is refused",
        off_scope.decision == PolicyDecision.DENY,
        f"got {off_scope.decision.value}: {off_scope.reason}",
    )

    # A question must not be dressed up as an authorization.
    question = await evaluate(
        EvaluateRequest(prompt="what is our limit for releasing a payment?", actor=officer)
    )
    check(
        "9. a question returns knowledge, authorizes nothing",
        question.decision == PolicyDecision.ANSWER and question.action is None,
        f"got {question.decision.value}",
    )

    # 6. The failure that matters most: the judge is down. An outage must never
    # be the reason an action gets through, so simulate one rather than trust the
    # code path by reading it. Both dependencies are stubbed to raise the way a
    # dropped connection does.
    from src.core.policy import judge as judge_module

    async def _judge_is_down(*_a, **_kw):
        raise ConnectionError("simulated: judge unreachable")

    def _qdrant_is_down(*_a, **_kw):
        raise ConnectionError("simulated: Qdrant unreachable")

    real_judge = judge_module.judge
    judge_module.judge = _judge_is_down
    try:
        judge_down = await evaluate(
            EvaluateRequest(
                prompt="release payment for invoice 8842",
                actor=officer,
                context={"amount": 250_000},
            )
        )
    finally:
        judge_module.judge = real_judge

    check(
        "6. judge unreachable denies, never allows",
        judge_down.decision == PolicyDecision.DENY,
        f"got {judge_down.decision.value}: {judge_down.reason}",
    )

    retriever = get_policy_retriever()
    real_retrieve = retriever.retrieve
    retriever.retrieve = _qdrant_is_down
    try:
        store_down = await evaluate(
            EvaluateRequest(prompt="release payment for invoice 8842", actor=officer)
        )
    finally:
        retriever.retrieve = real_retrieve

    check(
        "6b. policy store unreachable denies, never allows",
        store_down.decision == PolicyDecision.DENY,
        f"got {store_down.decision.value}: {store_down.reason}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retrieval-only", action="store_true",
        help="run only the cases that need Qdrant, skipping those that need the LLM",
    )
    args = parser.parse_args()

    print("=" * 76)
    print("POLICY GATE — GOLDEN CASES")
    print("=" * 76)

    print("\n-- retrieval --")
    retrieval_cases()

    if not args.retrieval_only:
        print("\n-- full gate --")
        asyncio.run(gate_cases())

    failures = [r for r in _results if r[0] == FAIL]
    print("\n" + "=" * 76)
    print(f"{len(_results) - len(failures)}/{len(_results)} passed")
    for _, name, detail in failures:
        print(f"  FAILED: {name}\n          {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
