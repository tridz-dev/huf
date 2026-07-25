# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HUFApp(Document):
	"""Registry record for a discovered HUF App manifest.

	Records are created and maintained by the app-seeding sync
	(huf.ai.app_seeding.apps_loader); they are discovered, not user-authored.
	"""

	pass
