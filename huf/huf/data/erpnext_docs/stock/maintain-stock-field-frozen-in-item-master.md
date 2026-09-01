---
title: "Maintain Stock Field Frozen in the Item Master"
source_url: "https://docs.frappe.io/erpnext/maintain-stock-field-frozen-in-item-master"
section: stock
---

# Maintain Stock Field Frozen in the Item Master

In ERPNext's item master, certain fields become locked after stock activity occurs:

1. Maintain Stock
2. Has Batch No.
3. Has Serial No.

## Why Fields Are Frozen

Once a stock ledger entry is created for an item, these fields are prevented from being modified. This protection exists to "prevent user from changing the value which can lead to mis-match of actual stock, and stock level in the system of an item."

For serialized items specifically, the concern is particularly important. Since inventory quantities depend on counting available Serial Nos., converting an item from serialized to non-serialized mid-stream would "break the sync, and item's stock level shown in the report will not be accurate."

## Restoring Field Editability

To unlock these fields and make them editable again, you must remove all stock transactions associated with that item. For items tracked by serial number or batch, you should also delete the corresponding Serial No. and Batch No. records tied to that item.
