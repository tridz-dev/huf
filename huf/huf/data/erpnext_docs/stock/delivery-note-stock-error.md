---
title: "Delivery Note Negative Stock Error"
source_url: "https://docs.frappe.io/erpnext/delivery-note-stock-error"
section: stock
---

# Delivery Note Negative Stock Error

**Question**: When submitting a Delivery Note, receiving a message says that item's stock is insufficient, but we have item's stock available in the Warehouse.

**Answer**: On submission of Delivery Note, "stock level is checked as on Posting Date and Posting Time of a Delivery Note." This issue typically arises when creating back-dated entries. Even if inventory exists currently, the system validates stock availability at the specific date and time assigned to the delivery note.

If an item was not in stock on the delivery note's posting date and time, you'll receive a negative stock error. Verify this by checking the Stock Ledger report.

**Resolution**: Modify the Posting Date and Time of your Delivery Note so it occurs after the receipt entry's posting date and time for that item.
