---
title: "Item Attribute"
source_url: "https://docs.frappe.io/erpnext/item-attribute"
section: stock
---

# Item Attribute

**Item Attributes** function as the foundational characteristics used to generate Item Variants in ERPNext.

These attributes enable you to define products based on physical properties and functional capabilities. Proper attribute configuration streamlines the process of creating multiple item variants through combinations of different attributes.

## Accessing Item Attributes

To view the Item Attribute list, navigate to:

> Home > Stock > Settings > Item Attribute

## Creating an Item Attribute

Follow these steps to establish a new attribute:

1. Go to the Item Attribute list and select 'Add Item Attribute'
2. Provide a name for the Attribute
3. Input the attribute values in the corresponding table
4. Save your changes

Attribute values can be structured as either numeric or non-numeric formats.

### Non-Numeric Attributes

For non-numeric attributes, you should document attribute values with their corresponding abbreviations within the Attribute Values table.

### Numeric Attributes

When your attribute is designated as 'Numeric', you need to establish a range and increment value. The system will then automatically generate the corresponding variants based on these parameters.

As an illustration: if cable length ranges from 1 to 5 with an increment of 1, the generated variants will be: 1, 2, 3, 4, 5.
