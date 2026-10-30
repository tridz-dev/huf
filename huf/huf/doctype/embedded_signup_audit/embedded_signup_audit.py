# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EmbeddedSignupAudit(Document):
	"""One row per broker token exchange. Never stores a code or a token."""
