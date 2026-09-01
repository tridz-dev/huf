---
title: "Table MultiSelect Field"
source_url: "https://docs.frappe.io/erpnext/table-multiselect-field"
section: data-model
---

# Table MultiSelect Field

The Table MultiSelect field functions similarly to a Link Field, with one critical distinction: it enables selection of multiple values instead of just one.

## Use Case Example

Consider a scenario where you need to assign a ToDo to several users simultaneously—this is where the Table MultiSelect field proves valuable.

## Implementation Steps

### Step 1: Create a Child DocType

Begin by establishing a new DocType with these configurations:
- Enable the "Is Child Table" checkbox
- Enable the "Editable Grid" checkbox
- Add a field using the "Link" type
- Mark the link field as mandatory
- Ensure the field has "In List View" enabled

### Step 2: Add a Table MultiSelect Field

Create a new field with type "Table MultiSelect" and reference the child DocType you created in the previous step within the options setting.

## Field Behavior

Users can remove selected values by either:
- Clicking the cross icon adjacent to the value
- Positioning the cursor next to the value and pressing Backspace

Each value may only be selected once within the field.

## Important Limitation

"Table MultiSelect fields cannot be added in child DocTypes."
