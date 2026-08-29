---
title: "Remove Description in Print Format"
source_url: "https://docs.frappe.io/erpnext/removing-description-removed-item-code-and-name"
section: configurations
---

# Remove Description in Print Format

## Question

The user wants to eliminate description text from their print format to conserve space, but discovers that disabling the description field also removes the Item Code and Name fields from the output.

## Answer

The root cause is the **"Compact Item Print"** setting being active in Print Settings. To resolve this issue, users should:

1. Navigate to Print Settings
2. Disable the "Compact Item Print" option
3. Return to the print format builder
4. Uncheck only the Description field

This approach allows removal of the description while preserving the Item Code and Name fields in the printed document.
