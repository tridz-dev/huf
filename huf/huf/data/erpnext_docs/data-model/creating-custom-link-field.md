---
title: "Creating Custom Link Field"
source_url: "https://docs.frappe.io/erpnext/creating-custom-link-field"
section: data-model
---

# Creating Custom Link Field

Link fields connect to another document type. For instance, the Customer field in a Sales Order is a Link Field pointing to the Customer master.

## Creating a Custom Link Field

### Step 1: Access Customize Form

Navigate to Home > Customization > Form Customize > Customize Form

### Step 2: Select Your Form

In the Customize Form interface, choose your Document Type (such as Quotation, Sales Order, or Purchase Invoice Item). After updating fields in the table, open the field above where you want to insert your custom field, then click "Insert Above."

### Step 4: Configure Field Values

To establish a Link field, set these values:

1. **Label**: The display name users will see in the form
2. **Type**: Set to 'Link'
3. **Name**: Your chosen field identifier
4. **Options**: The DocType name the field references

## Adding Filters to Link Fields

> Available in version 15 and above

Frappe offers an accessible method to apply filters on Link Fields through the Form Builder. An action icon appears on all Link Fields, enabling filter selection.

When clicked, a dialogue opens for choosing desired filters. After selection and application, filtered results display accordingly.

### Reset Functionality

A "Reset To Default" button appears when modifying filters. However, note that filters in "Customize Form" will override default filters.

### Dynamic Filters with Eval Support

Users can create dynamic filters based on form values:

- `eval: doc.fieldname`
- `eval: doc.fieldname1 + doc.fieldname2`

**For Child Tables**, two filter types apply:

- Child Table Row filters: Use `doc.child_table_field_name`
- Parent Document filters: Use `parent.parent_doc_fieldname`

The expression following "eval:" is evaluated and returns its value.

> Note: Filters set via `frm.set_query` take precedence over UI-applied filters.
