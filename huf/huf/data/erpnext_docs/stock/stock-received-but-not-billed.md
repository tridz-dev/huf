---
title: "Purpose of Stock Received but not Billed"
source_url: "https://docs.frappe.io/erpnext/stock-received-but-not-billed"
section: stock
---

# Purpose of Stock Received but not Billed

When items are purchased and received, accounting entries are created reflecting the stock's value in warehouse or asset accounts. The **Stock Received But Not Billed** account serves as a temporary holding account during the gap between receipt and invoicing.

## How It Works

Upon receiving purchased items, the warehouse account is debited while this adjustment account is credited. Simultaneously, a negative expense entry is recorded using a "Valuation" or "Total and Valuation" category account to prevent duplicate expense recognition.

When the supplier's bill arrives and a Purchase Invoice is created against the Purchase Receipt, the Stock Received But Not Billed account is debited, eliminating its balance.

## Account Balance Significance

The remaining balance in this account represents "the value of items for which Purchase Receipt has been made, but billing is pending." This balance reflects goods received but not yet invoiced by the supplier.
