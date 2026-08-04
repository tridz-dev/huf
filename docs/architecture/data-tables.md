# Dynamic Custom Data Tables

The `Huf Data Table` subsystem lets users (via the dashboard) or agents (via a builder tool) define arbitrary
database schemas at runtime: each entry creates both a lightweight registry row and a real, custom Frappe
`DocType` named `HF {table_name}` that behaves like any other DocType (list views, permissions, REST access,
Data Import).

## Table Registry: `Huf Data Table`

`Huf Data Table` (confirmed name — matches the old AGENTS.md description) is the registry DocType at
`huf/huf/doctype/huf_data_table/huf_data_table.json`. Key fields (`huf/huf/doctype/huf_data_table/huf_data_table.json:8-95`):

| Field | Type | Notes |
|---|---|---|
| `table_name` | Data, unique, required | Human-facing name, e.g. `Customers` |
| `doctype_name` | Data, unique, required, read-only | Always `HF {table_name}`, set in `validate()` |
| `autoname_method` | Select | `Autoincrement` (default) \| `Hash` \| `By Field` |
| `title_field_name` | Data | Only used when `autoname_method == "By Field"` |
| `description`, `table_group`, `icon` | — | Display metadata |
| `field_count`, `record_count` | Int, read-only | Denormalized counters |
| `is_active` | Check, default 1 | |

Controller logic (`huf/huf/doctype/huf_data_table/huf_data_table.py:1-14`) is minimal:
- `validate()`: derives `doctype_name = f"HF {table_name}"` if not already set.
- `on_trash()`: force-deletes the backing `DocType` when the registry row itself is deleted directly (belt-and-suspenders alongside the explicit deletion in `delete_data_table`, see below).

## Dynamic DocType construction

Table creation builds a real `DocType` document in Python and inserts it — there is no template file or code
generation step. The controlling logic lives in `huf/huf/doctype/huf_data_table/api.py` and
`huf/huf/doctype/huf_data_table/validators.py`:

- `validate_and_prepare_fields()` (`huf/huf/doctype/huf_data_table/validators.py:46-103`) whitelists field types
  (`ALLOWED_FIELD_TYPES`, `huf/huf/doctype/huf_data_table/validators.py:3-27` — Data, Text variants, Int, Float,
  Currency, Percent, Check, Date/Datetime/Time, Duration, Select, Link, Rating, Color, Phone, Attach/Attach Image,
  plus layout types Tab Break/Section Break/Column Break), rejects reserved fieldnames (`name`, `owner`,
  `creation`, etc.), and derives fieldnames from labels via `frappe.scrub()` when omitted. A `Link` field's
  `options` must point at another registered `Huf Data Table`'s `doctype_name` — links to arbitrary DocTypes are
  rejected.
- `resolve_autoname()` (`huf/huf/doctype/huf_data_table/validators.py:106-113`) maps the user-facing naming
  method to a Frappe `autoname` string: `By Field` + a title field → `field:{title_field}`, `Hash` → `hash`,
  anything else (including the default) → `autoincrement`.
- `get_search_fields()` (`huf/huf/doctype/huf_data_table/validators.py:116-130`) picks up to the first 3
  text-like fields (Data/Small Text/Text/Long Text/Phone) as the DocType's `search_fields`.

`create_data_table()` (`huf/huf/doctype/huf_data_table/api.py:136-227`) then:
1. Validates `table_name` against `[A-Za-z0-9][A-Za-z0-9 _-]{0,139}` and rejects collisions against both an
   existing `DocType` named `HF {table_name}` and an existing `Huf Data Table` registry row.
2. Inserts a new `DocType` with `custom=1`, `istable=0`, `module="Huf"`, the validated fields, computed
   `autoname`/`search_fields`, `track_changes=1`, `allow_rename=1`, `allow_import=1`.
3. Sets DocType-level permissions per role from `_import_permitted_roles()`/`_table_permission_row()`
   (`huf/huf/doctype/huf_data_table/api.py:67-106`) — System Manager gets full CRUD + import; every other Huf
   role that holds a `data.records.*`/`data.tables.manage` write capability gets a create+import-only DocPerm
   (record-level read/write/delete is instead governed separately, see below).
4. Inserts the matching `Huf Data Table` registry row.
5. Calls `sync_data_table_permissions()` to reconcile record-level access.

## Record-level permission sync

Because DocType Permission rows can't natively express "read your own records vs. all records" the way HUF's
capability model does, `huf/huf/doctype/huf_data_table/permissions.py` rebuilds each generated table's DocPerms
from the current Huf Role capability assignments whenever a role's capabilities change (`sync_data_table_permissions()`,
`huf/huf/doctype/huf_data_table/permissions.py:24-`). It reads `data.records.view_all`, `data.records.view_own`,
`data.records.edit_all`, `data.records.edit_own`, and `data.records.create` per role and skips/logs individual
tables on failure rather than aborting the whole rebuild. This is also exposed as a whitelisted endpoint,
`apply_data_permissions()` (`huf/huf/doctype/huf_data_table/api.py:757-766`), called by the Huf Role `on_update`
hook.

## API surface (`huf/huf/doctype/huf_data_table/api.py`)

All entry points below are `@frappe.whitelist()`. The old AGENTS.md only listed create/update/delete/count —
the actual surface is considerably larger (schema introspection, record CRUD/search, and CSV bulk import):

| Function | Line | Purpose | Capability gate |
|---|---|---|---|
| `create_data_table` | `api.py:136` | Create DocType + registry row | `data.tables.manage` |
| `update_data_table` | `api.py:231` | Replace field list and/or metadata on an existing table | `data.tables.manage` |
| `delete_data_table` | `api.py:274` | Force-delete the DocType and the registry row | `data.tables.manage` |
| `get_table_record_counts` | `api.py:299` | Live row counts for a list of registry names | any view capability |
| `get_table_schema` | `api.py:323` | Full field schema for one table | any view capability |
| `get_bulk_import_template_url` | `api.py:366` | Generate a CSV import template (or export) as a private File | view (template) / `data.tables.manage` (export) |
| `start_table_bulk_import` | `api.py:423` | Kick off a Frappe `Data Import` against the generated DocType | `data.tables.manage` |
| `get_table_bulk_import_status` | `api.py:469` | Poll a `Data Import`'s success/failure counts and error rows | any view capability |
| `get_table_records` | `api.py:524` | List/search rows with field-level or title-field search | any view capability |
| `get_table_agent_access` | `api.py:697` | Which agents can act on this table, and with what actions | any view capability |
| `get_tables_agent_counts` | `api.py:703` | Agent-count per table, for listing pages | any view capability |
| `set_table_agent_access` | `api.py:714` | Attach/detach the deterministic CRUD tools for a table on a given agent | `data.tables.manage` |
| `apply_data_permissions` | `api.py:758` | Force a full permission resync (`sync_data_table_permissions`) | `data.tables.manage` |

There is no dedicated "count" API distinct from `get_table_record_counts` / `get_table_records`'s `total` —
the old summary's phrase "counting rows" maps to those two.

### Agent access scaffolding

`set_table_agent_access` and friends (`api.py:570-754`) implement a deterministic tool set per data table:
enabling `view`/`create`/`edit`/`delete` for an agent lazily creates matching `Agent Tool Function` rows (types
`Get List`/`Get Document`/`Create Document`/`Update Document`/`Delete Document`) bound to the table's generated
DocType via `_scaffold_tool()`, with parameters derived straight from the DocType's field meta
(`_table_field_params()`, `api.py:615-628`). This is a separate mechanism from the builder tools described
below — it's how *other* agents (not the hub/builder agent) get scoped, typed CRUD access to a specific data
table.

## Relationship to the `create_huf_table` builder tool

The old AGENTS.md described the `Huf Data Table` subsystem and separately implied agents could build tables via
a `create_huf_table` tool — confirmed, and it is a thin wrapper, not a parallel implementation. In
`huf/ai/tools/builder.py:141-239`, `create_huf_table()`:

- Requires the caller to hold the `System Manager` or `Huf Manager` role (`_require_builder_capability()`,
  `huf/ai/tools/builder.py:48-54`) plus Frappe's own `create` permission on `Huf Data Table`.
- Re-runs the same `validate_and_prepare_fields` / `resolve_autoname` / `get_search_fields` validators from
  `huf/huf/doctype/huf_data_table/validators.py` to build a preview `diff`.
- Follows HUF's two-phase builder-tool contract: called with `confirm=False` it returns the diff without
  mutating anything; called again with `confirm=True` it calls `create_data_table()` from
  `huf/huf/doctype/huf_data_table/api.py` directly — the exact same function the dashboard UI calls.
- If the table already exists, it returns `already_exists: True` with the live schema instead of throwing,
  explicitly steering the calling agent toward `list_table_rows`/`add_table_row`/`update_table_row`/
  `delete_table_row` instead of re-creating it.

`create_huf_table` is registered in the tool registry at `huf/ai/tools/_registry.py:1015-1024`
(`function_path: huf.ai.tools.builder.create_huf_table`) and is one of the hub orchestrator's default tools
(`huf/ai/app_seeding/hub_orchestrator.py:56`). There is no `update_huf_table` or `delete_huf_table` builder
tool — schema updates and deletion are dashboard-only (`update_data_table`/`delete_data_table` in `api.py`).
What the builder toolset does provide beyond table creation is **row-level** CRUD against an existing table's
generated DocType, all in `huf/ai/tools/builder.py` and all following the same two-phase `confirm` pattern:

| Builder tool | Line | Purpose |
|---|---|---|
| `list_table_rows` | `builder.py:584` | Read-only row listing/filtering |
| `add_table_row` | `builder.py:626` | Two-phase row insert |
| `update_table_row` | `builder.py:658` | Two-phase row update (old/new diff) |
| `delete_table_row` | `builder.py:702` | Two-phase row delete |

These resolve the target table via `_get_table_registry()` (`builder.py:131-138`), which accepts either the
human `table_name` or the `Huf Data Table` registry name, then operate on the generated `HF {table_name}`
DocType with `frappe.get_list`/`get_doc`/`delete_doc` — no separate storage layer.

## Corrections vs. the old AGENTS.md summary

- The DocType name `Huf Data Table` was correct as stated.
- The API surface is much larger than "create/update/delete/count" — it also covers schema introspection, CSV
  bulk import (template generation, import start, status polling), record search/listing, and per-agent access
  scaffolding (table above).
- The `create_huf_table` agent tool is confirmed to reuse `create_data_table()` rather than duplicating table
  creation logic; it adds a confirm-gated preview step and role/capability checks on top.

See also: [docs/reference/doctypes.generated.md](../reference/doctypes.generated.md)
