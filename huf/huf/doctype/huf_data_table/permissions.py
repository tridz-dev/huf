"""
huf/huf/doctype/huf_data_table/permissions.py

Permission synchronisation for dynamically generated data-table DocTypes.

Each Huf Data Table is backed by a Frappe DocType named "HF {table_name}".
The rows in that DocType's "permissions" child table are derived from the
capability assignments of Huf Roles, so changing a role's data.* capabilities
automatically updates record-level access for every data table.
"""

import frappe

from huf.permissions import HUF_ROLE_FRAPPE_ROLE_MAP


# Capabilities that control data-table record access.
_DATA_VIEW_ALL = "data.records.view_all"
_DATA_VIEW_OWN = "data.records.view_own"
_DATA_EDIT_ALL = "data.records.edit_all"
_DATA_EDIT_OWN = "data.records.edit_own"
_DATA_CREATE = "data.records.create"


def sync_data_table_permissions() -> None:
	"""
	Rebuild the DocType Permission rows for every generated data table.

	Permissions are derived from the current capability assignments of all
	Huf Roles (except Huf Admin, which maps to System Manager and always
	keeps full access). Failures for individual tables are logged and skipped
	so that one broken table does not block the rest.
	"""
	if not frappe.db.table_exists("Huf Data Table"):
		return

	data_tables = frappe.get_all(
		"Huf Data Table",
		fields=["doctype_name"],
		ignore_permissions=True,
	)
	if not data_tables:
		return

	role_caps = _get_role_capabilities()

	for table in data_tables:
		doctype_name = table.doctype_name
		if not doctype_name:
			continue

		try:
			if not frappe.db.exists("DocType", doctype_name):
				continue

			dt = frappe.get_doc("DocType", doctype_name)
			new_permissions = _build_permissions(role_caps)
			dt.set("permissions", new_permissions)
			dt.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="Failed to sync data table permissions",
				message=frappe.get_traceback(),
			)


def _get_role_capabilities() -> dict[str, set[str]]:
	"""
	Return a mapping of Huf Role name -> set of granted capability strings.

	Huf Admin is excluded because it maps to System Manager, which always
	receives full access unconditionally.
	"""
	roles = frappe.get_all(
		"Huf Role",
		filters={"name": ["!=", "Huf Admin"]},
		fields=["name"],
		ignore_permissions=True,
	)

	role_caps: dict[str, set[str]] = {}
	for role in roles:
		role_name = role.name
		if role_name not in HUF_ROLE_FRAPPE_ROLE_MAP:
			continue

		rows = frappe.get_all(
			"Huf Role Permission",
			filters={"parent": role_name},
			fields=["capability"],
			ignore_permissions=True,
		)
		role_caps[role_name] = {r.capability for r in rows if r.capability}

	return role_caps


def _build_permissions(role_caps: dict[str, set[str]]) -> list[dict]:
	"""
	Build a DocType permissions array from role capability assignments.

	Rules:
	  - System Manager always keeps full CRUD.
	  - view_all  -> read, if_owner=0
	  - view_own  -> read, if_owner=1
	  - edit_all  -> write + delete, if_owner=0 (merged with view_all row)
	  - edit_own  -> write + delete, if_owner=1 (merged with view_own row)
	  - create    -> create flag added to the role's non-owner row if present,
	                otherwise the owner row, otherwise a new if_owner=0 row.
	"""
	permissions: list[dict] = [
		{
			"role": "System Manager",
			"read": 1,
			"write": 1,
			"create": 1,
			"delete": 1,
			"print": 1,
			"email": 1,
			"share": 1,
			"import": 1,
			"if_owner": 0,
		}
	]

	# One row per (frappe_role, if_owner) pair.
	rows: dict[tuple[str, int], dict] = {}

	for huf_role, caps in role_caps.items():
		frappe_role = HUF_ROLE_FRAPPE_ROLE_MAP.get(huf_role)
		if not frappe_role:
			continue

		if _DATA_VIEW_ALL in caps or _DATA_EDIT_ALL in caps:
			key = (frappe_role, 0)
			row = rows.setdefault(
				key,
				{
					"role": frappe_role,
					"if_owner": 0,
					"read": 0,
					"write": 0,
					"create": 0,
					"delete": 0,
					"print": 0,
					"email": 0,
					"share": 0,
					"import": 0,
				},
			)
			row["read"] = 1
			if _DATA_EDIT_ALL in caps:
				row["write"] = 1
				row["delete"] = 1

		if _DATA_VIEW_OWN in caps or _DATA_EDIT_OWN in caps:
			key = (frappe_role, 1)
			row = rows.setdefault(
				key,
				{
					"role": frappe_role,
					"if_owner": 1,
					"read": 0,
					"write": 0,
					"create": 0,
					"delete": 0,
					"print": 0,
					"email": 0,
					"share": 0,
					"import": 0,
				},
			)
			row["read"] = 1
			if _DATA_EDIT_OWN in caps:
				row["write"] = 1
				row["delete"] = 1

		# create is attached to the broadest row available for the role.
		if _DATA_CREATE in caps:
			if (frappe_role, 0) in rows:
				rows[(frappe_role, 0)]["create"] = 1
				rows[(frappe_role, 0)]["import"] = 1
			elif (frappe_role, 1) in rows:
				rows[(frappe_role, 1)]["create"] = 1
				rows[(frappe_role, 1)]["import"] = 1
			else:
				key = (frappe_role, 0)
				rows[key] = {
					"role": frappe_role,
					"if_owner": 0,
					"read": 0,
					"write": 0,
					"create": 1,
					"delete": 0,
					"print": 0,
					"email": 0,
					"share": 0,
					"import": 1,
				}

	# Drop rows that ended up with no effective permissions.
	for row in rows.values():
		if any(row.get(k) for k in ("read", "write", "create", "delete")):
			permissions.append(row)

	return permissions
