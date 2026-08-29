---
title: "Payment Entry"
source_url: "https://docs.frappe.io/erpnext/payment-entry"
section: selling
---

## Article Summary

Payment Entry is ERPNext's standard document for recording financial transactions involving money movement. According to the documentation, it handles "customer receipts, supplier payments, transfers, advances, and allocations."

### Key Functions

Payment Entry serves three primary purposes:

1. **Money Movement Recording** - Captures when funds are received, paid, or transferred between bank and cash accounts
2. **Invoice Linking** - Connects payments to source documents like Sales Invoices or Purchase Invoices, automatically updating outstanding amounts
3. **Ledger Management** - Creates appropriate General Ledger entries with debits and credits based on transaction type

### When to Use Payment Entry vs. Journal Entry

The documentation advises using Payment Entry "when the event is primarily a movement of money" and Journal Entry "when the event is primarily an accounting adjustment and no customer or supplier payment is taking place."

### Payment Types and Ledger Impact

Three transaction types exist:

- **Receive** - Debits bank/cash, credits customer receivables
- **Pay** - Debits supplier payables, credits bank/cash  
- **Internal Transfer** - Moves funds between company accounts without creating party balances

### Business Cycle Integration

Payment Entry completes both selling and buying cycles as the final settlement step, occurring after invoicing establishes the amount due.
