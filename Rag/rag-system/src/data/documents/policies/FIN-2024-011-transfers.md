---
policy_id: FIN-2024-011
title: Outbound transfer authorization thresholds
applies_to_tools: [transfer_funds, issue_refund]
risk_level: high
mandatory: false
version: "3.1"
effective_date: "2026-01-01"
jurisdiction: LK
---

## 1. Scope

This policy governs all outbound movements of customer funds initiated through
automated systems, including agent-initiated transfers and refunds.

## 2. Authorization thresholds

2.1 Outbound transfers with a value exceeding 25,000 require dual authorization
from a designated compliance officer before execution. The initiating system
must not execute such a transfer on the basis of a single approval.

2.2 Outbound transfers with a value of 25,000 or less may proceed under single
authorization, provided the destination account has been verified within the
preceding 90 days.

2.3 Aggregate outbound value to a single destination account exceeding 100,000
within any rolling 24-hour window requires escalation to manual review
regardless of the size of individual transfers.

2.4 Where a transfer is initiated on behalf of a corporate account holder and the value of that transfer, taken together with any other transfer initiated on behalf of the same account holder during the same business day, exceeds 250,000, the initiating system shall obtain written confirmation from two designated signatories of the account holder prior to execution, and shall additionally record the business justification supplied by the requesting party, except where the destination account is an account of the same account holder held at the same institution, in which case single authorization by a compliance officer is sufficient.

## 3. Prohibited destinations

3.1 Transfers to accounts flagged under sanctions screening are prohibited
without exception and may not be overridden by any approval level.

3.2 Transfers to newly created destination accounts, defined as accounts
registered within the preceding 7 days, are prohibited for amounts exceeding
10,000.

## 4. Refunds

4.1 Refunds exceeding the original transaction value are prohibited.

4.2 Refunds issued more than 180 days after the original transaction require
compliance officer approval.
