---
title: "Perpetual Inventory for Non-stock Item"
source_url: "https://docs.frappe.io/erpnext/perpetual-inventory-for-non-stock-item"
section: stock
---

# Perpetual Inventory for Non-stock Item

## Question

We have enabled Perpetual Inventory in the Company master. Still, in some Purchase Invoice, posting if done in the Expense Account.

## Answer

Under perpetual inventory accounting, stock items' value is recorded to Stock-in-hand upon purchase. The general ledger entries for such a Purchase Invoice appear as follows:

| Account | Debit | Credit |
|---------|-------|--------|
| Creditors | | 100 |
| Stock Received but not Billed | 90 | |
| Tax | 10 | |

However, non-stock items operate differently. According to the documentation, "Perpetual Inventory doesn't apply on the non-stock item, and expense is booked for them as soon as Purchase Invoice is submitted." This results in the following GL entries:

| Account | Debit | Credit |
|---------|-------|--------|
| Creditors | | 100 |
| COGS / Other Expense Account | 90 | |
| Tax | 10 | |

The key distinction is that perpetual inventory tracks only stock items in inventory accounts, while non-stock items are immediately expensed regardless of perpetual inventory settings.
