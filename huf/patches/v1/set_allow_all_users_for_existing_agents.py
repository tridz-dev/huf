import frappe


def execute():
	"""Preserve open-by-default access for pre-existing Agents.

	ST-R2.1 adds `allow_all_users` (default 0) to the Agent doctype and
	ST-R2.3/ST-R2.4 change the empty-allowed-lists branch of
	check_agent_access / get_permission_query_conditions from "always open"
	to "open only if allow_all_users=1". Without a one-time backfill, every
	Agent deployed before this change -- which relied on the empty-lists
	branch being open by default -- would suddenly become closed to everyone
	but its owner, System Manager, and capability holders.

	This patch sets allow_all_users=1 on every existing Agent whose
	`allowed_users` (Agent User) and `allowed_roles` (Agent Role) child
	tables are both empty, preserving current behavior. Agents that already
	have explicit allowed_users/allowed_roles are left untouched (their
	access was never governed by the empty-lists branch). New Agents created
	after this patch runs default to allow_all_users=0 (closed), per
	ST-R2.1's field default.

	Idempotent: setting an already-1 value to 1 again is a no-op-safe write,
	so re-running this patch is safe.
	"""
	if not frappe.db.has_column("Agent", "allow_all_users"):
		return

	users_by_parent = frappe.get_all("Agent User", pluck="parent", distinct=True)
	roles_by_parent = frappe.get_all("Agent Role", pluck="parent", distinct=True)
	agents_with_lists = set(users_by_parent) | set(roles_by_parent)

	agent_names = frappe.get_all("Agent", pluck="name")

	for agent_name in agent_names:
		if agent_name in agents_with_lists:
			continue
		try:
			frappe.db.set_value("Agent", agent_name, "allow_all_users", 1, update_modified=False)
		except Exception as e:
			frappe.log_error(
				title="Set Allow All Users For Existing Agents",
				message=f"Could not backfill allow_all_users for Agent '{agent_name}': {e}",
			)

	frappe.db.commit()
