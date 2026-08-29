---
title: "Selling Cycle Ledger Impact"
source_url: "https://docs.frappe.io/erpnext/selling-cycle-ledger-impact"
section: selling
---

The selling cycle encompasses the journey from initial commercial commitment through final customer payment. According to the documentation, "Not every document creates an accounting entry. A Sales Order records what you have agreed to sell, while Delivery Notes, Sales Invoices, and Payment Entries record the financial events that follow."

## Key Documents and Their Ledger Effects

Four primary documents shape the selling cycle's accounting impact:

**Sales Order** — Creates no General Ledger entries. It represents a commercial agreement but doesn't affect financial records until submission triggers subsequent transactions.

**Delivery Note (Stock Items)** — Debits Cost of Goods Sold and credits Stock In Hand, reflecting inventory leaving the warehouse and becoming an expense.

**Sales Invoice** — Debits Accounts Receivable and credits Sales revenue, formalizing the customer's debt obligation.

**Payment Entry** — Debits Bank or Cash and credits Accounts Receivable, completing the cycle when money arrives.

## Manufacturing vs. Services Workflows

Manufacturing operations typically involve all four documents in sequence. Services companies often bypass Delivery Notes, moving directly from Sales Orders to Sales Invoices since "services do not normally move inventory."

A critical distinction: "Cost of Goods Sold uses the item's stock valuation. Sales uses the price charged to the customer." This explains why a Delivery Note might post $866.76 in costs while the Sales Invoice recognizes $1,398 in revenue—the $531.24 difference represents gross profit.

## Important Considerations

Submitting Sales Invoices with stock-item **Update Stock** enabled combines delivery and invoicing effects into one entry, though this eliminates the separate delivery audit trail. Users can also create Sales Invoices directly without prior Sales Orders, but doing so sacrifices the documented commercial commitment and order-to-billing linkage.
