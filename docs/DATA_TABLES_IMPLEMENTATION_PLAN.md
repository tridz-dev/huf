# Huf Data Tables — Complete Implementation Plan

> **Status**: Planning
> **Author**: AI-assisted
> **Date**: 2026-03-07
> **References**: [Frappe Commander Reference](references/frappe-commander-doctype-creation.md) | [Frappe DocType Internals](references/frappe-doctype-internals.md)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope and Restrictions](#2-scope-and-restrictions)
3. [Architecture Overview](#3-architecture-overview)
4. [Backend Design](#4-backend-design)
5. [Frontend Design](#5-frontend-design)
6. [UX Design — User Flows](#6-ux-design--user-flows)
7. [Component Specifications](#7-component-specifications)
8. [API Specifications](#8-api-specifications)
9. [Type Definitions](#9-type-definitions)
10. [Route Plan](#10-route-plan)
11. [Implementation Phases](#11-implementation-phases)
12. [Future Considerations](#12-future-considerations)

---

## 1. Executive Summary

Data Tables enables Huf users to create, manage, and populate custom database tables directly from the Huf frontend. Each table is backed by a Frappe DocType (`custom=1`), but the complexity of Frappe's DocType system is hidden behind a simplified, purpose-built UI.

**Why**: Users need structured data storage for agent knowledge, workflow data, and general record-keeping — without leaving Huf or understanding Frappe internals.

**How**: A registry DocType (`Huf Data Table`) tracks which DocTypes belong to Huf. The frontend provides two distinct experiences:
1. **Table Builder** — Create/edit table structure (fields, layout, properties)
2. **Table Data View** — Add, view, edit, and delete records in a table

---

## 2. Scope and Restrictions

### In Scope (v1)

| Feature | Details |
|---------|---------|
| Table creation | Name, description, icon, fields |
| Field types | Curated subset (see below) |
| Field properties | Label, required, unique, read-only, default, options, description |
| Form layout | Section Break, Column Break for organizing fields |
| Data entry | Standard Frappe form for adding/editing records |
| Data listing | List view with search, filters, pagination |
| Table editing | Add/remove/reorder fields, change properties |
| Table deletion | With confirmation and data warning |
| Registry | Track all Huf-created tables |
| Link fields | Restricted to other Huf-created tables only |

### Out of Scope (v1)

| Feature | Reason |
|---------|--------|
| Child tables (Table field type) | Complexity — users can use Link fields instead |
| Conditional field logic (depends_on) | Simplicity — future enhancement |
| Tab breaks | Simplicity — Section/Column breaks sufficient for v1 |
| Custom scripts / validation | Security — future with sandboxing |
| Permissions per table | Simplicity — all tables use same default permissions |
| Import/Export (CSV) | Future enhancement |
| Attach / Attach Image fields | Complexity of file handling |
| Computed / formula fields | Future enhancement |

### Allowed Field Types

```
┌─────────────────────────────────────────────────────────┐
│  DATA ENTRY FIELDS (create DB columns)                   │
├──────────┬──────────────────────────────────────────────┤
│ Data     │ Short text (up to 140 chars)                  │
│ Text     │ Long text (multi-line textarea)               │
│ Int      │ Integer number                                │
│ Float    │ Decimal number                                │
│ Currency │ Money amount                                  │
│ Percent  │ Percentage (0-100)                            │
│ Check    │ Boolean checkbox                              │
│ Date     │ Date picker                                   │
│ Datetime │ Date + time picker                            │
│ Time     │ Time only picker                              │
│ Select   │ Dropdown with defined options                 │
│ Link     │ Reference to another Huf table                │
│ Rating   │ Star rating (0-5)                             │
│ Color    │ Color picker                                  │
│ Phone    │ Phone number                                  │
│ Small Text│ Medium text field                            │
│ Duration │ Time duration                                 │
├──────────┴──────────────────────────────────────────────┤
│  LAYOUT FIELDS (no DB columns)                           │
├──────────┬──────────────────────────────────────────────┤
│ Section Break │ Groups fields into a visual section      │
│ Column Break  │ Splits section into columns              │
└──────────┴──────────────────────────────────────────────┘
```

### Field Properties Exposed

| Property | Applicable To | Description |
|----------|---------------|-------------|
| `label` | All | Display name |
| `fieldname` | All | Auto-generated snake_case from label |
| `fieldtype` | All | Field type (from allowed list) |
| `reqd` | Data fields | Mandatory |
| `unique` | Data, Int, Float, Phone | Unique constraint |
| `read_only` | Data fields | Non-editable |
| `default` | Data fields | Default value |
| `options` | Select, Link | Select: newline-separated; Link: target table |
| `description` | All | Help text |
| `in_list_view` | Data fields | Show in list view |
| `non_negative` | Int, Float, Currency, Percent | Disallow negative |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│                                                                 │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Data Page │  │ Table Builder│  │  Table Data  │              │
│  │ (listing) │  │   (schema)   │  │   (records)  │              │
│  └─────┬─────┘  └──────┬───────┘  └──────┬───────┘              │
│        │               │                 │                       │
│  ┌─────┴───────────────┴─────────────────┴────────┐             │
│  │              dataTableApi.ts (service)          │             │
│  │    ┌────────────────────────────────────┐       │             │
│  │    │  frappe-sdk (db, call)             │       │             │
│  │    └────────────────────────────────────┘       │             │
│  └─────────────────────┬───────────────────────────┘             │
└────────────────────────┼─────────────────────────────────────────┘
                         │ HTTP
┌────────────────────────┼─────────────────────────────────────────┐
│                    BACKEND (Frappe/Python)                        │
│                        │                                         │
│  ┌─────────────────────┴───────────────────────────┐             │
│  │        huf.huf.doctype.huf_data_table           │             │
│  │     (Registry + API endpoints)                   │             │
│  │                                                  │             │
│  │  create_data_table()  ── frappe.new_doc("DocType")            │
│  │  update_data_table()  ── frappe.get_doc + save()              │
│  │  delete_data_table()  ── frappe.delete_doc()                  │
│  │  get_data_tables()    ── frappe.get_all()                     │
│  │  get_table_fields()   ── frappe.get_meta()                    │
│  └──────────────────────────────────────────────────┘             │
│                                                                   │
│  ┌──────────────────────────────────────────────────┐             │
│  │  Frappe ORM (DocType, DocField, Database)        │             │
│  │                                                  │             │
│  │  DocType (custom=1)  ←→  MariaDB Table           │             │
│  │  DocField records    ←→  Column definitions      │             │
│  └──────────────────────────────────────────────────┘             │
└───────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User creates table "Products"
        │
        ▼
Frontend sends POST to huf.huf.doctype.huf_data_table.api.create_data_table
        │
        ▼
Backend creates:
  1. Frappe DocType "Products" (custom=1, module="Huf")
     ├── fields: [name:Data:reqd, price:Currency, ...]
     └── permissions: [{role: "System Manager", ...}]
  2. Huf Data Table record (registry entry)
     ├── table_name: "Products"
     ├── doctype_name: "Products"  (link to actual DocType)
     ├── description: "Product catalog"
     └── field_count: 3
        │
        ▼
User adds data via standard Frappe db.createDoc("Products", {...})
```

---

## 4. Backend Design

### 4.1 Registry DocType: `Huf Data Table`

A new DocType to track which DocTypes were created through Huf's Data Tables feature.

**File location**: `huf/huf/doctype/huf_data_table/`

```
huf_data_table/
├── huf_data_table.json      # DocType definition
├── huf_data_table.py        # Controller with API methods
├── test_huf_data_table.py   # Tests
└── __init__.py
```

**Schema:**

| Field | Type | Label | Properties |
|-------|------|-------|------------|
| `table_name` | Data | Table Name | reqd, unique |
| `doctype_name` | Data | DocType Name | reqd, unique, read_only |
| `description` | Small Text | Description | — |
| `icon` | Data | Icon | — |
| `field_count` | Int | Field Count | read_only |
| `record_count` | Int | Record Count | read_only |
| `is_active` | Check | Is Active | default: 1 |
| `autoname_method` | Select | Naming Method | options: "Autoincrement\nHash\nBy Field" |
| `title_field_name` | Data | Title Field | — |

**Naming**: `autoname = "hash"` (system-managed IDs)

**Permissions**: System Manager — read, write, create, delete

### 4.2 API Endpoints

All endpoints are whitelisted methods in `huf/huf/doctype/huf_data_table/api.py`.

#### `create_data_table`

```python
@frappe.whitelist()
def create_data_table(
    table_name: str,
    fields: list[dict],
    description: str = "",
    icon: str = "",
    autoname_method: str = "Autoincrement",
    title_field: str = "",
) -> dict:
    """
    Create a new data table (DocType + registry entry).

    Args:
        table_name: Human-readable table name (e.g., "Products")
        fields: List of field definitions [{fieldname, fieldtype, label, ...}]
        description: Optional table description
        icon: Optional Lucide icon name
        autoname_method: "Autoincrement", "Hash", or "By Field"
        title_field: fieldname to use as title (if autoname_method is "By Field")

    Returns:
        {success: true, data: {name, table_name, doctype_name}}
    """
```

**Implementation logic:**

```python
def create_data_table(table_name, fields, description="", icon="",
                       autoname_method="Autoincrement", title_field=""):
    # 1. Validate table name (no special chars, not existing)
    doctype_name = f"HT {table_name}"  # Prefix to avoid collisions

    if frappe.db.exists("DocType", doctype_name):
        frappe.throw(f"Table '{table_name}' already exists")

    # 2. Validate fields
    validated_fields = validate_and_prepare_fields(fields)

    # 3. Determine autoname
    autoname = resolve_autoname(autoname_method, title_field)

    # 4. Create the DocType
    dt = frappe.new_doc("DocType")
    dt.update({
        "name": doctype_name,
        "module": "Huf",
        "custom": 1,
        "fields": validated_fields,
        "istable": 0,
        "issingle": 0,
        "autoname": autoname,
        "title_field": title_field or "",
        "search_fields": get_search_fields(validated_fields),
        "sort_field": "modified",
        "sort_order": "DESC",
        "track_changes": 1,
    })
    dt.set("permissions", [
        {"role": "System Manager", "read": 1, "write": 1,
         "create": 1, "delete": 1, "print": 1, "email": 1, "share": 1}
    ])
    dt.insert(ignore_permissions=True)

    # 5. Create registry entry
    registry = frappe.new_doc("Huf Data Table")
    registry.update({
        "table_name": table_name,
        "doctype_name": doctype_name,
        "description": description,
        "icon": icon,
        "field_count": len([f for f in validated_fields
                           if f["fieldtype"] not in ("Section Break", "Column Break")]),
        "autoname_method": autoname_method,
        "title_field_name": title_field,
    })
    registry.insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "success": True,
        "data": {
            "name": registry.name,
            "table_name": table_name,
            "doctype_name": doctype_name,
        }
    }
```

#### `update_data_table`

```python
@frappe.whitelist()
def update_data_table(
    name: str,
    fields: list[dict] | None = None,
    description: str | None = None,
    icon: str | None = None,
) -> dict:
    """
    Update table structure (add/remove/reorder fields, update metadata).

    Replaces ALL fields with the new list (frontend sends complete field list).
    Frappe handles column add/remove/rename via ALTER TABLE automatically.
    """
```

**Implementation logic:**

```python
def update_data_table(name, fields=None, description=None, icon=None):
    registry = frappe.get_doc("Huf Data Table", name)

    if fields is not None:
        validated_fields = validate_and_prepare_fields(fields)

        # Update the DocType
        dt = frappe.get_doc("DocType", registry.doctype_name)
        dt.fields = []
        for field_data in validated_fields:
            dt.append("fields", field_data)
        dt.save(ignore_permissions=True)

        # Update registry count
        registry.field_count = len([f for f in validated_fields
                                    if f["fieldtype"] not in ("Section Break", "Column Break")])

    if description is not None:
        registry.description = description
    if icon is not None:
        registry.icon = icon

    registry.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "data": {"name": registry.name}}
```

#### `delete_data_table`

```python
@frappe.whitelist()
def delete_data_table(name: str) -> dict:
    """Delete a data table and all its records."""
    registry = frappe.get_doc("Huf Data Table", name)
    doctype_name = registry.doctype_name

    # Count records for confirmation
    record_count = frappe.db.count(doctype_name)

    # Delete the DocType (this drops the DB table)
    frappe.delete_doc("DocType", doctype_name, force=True, ignore_permissions=True)

    # Delete registry entry
    frappe.delete_doc("Huf Data Table", name, ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "data": {"deleted_records": record_count}}
```

#### `get_data_tables`

```python
@frappe.whitelist()
def get_data_tables(
    search: str = "",
    limit: int = 20,
    start: int = 0,
) -> dict:
    """List all Huf data tables with pagination."""
    filters = {}
    if search:
        filters["table_name"] = ["like", f"%{search}%"]

    tables = frappe.get_all(
        "Huf Data Table",
        filters=filters,
        fields=["name", "table_name", "doctype_name", "description",
                "icon", "field_count", "is_active", "creation", "modified"],
        limit_page_length=limit + 1,
        limit_start=start,
        order_by="modified desc",
    )

    has_more = len(tables) > limit
    items = tables[:limit] if has_more else tables

    # Enrich with live record counts
    for table in items:
        try:
            table["record_count"] = frappe.db.count(table["doctype_name"])
        except Exception:
            table["record_count"] = 0

    return {
        "items": items,
        "has_more": has_more,
        "total": frappe.db.count("Huf Data Table", filters),
    }
```

#### `get_table_schema`

```python
@frappe.whitelist()
def get_table_schema(name: str) -> dict:
    """Get complete table schema (fields with all properties)."""
    registry = frappe.get_doc("Huf Data Table", name)
    meta = frappe.get_meta(registry.doctype_name)

    fields = []
    for field in meta.fields:
        fields.append({
            "fieldname": field.fieldname,
            "fieldtype": field.fieldtype,
            "label": field.label,
            "reqd": field.reqd,
            "unique": field.unique,
            "read_only": field.read_only,
            "hidden": field.hidden,
            "default": field.default,
            "options": field.options,
            "description": field.description,
            "in_list_view": field.in_list_view,
            "non_negative": field.non_negative,
            "idx": field.idx,
        })

    return {
        "name": registry.name,
        "table_name": registry.table_name,
        "doctype_name": registry.doctype_name,
        "description": registry.description,
        "icon": registry.icon,
        "autoname_method": registry.autoname_method,
        "title_field_name": registry.title_field_name,
        "fields": fields,
    }
```

#### `get_huf_table_names`

```python
@frappe.whitelist()
def get_huf_table_names() -> list[dict]:
    """Get list of all Huf data table names (for Link field options)."""
    return frappe.get_all(
        "Huf Data Table",
        filters={"is_active": 1},
        fields=["table_name", "doctype_name"],
        order_by="table_name asc",
    )
```

### 4.3 Validation Functions

```python
ALLOWED_FIELD_TYPES = {
    "Data", "Small Text", "Text", "Int", "Float", "Currency", "Percent",
    "Check", "Date", "Datetime", "Time", "Select", "Link", "Rating",
    "Color", "Phone", "Duration", "Long Text",
    "Section Break", "Column Break",
}

def validate_and_prepare_fields(fields: list[dict]) -> list[dict]:
    """Validate field definitions and prepare for DocType creation."""
    validated = []
    fieldnames_seen = set()

    for i, field in enumerate(fields):
        fieldtype = field.get("fieldtype")
        if fieldtype not in ALLOWED_FIELD_TYPES:
            frappe.throw(f"Field type '{fieldtype}' is not allowed")

        fieldname = field.get("fieldname") or frappe.scrub(field.get("label", f"field_{i}"))

        # Ensure unique fieldnames
        if fieldname in fieldnames_seen:
            frappe.throw(f"Duplicate field name: {fieldname}")
        fieldnames_seen.add(fieldname)

        validated_field = {
            "fieldname": fieldname,
            "fieldtype": fieldtype,
            "label": field.get("label", fieldname.replace("_", " ").title()),
            "idx": i + 1,
        }

        # Only set properties that are applicable
        if fieldtype not in ("Section Break", "Column Break"):
            for prop in ("reqd", "unique", "read_only", "hidden",
                        "default", "description", "in_list_view", "non_negative"):
                if field.get(prop) is not None:
                    validated_field[prop] = field[prop]

        # Handle options
        if fieldtype == "Select" and field.get("options"):
            validated_field["options"] = field["options"]
        elif fieldtype == "Link" and field.get("options"):
            # Validate Link target is a Huf table
            target = field["options"]
            if not frappe.db.exists("Huf Data Table", {"doctype_name": target}):
                frappe.throw(f"Link target '{target}' must be a Huf data table")
            validated_field["options"] = target

        # Section/Column break labels
        if fieldtype in ("Section Break", "Column Break") and field.get("label"):
            validated_field["label"] = field["label"]

        validated.append(validated_field)

    return validated
```

### 4.4 DocType Naming Convention

All Huf-created DocTypes use the prefix **`HT `** (Huf Table) to:
- Avoid name collisions with standard/other DocTypes
- Make them easily identifiable in database
- Allow filtering in queries

Example: User creates "Products" → DocType is named `HT Products`

### 4.5 File Structure (Backend)

```
huf/huf/doctype/
├── huf_data_table/
│   ├── __init__.py
│   ├── huf_data_table.json        # DocType definition
│   ├── huf_data_table.py          # Controller
│   ├── api.py                     # Whitelisted API methods
│   ├── test_huf_data_table.py     # Tests
│   └── validators.py              # Field validation logic
```

---

## 5. Frontend Design

### 5.1 File Structure (Frontend)

```
frontend/src/
├── pages/
│   ├── DataPage.tsx                    # MODIFY: Table listing (replace placeholder)
│   ├── DataTableBuilderPage.tsx        # NEW: Create/edit table schema
│   ├── DataTableBuilderWrapper.tsx     # NEW: Wrapper with breadcrumbs + layout
│   ├── DataTableViewPage.tsx           # NEW: View/manage table records
│   └── DataTableViewWrapper.tsx        # NEW: Wrapper with breadcrumbs + layout
├── components/
│   ├── data-table/                     # NEW: All data table components
│   │   ├── TableBuilderCanvas.tsx      # Field list builder (drag-drop reorder)
│   │   ├── FieldCard.tsx               # Single field in builder (draggable)
│   │   ├── FieldConfigPanel.tsx        # Right panel: field property editor
│   │   ├── FieldTypeSelector.tsx       # Field type picker (grid of types)
│   │   ├── AddFieldButton.tsx          # "+ Add Field" button
│   │   ├── SectionBreakCard.tsx        # Section break visual in builder
│   │   ├── ColumnBreakCard.tsx         # Column break visual in builder
│   │   ├── TableSettingsPanel.tsx      # Table-level settings (name, description)
│   │   ├── DataRecordForm.tsx          # Dynamic form for adding/editing records
│   │   ├── DataRecordList.tsx          # Table view of records with TanStack Table
│   │   ├── DataRecordFilters.tsx       # Filters for record list
│   │   ├── DeleteTableDialog.tsx       # Confirmation dialog for table deletion
│   │   └── LinkFieldSelector.tsx       # Custom selector for Link field targets
│   ├── DataHeaderActions.tsx           # NEW: Header actions for Data listing page
│   └── DataTableHeaderActions.tsx      # NEW: Header actions for table view
├── services/
│   └── dataTableApi.ts                 # NEW: Data table API service
├── types/
│   └── dataTable.types.ts              # NEW: TypeScript types
├── data/
│   └── doctypes.ts                     # MODIFY: Add "Huf Data Table" constant
│   └── fieldTypes.ts                   # NEW: Field type definitions and metadata
```

### 5.2 Service Layer: `dataTableApi.ts`

```typescript
// frontend/src/services/dataTableApi.ts

import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
  HufDataTable,
  DataTableSchema,
  DataTableFieldDef,
  PaginatedDataTablesResponse,
  GetDataTablesParams,
} from '@/types/dataTable.types';

/**
 * Fetch all data tables with pagination and search
 */
export async function getDataTables(
  params?: GetDataTablesParams
): Promise<PaginatedDataTablesResponse> {
  try {
    const result = await call.get(
      'huf.huf.doctype.huf_data_table.api.get_data_tables',
      {
        search: params?.search || '',
        limit: params?.limit || 20,
        start: params?.start || 0,
      }
    );
    return result.message as PaginatedDataTablesResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching data tables');
  }
}

/**
 * Get full table schema (fields + metadata)
 */
export async function getTableSchema(name: string): Promise<DataTableSchema> {
  try {
    const result = await call.get(
      'huf.huf.doctype.huf_data_table.api.get_table_schema',
      { name }
    );
    return result.message as DataTableSchema;
  } catch (error) {
    handleFrappeError(error, `Error fetching table schema`);
  }
}

/**
 * Create a new data table
 */
export async function createDataTable(data: {
  table_name: string;
  fields: DataTableFieldDef[];
  description?: string;
  icon?: string;
  autoname_method?: string;
  title_field?: string;
}): Promise<{ name: string; table_name: string; doctype_name: string }> {
  try {
    const result = await call.post(
      'huf.huf.doctype.huf_data_table.api.create_data_table',
      data
    );
    return result.message.data;
  } catch (error) {
    handleFrappeError(error, 'Error creating data table');
  }
}

/**
 * Update a data table structure
 */
export async function updateDataTable(
  name: string,
  data: {
    fields?: DataTableFieldDef[];
    description?: string;
    icon?: string;
  }
): Promise<void> {
  try {
    await call.post(
      'huf.huf.doctype.huf_data_table.api.update_data_table',
      { name, ...data }
    );
  } catch (error) {
    handleFrappeError(error, 'Error updating data table');
  }
}

/**
 * Delete a data table
 */
export async function deleteDataTable(name: string): Promise<{ deleted_records: number }> {
  try {
    const result = await call.post(
      'huf.huf.doctype.huf_data_table.api.delete_data_table',
      { name }
    );
    return result.message.data;
  } catch (error) {
    handleFrappeError(error, 'Error deleting data table');
  }
}

/**
 * Get list of Huf table names (for Link field target selection)
 */
export async function getHufTableNames(): Promise<
  Array<{ table_name: string; doctype_name: string }>
> {
  try {
    const result = await call.get(
      'huf.huf.doctype.huf_data_table.api.get_huf_table_names'
    );
    return result.message;
  } catch (error) {
    handleFrappeError(error, 'Error fetching table names');
  }
}

// ─── Record CRUD (uses standard Frappe SDK directly) ───

/**
 * Get records from a data table
 */
export async function getTableRecords(
  doctypeName: string,
  params?: {
    fields?: string[];
    filters?: Array<[string, string, unknown]>;
    limit?: number;
    start?: number;
    search?: string;
    orderBy?: { field: string; order: 'asc' | 'desc' };
  }
): Promise<{ items: Record<string, unknown>[]; hasMore: boolean; total?: number }> {
  try {
    const limit = params?.limit || 20;
    const records = await db.getDocList(doctypeName, {
      fields: params?.fields || ['*'],
      filters: params?.filters as any,
      limit: limit + 1,
      ...(params?.start && { limit_start: params.start }),
      orderBy: params?.orderBy || { field: 'modified', order: 'desc' },
    });

    const hasMore = records.length > limit;
    const items = hasMore ? records.slice(0, limit) : records;

    return { items: items as Record<string, unknown>[], hasMore };
  } catch (error) {
    handleFrappeError(error, 'Error fetching records');
  }
}

/**
 * Get a single record
 */
export async function getTableRecord(
  doctypeName: string,
  recordName: string
): Promise<Record<string, unknown>> {
  try {
    return (await db.getDoc(doctypeName, recordName)) as Record<string, unknown>;
  } catch (error) {
    handleFrappeError(error, 'Error fetching record');
  }
}

/**
 * Create a record in a data table
 */
export async function createTableRecord(
  doctypeName: string,
  data: Record<string, unknown>
): Promise<Record<string, unknown>> {
  try {
    return (await db.createDoc(doctypeName, data)) as Record<string, unknown>;
  } catch (error) {
    handleFrappeError(error, 'Error creating record');
  }
}

/**
 * Update a record
 */
export async function updateTableRecord(
  doctypeName: string,
  recordName: string,
  data: Record<string, unknown>
): Promise<void> {
  try {
    await db.updateDoc(doctypeName, recordName, data);
  } catch (error) {
    handleFrappeError(error, 'Error updating record');
  }
}

/**
 * Delete a record
 */
export async function deleteTableRecord(
  doctypeName: string,
  recordName: string
): Promise<void> {
  try {
    await db.deleteDoc(doctypeName, recordName);
  } catch (error) {
    handleFrappeError(error, 'Error deleting record');
  }
}
```

---

## 6. UX Design — User Flows

### 6.1 Overall Navigation

```
Sidebar: "Data" → /data
  │
  ├── Data Tables listing (grid of table cards)
  │     ├── Search bar + "Create Table" button (header action)
  │     ├── Each card shows: name, description, field count, record count, icon
  │     └── Click card → Table Data View (/data/:tableId)
  │
  ├── /data/new → Table Builder (create new table)
  │     └── Save → redirects to /data/:tableId
  │
  ├── /data/:tableId → Table Data View (records)
  │     ├── Record list with search/filter
  │     ├── "Add Record" button → opens record form (sheet/dialog)
  │     ├── Click record → edit record (sheet/dialog)
  │     └── "Edit Table" button → /data/:tableId/edit
  │
  └── /data/:tableId/edit → Table Builder (edit existing)
        └── Save → redirects back to /data/:tableId
```

### 6.2 User Flow: Creating a Table

```
┌──────────────────────────────────────────────────────────────┐
│  Step 1: User clicks "Create Table" on Data page             │
│  → Navigates to /data/new                                    │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Step 2: Table Builder opens with empty canvas               │
│                                                              │
│  ┌─────────────────────────┐  ┌──────────────────────────┐   │
│  │  LEFT: Builder Canvas   │  │  RIGHT: Config Panel     │   │
│  │                         │  │                          │   │
│  │  Table Name: [_______]  │  │  (shows table settings   │   │
│  │  Description: [______]  │  │   when no field selected)│   │
│  │                         │  │                          │   │
│  │  ┌───────────────────┐  │  │  Table Name: Products    │   │
│  │  │ + Add Field       │  │  │  Description: [_____]    │   │
│  │  └───────────────────┘  │  │  Naming: [Autoincrement] │   │
│  │                         │  │  Icon: [____]            │   │
│  └─────────────────────────┘  └──────────────────────────┘   │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Step 3: User clicks "+ Add Field"                           │
│  → Field Type Selector opens (popover/modal)                 │
│                                                              │
│  ┌───────────────────────────────────────────────┐           │
│  │  Choose Field Type                             │           │
│  │                                                │           │
│  │  Text           Numbers         Date/Time      │           │
│  │  ┌──────┐       ┌──────┐       ┌──────┐       │           │
│  │  │ Abc  │ Data  │ 123  │ Int   │ Cal  │ Date  │           │
│  │  │      │       │      │       │      │       │           │
│  │  ├──────┤       ├──────┤       ├──────┤       │           │
│  │  │ ¶    │ Text  │ 1.5  │ Float │ DT   │ D+T   │           │
│  │  │      │       │      │       │      │       │           │
│  │  ├──────┤       ├──────┤       ├──────┤       │           │
│  │  │ Sm   │ Small │ $    │ Curr. │ Clk  │ Time  │           │
│  │  └──────┘ Text  └──────┘       └──────┘       │           │
│  │                                                │           │
│  │  Choice         Reference      Other           │           │
│  │  ┌──────┐       ┌──────┐       ┌──────┐       │           │
│  │  │ ▼    │Select │ →    │ Link  │ ✓    │ Check │           │
│  │  └──────┘       └──────┘       └──────┘       │           │
│  │  ┌──────┐                      ┌──────┐       │           │
│  │  │ ★    │Rating               │ 🎨   │ Color │           │
│  │  └──────┘                      └──────┘       │           │
│  │                                                │           │
│  │  Layout                                        │           │
│  │  ┌──────┐       ┌──────┐                       │           │
│  │  │ ──── │Section│ │    │Column                 │           │
│  │  └──────┘ Break └──────┘ Break                 │           │
│  └───────────────────────────────────────────────┘           │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Step 4: Field appears in canvas, config panel shows props   │
│                                                              │
│  ┌─────────────────────────┐  ┌──────────────────────────┐   │
│  │  Builder Canvas         │  │  Field Properties        │   │
│  │                         │  │                          │   │
│  │  ┌───────────────────┐  │  │  Label: [Product Name ]  │   │
│  │  │ ≡ Product Name    │  │  │  Field Name: product_name│   │
│  │  │   Data  •Required │  │  │  Type: Data              │   │
│  │  └───────────────────┘  │  │                          │   │
│  │  ┌───────────────────┐  │  │  ☑ Required              │   │
│  │  │ ≡ Price           │  │  │  ☐ Unique                │   │
│  │  │   Currency        │  │  │  ☐ Read Only             │   │
│  │  └───────────────────┘  │  │  ☐ Show in List View     │   │
│  │  ┌───────────────────┐  │  │                          │   │
│  │  │ ── Details ──     │  │  │  Default: [________]     │   │
│  │  │   Section Break   │  │  │  Description: [______]   │   │
│  │  └───────────────────┘  │  │                          │   │
│  │  ┌───────────────────┐  │  │  [Delete Field]          │   │
│  │  │ ≡ Description     │  │  │                          │   │
│  │  │   Text            │  │  │                          │   │
│  │  └───────────────────┘  │  │                          │   │
│  │                         │  │                          │   │
│  │  ┌───────────────────┐  │  │                          │   │
│  │  │ + Add Field       │  │  │                          │   │
│  │  └───────────────────┘  │  │                          │   │
│  └─────────────────────────┘  └──────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  [Cancel]                              [Save Table]  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 User Flow: Viewing & Adding Data

```
┌──────────────────────────────────────────────────────────────┐
│  /data/:tableId — Table Data View                            │
│                                                              │
│  Breadcrumbs: Data > Products                                │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Products                    [Edit Table] [+ Add Row]│    │
│  │  Product catalog for inventory                       │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Search: [___________]    Status: [All ▼]            │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Name   │ Product Name │ Price  │ Status  │ Modified │    │
│  ├─────────┼──────────────┼────────┼─────────┼──────────┤    │
│  │  HT-001 │ Widget A     │ $29.99 │ Active  │ 2 hrs ago│    │
│  │  HT-002 │ Widget B     │ $49.99 │ Draft   │ 1 day ago│    │
│  │  HT-003 │ Gadget C     │ $99.99 │ Active  │ 3 days   │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Showing 3 of 3 records          [Load More]                 │
└──────────────────────────────────────────────────────────────┘

When user clicks "+ Add Row" or clicks a record row:

┌──────────────────────────────────────────────────────────────┐
│  Sheet slides in from right (or dialog)                      │
│                                                              │
│  ┌──────────────────────────────────────────────────┐        │
│  │  Add New Record               [✕ Close]          │        │
│  │                                                  │        │
│  │  Product Name *                                  │        │
│  │  [________________________]                      │        │
│  │                                                  │        │
│  │  Price                                           │        │
│  │  [________________________]                      │        │
│  │                                                  │        │
│  │  ── Details ──────────────────                   │        │
│  │                                                  │        │
│  │  Description                                     │        │
│  │  [________________________]                      │        │
│  │  [________________________]                      │        │
│  │  [________________________]                      │        │
│  │                                                  │        │
│  │  Status                                          │        │
│  │  [Active           ▼     ]                       │        │
│  │                                                  │        │
│  │  ┌──────────────────────────────────────┐        │        │
│  │  │         [Cancel]    [Save Record]    │        │        │
│  │  └──────────────────────────────────────┘        │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Component Specifications

### 7.1 DataPage (Modified)

**File**: `frontend/src/pages/DataPage.tsx`
**Pattern**: Same as `AgentsPage.tsx` — uses `PageLayout`, `FilterBar`, `GridView`, `ItemCard`

```typescript
// Uses useInfiniteScroll with getDataTables
// Each ItemCard shows:
//   - title: table_name
//   - description: table description
//   - metadata: field_count, record_count, modified time
//   - actions: View Records, Edit Table
//   - onClick: navigate to /data/:tableId
```

### 7.2 DataTableBuilderPage

**File**: `frontend/src/pages/DataTableBuilderPage.tsx`
**Layout**: Two-panel — canvas (left ~60%) + config panel (right ~40%)

**State management**: Local state with `useReducer` for field list management

```typescript
interface BuilderState {
  tableName: string;
  description: string;
  icon: string;
  autonameMethod: 'Autoincrement' | 'Hash' | 'By Field';
  titleField: string;
  fields: DataTableFieldDef[];
  selectedFieldIndex: number | null;
  isDirty: boolean;
}

type BuilderAction =
  | { type: 'SET_TABLE_NAME'; payload: string }
  | { type: 'SET_DESCRIPTION'; payload: string }
  | { type: 'ADD_FIELD'; payload: DataTableFieldDef }
  | { type: 'UPDATE_FIELD'; payload: { index: number; field: Partial<DataTableFieldDef> } }
  | { type: 'REMOVE_FIELD'; payload: number }
  | { type: 'REORDER_FIELDS'; payload: { from: number; to: number } }
  | { type: 'SELECT_FIELD'; payload: number | null }
  | { type: 'LOAD_SCHEMA'; payload: DataTableSchema }
  // ...
```

**Key behaviors:**
- `isNew` mode (from `/data/new`) vs `isEdit` mode (from `/data/:tableId/edit`)
- In edit mode, loads existing schema via `getTableSchema()`
- Drag-to-reorder fields using HTML5 DnD or a library like `@dnd-kit`
- Auto-generates `fieldname` from `label` (snake_case)
- Validates before save (table name required, at least one data field)
- Unsaved changes warning (`beforeunload` event)

### 7.3 TableBuilderCanvas

**File**: `frontend/src/components/data-table/TableBuilderCanvas.tsx`

Renders the ordered list of fields as cards. Each card shows:
- Drag handle (grip icon)
- Field label
- Field type badge
- Required indicator
- Selected state highlight
- Click to select → shows properties in config panel

Layout fields (Section Break, Column Break) render differently:
- Section Break: full-width divider with label
- Column Break: visual column separator

### 7.4 FieldConfigPanel

**File**: `frontend/src/components/data-table/FieldConfigPanel.tsx`

Right side panel that shows either:
- **Table settings** (when no field selected): name, description, icon, naming
- **Field properties** (when a field is selected): all applicable properties for that field type

Uses existing shadcn/ui form components: `Input`, `Select`, `Checkbox`, `Textarea`.

Properties shown depend on field type:
```typescript
const FIELD_PROPERTIES: Record<string, string[]> = {
  Data: ['label', 'reqd', 'unique', 'read_only', 'default', 'description', 'in_list_view'],
  Int: ['label', 'reqd', 'unique', 'read_only', 'default', 'description', 'in_list_view', 'non_negative'],
  Select: ['label', 'reqd', 'read_only', 'default', 'options', 'description', 'in_list_view'],
  Link: ['label', 'reqd', 'read_only', 'options', 'description', 'in_list_view'],
  'Section Break': ['label'],
  'Column Break': [],
  // ... etc
};
```

### 7.5 DataRecordList

**File**: `frontend/src/components/data-table/DataRecordList.tsx`

Uses **TanStack React Table** (already in the project) to render records.

- Dynamically generates columns from the table schema
- Columns with `in_list_view=1` are shown by default
- Always shows `name` (ID) and `modified` columns
- Row click → opens record in sheet/dialog for editing
- Supports sorting by clicking column headers
- Uses `getTableRecords()` for data fetching

### 7.6 DataRecordForm

**File**: `frontend/src/components/data-table/DataRecordForm.tsx`

Dynamically renders a form based on the table schema. Renders inside a `Sheet` (side panel) component.

- Reads field definitions from schema
- Renders appropriate input for each field type:
  - Data → `<Input />`
  - Text/Long Text → `<Textarea />`
  - Int/Float/Currency/Percent → `<Input type="number" />`
  - Check → `<Checkbox />`
  - Date → date picker from shadcn/ui
  - Datetime → date+time picker
  - Select → `<Select />` with options
  - Link → custom autocomplete that searches target table
  - Rating → star rating component
  - Color → color picker
- Respects Section Break and Column Break for layout
- Uses React Hook Form + Zod for validation
- Generates Zod schema dynamically from field definitions

### 7.7 FieldTypeSelector

**File**: `frontend/src/components/data-table/FieldTypeSelector.tsx`

Grid-based picker shown when user clicks "Add Field". Grouped by category.

```typescript
const FIELD_TYPE_GROUPS = [
  {
    label: 'Text',
    types: [
      { type: 'Data', label: 'Short Text', icon: Type },
      { type: 'Text', label: 'Long Text', icon: AlignLeft },
      { type: 'Small Text', label: 'Medium Text', icon: FileText },
    ],
  },
  {
    label: 'Numbers',
    types: [
      { type: 'Int', label: 'Integer', icon: Hash },
      { type: 'Float', label: 'Decimal', icon: Hash },
      { type: 'Currency', label: 'Currency', icon: DollarSign },
      { type: 'Percent', label: 'Percent', icon: Percent },
    ],
  },
  {
    label: 'Date & Time',
    types: [
      { type: 'Date', label: 'Date', icon: Calendar },
      { type: 'Datetime', label: 'Date & Time', icon: CalendarClock },
      { type: 'Time', label: 'Time', icon: Clock },
      { type: 'Duration', label: 'Duration', icon: Timer },
    ],
  },
  {
    label: 'Choice',
    types: [
      { type: 'Select', label: 'Dropdown', icon: ChevronDown },
      { type: 'Check', label: 'Checkbox', icon: CheckSquare },
      { type: 'Rating', label: 'Rating', icon: Star },
    ],
  },
  {
    label: 'Reference',
    types: [
      { type: 'Link', label: 'Link to Table', icon: Link2 },
    ],
  },
  {
    label: 'Other',
    types: [
      { type: 'Color', label: 'Color', icon: Palette },
      { type: 'Phone', label: 'Phone', icon: Phone },
    ],
  },
  {
    label: 'Layout',
    types: [
      { type: 'Section Break', label: 'Section', icon: Minus },
      { type: 'Column Break', label: 'Column', icon: Columns },
    ],
  },
];
```

### 7.8 DeleteTableDialog

Uses existing `AlertDialog` from shadcn/ui. Shows:
- Table name
- Record count (fetched before showing)
- Warning that all data will be permanently deleted
- Requires typing table name to confirm (for tables with data)

---

## 8. API Specifications

### Backend API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `huf.huf.doctype.huf_data_table.api.get_data_tables` | List tables |
| GET | `huf.huf.doctype.huf_data_table.api.get_table_schema` | Get table schema |
| POST | `huf.huf.doctype.huf_data_table.api.create_data_table` | Create table |
| POST | `huf.huf.doctype.huf_data_table.api.update_data_table` | Update table |
| POST | `huf.huf.doctype.huf_data_table.api.delete_data_table` | Delete table |
| GET | `huf.huf.doctype.huf_data_table.api.get_huf_table_names` | List table names (for Link) |

### Record CRUD (Standard Frappe SDK)

| Operation | SDK Method | Example |
|-----------|-----------|---------|
| List | `db.getDocList(doctypeName, ...)` | `db.getDocList("HT Products", { limit: 20 })` |
| Get | `db.getDoc(doctypeName, name)` | `db.getDoc("HT Products", "1")` |
| Create | `db.createDoc(doctypeName, data)` | `db.createDoc("HT Products", { product_name: "Widget" })` |
| Update | `db.updateDoc(doctypeName, name, data)` | `db.updateDoc("HT Products", "1", { price: 29.99 })` |
| Delete | `db.deleteDoc(doctypeName, name)` | `db.deleteDoc("HT Products", "1")` |

---

## 9. Type Definitions

### `frontend/src/types/dataTable.types.ts`

```typescript
/**
 * A field definition for the table builder
 */
export interface DataTableFieldDef {
  fieldname: string;
  fieldtype: DataTableFieldType;
  label: string;
  reqd?: 0 | 1;
  unique?: 0 | 1;
  read_only?: 0 | 1;
  hidden?: 0 | 1;
  default?: string;
  options?: string;
  description?: string;
  in_list_view?: 0 | 1;
  non_negative?: 0 | 1;
  idx?: number;
}

/**
 * Allowed field types for Huf data tables
 */
export type DataTableFieldType =
  | 'Data'
  | 'Small Text'
  | 'Text'
  | 'Long Text'
  | 'Int'
  | 'Float'
  | 'Currency'
  | 'Percent'
  | 'Check'
  | 'Date'
  | 'Datetime'
  | 'Time'
  | 'Duration'
  | 'Select'
  | 'Link'
  | 'Rating'
  | 'Color'
  | 'Phone'
  | 'Section Break'
  | 'Column Break';

/**
 * Layout-only field types (no DB column)
 */
export type LayoutFieldType = 'Section Break' | 'Column Break';

/**
 * Huf Data Table registry record (from Frappe)
 */
export interface HufDataTable {
  name: string;
  table_name: string;
  doctype_name: string;
  description: string;
  icon: string;
  field_count: number;
  record_count: number;
  is_active: 0 | 1;
  autoname_method: 'Autoincrement' | 'Hash' | 'By Field';
  title_field_name: string;
  creation: string;
  modified: string;
}

/**
 * Full table schema (registry + field definitions)
 */
export interface DataTableSchema {
  name: string;
  table_name: string;
  doctype_name: string;
  description: string;
  icon: string;
  autoname_method: string;
  title_field_name: string;
  fields: DataTableFieldDef[];
}

/**
 * Pagination params for data tables listing
 */
export interface GetDataTablesParams {
  search?: string;
  limit?: number;
  start?: number;
}

/**
 * Paginated response for data tables
 */
export interface PaginatedDataTablesResponse {
  items: HufDataTable[];
  has_more: boolean;
  total: number;
}

/**
 * Field type metadata for the field type selector
 */
export interface FieldTypeInfo {
  type: DataTableFieldType;
  label: string;
  description: string;
  icon: string;
  category: string;
  hasOptions: boolean;
  supportsUnique: boolean;
  supportsNonNegative: boolean;
}
```

### Update `frontend/src/data/doctypes.ts`

```typescript
export const doctype = {
  // ... existing entries ...
  "Huf Data Table": "Huf Data Table",
} as const;
```

---

## 10. Route Plan

### New Routes

| Route | Page Component | Layout | Description |
|-------|---------------|--------|-------------|
| `/data` | `DataPage` (modified) | `UnifiedLayout` + `DataHeaderActions` | Table listing |
| `/data/new` | `DataTableBuilderWrapper` | Breadcrumb layout | Create new table |
| `/data/:tableId` | `DataTableViewWrapper` | Breadcrumb layout | View table records |
| `/data/:tableId/edit` | `DataTableBuilderWrapper` | Breadcrumb layout | Edit table schema |

### Router Changes (`App.tsx`)

```tsx
// Replace existing /data route and add new routes:

<Route
  path="/data"
  element={
    <ProtectedRoute>
      <UnifiedLayout headerActions={<DataHeaderActions />}>
        <DataPage />
      </UnifiedLayout>
    </ProtectedRoute>
  }
/>
<Route
  path="/data/new"
  element={
    <ProtectedRoute>
      <DataTableBuilderWrapper />
    </ProtectedRoute>
  }
/>
<Route
  path="/data/:tableId"
  element={
    <ProtectedRoute>
      <DataTableViewWrapper />
    </ProtectedRoute>
  }
/>
<Route
  path="/data/:tableId/edit"
  element={
    <ProtectedRoute>
      <DataTableBuilderWrapper />
    </ProtectedRoute>
  }
/>
```

### Breadcrumb Structure

```
Data (listing):     Data
New table:          Data > New Table
Table records:      Data > Products
Edit table:         Data > Products > Edit
```

---

## 11. Implementation Phases

### Phase 1: Backend Foundation

**Goal**: Registry DocType + API endpoints

**Tasks**:
1. Create `Huf Data Table` DocType (JSON + controller)
2. Implement `api.py` with all endpoints
3. Implement `validators.py` with field validation
4. Add tests
5. Update `hooks.py` if needed (module registration)

**Files created**:
- `huf/huf/doctype/huf_data_table/huf_data_table.json`
- `huf/huf/doctype/huf_data_table/huf_data_table.py`
- `huf/huf/doctype/huf_data_table/api.py`
- `huf/huf/doctype/huf_data_table/validators.py`
- `huf/huf/doctype/huf_data_table/test_huf_data_table.py`
- `huf/huf/doctype/huf_data_table/__init__.py`

**Estimated complexity**: Medium

### Phase 2: Frontend Types, Service, Data

**Goal**: Type definitions, API service, field type metadata

**Tasks**:
1. Create `dataTable.types.ts`
2. Create `dataTableApi.ts` service
3. Create `fieldTypes.ts` with field type metadata
4. Update `doctypes.ts` with new constant

**Files created/modified**:
- `frontend/src/types/dataTable.types.ts` (new)
- `frontend/src/services/dataTableApi.ts` (new)
- `frontend/src/data/fieldTypes.ts` (new)
- `frontend/src/data/doctypes.ts` (modified)

**Estimated complexity**: Low

### Phase 3: Data Page (Table Listing)

**Goal**: Replace placeholder DataPage with functional table listing

**Tasks**:
1. Rewrite `DataPage.tsx` using `PageLayout`, `GridView`, `ItemCard`, `FilterBar`
2. Create `DataHeaderActions.tsx` with "Create Table" button
3. Update routes in `App.tsx`

**Files created/modified**:
- `frontend/src/pages/DataPage.tsx` (rewrite)
- `frontend/src/components/DataHeaderActions.tsx` (new)
- `frontend/src/App.tsx` (modified)

**Estimated complexity**: Low (follows existing AgentsPage pattern)

### Phase 4: Table Builder

**Goal**: Full table schema builder (create + edit)

**Tasks**:
1. Create `DataTableBuilderPage.tsx` with `useReducer` state
2. Create `DataTableBuilderWrapper.tsx` with breadcrumbs
3. Create `TableBuilderCanvas.tsx` — field list with drag-reorder
4. Create `FieldCard.tsx` — individual field card
5. Create `SectionBreakCard.tsx` / `ColumnBreakCard.tsx`
6. Create `FieldConfigPanel.tsx` — property editor
7. Create `FieldTypeSelector.tsx` — type picker grid
8. Create `AddFieldButton.tsx`
9. Create `TableSettingsPanel.tsx`
10. Create `LinkFieldSelector.tsx` — Link target picker
11. Wire up save logic (create/update API calls)
12. Add routes for `/data/new` and `/data/:tableId/edit`

**Files created**:
- `frontend/src/pages/DataTableBuilderPage.tsx`
- `frontend/src/pages/DataTableBuilderWrapper.tsx`
- `frontend/src/components/data-table/TableBuilderCanvas.tsx`
- `frontend/src/components/data-table/FieldCard.tsx`
- `frontend/src/components/data-table/SectionBreakCard.tsx`
- `frontend/src/components/data-table/ColumnBreakCard.tsx`
- `frontend/src/components/data-table/FieldConfigPanel.tsx`
- `frontend/src/components/data-table/FieldTypeSelector.tsx`
- `frontend/src/components/data-table/AddFieldButton.tsx`
- `frontend/src/components/data-table/TableSettingsPanel.tsx`
- `frontend/src/components/data-table/LinkFieldSelector.tsx`

**Estimated complexity**: High (core UX challenge)

### Phase 5: Table Data View

**Goal**: View, add, edit, delete records

**Tasks**:
1. Create `DataTableViewPage.tsx` — main records page
2. Create `DataTableViewWrapper.tsx` — with breadcrumbs
3. Create `DataRecordList.tsx` — TanStack Table for records
4. Create `DataRecordForm.tsx` — dynamic form in Sheet
5. Create `DataRecordFilters.tsx` — search/filter bar
6. Create `DataTableHeaderActions.tsx`
7. Create `DeleteTableDialog.tsx`
8. Add routes for `/data/:tableId`

**Files created**:
- `frontend/src/pages/DataTableViewPage.tsx`
- `frontend/src/pages/DataTableViewWrapper.tsx`
- `frontend/src/components/data-table/DataRecordList.tsx`
- `frontend/src/components/data-table/DataRecordForm.tsx`
- `frontend/src/components/data-table/DataRecordFilters.tsx`
- `frontend/src/components/DataTableHeaderActions.tsx`
- `frontend/src/components/data-table/DeleteTableDialog.tsx`

**Estimated complexity**: High (dynamic form generation)

### Phase 6: Polish & Integration

**Goal**: Edge cases, validation, UX refinements

**Tasks**:
1. Unsaved changes warning in builder
2. Empty states for new tables
3. Loading skeletons
4. Error handling for all API calls
5. Toast notifications for all operations
6. Keyboard shortcuts (Escape to deselect, Delete to remove field)
7. Mobile responsiveness for builder (collapse config panel)

**Estimated complexity**: Medium

---

## 12. Future Considerations

### v2 Enhancements (not in scope for v1)

| Feature | Notes |
|---------|-------|
| **Tab Breaks** | Add Tab Break field type for complex form layouts |
| **CSV Import/Export** | Bulk data operations |
| **Conditional visibility** | `depends_on` expressions for fields |
| **Custom permissions** | Per-table role-based access |
| **Attach fields** | File upload support |
| **Computed fields** | Read-only fields with formulas |
| **Validation rules** | Field-level validation expressions |
| **API access** | Expose table data via Huf API for external access |
| **Webhooks on data changes** | Trigger flows when records change |
| **Agent tool integration** | Auto-generate CRUD tools for data tables |

### Agent Integration (Future)

Data tables created via Huf can serve as:
1. **Knowledge sources** — Agents can query table data
2. **Tool targets** — Auto-generate "Get Products", "Create Product" tools
3. **Trigger sources** — Flow triggers on record create/update/delete
4. **Output destinations** — Agents write results to tables

### Migration Considerations

- All Huf-created DocTypes use `custom=1` — safe to create/modify at runtime
- DocType names prefixed with `HT ` — easily identified
- Registry (`Huf Data Table`) provides clean inventory
- If Huf is uninstalled, custom DocTypes remain (can be cleaned up manually)

---

## Appendix A: shadcn/ui Components to Use

All components already exist in `frontend/src/components/ui/`:

| Component | Usage |
|-----------|-------|
| `Button` | All buttons |
| `Input` | Text fields in forms |
| `Textarea` | Text/Long Text fields |
| `Select` / `SelectContent` / `SelectItem` | Select fields, dropdowns |
| `Checkbox` | Check fields, property toggles |
| `Card` | Field cards in builder |
| `Sheet` | Record form side panel |
| `Dialog` / `AlertDialog` | Delete confirmation |
| `Badge` | Field type badges, status |
| `Popover` | Field type selector |
| `Separator` | Section breaks |
| `Label` | Form labels |
| `Tabs` | Could use for builder/preview toggle |
| `Table` | Record list (via TanStack) |
| `Tooltip` | Help text on hover |
| `Skeleton` | Loading states |

## Appendix B: Libraries Already Available

| Library | Version | Usage |
|---------|---------|-------|
| `@tanstack/react-table` | ^8.21.3 | Record list table |
| `react-hook-form` | 7 | Record form |
| `zod` | 3 | Dynamic form validation |
| `lucide-react` | ^0.563.0 | Icons for field types |
| `motion` | ^12.23.24 | Animations (drag, transitions) |
| `sonner` | — | Toast notifications |

### Potential New Dependency

| Library | Purpose | Alternative |
|---------|---------|-------------|
| `@dnd-kit/core` + `@dnd-kit/sortable` | Drag-to-reorder fields in builder | HTML5 DnD API (no dependency needed, but less polished) |

**Recommendation**: Use `@dnd-kit` for the field reorder UX — it's lightweight, accessible, and provides a much better experience than raw HTML5 DnD. The builder's reorder interaction is a core UX element that benefits from a purpose-built library.

## Appendix C: Naming Convention Summary

| Entity | Convention | Example |
|--------|-----------|---------|
| DocType (backend) | `HT <Table Name>` | `HT Products` |
| Registry record | Auto hash | `abc123def` |
| DB table | `tabHT Products` | (Frappe auto-prefixes with `tab`) |
| Frontend route param | Registry `name` | `/data/abc123def` |
| Field name | snake_case from label | `product_name` |
| API method path | `huf.huf.doctype.huf_data_table.api.*` | Standard Frappe pattern |
