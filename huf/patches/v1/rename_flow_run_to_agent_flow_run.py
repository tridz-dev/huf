"""Rename the Huf DocType "Flow Run" to "Agent Flow Run" on existing sites.

Frappe core ships its own "Flow Run" DocType (module Flow). Huf used the same name, so on an
installed site the "Flow Run" row belongs to whichever app synced last. Only a row whose
module is Huf is renamed; a core-owned row is left alone.

The rename is done with plain SQL on purpose. ``frappe.rename_doc`` needs developer_mode, which
makes Frappe re-export core doctype files from DB metadata and rewrite Link options on core
doctypes that legitimately point at core's "Flow Run". This patch never enables developer_mode,
never writes files and never touches DocTypes outside module Huf.

Runs before model sync so the "Agent Flow Run" JSON updates the renamed table instead of creating
an empty second one. Idempotent. "Agent Flow Run" uses hash naming, so there is no Series to move.
"""

import frappe

OLD = "Flow Run"
NEW = "Agent Flow Run"

# (table, column) pairs that hold the DocType name and must follow the rename.
NAME_COLUMNS = (
	("DocType", "name"),
	("DocField", "parent"),
	("DocPerm", "parent"),
	("Custom DocPerm", "parent"),
	("DocType Link", "parent"),
	("DocType Action", "parent"),
	("DocType State", "parent"),
	("Custom Field", "dt"),
	("Property Setter", "doc_type"),
	("Version", "ref_doctype"),
	("Comment", "reference_doctype"),
	("Deleted Document", "deleted_doctype"),
	("Document Naming Rule", "document_type"),
)


def execute():
	if frappe.db.exists("DocType", NEW) or not frappe.db.exists("DocType", OLD):
		return
	module = frappe.db.get_value("DocType", OLD, "module")
	if module != "Huf":
		frappe.logger().info(f"rename_flow_run_to_agent_flow_run: '{OLD}' is owned by module {module}; skipped")
		return

	frappe.db.sql_ddl(f"RENAME TABLE `tab{OLD}` TO `tab{NEW}`")
	for table, col in NAME_COLUMNS:
		if frappe.db.table_exists(table) and frappe.db.has_column(table, col):
			frappe.db.sql(f"update `tab{table}` set `{col}` = %s where `{col}` = %s", (NEW, OLD))
	if frappe.db.table_exists("Property Setter"):
		frappe.db.sql(
			"update `tabProperty Setter` set name = concat(%s, substr(name, %s)) where name like %s",
			(NEW, len(OLD) + 1, OLD + "-%"),
		)

	# Repoint only Huf-owned fields; core doctypes keep pointing at core's "Flow Run".
	frappe.db.sql(
		"""update `tabDocField` set options = %s
		where fieldtype in ('Link', 'Table') and options = %s
		and parent in (select name from `tabDocType` where module = 'Huf')""",
		(NEW, OLD),
	)
	frappe.db.sql(
		"""update `tabCustom Field` set options = %s
		where fieldtype in ('Link', 'Table') and options = %s
		and dt in (select name from `tabDocType` where module = 'Huf')""",
		(NEW, OLD),
	)
	frappe.clear_cache()
