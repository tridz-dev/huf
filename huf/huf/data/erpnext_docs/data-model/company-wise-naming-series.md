---
title: "Company-wise Naming Series"
source_url: "https://docs.frappe.io/erpnext/company-wise-naming-series"
section: data-model
---

# Company-wise Naming Series

In a multi-company environment within ERPNext, you can establish naming conventions that vary by company. For instance, with three separate entities, you might need Sales Invoices labeled as "SINV-A-0001" for Company A and "SINV-B-0001" for Company B.

## Implementation Steps

**Step 1: Access the DocType Customization**

Open the Customize Form for your desired DocType (such as Sales Invoice).

**Step 2: Add an Abbreviation Field**

- Insert a new field below the Company field
- Name it 'Abbr'
- Set the Fetch From value to `company.abbr`
- Optionally hide this field from the user interface

**Step 3: Configure the Naming Series**

Within the Customize Form:

- Locate the Naming Series row and expand it
- Add a new line in the Options box with the pattern: `SINV-.abbr.-.####`
- Designate this as the default naming series
- Click Update

## Result

When you create a new document (like a Sales Invoice), simply select the company. The naming series automatically adjusts based on that company's abbreviation, generating sequential numbers accordingly.
