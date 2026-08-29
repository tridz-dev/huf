---
title: "Maintaining Supplier's Item Code In the Item master"
source_url: "https://docs.frappe.io/erpnext/maintaining-suppliers-part-no-in-item"
section: buying
---

# Maintaining Supplier's Item Code In the Item master

ERPNext enables businesses to track supplier-assigned codes for items, since an organization's internal item codes often differ from supplier designations. This feature allows these supplier codes to be automatically populated in purchase documents.

## Setting Up Supplier Item Codes

Within the Item master form, users can enter supplier-specific codes in the "Supplier Details" section. This mapping ensures that when purchase transactions reference both a particular supplier and item combination, the corresponding supplier code displays automatically.

## Using Codes in Purchase Documents

Purchase orders and related transactions include a field for displaying the supplier's item identifier. By default, this field remains hidden in both the standard form view and printed documents.

To make it visible, users should:
- Navigate to the print view menu and select customize
- Create a new print format
- Locate the Items table section
- Click the column selection button
- Check the "Supplier Part Number" option

The supplier code will only appear in purchase transactions when both the supplier and item selected match the mappings established in the Item master configuration.
