# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DesktopRemoteAudit(Document):
	"""Append-only audit record of a remote action against a desktop (mode change, rebind, remote run)."""
