"""Purge Memory Records past their retention period.

Retention is the site config ``huf_ai_memory_retention_days``; 0 or unset keeps everything. A record's
age is counted from its last change.
"""

import frappe
from frappe.utils import add_to_date, cint, now_datetime

DOCTYPE = "Memory Record"
CONF_KEY = "huf_ai_memory_retention_days"
BATCH = 1000


def purge_expired_memory(days: int | None = None, limit: int = BATCH) -> int:
	"""Delete up to ``limit`` records older than ``days``, with the Knowledge Input each was copied to.
	Returns the number of records deleted. A record that cannot be deleted is logged and kept."""
	if days is None:
		days = cint(frappe.conf.get(CONF_KEY))
	if days <= 0:
		return 0
	rows = frappe.get_all(
		DOCTYPE,
		filters={"modified": ["<", add_to_date(now_datetime(), days=-days)]},
		fields=["name", "knowledge_input"],
		order_by="modified asc",
		limit=limit,
	)
	deleted = 0
	for row in rows:
		frappe.db.savepoint("memory_purge")
		try:
			# the record links to the input, so it goes first
			frappe.delete_doc(DOCTYPE, row.name, force=True, ignore_permissions=True)
			if row.knowledge_input and frappe.db.exists("Knowledge Input", row.knowledge_input):
				frappe.delete_doc("Knowledge Input", row.knowledge_input, force=True, ignore_permissions=True)
			deleted += 1
		except Exception:
			frappe.db.rollback(save_point="memory_purge")
			frappe.log_error(title="Memory purge failed", message=f"{row.name}\n{frappe.get_traceback()}")
	return deleted
