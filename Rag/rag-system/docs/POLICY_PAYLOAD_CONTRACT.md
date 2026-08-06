# Policy Payload Contract — v0.1 (DRAFT, for review)

**Audience:** the developer building the data-transport / vectorisation layer
**Author:** AI decision module
**Status:** proposal — field names are negotiable, the *capabilities* are not

---

## 1. Why this document exists

The AI module decides whether an ERP action (e.g. a salary increase) is permitted
under company policy, and then executes it. To do that safely it must be able to
retrieve **every rule that governs an action** — not merely the rules that happen
to be semantically similar to how the employee phrased their request.

Pure vector similarity cannot provide that guarantee.

> An employee types *"bump Nimal's pay up a bit."*
> A rule exists: *"Salary increases exceeding 20% require board approval."*
> If that sentence doesn't embed close to that phrasing, the rule ranks #14. With
> `top_k=10`, the decision engine **never sees it** and approves the raise.

The fix is not a better embedding model. It's **metadata we can filter on**, so the
rule is retrieved by a database predicate rather than by a similarity guess.

Everything below exists to make that possible.

---

## 2. What we need on every chunk

### 2.1 Required — deterministic filtering is impossible without these

| Field | Type | Purpose |
|---|---|---|
| `doc_type` | enum: `policy` \| `rule` \| `privacy_policy` \| `company_data` | Separates governing rules from ordinary company data. Without it, an employee's salary record can be retrieved *as if it were a policy* and fed to the judge as authority. |
| `policy_id` | string | Stable identifier, e.g. `HR-2024-007`. Used for citation in the audit trail. Must be stable across re-ingestion. |
| `version` | string | e.g. `"2.1"`. **Audit requirement:** we must be able to answer "which version of which rule approved this payroll change?" months later. |
| `applies_to_actions` | array of string | The action names this rule governs — drawn verbatim from §3. This is the single most important field. |
| `mandatory` | boolean | `true` = always retrieved for every decision, regardless of similarity score. Use for blanket rules ("no action may violate the Shop and Office Employees Act"). |

### 2.2 Strongly requested — needed for correctness, workarounds are unreliable

| Field | Type | Purpose |
|---|---|---|
| `effective_date` | date | A rule not yet in force must not decide today's action. |
| `expires_date` \| `is_current` | date \| boolean | **Critical.** If superseded versions of a policy stay in the collection, retrieval can return a rule that was replaced last year. We must be able to exclude them by filter. |
| `title` | string | Human-readable rule name, shown in audit records and to the employee when an action is denied. |
| `source_document` | string | Original filename/document, for traceability back to the signed source. |
| `section` | string | Clause reference, e.g. `"2.4"`. Lets a denial cite the exact clause. |

### 2.3 Optional — enables deterministic evaluation instead of LLM judgement

Numeric and role conditions should never be decided by a language model. If you can
surface them as structured fields, we compare them in code:

| Field | Type | Example |
|---|---|---|
| `risk_level` | enum: `low`/`medium`/`high`/`critical` | `high` |
| `threshold_value` | number | `20` |
| `threshold_unit` | enum: `percent`/`absolute`/`days` | `percent` |
| `requires_role` | array of string | `["board", "cfo"]` |

If these are impractical to extract, say so — we will parse them from the rule text
on our side and accept the added risk. But structured is materially safer.

---

## 3. Action vocabulary — tag `applies_to_actions` with these exact strings

This list is owned by the AI module and versioned. Source of truth:
`src/core/actions/action_registry.py` (`REGISTRY_VERSION = 0.1.0`).

```
increase_salary
decrease_salary
issue_bonus
promote_employee
transfer_department
terminate_employee
approve_leave
reject_leave
update_bank_details
view_salary_record
```

**A typo here silently disables a rule.** A policy tagged `increase_salaries`
(plural) will never be retrieved by action filter for `increase_salary`, and the
failure is invisible — no error, just a rule that stopped applying. Please validate
tags against this list programmatically rather than by hand.

Rules that apply to *everything* should set `mandatory: true` rather than listing
every action name.

---

## 4. Chunking requirement

**Do not split a rule across chunks.**

Character-window splitting severs a rule from its own exception. Measured on a real
640-character clause using a 500-character window:

> `...record the business justification supplied by the requesting party, except where the destination account is`

The chunk ends mid-exception. A judge reading it sees the threshold and the
obligation but **not the exception that permits the action** — so it denies something
that was allowed. The mirror chunk carries the exception with no threshold attached,
which is worse.

Requested approach:

- Split on clause boundaries — headings, numbered items (`2.4`, `(a)`, `Section 3`)
- Target ~1200 characters, merging adjacent short clauses
- Only fall back to sentence-boundary splitting if a single clause exceeds the limit
- Never split mid-sentence

A working reference implementation is in `src/core/policy/policy_ingest.py`
(`split_clauses` / `pack_clauses`) — reuse or port it if helpful.

---

## 5. Vector configuration — must match exactly

| Setting | Value | Consequence of mismatch |
|---|---|---|
| Embedding model | `nomic-embed-text` (via Ollama) | Different model ⇒ different vector space ⇒ similarity scores are meaningless noise |
| Dimension | `768` | Qdrant rejects inserts outright |
| Distance | `Cosine` | Ranking silently degrades |

The **same** embedding model must be used at ingestion and at query time. Please
confirm the model before ingesting at volume — changing it later requires dropping
and rebuilding the collection.

---

## 6. Collection layout

Requested: **policies/rules in a collection separate from company data.**

Reason: a single missing filter on any query would let policy text leak into a data
response, or let employee records be treated as governing authority. Separate
collections make that failure impossible rather than merely unlikely. Policy text and
data records also want different chunk sizes, and chunk size is baked into the
vectors at ingest time.

If a single collection is unavoidable, `doc_type` (§2.1) becomes strictly mandatory
and every query on our side will filter on it.

---

## 7. Entity lookups do **not** belong in the vector database

Resolving *"employee 4471's current salary"* must be an **exact ERP lookup**, not a
similarity search. Vector search returns the *most similar* record, not the
*correct* one — for an ID lookup that is a data-integrity bug waiting to happen, and
it would put live PII into LLM prompt context.

Please expose employee/entity data via a normal query API. The vector DB should hold
policies, rules, and privacy documents — not records we need to look up by key.

---

## 8. Open questions

1. Is there one collection or several? What are the names?
2. Will superseded policy versions remain in the collection, or be deleted on update?
3. Can `applies_to_actions` be populated, given it requires reading each rule and
   deciding which actions it governs? If that tagging is manual, how is it validated?
4. What is the re-ingestion cadence, and are `policy_id` values stable across runs?
5. Is Qdrant payload indexing enabled on the filter fields? (Needed for performance
   once the corpus grows.)

---

## 9. Minimum viable fallback

If §2.1 cannot be delivered in full, the smallest set that keeps this safe is:

```
doc_type          — or policy chunks cannot be told apart from company data
policy_id         — or decisions cannot be cited in an audit
applies_to_actions — or rule retrieval stays probabilistic
```

Without `applies_to_actions` specifically, the module cannot guarantee it saw the
rules governing an action. That limitation would need to be recorded as an accepted
risk by whoever signs off on the system, not absorbed silently in code.
