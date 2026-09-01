---
title: "Periodic Inventory"
source_url: "https://docs.frappe.io/erpnext/periodic-inventory"
section: stock
---

# Periodic Inventory

When Perpetual Inventory is disabled in the Company master, users cannot rely on automatic GL entry creation for stock transactions. Instead, they must manually establish periodic accounting entries.

## Manual Process

The traditional approach requires creating a Journal Entry by hand. Users must then compare closing balances from the Stock Balance Report against the Trial Balance report for stock asset accounts. This comparison work is time-intensive and demands careful verification of any discrepancies.

## Automated Solution in Version 16

ERPNext Version 16 introduced a "Periodic Accounting Entry" Journal Entry type to streamline this workflow. Rather than performing manual calculations, the system automatically computes balance differences when users select the 'Get Balance' button.

This feature significantly reduces the accounting burden by eliminating the need for manual reconciliation between reports, allowing users to focus on other financial tasks.
