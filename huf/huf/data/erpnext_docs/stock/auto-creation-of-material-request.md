---
title: "Auto Creation of Material Request"
source_url: "https://docs.frappe.io/erpnext/auto-creation-of-material-request"
section: stock
---

# Auto Creation of Material Request

To prevent stockouts, you can track an item's reorder level. When stock level goes below reorder level, the purchase manager is notified and instructed to initiate the purchase process for the item.

In ERPNext, you can update an item's Reorder Level and Reorder Qty in the Item master. If the same item has different reorder levels across warehouses, you can also update warehouse-specific reorder levels and quantities.

With reorder level, you can define the next action—either initiating a new purchase or transferring stock from another warehouse. The Material Request purpose will be updated based on these Item master settings.

When an item's stock reaches the reorder level, a Material Request is created automatically. You can enable this feature from:

`Stock > Setup > Stock Settings`

A separate Material Request will be created for each item. Users with the Purchase Manager role will receive email alerts about these Material Requests.

If auto creation of Material Request fails, users with the Purchase Manager role will be informed of the error message. One commonly encountered error is:

"An error occurred for certain Items while creating Material Requests based on Re-order level. Date 01-04-2016 not in any Fiscal Year."

Fiscal Year configuration can be a source of such errors. See the Fiscal Year Error documentation for additional information.

### Note:

The system creates a material request by comparing the projected quantity of the group warehouse against the reorder level. If no group warehouse is set, the system compares the projected quantity of the Request for Warehouse instead. If projected quantity exceeds the reorder level, that item is not included in the material request.
