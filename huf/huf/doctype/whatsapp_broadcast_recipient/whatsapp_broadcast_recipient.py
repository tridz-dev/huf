import frappe
from frappe.model.document import Document

# Monotonic delivery ladder; failed is terminal from sending/sent, never from delivered/read.
STATUS_RANK = {"queued": 0, "deferred": 0, "sending": 1, "unknown": 2, "sent": 2, "delivered": 3, "read": 4}


class WhatsAppBroadcastRecipient(Document):
	"""One recipient of a WhatsApp Broadcast. The row state machine is the duplicate-send guard.

	Name is ``<broadcast>-<recipient>`` so (broadcast, recipient) is unique by primary key and the
	name doubles as ``opaque_ref`` echoed back by Meta's status webhooks.
	"""

	def autoname(self):
		self.name = f"{self.broadcast}-{self.recipient}"[:140]

	def validate(self):
		"""Rows are created and changed only by the broadcast API/runner (``prepare`` runs with the flag set)."""
		if not getattr(frappe.flags, "in_broadcast_api", False):
			frappe.throw("Recipients can only be changed through the broadcast API.", frappe.PermissionError)
		self.opaque_ref = self.name or f"{self.broadcast}-{self.recipient}"[:140]

	def on_trash(self):
		"""Rows are the duplicate-send/audit record: deletable only through the broadcast API, and only while Draft."""
		if not getattr(frappe.flags, "in_broadcast_api", False):
			frappe.throw("Recipients can only be deleted through the broadcast API.", frappe.PermissionError)
		status = frappe.db.get_value("WhatsApp Broadcast", self.broadcast, "status")
		if status and status != "Draft":
			frappe.throw("Recipients can only be deleted while the broadcast is a Draft.", frappe.PermissionError)
