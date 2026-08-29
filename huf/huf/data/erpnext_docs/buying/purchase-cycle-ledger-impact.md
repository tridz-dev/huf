---
title: "Purchase Cycle Ledger Impact"
source_url: "https://docs.frappe.io/erpnext/purchase-cycle-ledger-impact"
section: buying
---

# Purchase Cycle Ledger Impact

## Overview

The purchasing process in ERPNext spans from initial supplier commitment through final payment. According to the documentation, "Not every document creates an accounting entry. A Purchase Order records the commitment, while the Purchase Receipt, Purchase Invoice, and Payment Entry record the inventory, liability, expense, and cash effects that follow."

## When Ledger Changes Occur

General Ledger entries are created only when accounting or stock transactions are submitted—draft documents don't affect the ledger. The key documents and their impacts are:

- **Purchase Order**: No General Ledger entry (records commitment only)
- **Purchase Receipt for stock**: Debits Stock In Hand; credits Stock Received But Not Billed
- **Purchase Invoice (stock)**: Debits Stock Received But Not Billed; credits Accounts Payable
- **Purchase Invoice (service)**: Debits relevant Expense; credits Accounts Payable
- **Payment Entry**: Debits Accounts Payable; credits Bank or Cash

## Stock Item Purchase Workflow

For a manufacturer purchasing $2,600 in electronic components:

1. **Purchase Order** → No ledger impact
2. **Purchase Receipt** → Creates temporary liability in Stock Received But Not Billed
3. **Purchase Invoice** → Transfers liability from clearing account to Accounts Payable
4. **Payment Entry** → Clears supplier payable and reduces bank balance

The Stock Received But Not Billed account bridges timing gaps between physical receipt and invoice arrival.

## Service Purchase Workflow

For service purchases, the process typically skips the stock receipt step since services don't create inventory. The flow moves directly from Purchase Order to Purchase Invoice (recognizing the expense) to Payment Entry.

## Key Differences

Stock purchases use an inventory-focused workflow with a clearing account, while service purchases move directly to expense recognition. Both ultimately settle through the same payment mechanism.
