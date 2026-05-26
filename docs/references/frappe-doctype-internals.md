# Frappe DocType Internals Reference

> Source: [github.com/frappe/frappe](https://github.com/frappe/frappe) — `frappe/core/doctype/doctype/` and `frappe/core/doctype/docfield/`

This document describes how Frappe stores DocType definitions, field schemas, and form layouts internally.

## DocType Document Structure

A DocType is itself a Frappe document (meta-DocType). When you create a DocType, Frappe stores it as a JSON file on disk (for standard DocTypes) or in the database (for custom DocTypes with `custom=1`).

### Key DocType Fields

| Field | Type | Purpose |
|-------|------|---------|
| `module` | Link → Module Def | Which module this DocType belongs to |
| `custom` | Check | `1` = stored in DB only (no JSON/py files on disk) |
| `is_submittable` | Check | Enables Submit/Cancel workflow |
| `istable` | Check | `1` = child table DocType |
| `issingle` | Check | `1` = singleton (one record only) |
| `editable_grid` | Check | Allow inline editing in child tables |
| `quick_entry` | Check | Enable quick-entry dialog |
| `track_changes` | Check | Track field-level changes |
| `fields` | Table → DocField | The field definitions (ordered list) |
| `permissions` | Table → DocPerm | Role-based permissions |
| `autoname` | Data | Naming rule (e.g., `field:title`, `hash`, `format:PRD-{####}`) |
| `naming_rule` | Select | High-level naming: Set by user, Autoincrement, By fieldname, etc. |
| `title_field` | Data | Field to use as display title |
| `search_fields` | Data | Comma-separated fields for search |
| `sort_field` | Data | Default sort field |
| `sort_order` | Select | `ASC` or `DESC` |
| `image_field` | Data | Field containing image URL |
| `description` | Small Text | DocType description |
| `allow_rename` | Check | Allow document renaming |
| `allow_import` | Check | Allow CSV import |
| `is_virtual` | Check | Virtual DocType (no DB table) |
| `is_tree` | Check | Tree structure DocType |
| `document_type` | Select | Classification: Document, Setup, etc. |

### Naming Rules

| `naming_rule` Value | `autoname` Pattern | Example |
|---------------------|-------------------|---------|
| Set by user | (empty) | User enters name |
| Autoincrement | (empty) | 1, 2, 3... |
| By fieldname | `field:field_name` | Uses field value as name |
| By "Naming Series" field | `naming_series:` | PRD-.####, INV-.YYYY.-.#### |
| Expression | `format:PRD-{####}` | Pattern-based |
| Random | `hash` | Random hash |
| By script | `prompt` | Custom Python |

## DocField Structure

Each field in a DocType is a **DocField** child record. Fields are stored as an ordered list — the order determines form layout.

### Key DocField Properties

| Property | Type | Purpose |
|----------|------|---------|
| **`fieldname`** | Data | Internal name (snake_case, unique within DocType) |
| **`fieldtype`** | Select | Field type (see list below) |
| **`label`** | Data | Display label |
| `reqd` | Check | `1` = mandatory |
| `unique` | Check | `1` = unique constraint |
| `read_only` | Check | `1` = non-editable |
| `hidden` | Check | `1` = hidden from form |
| `default` | Small Text | Default value |
| `options` | Small Text | Type-specific: Select options, Link target, etc. |
| `in_list_view` | Check | Show in list view |
| `in_standard_filter` | Check | Show as list filter |
| `in_global_search` | Check | Include in global search |
| `in_preview` | Check | Show in preview popup |
| `bold` | Check | Bold label |
| `translatable` | Check | Enable translation |
| `description` | Small Text | Help text below field |
| `length` | Int | Max character length |
| `precision` | Select | Decimal precision for numeric fields |
| `set_only_once` | Check | Can only be set during creation |
| `allow_on_submit` | Check | Editable after submit |
| `no_copy` | Check | Don't copy when duplicating |
| `permlevel` | Int | Permission level (0-9) |
| `columns` | Int | Grid columns (1-10) for list view |
| `non_negative` | Check | For numeric: disallow negative values |

### Layout Properties

| Property | Type | Purpose |
|----------|------|---------|
| `collapsible` | Check | For Section Break: start collapsed |
| `hide_border` | Check | For Section Break: no border |
| `width` | Data | CSS width (e.g., `50%`) |

### Conditional Properties (NOT used in Huf v1)

| Property | Type | Purpose |
|----------|------|---------|
| `depends_on` | Code | JS expression for visibility |
| `mandatory_depends_on` | Code | JS expression for conditional mandatory |
| `read_only_depends_on` | Code | JS expression for conditional read-only |
| `fetch_from` | Small Text | Auto-fetch from linked document |
| `fetch_if_empty` | Check | Only fetch if field is empty |

## All Frappe Field Types

```
Autocomplete          Attach              Attach Image
Barcode               Button              Check
Code                  Color               Column Break
Currency              Data                Date
Datetime              Duration            Dynamic Link
Float                 Fold                Geolocation
Heading               HTML                HTML Editor
Icon                  Image               Int
JSON                  Link                Long Text
Markdown Editor       Password            Percent
Phone                 Read Only           Rating
Section Break         Select              Signature
Small Text            Tab Break           Table
Table MultiSelect     Text                Text Editor
Time
```

### Field Types Relevant for Huf

**Data Entry Fields** (create database columns):
| Type | Description | `options` Usage |
|------|-------------|-----------------|
| `Data` | Short text, up to 140 chars | Validation regex, or "Email"/"URL"/"Phone" |
| `Small Text` | Medium text, stored as text | — |
| `Text` | Long text (textarea) | — |
| `Int` | Integer | — |
| `Float` | Decimal | — |
| `Currency` | Money amount | Currency field name |
| `Percent` | Percentage (0-100) | — |
| `Check` | Boolean checkbox (0/1) | — |
| `Date` | Date picker | — |
| `Datetime` | Date + time picker | — |
| `Time` | Time picker | — |
| `Select` | Dropdown | Newline-separated options |
| `Link` | Foreign key to another DocType | Target DocType name |
| `Rating` | Star rating (0-5) | — |
| `Color` | Color picker | — |
| `Phone` | Phone number | — |
| `Duration` | Time duration | — |
| `Long Text` | Very long text | — |
| `Password` | Encrypted field | — |

**Layout Fields** (NO database columns):
| Type | Description |
|------|-------------|
| `Section Break` | Starts a new section (with optional label) |
| `Column Break` | Starts a new column within a section |
| `Tab Break` | Starts a new tab (with label) |

### How Layout Works

Frappe's form layout is determined by the **order of fields** in the fields list:

```
Tab Break "Details"        ← New tab
  Section Break "Basic"    ← New section in tab
    Data "Name"            ← Field in column 1
    Data "Email"
    Column Break           ← Switch to column 2
    Data "Phone"
    Date "DOB"
  Section Break "Address"  ← New section
    Text "Street"
    Column Break
    Data "City"
    Data "State"
Tab Break "Settings"       ← New tab
  Section Break
    Check "Active"
```

**Rules:**
- A form starts with an implicit first tab and first section
- `Tab Break` creates a new tab — all subsequent fields go into this tab
- `Section Break` creates a new section — displayed as a card/panel
- `Column Break` splits the current section into columns (max ~3-4 practical)
- Layout fields don't create database columns
- Layout fields have `fieldname` but it's auto-generated (e.g., `section_break_5`)

## Programmatic DocType Creation

```python
import frappe

# Create DocType
dt = frappe.new_doc("DocType")
dt.update({
    "name": "My Custom Table",
    "module": "Custom",      # or specific module
    "custom": 1,             # IMPORTANT: custom=1 means DB-only, no files
    "istable": 0,
    "issingle": 0,
    "autoname": "autoincrement",  # or "hash", "field:title", etc.
    "fields": [
        {
            "fieldname": "title",
            "fieldtype": "Data",
            "label": "Title",
            "reqd": 1,
            "in_list_view": 1,
        },
        {
            "fieldname": "section_break_1",
            "fieldtype": "Section Break",
            "label": "Details",
        },
        {
            "fieldname": "description",
            "fieldtype": "Text",
            "label": "Description",
        },
        {
            "fieldname": "column_break_1",
            "fieldtype": "Column Break",
        },
        {
            "fieldname": "status",
            "fieldtype": "Select",
            "label": "Status",
            "options": "Draft\nActive\nArchived",
            "default": "Draft",
            "in_list_view": 1,
        },
    ],
    "permissions": [
        {
            "role": "System Manager",
            "read": 1, "write": 1, "create": 1, "delete": 1,
        }
    ],
})
dt.insert()
frappe.db.commit()
```

## Modifying Existing DocTypes

```python
# Add field to existing DocType
dt = frappe.get_doc("DocType", "My Custom Table")
dt.append("fields", {
    "fieldname": "new_field",
    "fieldtype": "Data",
    "label": "New Field",
})
dt.save()
frappe.db.commit()

# Remove field
dt = frappe.get_doc("DocType", "My Custom Table")
dt.fields = [f for f in dt.fields if f.fieldname != "old_field"]
dt.save()
frappe.db.commit()

# Modify field properties
dt = frappe.get_doc("DocType", "My Custom Table")
for field in dt.fields:
    if field.fieldname == "title":
        field.reqd = 1
        field.in_list_view = 1
        break
dt.save()
frappe.db.commit()
```

## Custom vs Standard DocTypes

| Aspect | Standard (`custom=0`) | Custom (`custom=1`) |
|--------|----------------------|---------------------|
| Storage | JSON file + Python file on disk | Database only |
| Module required | Yes (valid Module Def) | "Custom" module |
| Migration | Via `bench migrate` | Immediate |
| Version control | Git tracked | Not tracked |
| Performance | Slightly faster (cached from file) | Loaded from DB |
| **Best for Huf** | No | **Yes** — no file system access needed |

## Relevance to Huf

1. **Always use `custom=1`**: Huf creates tables at runtime; no file-system artifacts needed
2. **Use layout fields**: Section Break, Column Break for form organization — same mechanism Frappe uses
3. **Tab Breaks**: Can be added later (v2) for complex forms
4. **Field ordering**: Store fields in order — the order IS the layout
5. **Standard properties**: Reuse `reqd`, `read_only`, `unique`, `default`, `options`, `in_list_view`, `description`
6. **Naming**: Use `autoname: "autoincrement"` or `"hash"` for simplicity
7. **Permissions**: Set per-role permissions at creation time
