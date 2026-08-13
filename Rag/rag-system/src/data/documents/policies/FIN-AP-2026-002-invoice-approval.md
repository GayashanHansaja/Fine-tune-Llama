---
policy_id: FIN-AP-2026-002
doc_type: policy
title: Invoice and purchase order approval
applies_to_actions: [approve_invoice, approve_purchase_order]
risk_level: high
mandatory: false
version: "2.0"
effective_date: "2026-01-01"
is_current: true
source_document: accounts_payable_manual.pdf
threshold_value: 500000
threshold_unit: absolute
requires_role: [finance_officer, finance_manager]
---

## 1. Scope

This policy governs the approval of supplier invoices and purchase orders raised in
the ERP system, whether entered manually or received through automated invoice
capture.

## 2. Three-way match

2.1 An invoice may be approved only where it matches an approved purchase order and
a recorded goods receipt note in supplier, quantity, and value. An invoice failing
any leg of that match must not be approved.

2.2 A variance of up to 2% between the invoice value and the purchase order value
may be accepted without re-approval of the purchase order, provided the absolute
variance does not exceed 25,000.

2.3 An invoice with no corresponding purchase order may be approved only where the
spend category is on the exempt list maintained by the Finance Control Unit, and
must record the exemption relied upon.

## 3. Approval authority

3.1 Invoices and purchase orders of 500,000 or less may be approved by a Finance
Officer.

3.2 Invoices and purchase orders exceeding 500,000 require approval by the Finance
Manager. This authority may not be delegated downward.

3.3 A purchase order exceeding 5,000,000 additionally requires the endorsement of
the Chief Financial Officer before the commitment is recorded.

## 4. Anti-splitting

4.1 A spend must not be divided across multiple invoices or purchase orders to bring
each below an approval threshold. Two or more documents to the same vendor for
related goods or services within a thirty-day period are treated as one spend for
the purposes of clause 3, and the aggregate value determines the required approver.

4.2 Duplicate invoice numbers from the same vendor must be rejected without approval
and referred to the Accounts Payable supervisor.
