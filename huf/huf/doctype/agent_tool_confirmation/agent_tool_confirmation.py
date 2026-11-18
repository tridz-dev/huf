# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentToolConfirmation(Document):
	"""Audit record + parked call for a tool flagged ``requires_confirmation``.

	All logic lives in ``huf.ai.tool_confirmation``; rows are never edited by hand."""
