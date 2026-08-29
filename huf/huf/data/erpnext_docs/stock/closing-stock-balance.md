---
title: "Closing Stock Balance"
source_url: "https://docs.frappe.io/erpnext/closing-stock-balance"
section: stock
---

# Closing Stock Balance

**Note:** In v16 the closing stock balance has been renamed as [Stock Closing Entry](/erpnext/stock-closing-entry)

## How the Stock Balance Report is Prepared

The Stock Balance report serves as an important mechanism for tracking inventory. It contains four primary columns: Opening Stock, In Stock, Out Stock, and Balance Stock. The Balance Stock calculation follows this formula: "Opening Stock + In Stock - Out Stock."

A significant challenge emerges when calculating Opening Stock, particularly when the Stock Ledger Entry table contains extensive records without specific item code or warehouse filters applied. This scenario can substantially degrade system performance.

## Closing Stock Balance

![](/files/QqWv6uJ.png)

The "Closing Stock Balance" feature addresses this performance concern by allowing systems to precompute Opening Stock data, thereby accelerating Stock Balance report generation.

**Implementation steps include:**

1. **Closing Stock Balance Creation:** After a financial year concludes and audits are finalized, create the Closing Stock Balance entry for that year's end date (for example, the 2022-2023 financial year).

2. **Data Preparation:** Upon submission, the system processes data and calculates Opening Stock values for subsequent use.

3. **Utilizing Closing Stock Balance:** With prepared data, the Stock Balance Report can now retrieve Opening Stock values efficiently from the Closing Stock Balance records.

4. **Annual Closing Stock Balance:** Establish closing stock balance annually following each financial year's closure to maintain accurate and current Opening Stock values across reporting periods.

This approach enables businesses to enhance report generation performance, even when managing substantial Stock Ledger Entry volumes.
