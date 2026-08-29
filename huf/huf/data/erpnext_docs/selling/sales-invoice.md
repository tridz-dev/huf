---
title: "Sales Invoice"
source_url: "https://docs.frappe.io/erpnext/sales-invoice"
section: selling
---

## Overview

A Sales Invoice formalizes a sale by creating a bill that customers owe. Once submitted, it records receivables, income, and taxes in the general ledger. The system can simultaneously update inventory if the "Update Stock" option is enabled, making it suitable for direct sales without separate delivery documentation.

## Before Creating an Invoice

The following prerequisites should be in place:

- A Customer record with billing address, contact details, currency, and receivable account
- Items configured with income accounts and units of measure
- A selling Price List for automatic rate retrieval
- Sales tax accounts or a Sales Taxes and Charges Template
- Payment Terms for installment arrangements
- Warehouse and available inventory if stock updates are needed

## Creating a Sales Invoice

The standard creation process involves:

1. Navigating to **Accounting > Sales and Receivables > Sales Invoice**
2. Selecting the Company and Customer (which auto-populates related defaults)
3. Verifying the Posting Date and Payment Due Date
4. Adding line items with quantities, rates, and warehouse information
5. Applying applicable taxes
6. Reviewing the payment schedule
7. Saving as draft, then submitting when finalized

The interface displays stock availability indicators—green for in-stock items and red for out-of-stock items.

## Alternative Creation Methods

**From a Sales Order:** Open a submitted Sales Order, select **Create > Sales Invoice**, and choose which lines to invoice. This enables partial billing across multiple invoices.

**From a Delivery Note:** After selecting **Create > Sales Invoice**, ensure "Update Stock" remains disabled since the delivery already recorded the movement.

**Direct Invoice with Stock Update:** For immediate counter sales or service-based transactions, enable "Update Stock" on the invoice itself. This single document updates both Stock and General Ledgers simultaneously.

**Services and Projects:** Use non-stock items without stock updates. Link projects and cost centers as needed. Timesheet integration supports time-based billing.

## Key Fields Explained

| Field | Purpose |
|-------|---------|
| Customer | Supplies billing address, contact, currency, price list, tax, and account defaults |
| Posting Date | Determines the accounting period; backdating may face restrictions |
| Payment Due Date | Used for aging analysis and overdue status determination |
| Update Stock | Posts item quantities to the Stock Ledger upon submission |
| Warehouse | Identifies the stock source when Update Stock is enabled |
| Income Account | The ledger account credited for item value |
| Debit To | The receivable account debited for the Customer |
| Is Return (Credit Note) | Designates the document as a return or credit note |

## Ledger Impact

When submitted, a typical accrual invoice creates these General Ledger entries:

| Entry | Debit | Credit |
|-------|-------|--------|
| Customer receivable | Grand Total | — |
| Income accounts | — | Net item amount |
| Tax and charge accounts | — | Applicable tax/charge amount |

If "Update Stock" is enabled with perpetual inventory, the system also records Stock Ledger entries and corresponding cost-of-goods adjustments.

## Post-Submission Actions

After submission, users can:

- Create a Payment Entry to record customer payments
- Issue a Credit Note for returns
- Generate a Payment Request or Dunning document
- View ledger entries for verification
- Cancel only after resolving linked payments and stock transactions

## Invoice Status Definitions

- **Draft:** Saved but not submitted; no ledger effect
- **Unpaid:** Submitted with an outstanding, non-overdue amount
- **Overdue:** Past due date with outstanding balance remaining
- **Partly Paid:** Partially reduced through payments or credits
- **Paid:** Outstanding amount cleared
- **Credit Note Issued:** A return or credit note exists
- **Return:** The document itself is a submitted credit note
- **Cancelled:** Ledger effects have been reversed

## Common Issues and Solutions

**Sales Order billed percentage unchanged:** Create invoices from the Sales Order itself or use "Get Items From" to maintain the reference link.

**Outstanding invoice despite payment receipt:** Verify the Payment Entry is submitted and allocated to this specific invoice.

**Unexpected tax or rate:** Review the Customer's Tax Category, Item Tax Template, applicable Pricing Rules, and transaction date.

**Insufficient stock error:** Confirm the Warehouse selection, available quantity, reserved stock, and serial/batch assignments. Disable "Update Stock" if a Delivery Note already recorded the movement.

**Incorrect account or Cost Center:** Check individual item row settings and update Item or Item Group defaults to prevent recurrence.

## Frequently Asked Questions

**Can I invoice without a Sales Order?** Yes, unless company settings or customer configuration mandates one. Direct invoices suit services and immediate sales.

**Can multiple invoices come from one Sales Order?** Yes. Create invoices for selected lines or quantities, then generate additional invoices for remaining balances.

**Is a Delivery Note required?** Not necessarily. Use it when delivery requires separate tracking. For direct stock sales, enable "Update Stock" on the invoice. Services require neither.

**How do I correct a submitted invoice?** Use a Credit Note for returns or reductions. For rate adjustments, apply a Debit Note. Full amendments require cancellation and resolution of linked documents.

**Can I bill in foreign currency?** Yes. Select the transaction currency, verify the exchange rate, and ensure the receivable account supports multi-currency balances.

## Related Resources

- [Sales Order](/erpnext/sales-order)
- [Delivery Note](/erpnext/delivery-note)
- [Payment Entry](/erpnext/payment-entry)
- [Credit Note and Sales Return](/erpnext/sales-return)
- [Payment Reconciliation](/erpnext/payment-reconciliation)
- [Applying a Discount](/erpnext/applying-discount)
- [Accounting Dimensions](/erpnext/accounting-dimensions)
