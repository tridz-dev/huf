# Seeding agents from external apps

An external app ships `<app>/huf/{tools,agents,...}/*.json`. Seeding runs on
app install (`after_app_install`) and on every `bench migrate`
(`after_migrate` -> `seeder.on_migrate`). It is idempotent.

## Admin edits are preserved
Agent and Agent Tool Function carry a hidden `seed_snapshot` (JSON of the values
last written by the seeder). Seed-owned fields are every key in the seed JSON
except `source_app`/`source_file`. On re-seed a field is overwritten only if
its current value still equals the snapshot; a field changed by an admin is kept.
Docs without a snapshot take the seed values once. Other seed types (prompts,
knowledge, triggers) still overwrite.

## Tool roles
- `required_roles` (Small Text, comma/newline separated): user needs any one.
  Role-gated tools are never allowed for Guest, even with `allowed_for_guest`.
- `is_outbound`: tool sends outside the system. With empty `required_roles` it
  fails closed to System Manager.
- Enforced in `PermissionAwareToolRegistry._can_use_tool` (load) and
  `huf.ai.tools.registry.assert_tool_role(tool, user)` (call time; raises
  `frappe.PermissionError`). Call-time enforcement runs in `huf/ai/sdk_tools.py` (`on_invoke_tool`)
  and in `huf/ai/tools/invocation.py` (`invoke_tool`).
- Also enforced on the shared path `huf.ai.tools.invocation.invoke_tool` (flows,
  procedures, approval resume), so a flow cannot run a role-restricted tool as a user
  without the role (Administrator passes). Only the approval-resume call skips it
  (internal `_skip_role_check`; the role is re-checked in `decide`).
- Decision: `requires_confirmation` parking is an agent-chat control only. It is NOT
  applied to flows/procedures (those have their own human.approval nodes).

## Agents
Seed `agent_icon` (default `SquareAsterisk`) and `allowed_roles`
(`[{"role": "..."}]`) to restrict who may run the agent.

## Decisions
- Prefer plain agent tools over flows (#873 is design-only; no flow seeding).
- Knowledge Input / Flow Definition loaders for external apps are deferred.
