---
title: "Linking Stock Warehouse and Accounts"
source_url: "https://docs.frappe.io/erpnext/warehouse-ledger-link"
section: stock
---

# Linking Stock Warehouse and Accounts

The inventory held in warehouses requires financial tracking through the accounting system.

## Account Assignment Hierarchy

Each warehouse connects to a Chart of Accounts ledger via the 'Account' field within the warehouse configuration. The system follows a priority-based approach when determining the appropriate accounting ledger:

1. First, it checks the Account field in the specific warehouse
2. If empty, it looks to the parent warehouse's Account field
3. If still unresolved, it defaults to the Default Inventory Account specified in the Company record

## Default Setup

When establishing a new company, the system automatically generates a ledger called 'Stock In Hand' within the Chart of Accounts structure:

**Chart of Accounts > Assets > Current Assets > Stock Assets > Stock In Hand**

## Customization Options

Organizations may establish supplementary ledgers beneath the 'Stock Assets' grouping as needed for their operational structure.
