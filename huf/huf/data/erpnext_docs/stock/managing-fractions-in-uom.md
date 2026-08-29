---
title: "Managing Fractions in UOM"
source_url: "https://docs.frappe.io/erpnext/managing-fractions-in-uom"
section: stock
---

# Managing Fractions in UOM

UoM stands for Unit of Measurement. Common examples include Numbers (Nos), Kgs, Litre, Meter, Box, and Carton.

Some units of measurement cannot accommodate decimal values. For instance, you cannot order 1.5 televisions or 3.7 computer sets when the UoM is "Nos" (numbers). These quantities must be expressed as whole numbers only.

ERPNext allows you to configure whether a particular UoM accepts decimal values. By default, all UOMs permit decimal places. To restrict fractional quantities for any specific UoM, follow these steps.

## UOM List

Navigate to the UoM configuration at:

`Stock > Setup > UoM`

From the available UOMs, select the one requiring decimal restrictions. For this example, we'll use "Nos."

## Configure

Within the UoM master record, locate the field labeled "Must be whole number". Enabling this field prevents users from entering fractional quantities for items using that UoM.

![UoM Must be Whole No](/files/uom-fraction-1.png)

## Validation

During transaction creation, if you attempt to enter a fractional quantity for an item whose UoM has "Must be whole number" enabled, the system displays this error:

`Quantity cannot be a fraction at row #`

![UoM Validation Message](/files/uom-fraction-2.png)
