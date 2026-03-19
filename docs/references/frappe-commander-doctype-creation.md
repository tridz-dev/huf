# Frappe Commander - DocType Creation Reference

> Source: [github.com/esafwan/frappe_commander](https://github.com/esafwan/frappe_commander)

This document summarizes how **Frappe Commander** creates DocTypes programmatically, serving as a reference for Huf's Data Table Builder implementation.

## Overview

Frappe Commander provides both a CLI (`bench new-doctype`) and a REST API (`commander.api.create_doctype_api`) for creating DocTypes without writing code. It uses Frappe's standard ORM to create DocType documents with fields, permissions, and module assignments.

## Core Function: `create_doctype()`

```python
# From commander/commands.py

def create_doctype(doctype_name, fields, module_name, custom=False):
    if frappe.db.exists("DocType", doctype_name):
        raise Exception(f"DocType '{doctype_name}' already exists.")

    # Module resolution
    if module_name.lower() == "custom":
        custom = True
    else:
        # Validate module exists or create from app
        module_doc = frappe.get_doc("Module Def", module_name)

    dt = frappe.new_doc("DocType")
    dt.update({
        "name": doctype_name,
        "module": module_name,
        "custom": 1 if custom else 0,
        "fields": fields,           # List of field dicts
        "istable": 0,               # Not a child table
        "issingle": 0,              # Not a single doctype
        "document_type": "Document"
    })
    dt.set("permissions", [{
        "role": "System Manager",
        "read": 1, "write": 1, "create": 1, "delete": 1,
        "print": 1, "email": 1, "share": 1
    }])
    dt.insert()
    frappe.db.commit()
    return dt.name
```

**Key takeaways:**
- Uses `frappe.new_doc("DocType")` to create DocType documents
- Sets `custom=1` for custom (non-module) DocTypes
- Fields are passed as a list of dictionaries
- Permissions are set explicitly
- Must call `frappe.db.commit()` after insert

## Allowed Field Types

```python
ALLOWED_FIELD_TYPES = {
    "Data",      # Short text (up to 140 chars)
    "Text",      # Long text (multi-line)
    "Int",       # Integer number
    "Float",     # Decimal number
    "Date",      # Date picker
    "Datetime",  # Date and time picker
    "Select",    # Dropdown with predefined options
    "Link",      # Link to another DocType
    "Table",     # Child table (references another DocType)
    "Check",     # Boolean checkbox
    "Currency",  # Currency amount
    "Percent",   # Percentage value
}
```

## Field Definition Parsing

Commander uses a string-based field definition format: `<fieldname>:<fieldtype>[:<attr1>[:<attr2>...]]`

### Supported Attributes

| Attribute | Syntax | Result | Notes |
|-----------|--------|--------|-------|
| Required | `*` | `reqd: 1` | Any field type |
| Unique | `unique` | `unique: 1` | Data, Int, Float only |
| Read-only | `readonly` | `read_only: 1` | Any field type |
| Options | `options=val1\|val2` | `options: "val1\nval2"` | Select: pipe/comma separated; Link/Table: DocType name |
| Default | `?=value` | `default: "value"` | Type-validated (int for Int/Check, float for Float/Currency/Percent) |

### Field Dictionary Output

```python
# Input: "product_name:Data:*:unique"
# Output:
{
    "fieldname": "product_name",
    "fieldtype": "Data",
    "label": "Product Name",  # Auto-generated from fieldname
    "reqd": 1,
    "unique": 1
}

# Input: "status:Select:options=Active|Inactive|Archived:?=Active"
# Output:
{
    "fieldname": "status",
    "fieldtype": "Select",
    "label": "Status",
    "options": "Active\nInactive\nArchived",
    "default": "Active"
}

# Input: "customer:Link:options=Customer"
# Output:
{
    "fieldname": "customer",
    "fieldtype": "Link",
    "label": "Customer",
    "options": "Customer"  # Target DocType name
}
```

## REST API: `create_doctype_api()`

```python
@frappe.whitelist()
def create_doctype_api(
    doctype_name: str,
    fields: Optional[List[str]] = None,
    module: str = "Custom",
    custom: bool = False,
) -> Dict[str, Any]:
    """
    Endpoint: /api/method/commander.api.create_doctype_api
    Method: POST
    Auth: System Manager role required
    """
```

### Request Format

```json
{
    "doctype_name": "Product",
    "fields": [
        "product_name:Data:*",
        "price:Currency:?=0",
        "description:Text"
    ],
    "module": "Custom",
    "custom": false
}
```

### Response Format

```json
{
    "success": true,
    "message": "DocType created successfully",
    "data": {
        "doctype_name": "Product",
        "module": "Custom",
        "fields_count": 3
    }
}
```

## Custom Field Management

Commander also supports adding fields to existing DocTypes:

```python
@frappe.whitelist()
def add_custom_field_api(
    doctype: str,
    field_definition: str,
) -> Dict[str, Any]:
    """Add a custom field to an existing DocType"""
```

Uses `frappe.custom.doctype.custom_field.custom_field.create_custom_field()` for adding fields to existing DocTypes.

## Relevance to Huf

For Huf's Data Table Builder, we adapt Commander's approach:
1. **Use `frappe.new_doc("DocType")`** for creating DocTypes - proven pattern
2. **Set `custom=1`** for all Huf-created tables (no file-system artifacts)
3. **Restrict field types** to a curated subset (exclude Table, exclude complex types)
4. **Restrict Link targets** to only Huf-created tables
5. **Add a registry layer** to track which DocTypes belong to Huf
6. **Wrap in Huf API endpoints** with proper validation and Huf-specific permissions
