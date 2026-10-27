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
		self.opaque_ref = self.name or f"{self.broadcast}-{self.recipient}"[:140]
