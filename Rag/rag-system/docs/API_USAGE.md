# API Usage — ERP Finance Policy Gate

**What this service does:** decides whether a natural-language finance request
is permitted under company policy, and returns the verdict plus what the
caller needs to execute it. **It never executes anything itself** — no MCP
calls, no ERP writes, no credentials to any system of record.

```
prompt -> intent -> retrieve rules -> deterministic checks -> judge -> verdict
```

Three ways to reach it: REST, MCP, and a browser demo. All three end up
calling the same `policy_gate.evaluate()` — there is one decision path, not
three.

---

## Auth

Every endpoint except `/health` requires a header:

```
X-API-Key: <your-api-key>
```

Get the current key from whoever holds the deployment secrets — it's stored
as an Azure Container Apps secret (`gate-key`), never committed to the repo.
Locally, it's whatever `API_KEYS` is set to in your `.env` (unset = auth
disabled, fine for `localhost` only).

A missing or wrong key returns `401` with no indication of which — deliberately,
so a caller can't probe for a partially-correct key.

Multiple keys can be issued (comma-separated in `API_KEYS`), one per caller
system, all equally privileged — there's no per-key scope or rate limit.

---

## Base URL

azure base url

---

## `POST /api/policy/evaluate` — the main endpoint

Send a request, get a decision.

### Request

```json
{
  "prompt": "release payment for invoice INV-8842",
  "actor": {
    "user_id": "U-1001",
    "role": "finance_manager",
    "department": "finance",
    "is_document_owner": false
  },
  "context": {
    "amount": 1450000,
    "currency": "LKR"
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `prompt` | yes | Natural language. Free text. |
| `actor.user_id` | yes | Caller-side identifier, for audit only — carries no policy weight. |
| `actor.role` | yes | **Must come from your authenticated session, never from the prompt.** Every threshold, role, and segregation check is decided against this string. A role claimed in the prompt is a claim, not an identity — this service cannot verify it and trusts it completely. |
| `actor.department` | no | |
| `actor.is_document_owner` | no | Set when the requester raised or benefits from the target document (segregation-of-duties check). **Omit if unknown** — it comes back as an unmet condition, never assumed `false`. |
| `context` | no | Pre-resolved ERP facts, e.g. `{"amount": 1450000}`. Compared against the limits the matched policies state. Whatever's missing comes back as a condition instead of being assumed to pass. |

### Response

```json
{
  "request_id": "a1b2c3...",
  "request_type": "action",
  "decision": "allow_with_conditions",
  "reason": "Payment exceeds the single-approver threshold; dual authorization required.",
  "action": {
    "name": "release_payment",
    "parameters": {"invoice_id": "INV-8842", "amount": 1450000, "currency": "LKR"},
    "confidence": "high"
  },
  "conditions": [
    {
      "type": "threshold",
      "description": "Payments over 1,000,000 require a second authorizer.",
      "source": "FIN-PAY-2026-003@1.0#2",
      "field": "amount",
      "operator": "<=",
      "value": 1000000,
      "satisfied": false
    }
  ],
  "citations": [
    {
      "policy_id": "FIN-PAY-2026-003",
      "version": "1.0",
      "section": "2",
      "title": "Payment Release Policy",
      "quote": "Payments exceeding LKR 1,000,000 require dual authorization..."
    }
  ],
  "knowledge": "",
  "retrieval": {"mandatory": 2, "action_filtered": 3, "semantic": 1, "total_unique": 5},
  "audit": {
    "judge_model": "gemini-3.5-flash-lite",
    "registry_version": "0.2.0",
    "policies_seen": ["FIN-PAY-2026-003@1.0", "FIN-GOV-2026-001@1.0"],
    "evaluated_at": "2026-08-27T09:00:00+00:00"
  }
}
```
## `GET /api/policy/actions` — the action vocabulary

Same auth as above. Returns every action this gate recognizes — build your
execution mapping from this list, not by hardcoding names, since it's a
versioned contract (`registry_version`).

```bash
curl https://<host>/api/policy/actions -H 'X-API-Key: <your-api-key>'
```

| Action | Flow | Risk | Financial | Mutates PII |
|---|---|---|---|---|
| `approve_invoice` | out | high | yes | no |
| `approve_purchase_order` | out | high | yes | no |
| `issue_credit_note` | neutral | high | yes | no |
| `release_payment` | out | **critical** | yes | no |
| `update_vendor_bank_details` | out | **critical** | yes | **yes** |
| `approve_travel_claim` | out | medium | yes | no |
| `reimburse_expense` | out | high | yes | no |
| `post_journal_entry` | neutral | high | yes | no |
| `approve_budget_transfer` | neutral | medium | yes | no |
| `view_ledger_entry` | neutral | medium | no | yes |

Each action also carries a JSON Schema for its parameters (returned in the
`parameters` field) — the gate validates extracted parameters against this
before any policy reasoning runs.

---

## `GET /health` — no auth required

```bash
curl https://<host>/health
```

```json
{
  "status": "ok",
  "policy_store": "ok",
  "policy_collection": "policy_docs",
  "policy_chunks": 48,
  "model_provider": "api",
  "model_credentials": "ok",
  "llm_model": "gemini-3.5-flash-lite",
  "judge_model": "gemini-3.5-flash-lite",
  "embed_model": "gemini-embedding-001",
  "embed_dimension": 3072,
  "fail_closed": true,
  "mcp": "/mcp"
}
```

`status: degraded` or `policy_chunks: 0` means the container is healthy but
the corpus isn't reachable or is empty — every request will deny, with a
reason that reads like strict policy rather than missing configuration. Check
this first if every request is unexpectedly denied.

---

## MCP — `/mcp`

For an agent client that speaks MCP rather than calling REST directly. Same
auth header, same underlying `evaluate()` call, same response shape as
`POST /api/policy/evaluate` — no second implementation to drift out of sync.

```json
{
  "mcpServers": {
    "policy-gate": {
      "url": "https://<host>/mcp",
      "headers": { "X-API-Key": "<your-api-key>" }
    }
  }
}
```

Exposes one tool: `check_policy(prompt, actor, context)`.

**This is a convenience surface, not an enforcement point.** An MCP tool is
called only when the calling model decides to call it — that's fine for an
agent *asking* whether something is permitted, and wrong for something that
must always run before a write. Real enforcement is your code calling
`POST /api/policy/evaluate` unconditionally, in your own request path, not an
agent's optional tool call.

---

## `GET /demo` — browser UI

Human-facing only, not for integration. Gated by `ENABLE_DEMO`; when on, the
page embeds a working API key so the browser can call the API — anyone who
loads the page gets that credential. Don't point this at a deployment meant
to stay private.

---

## Errors and failure behavior

- **`401`** — missing or invalid `X-API-Key`.
- **`422`** — request body fails schema validation (e.g. missing `actor.role`).
- **`500`** — essentially shouldn't happen. `policy_gate.evaluate()` converts
  every internal failure (Qdrant down, judge unreachable, malformed model
  reply, unknown action) into an explicit `deny` with a reason, rather than
  raising — the caller gets a decision, not an error, whenever a decision is
  possible at all. If you do see a `500`, something is broken outside the
  gate's normal fail-closed path.
- **Everything fails closed.** Any internal uncertainty resolves to `deny`,
  never `allow`. A `deny` that reads like "the judge was unreachable" is a
  real operational signal — check `/health` — not a policy finding to argue
  with.

---

## Not yet available

`docs/ASSIST_CONTRACT.md` describes a proposed `POST /api/assist` endpoint
for planning read-only tool calls (an agent-loop assistant, distinct from
this policy gate). **It is a draft only — not implemented in `src/` yet.**
Don't build against it until it actually exists.
