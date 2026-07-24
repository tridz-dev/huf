# Phase 4a — Backend Implementation: HUF Table → Agent Actions

Branch: `feat/huf-table-agent-actions`. Scope: backend only (`huf/`). No `frontend/` changes.

## What was built

### Endpoints (both in `huf/huf/doctype/huf_data_table/api.py`)

```python
@frappe.whitelist()
def get_table_agent_access(table: str) -> list:
    """Which agents currently have access to this HUF Table, and with which actions.
    Returns: [{"agent": <name>, "agent_name": <label>, "actions": [...], "tools": [...]}]
    Requires: flows.use"""

@frappe.whitelist()
def set_table_agent_access(table: str, agent: str, actions: str | list) -> dict:
    """Make the agent's access to this table EXACTLY `actions` (idempotent).
    Returns the resulting state in the same shape as get_table_agent_access (one agent).
    Requires: flows.manage"""
```

Guards reuse the file's existing `_require_read()` / `_require_write()` helpers
(capabilities `flows.use` / `flows.manage`, `huf/permissions.py`) — the same posture as
`create_data_table` (`api.py:32-44`). System Manager / Administrator hold every
capability (`permissions.py:181-182`), so this matches the "System Manager only" brief.

`table` accepts either the `Huf Data Table` registry docname (hash autoname) or the
human `table_name` (`_resolve_table_registry`).

### The mapping (single source, B2)

```python
TABLE_ACTION_MAP: dict[str, tuple[tuple[str, str], ...]] = {
	"view": (("Get List", "read"), ("Get Document", "read")),
	"create": (("Create Document", "create"),),
	"edit": (("Update Document", "write"),),
	"delete": (("Delete Document", "delete"),),
}
_TYPES_TO_ACTION = {types: action for action, specs in TABLE_ACTION_MAP.items() for types, _ in specs}
```

`_TYPES_TO_ACTION` is *derived* from `TABLE_ACTION_MAP` — nothing is duplicated. A
comment above the constant marks the future "Advanced drawer" TODO (Submit/Cancel
Document, Get/Set Value, bulk "Multiple" variants).

### Tool naming — DEVIATION from the decided literal name (forced by validation)

Decided: `tool_name = f"{doctype_name} - {types}"` → e.g. `"HF Customers - Get List"`.

**That literal string cannot be saved.** `AgentToolFunction.validate_tool_name`
(`agent_tool_function.py:76-81`) enforces `^[a-zA-Z0-9_-]{1,128}$` — spaces are rejected
with a `frappe.throw`. Resolution: keep the readable form as the base and collapse
invalid characters deterministically:

```python
def _table_tool_name(doctype_name: str, types: str) -> str:
	return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{doctype_name} - {types}")
```

`"HF Customers - Get List"` → `"HF_Customers_-_Get_List"`. Still one name per
(doctype, types) pair, so reuse-if-exists idempotency is preserved.

### Scaffolding behaviour

- `_scaffold_tool` sets ONLY `tool_name`, `description`, `types`, `reference_doctype`,
  `required_permission`, `tool_type` on the new `Agent Tool Function` doc. `params` and
  `function_definition` are left to the controller (see evidence below).
- `tool_type` is a **required** Link; no existing `Agent Tool Type` fits, so a
  `"Data Table"` category is created on demand (`_ensure_table_tool_type`), mirroring
  `app_seeding/loaders.py` auto-creating missing categories.
- Attach: `agent_doc.append("agent_tool", {"tool": ...})` only if not already linked.
- Detach: attached tools whose `reference_doctype` is this table AND whose mapped
  action is not in `actions` are removed from `agent_tool`. Tool docs are never deleted.
- Descriptions come from the registry's human `table_name`, e.g.
  `"List records from Evidence Books with optional filters"`,
  `"Create a new Evidence Books record"` (B3).
- Return shape includes a `tools` list (actual attached tool names) so a **partial
  "view"** (only Get List, say) is visible — `actions` contains `view` if EITHER
  view tool is attached, per the brief, and `tools` shows exactly which.

## Auto-generation of params / function_definition — YES, verified live

One-off runtime probe (scaffold against a real table `HF Evidence Books`, dump fields,
clean up — script deleted afterwards). The controller generated everything:

- `Get List` → `params.properties = {filters{...}, fields: array<string>, limit: integer}`,
  `function_definition = {name, description, parameters}` — matches
  `prepare_function_params` (`agent_tool_function.py:317-348`) and `before_save`
  (`agent_tool_function.py:735-746`).
- `Get Document` → `properties.document_id`, `required: []`.
- `Create Document` → `{"type":"object","properties":{},"required":[]}` — **empty
  properties**, because `build_params_json_from_table` (`agent_tool_function.py:592-676`)
  builds the schema from the tool's `parameters` child rows, not from DocType meta, and
  the scaffolder (per the critical constraint) does not add parameter rows. This is the
  same state a hand-created tool is in before the user adds parameters. **Noted for
  phase 5/frontend:** a scaffolded Create/Update tool exposes no field-level schema
  until `parameters` rows are added; if that turns out to matter for LLM usability, the
  correct fix is to populate `parameters` child rows (a document field) — still not
  hand-written JSON — but that was explicitly out of scope here.

The integration test `test_scaffold_creates_expected_tools` asserts generation too
(`params["type"] == "object"`, `properties` present, `function_definition.name == tool_name`,
`function_definition.parameters == params`).

## Tests — `huf/huf/doctype/huf_data_table/test_agent_access.py`

`IntegrationTestCase` (NOT `FrappeTestCase`): the old class lands in the
`old-frappe-test-class-category`, whose preparation **walks the whole app importing
every `test_*.py`** (`deprecation_dumpster.py:~860`) — that imports
`huf/tests/test_audio_service.py`, which installs a `frappe` MagicMock into
`sys.modules` and breaks the entire run (`frappe.logger` AttributeError).
`IntegrationTestCase` maps to the `integration` category and skips that walk.

Fixtures (created in `setUpClass`, deleted in `tearDownClass`): HUF Table
"Test Agent Access Books" via `create_data_table`, AI Provider, AI Model, Agent.
Explicit `frappe.db.commit()  # nosemgrep` around fixture setup/teardown because
DocType DDL implicitly commits in MariaDB, so rollback can't manage fixture lifetime.
Both commits carry `# nosemgrep` justifications; `scripts/check_explicit_commits.py`
passes on the file.

Note: within a class, `IntegrationTestCase` does NOT roll back between test methods on
this site (observed: tool docs from an earlier test visible in a later one). The
idempotency test therefore snapshots tool-doc names around the second `set_` call
instead of asserting an absolute count — the assertions are still the key properties:
no new tool docs, no duplicate child rows, identical results.

### Test run (gate)

```
$ bench --site huf.localhost run-tests --app huf --module huf.huf.doctype.huf_data_table.test_agent_access
Running 8 integration tests for huf
 ✔ test_action_map_covers_four_plain_actions
 ✔ test_get_round_trips_set
 ✔ test_requires_manage_capability
 ✔ test_scaffold_creates_expected_tools
 ✔ test_set_is_idempotent
 ✔ test_uncheck_detaches_but_keeps_tool_doc
 ✔ test_unknown_action_throws
 ✔ test_view_counts_with_only_one_view_tool
Ran 8 tests in 5.198s
OK
```

**8 passed / 0 failed.** Coverage: scaffolding shape + auto-generation, idempotent
double-call, detach-keeps-tool-doc (incl. detach-to-empty), get/set round-trip,
partial-view semantics, unknown-action validation, capability guard (Guest denied).

## Other gates

- `python3 -m py_compile api.py test_agent_access.py` → OK.
- `ruff check` + `ruff format --check` on `huf/huf/doctype/huf_data_table/` → all passed.
- `pre-commit run --files <both files>` → all hooks passed EXCEPT
  `check-explicit-frappe-commits`, which failed with `Executable 'python' not found` —
  an environment issue (hook runs `python`, host only has `python3`), not a code issue.
  Running the underlying script directly:
  `python3 scripts/check_explicit_commits.py <both files>` → **passed** (exit 0).
- `git diff` touches only `huf/huf/doctype/huf_data_table/api.py` (+ new test file).
  **Nothing under `frontend/`.**
- Site cleanliness after tests: `tabDocType` has 0 `HF %` rows, 0 tool docs with
  `HF %` reference, 0 `tabAgent Tool` rows, fixture Agent/Provider/Model deleted.
  The shared `"Data Table"` Agent Tool Type row remains (created on demand; harmless,
  reusable — same policy as orphan tools).

## Surprises / notes for the next phases

1. **Tool-name sanitization** (above) — frontend must not assume the literal
   `"HF X - Get List"` form; names contain underscores. The frontend never needs to
   construct names though — both endpoints take/return plain actions.
2. **Empty `properties` on Create/Update tools** until `parameters` rows exist (above).
3. **`FrappeTestCase` is a trap** in this repo for any new DB-backed test module
   (app-wide test-module walk + frappe mock). Use `IntegrationTestCase`.
4. **No per-test rollback** under `IntegrationTestCase` here — write tests to converge
   state (the endpoints' idempotency makes this natural).
5. R-2/R-3 from triage stand: reuse-if-exists handles hand-made name collisions;
   deleting a HUF Table still leaves orphan tools (out of scope, per design).

## UNKNOWNs

- Whether the frontend phase wants `parameters` child rows scaffolded per writable
  field (would give Create/Update tools a real field schema). Flagged, not decided.
