# Plan 005: Stop guest agent tools from reaching arbitrary doctypes via injected ignore_permissions

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat abdd987..HEAD -- huf/ai/sdk_tools.py`
> If that file changed since this plan was written, compare the "Current state"
> excerpts against the live code before proceeding; on a mismatch, treat it as a
> STOP condition.
>
> **This is a security-sensitive change with a behavior-change risk.** Do Step 0
> (the decision gate) before touching code. If Step 0 finds an affected
> deployment config, STOP and let the operator decide.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (uses `huf/ai/tests/`; create `huf/ai/tests/__init__.py` if absent)
- **Category**: security
- **Planned at**: commit `abdd987`, 2026-06-13

## Why this matters

When an agent runs for an anonymous user, `sdk_tools.py` injects `ignore_permissions=True` into every guest-allowed tool call (`huf/ai/sdk_tools.py:322-323`). The CRUD tool handlers then (a) skip their own `frappe.has_permission` pre-check — each is written `if not ignore_permissions and not frappe.has_permission(...)` — and (b) pass `ignore_permissions=True` straight into `frappe.delete_doc` / `doc.insert` / `doc.save`. So a guest-allowed CRUD tool runs with Frappe's permission system fully bypassed.

This requires an admin opt-in (`Agent.allow_guest=1` AND `Agent Tool Function.allowed_for_guest=1`, both default `0`), so it is not exploitable on a default install. But once opted in, the blast radius is larger than intended. A tool pins its target via `reference_doctype`, and pinned `extra_args` override LLM-supplied args (`sdk_tools.py:316-317`), so a *pinned* tool is constrained to its doctype. The danger is a guest-allowed CRUD tool with **no** pinned `reference_doctype`: `extra_args` then carries no doctype, the LLM-supplied `reference_doctype` survives in `args_dict`, and the handler falls back to it (`sdk_tools.py:725`). Combined with the injected `ignore_permissions=True`, the LLM — steered by the anonymous user's prompt (prompt injection) — can read/create/update/delete rows of **any doctype it names** (`User`, `AI Provider`, etc.) with no permission enforcement.

This plan closes that worst case: a guest-allowed CRUD tool must have a pinned `reference_doctype`, or the guest call is refused. It does **not** attempt the larger redesign (running guest tools as a dedicated low-privilege user so Frappe's permission system actually enforces row-level access) — that is documented as a maintainer-gated follow-up in Maintenance notes, because it is higher-risk and needs a product decision an executor cannot make alone.

## Current state

File: `huf/ai/sdk_tools.py` (2780 lines).

Verified excerpt — the `ignore_permissions` injection inside `create_function_tool`'s closure, `huf/ai/sdk_tools.py:316-323`:

```python
                if _extra_args:
                    args_dict.update(_extra_args)

                if "ignore_permissions" in args_dict:
                    del args_dict["ignore_permissions"]

                if allowed_for_guest and frappe.session.user == "Guest":
                    args_dict["ignore_permissions"] = True
```

The closure `on_invoke_tool` is defined inside `create_function_tool` (`sdk_tools.py:261-269` signature) and closes over `_extra_args` (`:290`), `tool_type` (param, `:267`), `name` (param, `:262`), and `allowed_for_guest` (param, `:268`). So all four names are in scope at line 322.

Verified excerpt — how `reference_doctype` is (or isn't) pinned into `extra_args`, `huf/ai/sdk_tools.py:160-174`:

```python
                    extra_args = {}
                    if function_doc.types == "Attach File to Document":
                        if function_doc.reference_doctype:
                            extra_args["reference_doctype"] = function_doc.reference_doctype

                    elif (
                        function_doc.types
                        in [
                            "Get Document", "Get Multiple Documents", "Get List",
                            "Create Document", "Create Multiple Documents",
                            "Update Document", "Update Multiple Documents",
                            "Delete Document", "Delete Multiple Documents"
                        ]
                        and function_doc.reference_doctype
                    ):
                        extra_args["reference_doctype"] = function_doc.reference_doctype
```

Note the `and function_doc.reference_doctype` guard: if the tool has no `reference_doctype` set, `extra_args` gets none, and the LLM can then supply one.

Verified excerpt — a representative handler showing the bypass, `huf/ai/sdk_tools.py:723-741` (`handle_delete_document`):

```python
    try:
        if not reference_doctype:
            reference_doctype = frappe.flags.get("current_function_doctype")

        if not reference_doctype:
            return {"success": False, "error": "No reference doctype provided."}

        if not frappe.db.exists(reference_doctype, document_id):
            return {"success": False, "error": f"Document {document_id} not found in {reference_doctype}"}

        #Pre-check delete permission
        if not ignore_permissions and not frappe.has_permission(reference_doctype, "delete", doc=document_id):
            return {
                "success": False,
                "error": f"You do not have delete permission on {reference_doctype} {document_id}",
                "permission_denied": True
            }

        frappe.delete_doc(reference_doctype, document_id, ignore_permissions=ignore_permissions)
```

The same `if not ignore_permissions and not frappe.has_permission(...)` pattern appears in: `handle_create_document` (`:684`), `handle_update_document` (`:888`), `handle_get_value` (`:1035`), `handle_set_value` (`:1073`), `handle_submit_document` (`:997`), `handle_cancel_document` (`:1005`), `handle_get_report_result` (`:1098`). All are bypassed when `ignore_permissions=True`. This plan does NOT modify these handlers — it constrains which guest calls reach them with the bypass.

Repo conventions: tab-indented Python, double quotes, line length ≤ 110. Tests subclass `FrappeTestCase` from `frappe.tests.utils`; new backend tests live in `huf/ai/tests/`.

## Commands you will need

| Purpose             | Command                                                                              | Expected on success |
|---------------------|--------------------------------------------------------------------------------------|---------------------|
| Run sdk_tools test  | `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_sdk_tools_guest` | `OK`            |
| All app tests       | `bench --site <sitename> run-tests --app huf`                                         | `OK`                |
| Find guest tools    | `grep -rn "allowed_for_guest" huf/`                                                   | inspect             |
| Confirm guard       | `grep -n "_GUEST_DOCTYPE_PINNED_TYPES\|reference_doctype" huf/ai/sdk_tools.py`        | guard present       |

Replace `<sitename>` with the bench site. If unknown, that is a STOP condition.

## Scope

**In scope** (the only files you should modify):
- `huf/ai/sdk_tools.py` — add a module-level set of doctype-pinned CRUD tool types and a guard at the guest `ignore_permissions` injection point that refuses guest CRUD calls lacking a pinned `reference_doctype`.
- `huf/ai/tests/test_sdk_tools_guest.py` (create). Create `huf/ai/tests/__init__.py` if absent.
- `plans/README.md` — status row update.

**Out of scope** (do NOT touch):
- The CRUD handler bodies (`handle_create_document`, `handle_delete_document`, etc.) — their `if not ignore_permissions and ...` pattern stays. This plan constrains the caller, not the handlers.
- The blanket `ignore_permissions=True` for the PINNED case — keep it. Removing the bypass entirely (the dedicated-restricted-user redesign) is the deferred Option B; do NOT attempt it here.
- `Agent` / `Agent Tool Function` doctype JSON — no schema change.
- The non-guest path (`frappe.session.user != "Guest"`) — unchanged.

## Git workflow

- Branch: `advisor/005-guest-tool-permission-bypass`
- One commit: guard + tests. Message style: conventional commits (`fix:`). Suggested: `fix: require pinned doctype for guest CRUD tools (no arbitrary-doctype bypass)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0 (DECISION GATE — do this before any code change)

Determine whether any existing deployment relies on a guest-allowed CRUD tool WITHOUT a pinned `reference_doctype`. Such a tool is exactly the vulnerable config — but refusing it is a behavior change, so the operator must confirm it is acceptable to break.

1. Search the repo for committed tool fixtures: `grep -rn "allowed_for_guest" huf/` and inspect any `Agent Tool Function` fixtures/JSON for `allowed_for_guest: 1` with an empty `reference_doctype` and a CRUD `types`.
2. Ask the operator (or, with bench DB access, query): "Are there any active `Agent Tool Function` records with `allowed_for_guest = 1`, a CRUD type (Get/Create/Update/Delete Document/Documents, Get List), and an empty `reference_doctype`?"

- If NONE exist (expected on most installs): proceed — the guard only refuses configs that are already the vulnerability.
- If one or more EXIST: STOP and report (see STOP conditions). The operator must decide whether to pin a `reference_doctype` on those tools (the fix) or accept that they will start refusing guest calls.

**Verify**: `grep -rn "allowed_for_guest" huf/` → reviewed; no auth-less arbitrary-doctype guest tool depends on the current behavior, or the operator approved breaking it.

### Step 1: Add the pinned-CRUD-type set and the guest guard

In `huf/ai/sdk_tools.py`:

1. Add a module-level constant near the top of the file (after imports, before the first function). Target shape (tabs):

```python
# Guest-allowed tools of these types MUST pin a reference_doctype; otherwise the
# LLM could supply an arbitrary doctype and, combined with the guest
# ignore_permissions bypass, reach data outside the tool's intended scope.
_GUEST_DOCTYPE_PINNED_TYPES = {
	"Get Document",
	"Get Multiple Documents",
	"Get List",
	"Create Document",
	"Create Multiple Documents",
	"Update Document",
	"Update Multiple Documents",
	"Delete Document",
	"Delete Multiple Documents",
	"Attach File to Document",
}
```

2. Replace the guest injection block at lines 322-323 with a guard that refuses an unpinned guest CRUD call before granting the bypass. Target shape (match the file's existing indentation at that site — it is space-indented inside the closure; copy the surrounding lines' indentation exactly):

```python
                if allowed_for_guest and frappe.session.user == "Guest":
                    if tool_type in _GUEST_DOCTYPE_PINNED_TYPES and not _extra_args.get("reference_doctype"):
                        return json.dumps({
                            "error": (
                                "This tool is not available for guest access: it has no "
                                "fixed target doctype configured."
                            ),
                            "denied": True,
                        })
                    args_dict["ignore_permissions"] = True
```

This refuses the call (returning the SDK's standard `{"error": ..., "denied": True}` shape, matching the permission-denied return at `sdk_tools.py:298-299`) when a guest invokes a CRUD-type tool that has no pinned `reference_doctype`. Pinned tools and non-CRUD tools are unaffected.

**Verify**: `grep -n "_GUEST_DOCTYPE_PINNED_TYPES" huf/ai/sdk_tools.py` → definition + use.
**Verify**: `python3 -c "import ast,sys; ast.parse(open('huf/ai/sdk_tools.py').read()); print('SYNTAX_OK')"` → `SYNTAX_OK` (the file parses after the edit).

### Step 2: Write `huf/ai/tests/test_sdk_tools_guest.py`

The guard lives inside a closure, so the cleanest unit test exercises `create_function_tool`'s returned tool with `frappe.session.user` set to `"Guest"`. If invoking the FunctionTool's callable directly is awkward in this Frappe version, fall back to testing the decision predicate by extracting it (see note). Preferred shape:

```python
import json

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai import sdk_tools


class TestGuestCrudGuard(FrappeTestCase):
	def setUp(self):
		self._orig_user = frappe.session.user

	def tearDown(self):
		frappe.set_user(self._orig_user)

	def _invoke(self, tool, args):
		# FunctionTool exposes its async callable; run it to completion.
		import asyncio

		coro = tool.on_invoke_tool(None, json.dumps(args))
		return asyncio.get_event_loop().run_until_complete(coro)

	def test_guest_unpinned_crud_tool_denied(self):
		frappe.set_user("Guest")
		tool = sdk_tools.create_function_tool(
			name="del_tool",
			description="delete",
			tool_name="huf.ai.sdk_tools.handle_delete_document",
			parameters={"type": "object", "properties": {}},
			extra_args={},  # NO reference_doctype pinned
			tool_type="Delete Document",
			allowed_for_guest=True,
		)
		out = json.loads(self._invoke(tool, {"reference_doctype": "User", "document_id": "Administrator"}))
		self.assertTrue(out.get("denied"))

	def test_guest_pinned_crud_tool_allowed_through_guard(self):
		# A pinned tool passes the guard (it may still fail later for other
		# reasons, but it must NOT be denied by THIS guard).
		frappe.set_user("Guest")
		tool = sdk_tools.create_function_tool(
			name="get_tool",
			description="get",
			tool_name="huf.ai.sdk_tools.handle_get_list",
			parameters={"type": "object", "properties": {}},
			extra_args={"reference_doctype": "ToDo"},
			tool_type="Get List",
			allowed_for_guest=True,
		)
		out = json.loads(self._invoke(tool, {}))
		self.assertNotEqual(out.get("error", ""), "This tool is not available for guest access: it has no fixed target doctype configured.")
```

Note: if `tool.on_invoke_tool` is not directly callable in this SDK version, instead refactor the predicate into a tiny module-level pure function `_guest_crud_requires_pin(tool_type, extra_args)` and unit-test THAT (assert True for unpinned CRUD type, False for pinned or non-CRUD). Keep the guard in the closure calling that predicate. Either approach is acceptable; the required coverage is "unpinned guest CRUD → denied, pinned → not denied by this guard".

**Verify**: `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_sdk_tools_guest` → `OK`.

### Step 3: Run the full suite

**Verify**: `bench --site <sitename> run-tests --app huf` → `OK`.

## Test plan

- New file `huf/ai/tests/test_sdk_tools_guest.py`: at minimum (a) guest + unpinned CRUD tool → `denied: True`; (b) guest + pinned CRUD tool → not denied by this guard. Optionally (c) non-guest unpinned CRUD tool → not denied (guard only applies to Guest).
- Structural pattern: `huf/ai/tests/test_flow_eval.py` (plan 001) for the FrappeTestCase shape; `frappe.set_user` for the guest context.
- Verification: per-module `OK`, then full-suite `OK`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "_GUEST_DOCTYPE_PINNED_TYPES" huf/ai/sdk_tools.py` → set defined and referenced in the guest guard
- [ ] The guest guard refuses an unpinned CRUD guest call before setting `ignore_permissions=True` (verify by reading lines around `:322`)
- [ ] `python3 -c "import ast; ast.parse(open('huf/ai/sdk_tools.py').read()); print('OK')"` → `OK`
- [ ] `bench --site <sitename> run-tests --app huf --module huf.ai.tests.test_sdk_tools_guest` → `OK`
- [ ] `bench --site <sitename> run-tests --app huf` → `OK`
- [ ] `git status --porcelain` shows ONLY `huf/ai/sdk_tools.py`, `huf/ai/tests/test_sdk_tools_guest.py` (+ `__init__.py` if created, + README)
- [ ] `plans/README.md` status row for 005 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- Step 0 finds an active guest-allowed CRUD tool with no pinned `reference_doctype` and the operator has not approved breaking it.
- The drift check shows `sdk_tools.py` changed since `abdd987` and the injection block at `:316-323` no longer matches the "Current state" excerpt (e.g. the guest `ignore_permissions` injection is already gated or removed).
- You cannot determine the bench `<sitename>`.
- `tool.on_invoke_tool` cannot be invoked in a test AND you cannot cleanly extract a `_guest_crud_requires_pin` predicate to test — report rather than ship the guard untested.
- You find that `extra_args.get("reference_doctype")` is not actually the pin key for some CRUD type in scope (re-read lines 160-174) — the guard's key must match the pin key.

## Maintenance notes

- **Deferred Option B (the fuller fix, needs a maintainer decision).** This plan stops arbitrary-doctype access but a guest tool pinned to doctype X can still read/modify ALL rows of X with permissions bypassed (the LLM controls `filters`/`document_id`). The correct long-term fix is to NOT inject `ignore_permissions=True` for guests at all, and instead run guest tool calls as a dedicated low-privilege Frappe user with explicit roles, so Frappe's permission/user-permission system enforces row-level access. That requires: creating the restricted user + role, switching to it around guest tool execution (with try/finally restore, like `flow_tool_executor.py:34-42`), and migrating existing guest tool configs to grant that role the needed permissions. It is deferred because it is higher-risk and changes the security model — get the maintainer's sign-off and scope it as its own plan.
- If new CRUD-style handlers are added, add their `tool_type` strings to `_GUEST_DOCTYPE_PINNED_TYPES`, or they will silently escape the guard.
- Reviewer should scrutinize: (1) the guard runs BEFORE `args_dict["ignore_permissions"] = True`; (2) the type set matches the pinning list at `:164-171` exactly; (3) non-guest and non-CRUD tool behavior is unchanged; (4) the deny return shape matches the SDK's existing `{"error":..., "denied": True}` convention.
