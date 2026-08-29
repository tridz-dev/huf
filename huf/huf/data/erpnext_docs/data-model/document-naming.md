---
title: "Document Naming Rule"
source_url: "https://docs.frappe.io/erpnext/document-naming"
section: data-model
---

# Document Naming Rule

In ERPNext, the Document Naming Rule feature enables systematic management of naming conventions through dynamic, condition-based approaches. This goes beyond traditional naming by allowing "conditional logic to apply naming series based on specific field values."

## Key Differences from Traditional Naming Settings

Standard Document Naming Settings apply patterns globally across a doctype, whereas Document Naming Rule introduces conditional logic tied to specific document fields.

## How to Set Up a Document Naming Rule

### Steps:

**1. Select the Document Type**
Choose the Doctype (such as Sales Invoice or Customer) where the rule will apply.

**2. Set Priority**
- Higher priority numbers (e.g., 10) execute before lower ones (e.g., 5)
- When multiple rules match, the highest priority rule takes precedence

**3. Add Rule Conditions**
Multiple conditions can be added per rule, and "the rule is applied only when all conditions are satisfied."

**4. Define the Prefix**
Enter your desired prefix in the Naming section (example: PSI/)

**5. Set the Serial Number Start**
Specify the starting serial number. For instance, entering 5 means "the first document will be named PSI/00005"

## Example Use Case

Consider naming Customers by location:
- Rule 1: Prefix = CUST-INDIA-, Condition = Country = India (produces CUST-INDIA-00001, etc.)
- Rule 2: Prefix = CUST-USA-, Condition = Country = USA (produces CUST-USA-00001, etc.)

## Benefits

- Automates naming based on document field values
- Reduces manual selection and human error
- Supports multiple patterns within a single Doctype
- Ideal for multi-branch, multi-country, or multi-category scenarios

## Notes

Ensure conditions are specific to prevent rule conflicts. If no rule matches, the system defaults to the configured Naming Series.
