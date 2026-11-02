# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ChannelEmbeddedSignupSettings(Document):
	def validate(self):
		if self.mode == "broker" and self.broker_url:
			from huf.ai.channels.embedded_signup import require_https_url

			require_https_url(self.broker_url, _("Broker URL"))
		if self.graph_version and not str(self.graph_version).startswith("v"):
			frappe.throw(_("Graph API Version must look like v21.0"))
