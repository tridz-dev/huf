---
title: "Item Valuation Setup and Transactions"
source_url: "https://docs.frappe.io/erpnext/item-valuation-transactions"
section: stock
---

# Item Valuation Setup and Transactions

In ERPNext, an item's stock valuation updates when certain transactions are created:

1. Purchase Receipt
2. Stock Entry (Material Receipt type)
3. Stock Reconciliation (for opening balance updates)

## Valuation Method Configuration

The valuation method determines how item values are calculated. You can establish this setting in two ways:

**Global Level:** Configure the default valuation method for all items through Stock Settings.

**Item Level:** Set a specific valuation method in the item master when an individual item requires a different approach than the global default.

Once ledger entries exist for an item, "this option will no longer be visible in the Item form."

For detailed information about available valuation methods and their mechanics, additional resources are available on the Frappe blog.

## Version 16 Updates

ERPNext v16 introduced company-level valuation method selection. A new field was added to the Company DocType for this purpose. The existing Stock Settings field persists for documents without company references, such as Batch records.

The system retrieves valuation methods using this hierarchy:

1. Item level
2. Company level  
3. Manufacturing Settings (global) level

Set the valuation method at all three levels appropriately to maintain accurate stock valuations.
