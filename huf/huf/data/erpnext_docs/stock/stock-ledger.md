---
title: "Stock Ledger Report"
source_url: "https://docs.frappe.io/erpnext/stock-ledger"
section: stock
---

# Stock Ledger Report

A Stock Ledger Report functions as a comprehensive tracking mechanism for inventory movements within an organization. The system captures transactions spanning manufacturing, purchasing, sales, and stock transfers, documenting the quantity and value of items alongside warehouse information.

## Key Attributes

The report includes three essential metrics:

**Incoming Rate**: Reflects the actual value at which inventory was acquired, matching the rate documented in the source transaction.

**Balance Value**: Represents the total worth of remaining inventory, calculated by multiplying the Valuation Rate by the Balance Quantity.

**Valuation Rate**: Determined according to the selected valuation methodology.

## Report Applications

This report becomes particularly valuable when the Perpetual Inventory system is activated, as it "presents a more granular view of the stock transactions" and maintains a complete transaction history.

## Source Transactions

Stock Ledger entries originate from these document types:

- Sales Invoice and Purchase Invoice (with stock updates enabled)
- Delivery Note
- Purchase Receipt
- Stock Entry
- Stock Reconciliation

Users can expand the report's scope by accessing the Menu option to Add Column, enabling field incorporation from the previously mentioned Document Types.
