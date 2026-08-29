---
title: "Dynamic Link Fields"
source_url: "https://docs.frappe.io/erpnext/dynamic-link-fields"
section: data-model
---

# Dynamic Link Fields

Dynamic Link field is "a field which can search and hold the value of any DocType." This feature eliminates the need for multiple separate link fields when a single field might reference different document types.

## How It Works

The documentation illustrates this concept through the example of creating Opportunities or Quotations. When building these documents, users must first specify whether the record relates to a Lead or Customer. Once selected, a subsequent link field automatically filters to show only records from the chosen category.

By designating the initial field as a Dynamic Link, the system automatically connects to the master type selected in the preceding field—whether Leads or Customers—without requiring duplicate link field definitions.

## Implementation Steps

### Step 1: Insert Link Field for DocType

The first step involves creating a link field connected to the DocType itself. As explained in the documentation, "DocType mentioned in the Option field" refers to the parent DocType. The DocType record stores all available document types as individual records, including:

- Sales Order
- Purchase Invoice
- Quotation
- Sales Invoice
- Employee
- Work Order

Linking a field to this parent DocType displays all available DocType records.

### Step 2: Insert Dynamic Link Field

The custom field type should be set as "Dynamic Link," with the Option field referencing "the name of the Doctype link field." This configuration allows users to select document IDs based on values chosen in the preceding DocType link field. For instance, selecting Sales Order filters the Dynamic Link field to display only Sales Order IDs.

## Customization

"By default, the DocType link field will provide all the forms/docTypes for selection." To restrict displayed options to specific document types, custom scripting is necessary.
