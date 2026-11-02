# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from huf.ai.whatsapp.broadcast import policy


class WhatsAppBroadcastSettings(Document):
	def validate(self):
		raw = {k: self.get(k) for k, lim in policy.BY_KEY.items() if lim.editable}
		try:
			policy.validate_values(raw)
			policy.validate_combination(policy._parse_doc(self))
		except ValueError as exc:
			frappe.throw(str(exc))

	def on_update(self):
		"""One audit line per change, whoever saved (API, desk form or resource save)."""
		before = self.get_doc_before_save()
		changes = []
		for key, lim in policy.BY_KEY.items():
			if not lim.editable:
				continue
			old = str((before.get(key) if before else "") or "").strip()
			new = str(self.get(key) or "").strip()
			if old != new:
				changes.append(f"{key}={new or 'default'}")
		if not changes:
			return
		user = frappe.session.user
		summary = ", ".join(changes)
		frappe.logger("huf.whatsapp.broadcast").info(f"limits updated by={user} {summary}")
		try:
			self.add_comment("Info", f"limits changed by {user}: {summary}")
		except Exception:  # noqa: BLE001 - auditing never blocks a save
			frappe.logger("huf.whatsapp.broadcast").warning("limits audit comment failed")
