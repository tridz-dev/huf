## Huf permissions and roles

### Overview

Huf adds a capability-based permission layer on top of Frappe:

- **Huf Role** → set of capabilities (for example `agent.create`, `flows.use`).
- **Huf User Role** → assigns one Huf Role to a Frappe User.
- **Frappe Role** → backs each Huf Role and enforces DocType-level permissions.

Backend logic for this lives in `huf/permissions.py`, `huf/huf/doctype/Huf Role`, and `huf/huf/doctype/Huf User Role`. The React frontend consumes permissions via `huf.permissions.get_me` and `PermissionsContext` in `frontend/src/contexts/PermissionsContext.tsx`.

### Roles and capabilities

Core capabilities are defined in `huf/permissions.py` as flat strings, grouped by area:

- **Agents**: `agent.use`, `agent.create`, `agent.edit`, `agent.delete`, `agent.view_all`
- **Chat**: `chat.use`, `chat.view_own`, `chat.view_all`
- **Knowledge**: `knowledge.use`, `knowledge.create`, `knowledge.manage`
- **Tools**: `tools.use`, `tools.create`, `tools.manage`
- **Flows**: `flows.use`, `flows.create`, `flows.manage`
- **System**: `system.providers.manage`, `system.models.manage`, `system.mcp.manage`, `system.settings.manage`
- **Users & Roles**: `users.invite`, `users.manage`, `roles.manage`

Default Huf roles and their capabilities:

- **Huf Admin**
  - Backed by Frappe role `System Manager`.
  - Gets **all** capabilities.
  - Intended for full system control (providers, models, flows, agents, tools, users, roles, settings).

- **Huf Manager**
  - Backed by Frappe role `Huf Manager`.
  - Intended for operational control of Agents, Chat, Knowledge, Tools, and Flows.
  - Typical capabilities:
    - Agents: `agent.use`, `agent.create`, `agent.edit`, `agent.delete`, `agent.view_all`
    - Chat: `chat.use`, `chat.view_own`, `chat.view_all`
    - Knowledge: `knowledge.use`, `knowledge.create`, `knowledge.manage`
    - Tools: `tools.use`, `tools.create`, `tools.manage`
    - Flows: `flows.use`, `flows.create`, `flows.manage`

- **Huf User**
  - Backed by Frappe role `Huf User`.
  - Intended as an end-user profile that can **use** agents, chat, knowledge, tools, and flows, but not configure them.
  - Typical capabilities:
    - Agents: `agent.use`
    - Chat: `chat.use`, `chat.view_own`
    - Knowledge: `knowledge.use`
    - Tools: `tools.use`
    - Flows: `flows.use`

- **Huf Viewer**
  - Backed by Frappe role `Huf Viewer`.
  - Intended for limited read-only access.
  - Typical capabilities:
    - Agents: `agent.use`
    - Chat: `chat.view_own`

Each `Huf Role` document stores its capabilities in the `permissions` child table (`Huf Role Permission`, field `capability`). System roles are guarded against deletion and their capability sets are validated against the official catalogue.

### Mapping to Frappe roles and doctypes

Each Huf Role maps to a backing Frappe Role via `HUF_ROLE_FRAPPE_ROLE_MAP` in `huf/permissions.py`:

- `Huf Admin` → `System Manager`
- `Huf Manager` → `Huf Manager`
- `Huf User` → `Huf User`
- `Huf Viewer` → `Huf Viewer`

`Huf User Role` keeps Frappe `Has Role` records in sync:

- On insert/update it:
  - Removes any stale Huf-managed Frappe roles from the user.
  - Grants the Frappe role that backs the current Huf Role (if `enabled`).
- On delete it:
  - Removes all Huf-managed Frappe roles from the user (never stripping `System Manager`).

---

### Default DocType permissions (Frappe Role Permission Manager)

This is the **planned default** permission matrix to add in Frappe (via Role Permission Manager or `_setup_doctype_permissions()`). Use it as the single source of truth for DocType-level access; only add `has_permission` in code where the table below is not enough.

**Conventions:**

- **System Manager** (and thus **Huf Admin**) always has full access (Create, Read, Write, Delete) on all Huf DocTypes via DocType JSON `permissions`; it is not repeated below.
- **1** = granted, **0** or blank = not granted.
- Child tables (e.g. Agent User, Agent Role, Agent Tool, Agent Knowledge, Huf Role Permission) are not listed separately; access is controlled by the **parent** DocType. Ensure the role that can write the parent has write (and thus create/delete on child rows) on the parent.

| DocType | Role | Create | Read | Write | Delete |
|---------|------|:------:|:----:|:-----:|:------:|
| **Agent** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent | Huf User | 0 | 1 | 0 | 0 |
| Agent | Huf Viewer | 0 | 1 | 0 | 0 |
| **Agent Tool Function** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent Tool Function | Huf User | 0 | 1 | 0 | 0 |
| Agent Tool Function | Huf Viewer | 0 | 0 | 0 | 0 |
| **Agent Trigger** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent Trigger | Huf User | 0 | 0 | 0 | 0 |
| Agent Trigger | Huf Viewer | 0 | 0 | 0 | 0 |
| **Agent Conversation** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent Conversation | Huf User | 1 | 1 | 1 | 0 |
| Agent Conversation | Huf Viewer | 0 | 1 | 0 | 0 |
| **Agent Message** | Huf Manager | 1 | 1 | 1 | 0 |
| Agent Message | Huf User | 1 | 1 | 1 | 0 |
| Agent Message | Huf Viewer | 0 | 1 | 0 | 0 |
| **Agent Run** | Huf Manager | 0 | 1 | 0 | 0 |
| Agent Run | Huf User | 0 | 1 | 0 | 0 |
| Agent Run | Huf Viewer | 0 | 1 | 0 | 0 |
| **Agent Run Feedback** | Huf Manager | 0 | 1 | 0 | 0 |
| Agent Run Feedback | Huf User | 1 | 1 | 0 | 0 |
| Agent Run Feedback | Huf Viewer | 0 | 1 | 0 | 0 |
| **Agent Chat** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent Chat | Huf User | 1 | 1 | 1 | 0 |
| Agent Chat | Huf Viewer | 0 | 1 | 0 | 0 |
| **Agent Console** (singleton) | Huf Manager | 0 | 1 | 1 | 0 |
| Agent Console | Huf User | 0 | 1 | 1 | 0 |
| Agent Console | Huf Viewer | 0 | 0 | 0 | 0 |
| **Agent Prompt** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent Prompt | Huf User | 0 | 1 | 0 | 0 |
| Agent Prompt | Huf Viewer | 0 | 0 | 0 | 0 |
| **Agent Prompt Category** | Huf Manager | 1 | 1 | 1 | 1 |
| Agent Prompt Category | Huf User | 0 | 1 | 0 | 0 |
| **Flow Definition** | Huf Manager | 1 | 1 | 1 | 1 |
| Flow Definition | Huf User | 0 | 1 | 0 | 0 |
| Flow Definition | Huf Viewer | 0 | 1 | 0 | 0 |
| **Flow Run** | Huf Manager | 1 | 1 | 1 | 0 |
| Flow Run | Huf User | 1 | 1 | 0 | 0 |
| Flow Run | Huf Viewer | 0 | 0 | 0 | 0 |
| **Knowledge Source** | Huf Manager | 1 | 1 | 1 | 1 |
| Knowledge Source | Huf User | 0 | 1 | 0 | 0 |
| Knowledge Source | Huf Viewer | 0 | 0 | 0 | 0 |
| **Knowledge Input** | Huf Manager | 1 | 1 | 1 | 1 |
| Knowledge Input | Huf User | 0 | 1 | 0 | 0 |
| **MCP Server** | Huf Manager | 1 | 1 | 1 | 1 |
| MCP Server | Huf User | 0 | 1 | 0 | 0 |
| MCP Server | Huf Viewer | 0 | 0 | 0 | 0 |
| **AI Provider** | Huf Manager | 0 | 1 | 0 | 0 |
| AI Provider | Huf User | 0 | 0 | 0 | 0 |
| **AI Model** | Huf Manager | 0 | 1 | 0 | 0 |
| AI Model | Huf User | 0 | 1 | 0 | 0 |
| **Agent Settings** (singleton) | Huf Manager | 0 | 1 | 1 | 0 |
| Agent Settings | Huf User | 0 | 1 | 0 | 0 |
| **Huf Role** | Huf Manager | 0 | 1 | 0 | 0 |
| Huf Role | Huf User | 0 | 0 | 0 | 0 |
| **Huf User Role** | Huf Manager | 1 | 1 | 1 | 1 |
| Huf User Role | Huf User | 0 | 0 | 0 | 0 |

**Notes:**

- **Agent**: Row-level visibility is further restricted by `get_permission_query_conditions` (owner, Agent User, Agent Role, or public when both tables empty). DocType permissions above only define who can create/read/write/delete at all.
- **Agent Conversation / Agent Run**: Row-level filters (e.g. `get_conversation_permission_conditions`, `get_run_permission_conditions`) limit which rows a user sees; the matrix above defines the role’s base CRUD.
- **AI Provider / AI Model**: Full create/write/delete is reserved for System Manager (e.g. `system.providers.manage`, `system.models.manage`). Huf Manager gets read-only by default; grant write/create/delete only to a role that has the corresponding capability if you expose provider/model management in the app.
- **Huf Role / Huf User Role**: Managing roles and user assignments is gated by capabilities `roles.manage` and `users.manage` in APIs. The matrix above gives Huf Manager full CRUD on Huf User Role so they can manage users from the Desk; restrict if you want only Huf Admin to do that.
- **Child tables** (Agent User, Agent Role, Agent Tool, Agent Knowledge, Agent MCP Server, Agent Function Params, Agent Tool HTTP Header, MCP Server Header, MCP Server Tool, Huf Role Permission, etc.): No separate permission rows needed; access follows the parent DocType.
- **Singletons** (Agent Settings, Agent Console, Elevenlabs Settings, OpenAI Settings, Groq Settings): Agent Settings and Agent Console are in the table. Provider-specific settings (Elevenlabs, OpenAI, Groq) are typically System Manager only unless you explicitly add a role.

---

### When to use `has_permission` in APIs

Rely on **Frappe’s DocType permissions** (the matrix above) as the default. Use `frappe.has_permission(...)` or capability checks in code only in these cases:

1. **Record-level rules that can’t be expressed in Permission Manager**
   - Example: “user can submit this document only if they are in the document’s approver list.” Implement in the DocType’s `has_permission(permission_type, verbose)` and keep it there; APIs that load/save the doc will then get the same behavior.

2. **Cross-doctype or workflow checks**
   - Example: “allow starting a Flow Run only if the user has read on the Flow Definition and create on Flow Run.” A single API (e.g. `flow_api.run_flow`) can do one explicit check when the action doesn’t map to a single doc save (e.g. create Flow Run + update context). Prefer doing the minimal check (e.g. `frappe.has_permission("Flow Run", "create")`) and let the rest be enforced by DocType permissions on get_doc/insert/save.

3. **Feature/capability gating without a single owning DocType**
   - Example: “only users with `users.manage` can call `get_users`.” The API doesn’t read a single DocType that could be permission-controlled; use `has_capability("users.manage")` (or equivalent) in that API.

4. **Avoid**
   - Repeating the same DocType permission check in many places (e.g. every tool_functions/sdk_tools helper). If the user is allowed to create/update/delete via the matrix, calling `frappe.get_doc(...).insert()` or `.save()` is enough; Frappe will enforce. Add one central helper (e.g. `require_doctype_perm(doctype, ptype, docname)`) only if you need a consistent error message or a single place to log.

Summary: **Default = DocType permissions in Frappe. Use `has_permission` / capabilities only when necessary for record-level, cross-doctype, or capability-only actions.**

### Backend permission flows

Three layers:

1. **DocType permissions (primary)**  
   The [default DocType permissions](#default-doctype-permissions-frappe-role-permission-manager) table above is the source of truth for who can create/read/write/delete which DocTypes. Frappe enforces this on `get_doc`, `insert`, `save`, `delete`. No extra `has_permission` in code is needed for normal CRUD.

2. **Capabilities (Huf layer)**  
   Used for product-level feature toggles and for APIs that don’t map to a single DocType:
   - `has_capability(user, capability)` in `huf/permissions.py` (Administrator and System Manager get all capabilities; others from `Huf Role Permission`).
   - `check_app_permission()` for the Huf app tile.
   - `huf.permissions.get_me` returns `user`, `full_name`, `huf_role`, `capabilities`.

3. **Record-level logic**  
   Implemented in DocType controllers and hooks, not scattered in APIs:
   - **Agent**: `get_permission_query_conditions` (owner, Agent User, Agent Role, or public).
   - **Agent Conversation / Agent Run**: `permission_query_conditions` in `huf/hooks.py` (e.g. `get_conversation_permission_conditions`, `get_run_permission_conditions`).
   - **Knowledge Source**: row-level read can be enforced via permission query or, where needed, a single check in the retriever.

Use **`has_permission` in APIs only when necessary**; see [When to use `has_permission` in APIs](#when-to-use-has_permission-in-apis) above.

### Frontend permission model

The React app consumes permissions exclusively through the `get_me` API and capabilities:

- `PermissionsContext` in `frontend/src/contexts/PermissionsContext.tsx`:
  - Calls `huf.permissions.get_me` on load.
  - Exposes:
    - `hufRole: string | null`
    - `capabilities: string[]`
    - `hasCapability(capability: string): boolean`
    - `isLoading` and `refresh()`

- Sidebar and navigation:
  - `frontend/src/components/app-sidebar.tsx` defines `allNavItems` with optional `capability`:
    - `Dashboard` has `capability: null` (always visible).
    - `Chat` requires `chat.use`.
    - `Agents` and `Executions` require `agent.use`.
    - `Flows` requires `flows.use`.
    - `Data` requires `agent.view_all`.
    - `AI Providers` requires `system.providers.manage`.
    - `MCP Servers` requires `system.mcp.manage`.
    - `Users` requires `users.manage`.
  - While capabilities are loading, only items without a capability requirement are shown to avoid UI flicker.

- Users & Roles pages:
  - `frontend/src/services/permissionsApi.ts` calls whitelisted backend methods:
    - `get_users`, `invite_user`, `update_user_role`, `set_user_enabled`.
    - `get_huf_roles`, `get_capabilities_catalogue`, `create_huf_role`, `update_huf_role`.
  - Those APIs are gate-kept by capabilities like `users.manage`, `users.invite`, and `roles.manage` before performing any database operations.

The frontend should treat capabilities as **feature flags** for pages and actions. It should not attempt to mirror DocType-level logic; instead it relies on a small, stable set of capability strings, and the backend ensures those map correctly to Frappe permissions.

### Common anti-patterns and how to avoid them

These are patterns to watch for as the permissions system evolves:

- **Dual sources of truth**
  - Avoid checking capabilities and independently hard-coding doctypes or roles in the same function.
  - Prefer: capability for feature access, DocType permissions for CRUD and row visibility.

- **Scattered `frappe.has_permission` checks**
  - Consolidate permission checks in:
    - DocType controllers (`has_permission`, `get_permission_query_conditions`), or
    - Small reusable helpers when additional checks are truly needed.
  - Avoid copy-pasting `frappe.has_permission` and custom error messages throughout the codebase.

- **Overuse of `ignore_permissions=True`**
  - Reserve `ignore_permissions=True` for:
    - Install/migration hooks.
    - Internal background tasks executed as Administrator.
  - For normal user-facing APIs, rely on:
    - Capability checks for feature access, and
    - Frappe’s own DocType permission system for data safety.

- **Misaligned role definitions**
  - When introducing a new capability or high-level feature:
    - Add it to the `CAPABILITIES` catalogue in `huf/permissions.py`.
    - Decide which Huf roles should receive it and update `DEFAULT_ROLE_CAPABILITIES`.
    - Ensure the backing Frappe roles have matching DocType permissions (via Role Permission Manager or a migration).

Keeping these rules in mind ensures the Huf permissions system remains scalable, predictable, and easy to reason about across both backend and frontend.

