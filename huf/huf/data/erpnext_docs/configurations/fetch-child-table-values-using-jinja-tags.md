---
title: "Fetch child table values using Jinja tags"
source_url: "https://docs.frappe.io/erpnext/fetch-child-table-values-using-jinja-tags"
section: configurations
---

# Fetch child table values using Jinja tags

Jinja templating enables referencing fields across DocTypes in ERPNext through the syntax `{{doc.field_name}}` in print formats. However, this method has limitations when dealing with child tables nested within a DocType. This guide demonstrates how to iterate through and display child table rows.

## Pre Requisites

Two key pieces of information are necessary:

1. The variable name of the child table from the DocType's Customize Form section
2. Variable names of individual fields within the child table, also obtainable from its Customize Form

## Method 1. Displaying rows of a Child Table on an unordered list

```jinja
{% for row in doc.items %}
* Item Code: {{ row.get_formatted("item_code", doc) }}
Quantity: {{ row.get_formatted("qty", doc) }}
Rate: {{ row.get_formatted("rate", doc) }}
Amount: {{ row.get_formatted("amount", doc) }}

{% endfor %}
```

This approach produces an unformatted list output in print formats.

## Method 2. Displaying rows of a Child Table as a table

```jinja
{% for item in doc.items %}
| {{item.item_code }} | {{item.qty}} | {{item.rate}} | {{item.amount}} |
{% endfor %}
```

| Item Code | Quantity | Rate | Amount |
|---|---|---|---|
| {{item.item_code }} | {{item.qty}} | {{item.rate}} | {{item.amount}} |

Additional child table fields can be incorporated by modifying the template accordingly.
