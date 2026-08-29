---
title: "Unit of Measure (UoM)"
source_url: "https://docs.frappe.io/erpnext/uom"
section: stock
---

# Unit of Measure (UoM)

A UoM represents the unit through which items are measured in the system.

ERPNext includes many built-in UoMs, with the flexibility to add additional ones based on specific business requirements.

## Key Features

The UoM configuration includes a "Must be Whole Number" option. When enabled, this setting prevents the use of fractional quantities in that particular measurement unit. For detailed information on handling fractions with UoMs, refer to the managing fractions documentation.

## Conversion Factors

The UoM list maintains only the unit names themselves. Conversion rates between different units are managed through a separate document type called 'UoM Conversion Factor'.

When implementing new UoMs that will require conversion to other units during transactions, it is recommended to register the conversion factors. For instance, the conversion between kilograms and pounds (approximately 1 kg equals 2.2 pounds) would be stored with its precise conversion factor in this system.
