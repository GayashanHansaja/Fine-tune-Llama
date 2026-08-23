---
policy_id: FIN-PAY-2026-003
doc_type: policy
title: Payment release authorization
applies_to_actions: [release_payment]
risk_level: critical
mandatory: false
version: "1.0"
effective_date: "2026-01-01"
is_current: true
source_document: treasury_controls_manual.pdf
threshold_value: 1000000
threshold_unit: absolute
requires_role: [finance_manager, treasury_officer]
---

## 1. Scope

This policy governs the release of funds against approved invoices, payment runs,
and manual payment instructions.

## 2. Preconditions

2.1 Funds may be released only against an invoice that has been approved under the
invoice approval policy. An unapproved, partially approved, or disputed invoice must
not be paid.

2.2 The vendor bank account used must be the account recorded in the vendor master
at the time of release. A payment must never be released to account details supplied
in the payment request itself.

2.3 A payment must not be released where the vendor bank details were changed within
the preceding two working days, except as permitted by the vendor bank detail policy.

## 3. Authorization

3.1 Payments of 1,000,000 or less may be released on the authority of a single
Treasury Officer.

3.2 Payments exceeding 1,000,000 require dual authorization: two authorized
signatories, of whom at least one must hold the Finance Manager role, must each
record their approval against the payment before funds move.

3.3 The dual authorization requirement in clause 3.2 may not be satisfied by the
same person acting in two capacities, and may not be waived by reason of urgency,
supplier pressure, or an imminent payment run cut-off.

## 4. Payment runs

4.1 A payment run must be released as a whole. Individual payments must not be added
to a run after its approval.

4.2 A payment released outside a scheduled run must record the reason for the
exception, and such payments are reviewed monthly by the Finance Control Unit.

4.3 Same-day value payments require Finance Manager authorization regardless of
amount.
