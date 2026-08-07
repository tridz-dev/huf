# Execution: RBAC and Execution Profiles

HUF has two distinct layers that both get called "permissions" but gate different things: a capability-based RBAC layer (Huf Roles / `has_capability`) that controls what a *user* can do in the dashboard and API, and an Execution Profile layer that controls what a *sandboxed tool call* (code execution, SSH) is allowed to do and whether it needs human approval. This doc covers both, since they're the two places "is this action allowed to run" gets decided.

## 1. Capability-Based RBAC

HUF layers a capability catalogue on top of standard Frappe DocType permissions. Instead of checking Frappe roles directly, backend code and API endpoints check for a named capability string (e.g. `"agent.create"`), and a capability maps to one or more Huf Roles. This lets the dashboard show/hide modules and gate mutations without every check knowing about the underlying Frappe role name.

The whole layer lives in `huf/permissions.py:1`.

### Mental model

```
Huf Role  →  set of capabilities   (e.g. "Huf Manager" → {"agent.create", "flows.use", ...})
Huf User Role  →  a user is assigned exactly one Huf Role
Frappe Role  →  the real DocType-level enforcement underneath, kept in sync automatically
```

### DocTypes involved

| DocType | Purpose | Source |
|---|---|---|
| `Huf Role` | A named bundle of capabilities (`Huf Admin`, `Huf Manager`, `Huf User`, `Huf Viewer`, or a custom role) | `huf/huf/doctype/huf_role/huf_role.json` |
| `Huf Role Permission` | Child table row on `Huf Role`; one row per granted capability string | `huf/huf/doctype/huf_role_permission/huf_role_permission.json` |
| `Huf User Role` | Bridges a Frappe `User` to exactly one `Huf Role`; has an `enabled` flag | `huf/huf/doctype/huf_user_role/huf_user_role.json` |

Full field tables for these are in `docs/reference/doctypes.generated.md` — not reproduced here.

### The capability catalogue

`CAPABILITIES` in `huf/permissions.py:30-81` is the single source of truth for every capability string HUF understands (35 entries as of this writing), grouped by area: Agents, Chat, Knowledge, Tools, Flows, System, Data, Users & Roles, Code Execution, SSH Execution, Docker Execution. `Huf Role.validate()` (`huf/huf/doctype/huf_role/huf_role.py:20-26`) rejects any capability string not present in this dict, so custom roles can't reference typo'd or made-up capabilities.

### Role → capability mapping

Default seed data lives in `DEFAULT_ROLE_CAPABILITIES` (`huf/permissions.py:85-136`) and is applied by `create_huf_roles()` in `huf/install.py:800-879` on both `after_install` and `after_migrate` (idempotent — it adds missing capability rows to existing roles rather than overwriting them).

| Huf Role | Capability scope |
|---|---|
| `Huf Admin` | All capabilities (`list(CAPABILITIES.keys())`) — no explicit list is seeded, it's computed |
| `Huf Manager` | Full edit access: agents (use/create/edit/delete/view_all), chat (use/view_own/view_all), knowledge (use/create/manage), tools (use/create/manage), flows (use/create/manage), data tables (manage/create/view_all/edit_all), execution profile & network policy management, execution/SSH approval, code execution, SSH run, Docker run |
| `Huf User` | Use-only: `agent.use`, `chat.use`, `chat.view_own`, `knowledge.use`, `tools.use`, `flows.use`, `data.records.create`, `data.records.view_all`, `data.records.edit_own`, `code_execution.run`, `ssh.run` |
| `Huf Viewer` | Read-only: `agent.use`, `chat.view_own`, `data.records.view_own` |

This matches the old AGENTS.md description reasonably well but is more precise — the old doc's one-line summaries ("Full edit access to agents, tools, knowledge, and flows") undersell that Manager also gets execution/SSH/Docker capabilities and data-table management.

### Frappe Role mapping

`HUF_ROLE_FRAPPE_ROLE_MAP` (`huf/permissions.py:140-145`):

| Huf Role | Backing Frappe Role |
|---|---|
| `Huf Admin` | `System Manager` (reused, not a separate Frappe role) |
| `Huf Manager` | `Huf Manager` |
| `Huf User` | `Huf User` |
| `Huf Viewer` | `Huf Viewer` |

`create_huf_roles()` creates the three non-admin Frappe `Role` records (`desk_access: 1`) if missing (`huf/install.py:809-816`); `Huf Admin` deliberately has no dedicated Frappe Role — it piggybacks on `System Manager`.

`HufUserRole` (`huf/huf/doctype/huf_user_role/huf_user_role.py`) keeps the Frappe `Has Role` table in sync automatically:
- `after_insert` / `on_update` → `_sync_frappe_role()`: grants the target Frappe role, strips any other Huf-managed Frappe role the user previously held, and never strips `System Manager` even when the Huf role is disabled (`huf/huf/doctype/huf_user_role/huf_user_role.py:44-73`).
- `on_trash` → removes every Huf-managed Frappe role except `System Manager` (`huf/huf/doctype/huf_user_role/huf_user_role.py:75-81`).

So Frappe's own DocType-level read/write matrix stays consistent with the Huf role assignment without manual upkeep.

### Enforcement

- **`get_user_huf_role(user)`** (`huf/permissions.py:178-203`): Administrator or anyone holding `System Manager` is always treated as `Huf Admin`. Otherwise it reads the enabled `Huf User Role` record, falling back to scanning `frappe.get_roles(user)` for `Huf Manager`/`Huf User`/`Huf Viewer` if no `Huf User Role` row exists.
- **`get_user_capabilities(user)`** (`huf/permissions.py:206-239`): Admin/System Manager short-circuits to every capability. Otherwise looks up the user's Huf Role's `Huf Role Permission` rows, filtered to only capabilities still present in `CAPABILITIES` (so a stale/removed capability string can't leak through). Results are cached per-user in `frappe.cache()` for 300 seconds (`_cache_key`, `_bust_cache` in `huf/permissions.py:158-166`); the cache is busted whenever a `Huf User Role` or `Huf Role` is saved/deleted (`huf/huf/doctype/huf_user_role/huf_user_role.py:37`, `huf/huf/doctype/huf_role/huf_role.py:44-64`).
- **`has_capability(user, capability)`** (`huf/permissions.py:242-254`): the actual gate. Usage pattern throughout the codebase:
  ```python
  from huf.permissions import has_capability
  if not has_capability(frappe.session.user, "agent.create"):
      frappe.throw(_("Not permitted"), frappe.PermissionError)
  ```
  `huf/ai/permissions_api.py:27-33` wraps this in a local `_require(capability)` helper used by every whitelisted endpoint in that file (`get_users`, `invite_user`, `update_user_role`, `set_user_enabled`, `get_huf_roles`, `get_capabilities_catalogue`, `create_huf_role`, `update_huf_role`).
- **`check_app_permission()`** (`huf/permissions.py:262-279`): the Frappe `add_to_apps_screen` hook controlling whether the Huf tile even appears on the Frappe Apps page — true for Administrator, System Manager, or anyone with an active `Huf User Role`.
- **`get_me()`** (`huf/permissions.py:287-312`): whitelisted `GET /api/method/huf.permissions.get_me`, called once by the React app on load. Returns `{user, full_name, huf_role, capabilities}`; the frontend's `getMe()` wrapper is `frontend/src/services/permissionsApi.ts:37-46` and drives module visibility, falling back to an all-empty response on error so the UI doesn't crash. `AgentExecutionApproval.has_permission()` (`huf/huf/doctype/agent_execution_approval/agent_execution_approval.py:8-30`) is a good example of a DocType-level permission hook built directly on `has_capability` rather than static role permissions: System Manager always passes, and create/write/delete require `execution.approve` or `ssh.approve` depending on `execution_kind`.

## 2. Execution Profiles (tool sandbox policy — not RBAC)

Execution Profile is a **different subsystem** from the RBAC layer above: it doesn't gate dashboard/API access by user, it gates what a sandboxed **tool call** (the Code Execution tool, the SSH Execution tool) is allowed to do at runtime, and whether that specific call needs a human approval step before it runs. The old AGENTS.md conflated this with RBAC in places; treat them as separate.

### Schema

`Execution Profile` (`huf/huf/doctype/execution_profile/execution_profile.json`):

| Field | Type | Notes |
|---|---|---|
| `profile_name` | Data | Autoname key |
| `is_builtin` | Check | Built-in profiles are reused/snapshotted at execution time |
| `disabled` | Check | Disabled profiles can't be used for new executions |
| `approval_mode` | Select | **`Auto Approve` \| `Ask Every Time` \| `Never Allow`** — default `Ask Every Time` |
| `filesystem_policy` | Select | `None` \| `Scratch Only` \| `Shared Directory` — default `None` |
| `network_policy` | Link → `Network Access Policy` | Optional egress allowlist |
| `allowed_modules` | JSON | Stdlib/library import allowlist for the sandboxed interpreter |
| `max_wall_time_s`, `max_cpu_seconds`, `max_memory_mb`, `max_output_bytes` | Int | Resource limits |
| `permissions` | Table → `Execution Profile Permission` | Capabilities the sandbox broker may invoke back into Frappe |

`Execution Profile Permission` (`huf/huf/doctype/execution_profile_permission/execution_profile_permission.json`) rows: `capability` (Data, dot-string like `doc.read`, `doc.create`, `email.send`, `http.request`), `reference_doctype` (optional Link scoping the capability to one DocType), `is_read_only` (Check).

**Correction to the old AGENTS.md**: the previous doc gave `approval_mode` values as `none` / `auto` / `manual`. The actual Select options, per the JSON above, are `Auto Approve`, `Ask Every Time`, `Never Allow` — confirmed both in the DocType JSON and in every call site (`huf/ai/tools/code_execution.py:598-611`, `huf/ai/tools/ssh_execution.py:338-346`, `huf/install.py:1348/1358/1368`).

### Built-in profiles

Seeded by `create_default_execution_profiles()` (`huf/install.py:1342-1385`), idempotent (skips if a profile with that name already exists):

| Profile | `approval_mode` | `filesystem_policy` | Limits |
|---|---|---|---|
| `Restricted` | `Ask Every Time` | `Scratch Only` | 30s wall/CPU, 256MB, 1MB output |
| `Trusted` | `Auto Approve` | `Scratch Only` | 60s wall/CPU, 512MB, 2MB output |
| `Blocked` | `Never Allow` | `None` | 5s wall/CPU, 128MB, 64KB output |

### Enforcement flow

Both the Code Execution tool (`huf/ai/tools/code_execution.py`) and the SSH Execution tool (`huf/ai/tools/ssh_execution.py`) branch on `profile.approval_mode` right before dispatch:

1. **`Never Allow`** — hard deny. The `Agent Tool Call` is marked `Failed` and `frappe.throw(..., frappe.PermissionError)` is raised immediately; nothing is enqueued (`huf/ai/tools/code_execution.py:600-608`, `huf/ai/tools/ssh_execution.py:339-344`).
2. **`Ask Every Time`** — the call is parked behind a new `Agent Execution Approval` record (`status: "Pending"`, TTL via `_APPROVAL_TTL_HOURS`) instead of being enqueued (`huf/ai/tools/code_execution.py:610-629`, `huf/ai/tools/ssh_execution.py:346-354`). The approval record is inserted with `ignore_permissions=True` because the dispatcher is a trusted internal path — but *deciding* on it (approve/reject) still requires the `execution.approve` / `ssh.approve` capability or a designated approver, so the requesting user can't self-approve (see `_can_decide` in `huf/huf/doctype/agent_execution_approval/agent_execution_approval.py:65-79`).
3. **`Auto Approve`** — execution proceeds without a manual gate, still subject to the profile's resource limits and `permissions` (broker capability) rows.

The capability rows on `Execution Profile Permission` are a separate, narrower authorization surface from the RBAC capabilities in `huf/permissions.py` — they scope what the *sandbox broker* can call back into Frappe with (e.g. `doc.read` on a specific DocType), not what the human user can do in the dashboard.

## See also

`docs/reference/doctypes.generated.md` for full field-level schemas of `Huf Role`, `Huf Role Permission`, `Huf User Role`, `Execution Profile`, `Execution Profile Permission`, and `Agent Execution Approval`.
