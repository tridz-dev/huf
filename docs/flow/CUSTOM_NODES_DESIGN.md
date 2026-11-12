# Flow custom nodes from other apps: findings and design

Status: proposal (no code yet). Branch `claude/flow-custom-node-extensibility-yu12yp`, based on `pre-develop`.

## 1. Question

Prompts, tools, knowledge, agents, triggers and app manifests can already be seeded from other Frappe apps. Can another app (Frappe CRM, Raven, ...) also:

1. add **new node types** to the Flow builder (inputs, outputs, config form, palette entry), usable like any built-in node, and
2. **seed whole flows** that use those nodes?

## 2. What exists today

### 2.1 Built-in node types (22)

| Group | Types |
|---|---|
| Triggers | `trigger.webhook`, `trigger.schedule`, `trigger.doc-event`, `trigger.unset`, `trigger.gateway`, `trigger.whatsapp`, `trigger.telegram` |
| AI | `agent.run`, `tool.call` |
| Control | `condition` (if), `foreach` (loop), `router.llm`, `router.decision`, `human.approval`, `validate`, `output` |
| Data | `transform`, `state.get/set/delete`, `doc.create`, `code.run` (sandboxed code) |

Slack, Gmail, Google Drive, Google Sheets and Telegram actions are **not** node types. They are *tools* called through `tool.call` (`huf/ai/flow/integrations.py` maps tool-id prefixes such as `slack_`, `gmail_` to a connection check). Telegram and WhatsApp *triggers* are node types, but they share one gateway shape.

### 2.2 The node-type set is closed

A node type must be added in all of these places, so no app can add one without editing Huf:

| Layer | Location |
|---|---|
| JSON schema (`oneOf` of `FlowNode`, `additionalProperties:false`) | `huf/ai/graph/graph_ir.schema.json` (and an embedded copy noted in `validator.py`) |
| Profile allow-list | `FLOW_ONLY_NODE_TYPES` / `FLOW_NODE_TYPES` in `huf/ai/graph/validator.py`; `FlowDefinition.ALLOWED_NODE_TYPES` imports it |
| Runtime | `_NODE_EXECUTORS`, `NODE_ROUTING`, `EXTERNALLY_PAUSABLE_TYPES` in `huf/ai/flow/engine.py` |
| Editor metadata | `_NODE_DISPLAY` in `huf/ai/flow/support/node_schemas.py` (served by `get_node_schemas`) |
| Frontend | hard-coded in `types/flow.types.ts`, `services/flow/serializerTables.ts`, `components/flow/NodeConfigForms.tsx`, `data/actions.ts`, `lib/flow/flowNodeCard.ts`, run-story helpers and more. `getNodeSchemas()` exists but forms are not generated from it. |

`grep` finds no `hooks`-based discovery for flow nodes.

### 2.3 The extension points that do exist

* **`huf_tools` hook** (`huf/ai/tools/registry.py`): an app declares tool definitions; they sync into `Agent Tool Function` and appear in the Flow "Call Tool" picker (`list_flow_tools`). A flow calls one with `tool.call {tool_id, input}`. This is the **only** way another app extends flows today. It works, but a tool is one flat call: one input object, one result, no named outcomes, no own config form, no palette category, no declared output shape, no pause.
* **Gateway trigger registry** (`huf/ai/flow/gateways/registry.py`): a precedent for "a spec in Python drives the form, no schema or frontend change". Only for chat triggers and only inside Huf.
* **App seeding** (`huf/ai/app_seeding`): scans each installed app's `huf/` folder; `LOAD_ORDER` is prompts, tools, knowledge, agents, triggers, apps. There is **no `flows/` folder**. `Flow Definition` already has `is_system` and `solution` fields, and Huf ships demo flows (`docs/flow/DEMO_FLOWS.md`), but nothing lets another app ship a flow.

### 2.4 Conclusion

Neither custom nodes nor seeded flows exist. Apps can approximate the first with tools. Both need new work.

## 3. Goals and non-goals

Goals
* A provider app adds node types by hook and Python only, no Huf edits, no frontend build.
* Nodes take input, return output, and may expose **named outcomes** for branching (`found` / `not_found`).
* Nodes behave like built-ins: palette, config form, validation, test run, run log, permissions, plain-language errors.
* A provider app can seed flows that use its nodes, and fail cleanly if the app is absent.

Non-goals (v1)
* Custom triggers from hooks (use `trigger.doc-event` / `trigger.webhook`; the gateway registry stays Huf-owned).
* Nodes that pause and resume (human-style wait). Possible later.
* Custom React components per node.
* Arbitrary Python from flow JSON (see section 7).

## 4. Options considered

| Option | Verdict |
|---|---|
| A. Keep only `huf_tools` | Already works; too weak for outcomes, forms, categories. Stays as the simple path. |
| B. Extend the JSON schema `oneOf` dynamically per installed app | Rejected: schema is static and embedded in the validator and Procedure profile; every app would change the validation contract. |
| **C. One generic core node `ext.node` that names a registered extension node** | **Recommended.** The schema, validator allow-list and engine learn one new type once. Apps register definitions by hook; the registry supplies per-node validation, form, routing and handler. |

## 5. Design (Option C)

### 5.1 Stored shape

```json
{
  "id": "find_lead",
  "type": "ext.node",
  "config": {
    "node": "crm.find_lead",
    "input": { "email": { "$from": "trigger.email" } }
  },
  "next": "..."
}
```

* `config.node` is a **literal** registry key, `<app>.<name>`, the same rule as the literal `tool_id` (invariant I3, no dynamic dispatch).
* `config.input` values use the existing reference form (`$from` / `$template`), so the existing expression and reference checks apply unchanged.
* Named outcomes route through the existing edge label (`meta.outcome`) mechanism already used by `labelled_resolver` in `engine._build_router`.

### 5.2 Registration hook

In the provider app's `hooks.py`, same style as `huf_tools`:

```python
huf_flow_nodes = ["crm.huf_nodes.NODES"]   # dotted path to a list/dict of specs
```

```python
# crm/huf_nodes.py
NODES = [{
    "key": "crm.find_lead",                 # <app>.<name>, unique, lowercase
    "label": "Find CRM Lead",
    "description": "Looks up a lead by email.",
    "category": "CRM",                      # palette group
    "icon": "UserSearch",                   # lucide name, validated against an allow-list
    "handler": "crm.huf_nodes.find_lead",
    "input_schema": {                       # JSON Schema subset (see 5.4)
        "type": "object", "required": ["email"],
        "properties": {"email": {"type": "string", "title": "Email"}}
    },
    "output_schema": {                      # drives the reference picker, never trusted at runtime
        "type": "object",
        "properties": {"lead": {"type": "object"}, "name": {"type": "string"}}
    },
    "outcomes": [                           # omit for a single "next" exit
        {"key": "found", "label": "Found"},
        {"key": "not_found", "label": "Not found"}
    ],
    "effect": "reads",                      # reads | changes | sends (test-run behaviour)
    "permissions": [{"doctype": "CRM Lead", "ptype": "read"}],
    "requires_integration": None,           # optional, same check as integrations.py
}]
```

Handler contract:

```python
from huf.ai.flow.ext_nodes import NodeResult

def find_lead(ctx):                         # ctx: NodeContext
    row = frappe.db.get_value("CRM Lead", {"email": ctx.input["email"]}, ["name", "lead_name"], as_dict=True)
    if not row:
        return NodeResult.outcome("not_found", output={"name": None})
    return NodeResult.outcome("found", output={"name": row.name, "lead": row})
    # or NodeResult.failed("plain sentence for the person running the flow")
```

`NodeContext` exposes resolved `input`, `config`, `user`, `flow_id`, `flow_run_id`, `node_id`, `is_test_run`, `get_credential(service, key)` (the existing credential resolver). It does **not** expose the raw context or the `Flow Run` document.

### 5.3 New backend pieces (`huf/ai/flow/ext_nodes/`)

* `registry.py`: `get_ext_nodes()` reads `frappe.get_hooks("huf_flow_nodes")` for **installed apps only**, normalizes like `_normalize_hook_tools`, validates each spec (key format `^[a-z0-9_]+\.[a-z0-9_]+$`, key prefix equals the declaring app name, no duplicate, handler path importable, icon (unknown icon falls back to a default), outcome keys unique), and caches per site in the Frappe cache, cleared on migrate and app install (tool discovery has no such cache; it only stores scan timestamps in `Agent Settings.last_app_scans`). A bad spec is skipped and logged; it never breaks Huf.
* `context.py`: `NodeContext`, `NodeResult`.
* Engine: register `"ext.node": _exec_ext_node` in `_NODE_EXECUTORS`. `_build_program` (not `_build_router`, which builds an empty program) sets routing per instance: SELF_ROUTED when the registered node declares `outcomes`, DEFAULT otherwise (today `NODE_ROUTING` is keyed by type only, so this is the one engine change that is not purely additive).
* `_exec_ext_node` order: resolve `config.node` in registry (fail with a plain "this step needs the CRM app" sentence if absent) -> permission gate (5.5) -> test-run simulate for `changes`/`sends` effects -> call handler -> normalize with the existing `normalize_tool_result` style checks -> `enforce_output_budget` -> write an `Agent Run` log row (`run_kind="ext"`) like `tool.call` does -> map outcome to the router.
* Handler exceptions become a failed node with `plain_error`; `on_error` / `on_failure` edges work unchanged.

### 5.4 Config form without frontend releases

`get_node_schemas()` already returns `{label, icon, category, config_schema[], json_schema}` per type. Extend it with a second block `ext_nodes` generated from the registry; `input_schema` is converted with the existing `_field_type` (string, number, boolean, select from `enum`, `json`, and `value`/`expression` for reference-capable fields). Supported schema subset is deliberately small: `type`, `title`, `description`, `enum`, `default`, `required`. Length/range limits and a document-picker extension (`x-huf-link`) are later additions.

Frontend work: one generic **ExtNodeForm** that renders `config_schema` with existing field components, a palette section per `category`, a card/summary using the node label, outcome handles from `outcomes`, serializer passthrough for `ext.node` (`config.node`, `config.input`), run-story wording from the label. The hard-coded per-type code stays for built-ins.

### 5.5 Validation, permissions, safety

* **Schema**: add `ExtNode` (`type` const `ext.node`, `config.node` string with the key pattern, `config.input` object of `Value`, `additionalProperties:false`) and add `ext.node` to `FLOW_ONLY_NODE_TYPES` (the embedded copy must be kept in sync, as `validator.py` already warns).
* **Registry-aware checks** in `validator.py`, following the injected-classifier pattern in `graph/permissions.py` so the pure validator stays frappe-free: node key exists; `input` satisfies `input_schema` (publish mode; draft mode only warns, matching "saving never blocks on an unfinished flow"); each outgoing edge label is a declared outcome; every declared outcome is wired or defaults to the node's `next`.
* **Missing provider app**: draft saves keep the node; publish and run fail with a plain message naming the app; the flow list shows the same warning as other broken-step cases.
* **Permissions**: the handler runs as the flow's run-as user (same as tool calls). The spec's `permissions` are **self-reported by the app and are not a security boundary**: a handler is arbitrary Python and can bypass checks (`ignore_permissions`, `get_all`). Unlike `tool.call`, Huf cannot re-derive what the handler does (`classify_tool`, `graph/permissions.py`). So the declared list is used for (a) a pre-handler `frappe.has_permission` check as a convenience and early failure, and (b) showing the author what the step touches. It is not counted as a verified permission envelope. The real control is that installing a provider app is itself a trust decision. There is no `elevated` flag.
* **No dynamic code loading from flows**: the only dotted paths executed are those declared in the hook of an installed app, the same trust model as `get_hook_declared_function_paths` for `App Provided` tools (finding F-07). Flow JSON carries only the registry key.
* Secrets: nodes read credentials through `ctx.get_credential`. `flow/support/redact.py` only hides webhook secrets in a graph definition, so it does **not** cover node input or output. Phase 1 adds a redaction pass for ext-node input and output before they reach the `Agent Run` log (mask values of keys such as `token`, `secret`, `password`, `authorization`).
* Limits: per-node wall time and output size reuse the contract limits. In test runs, `effect: changes|sends` nodes are simulated and not executed unless the spec sets `supports_test_run: true` (the handler then checks `ctx.is_test_run`). `effect: reads` nodes do run their real queries.
* **Registry snapshot**: `PinnedVersion` pins the graph, not the registry. At publish and again at run start the node's spec (outcome keys and input schema) is snapshotted into the run, so a provider upgrade cannot change routing for an in-flight run.

### 5.6 Seeding flows from apps

Add a `flows/` folder to the seed framework:

* Seeding uses `ignore_permissions=True` and `_validate_link_refs` does not look inside `definition_json`, so `upsert_flow` itself checks that every `ext.node` key is registered and every `agent.run` agent exists, and reports misses through the existing `missing_refs` result.
* `LOAD_ORDER` gets `("flows", upsert_flow)` **after** agents and triggers, so referenced agents exist. `scanner.get_seed_files` already handles arbitrary folder names.
* Seed file: a `Flow Definition` payload (`flow_id`, `flow_name`, `description`, `category`, `definition_json`) (required nodes are found by scanning the definition each time; no separate field).
* `upsert_flow` validates the definition in **draft** mode, checks that every required node key is registered (missing -> the existing `missing_refs` skip result, shown in the seed summary), writes provenance (`source_app`, `source_file`) and `is_system=1`, and **always lands as Draft**. Publishing remains an explicit user action, because publishing starts triggers.
* Re-seeding: `_upsert_doc` today overwrites by key with `doc.update(data)`, which would destroy user edits. Policy for flows: update only while the flow is still Draft and unmodified since it was seeded; otherwise skip and report "edited locally, not updated". `is_system=1` must not block user edits or deletes of seeded flows; check what `is_system` enforces on `Flow Definition` before reusing it, and add a separate `source_app`-based marker if it does.
* The seeder skips the `huf` app itself, so Huf's own demo flows would continue to ship separately.

### 5.7 Example: end to end

CRM ships `crm/huf/flows/new_lead_followup.json`:

```
trigger.doc-event (CRM Lead, after_insert)
  -> ext.node crm.find_lead
       found     -> ext.node raven.post_message (channel "sales")
       not_found -> agent.run "Lead qualifier" -> ext.node crm.create_lead
```

CRM contributes `crm.find_lead`, `crm.create_lead`; Raven contributes `raven.post_message`. Both only add a hooks line and a Python file; the flow uses built-in trigger and agent nodes alongside them.

## 6. Tests

* Registry: valid spec, bad key, wrong app prefix, duplicate, un-importable handler, bad key etc. (skipped, logged, others unaffected).
* Validator: unknown key, bad input vs `input_schema`, unknown outcome label, profile allow-list, draft vs publish severity.
* Engine: success, outcome routing, handler exception -> `on_error`, missing app, permission denied, output budget, test-run simulation, `Agent Run` row written.
* `get_node_schemas`: ext block shape, snapshot test (pattern from `gateways/tests/test_registry_snapshot.py`).
* Seeding: flow lands as Draft; missing node -> skipped with `missing_refs`; unchanged re-seed updates; locally edited flow untouched.
* Frontend (Vitest): form render from schema, serializer round trip, palette grouping.
* Reference app fixture: a tiny test app (or fixture hook injection) registering two nodes.

## 7. Delivery phases

1. **Core**: registry, schema + validator change, `_exec_ext_node`, per-instance routing, unit tests. Backend only; usable via hand-written JSON.
2. **Editor**: `get_node_schemas` ext block, generic ExtNodeForm, palette, serializer, run story.
3. **Seeding**: `flows/` folder, `upsert_flow`, provenance and re-seed policy, seed summary.
4. **Docs and reference**: this doc turned into a how-to for app authors; sample nodes for one real app.
5. **Later**: custom triggers, pausing nodes, per-node React override, async handlers.

Rough size: phase 1 and 3 are small backend changes; phase 2 (frontend) is the largest.

## 8. Risks

* Closed enums in several layers (schema, embedded validator copy, Procedure profile, frontend tables). Mitigation: only `ext.node` is added; add a test asserting the schema file and embedded copy stay equal.
* Procedure profile: Procedures share the graph IR. v1 allows `ext.node` in Flows only; Procedure support needs the same permission-envelope review.
* Per-instance routing touches the engine's central table; cover with the existing `test_flow_engine` suite.
* Supply chain: a malicious installed app already runs arbitrary Python; the hook adds no new trust level beyond `huf_tools`, but it must not widen what a flow author can invoke (hence the literal key).

## 9. Open questions

1. (Decided for v1) Re-seed only unmodified Drafts; revisit if app authors need to push fixes to edited flows.
2. Should outcome-less nodes also be able to emit `meta.outcome` ad hoc, or must outcomes always be declared? (Recommend declared.)
3. (Decided) No `elevated` flag; see 5.5.
4. (Decided for v1) Uninstalling a provider leaves published flows in place; the flow list flags them and runs fail with a plain message naming the app. No auto-draft.
5. Can `Procedure` reuse `ext.node` later, and with which effect classes?
