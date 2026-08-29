---
title: "Set Current Value for Naming Series"
source_url: "https://docs.frappe.io/erpnext/naming-series-current-value"
section: data-model
---

# Set Current Value for Naming Series

The Naming Series feature in ERPNext allows you to establish prefixes for document numbering. For instance, a Sales Order with prefix "SO" generates numbers like SO-00001, SO-00002, and so forth.

## 1. Setting the Current Value

This feature includes a tool for adjusting the current value associated with a specific prefix. Organizations typically use this when transitioning to ERPNext from legacy systems, ensuring the new numbering sequence continues from where the old system concluded.

### Example Scenario

Suppose your previous system contained 322 Sales Orders, with SO00322 being the highest ID. Upon implementing ERPNext, you'd want the initial Sales Order to receive #323. To accomplish this:

#### Access the Naming Series Tool

Navigate to: `Setup > System > Naming Series`

#### Locate the Update Series Section

This section allows modification of series parameters.

#### Choose the Appropriate Prefix

In this example, select "SO" for Sales Orders.

#### Modify the Current Value

If your account currently shows 12 Sales Orders, the current value displays as 12. You can change this to 322 and select "Update Series Number."

Following this adjustment, subsequent Sales Orders will begin numbering from #323.

## 2. Resolving Duplicate Name Errors

A "Duplicate name" error indicates a mismatch between the system's allocated number and existing records. For example: `Duplicate name Item Price RFD/00016`

This occurs when the current value for a series falls out of sync with actual records in the system.

### Diagnostic Steps

1. Examine the relevant document report to identify the highest existing ID number
2. Access Naming Series via `Setup > Settings > Naming Series`
3. Select the appropriate prefix
4. Update the current value to match the highest ID found
5. Click "Update Series Numbering"

### Example: ToDo Assignment Error

An error message stating `Duplicate name ToDo TDI00014286` suggests the TDI prefix current value requires correction:

1. Review the ToDo report for the maximum ToDo ID
2. Navigate to `Setup >> Settings >> Naming Series`
3. Locate Section B of the Update Series area
4. Select the "TDI" prefix
5. Verify that the highest ToDo number matches the current value listed
6. If discrepancies exist, correct the current value and select "Update Series Numbering"
