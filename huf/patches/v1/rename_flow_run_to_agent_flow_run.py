"""Rename the Huf DocType "Flow Run" to "Agent Flow Run" on existing sites.

Frappe core ships its own "Flow Run" DocType (module Flow). Huf used the same name, so on an
installed site the "Flow Run" row belongs to whichever app synced last. Only a row whose
module is Huf is renamed; a core-owned row is left alone. ``rename_doc`` renames the table,
repoints every Link field (``options``) at the new name and rewrites Custom Fields, Property
Setters, Version, Comment and other dependents. After the rename, the Frappe core sync
recreates core's own "Flow Run" in the model-sync step that follows.

Runs before model sync so the new "Agent Flow Run" JSON updates the renamed table instead of
creating an empty second one. Idempotent: does nothing on fresh sites or on a re-run.
"""

import frappe

OLD = "Flow Run"
NEW = "Agent Flow Run"


def execute():
	if frappe.db.exists("DocType", NEW) or not frappe.db.exists("DocType", OLD):
		return
	module = frappe.db.get_value("DocType", OLD, "module")
	if module != "Huf":
		# Core's Flow Run (or a clobbered row): never rename or delete it. Model sync creates
		# "Agent Flow Run" fresh; any legacy Huf rows in tabFlow Run are left in place.
		frappe.logger().info(f"rename_flow_run_to_agent_flow_run: '{OLD}' is owned by module {module}; skipped")
		return

	# DocType.before_rename refuses renames outside developer mode; this is a trusted data patch.
	prev = frappe.conf.get("developer_mode")
	frappe.conf.developer_mode = 1
	try:
		frappe.rename_doc("DocType", OLD, NEW, force=True)
	finally:
		frappe.conf.developer_mode = prev

	# rename_doc repoints every Link to "Flow Run", including those of core Frappe DocTypes that
	# mean core's own "Flow Run". Point those back; only Huf's own DocTypes keep the new name.
	frappe.db.sql(
		"""update `tabDocField` set options = %s
		where fieldtype in ('Link', 'Table', 'Dynamic Link') and options = %s
		and parent in (select name from `tabDocType` where module != 'Huf')""",
		(OLD, NEW),
	)
	frappe.clear_cache()
