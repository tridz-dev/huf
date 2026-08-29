---
title: "Item Alternative"
source_url: "https://docs.frappe.io/erpnext/item-alternative"
section: stock
---

# Item Alternative

An Item Alternative is a substitute product that can be used in place of the original item during manufacturing processes. This feature proves valuable when the specified raw material in a Bill of Materials (BOM) becomes unavailable during production.

## Prerequisites

Before implementing Item Alternatives, ensure you have created the following:

* [Item](/erpnext/item)

## Setting Up Item Alternatives

To enable this functionality, activate the "Allow Alternative Item" option within the Item master record. You can then access the Item Alternative list via:

> Home > Stock > Items and Pricing > Item Alternative

Alternatively, click the plus icon adjacent to 'Item Alternative' on the Item master dashboard.

The system supports bidirectional replacement, allowing two items to function as alternatives for one another when both can substitute for each other.

## Using Alternatives in Manufacturing

### In Bill of Materials

Enable 'Allow Alternative Item' within the BOM, then designate the substitute item during Stock Entry creation. This same capability exists for Work Orders.

### In Work Orders

You can independently toggle the 'Allow Alternative Item' option for individual Work Orders. When activated, an 'Alternate Item' button appears, enabling you to configure item substitutes directly within that Work Order.

**Important:** If 'Allow Alternative Item' remains unchecked in the Item table row, you cannot assign an alternate item for that line.

### For Subcontracting

When transferring raw materials to subcontracted suppliers, if your stock lacks the specified material, this feature allows you to send an alternate item instead through Stock Entry. The alternate item will subsequently appear when generating a Purchase Receipt from the Work Order.

## Related Topics

1. [Bill Of Materials](/erpnext/bill-of-materials)
2. [Work Order](/erpnext/work-order)
