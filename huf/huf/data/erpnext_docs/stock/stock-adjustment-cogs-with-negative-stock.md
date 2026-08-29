---
title: "Stock Adjustment / COGS with Negative Stock"
source_url: "https://docs.frappe.io/erpnext/stock-adjustment-cogs-with-negative-stock"
section: stock
---

# Stock Adjustment / COGS with Negative Stock

This documentation explains how negative stock entries can create stock adjustments in ERPNext. The scenario occurs when users dispatch materials without existing inventory, typically after enabling the "allow negative stock" option in Stock Settings.

## The Problem Scenario

Users often create delivery notes before recording purchase receipts, resulting in negative stock entries. When a delivery note is issued for an item with no stock, the system requires a valuation rate to proceed. Users may temporarily assign a rate (such as 100) to continue.

The system then records this transaction using the temporary valuation rate. Later, when a purchase receipt is created with the actual cost (for example, 300), a timing issue emerges: the purchase entry posts after the delivery note.

Since stock was negative when the purchase receipt was recorded, the system applies the earlier valuation rate from the delivery note rather than the purchase cost. This prevents the stock value from becoming incorrect, but creates a discrepancy. The difference is recorded as an expense in the "Stock Adjustment/COGS account."

## The Solution

To prevent these adjustments, follow one of two approaches:

1. **Avoid negative stock entirely** — disable the feature in Stock Settings

2. **Backdate purchase entries** — record the purchase receipt before the delivery note's posting date. When the backdated purchase entry is submitted, the system generates a reposting entry that corrects the delivery note's valuation rate automatically.

When a purchase entry is backdated properly, the delivery note's valuation rate updates to reflect the actual purchase cost, eliminating the need for stock adjustment entries.
