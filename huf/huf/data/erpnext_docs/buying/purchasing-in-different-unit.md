---
title: "Purchasing in Different UoM"
source_url: "https://docs.frappe.io/erpnext/purchasing-in-different-unit"
section: buying
---

# Purchasing in Different UoM

Each item maintains a default stock unit of measurement, but suppliers may require different purchasing units. ERPNext allows you to specify a separate purchase UoM during order creation.

## Practical Example

Consider purchasing pens stocked in individual units (Nos) but ordered by the box. The system handles this conversion seamlessly through the purchase order interface.

## Configuration Steps

**Adjusting Units in Purchase Orders**

The purchase order contains two distinct UoM fields. The default unit appears automatically in both. You should modify the UoM field to reflect what you're actually purchasing from the supplier. This change appears in printed documents for supplier reference.

**Setting Conversion Ratios**

If one box contains 20 pens, the conversion factor equals 20. The system automatically calculates stock quantities using this ratio—ordering one box results in 20 units recorded in inventory.

## Important Considerations

Regardless of the purchase unit selected, inventory records always use the item's default UoM. Accurate conversion factors are essential for proper stock tracking.

## Streamlining Future Purchases

The Item master record includes a dedicated Purchase section where you can pre-configure all acceptable purchase units and their corresponding conversion factors. This eliminates repetitive data entry for recurring supplier transactions.
