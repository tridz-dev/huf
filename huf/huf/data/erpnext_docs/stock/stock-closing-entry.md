---
title: "Stock Closing Entry"
source_url: "https://docs.frappe.io/erpnext/stock-closing-entry"
section: stock
---

# Stock Closing Entry

The stock closing entry feature generates consolidated stock balances for a specified accounting period. According to the documentation, it produces "the consolidated stock quantity and consolidated stock value for the selected period."

## How it Works

Users create a stock closing entry designating their chosen time span—whether monthly, bi-monthly, or yearly. When submitted, the system calculates closing balances organized by item, batch, inventory dimensions, and warehouse locations.

The documentation notes that "Stock reports, such as Stock Balance and Batch-Wise Balance History, use the Stock Closing Balance data to calculate the opening stock, which is significantly faster than calculating the closing stock using the Stock Ledger Entry."

This approach enables faster report generation by leveraging pre-calculated closing balances rather than processing raw ledger entries.

**Note:** This functionality will be available beginning in version 16 of the platform.
