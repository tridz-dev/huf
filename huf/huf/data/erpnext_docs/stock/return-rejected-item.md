---
title: "Return Rejected Items"
source_url: "https://docs.frappe.io/erpnext/return-rejected-item"
section: stock
---

# Return Rejected Items

In ERPNext's Purchase Receipt module, items can be directed to either an Accepted or Rejected Warehouse upon receipt. When you need to process a return for items that went into the Rejected Warehouse, follow this procedure:

## Steps to Create a Return Entry

1. Locate the relevant item in the Purchase Receipt Item table that requires a return
2. In the Received Qty field, "enter return entry in negative"
3. Adjust the Accepted Warehouse field to zero
4. In the Rejected Warehouse field, "set the quantity to be returned in negative"

The documentation includes a visual guide demonstrating this process for returning rejected items.
