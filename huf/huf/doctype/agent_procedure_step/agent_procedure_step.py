# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentProcedureStep(Document):
	"""Child table row: one row per graph node visited by an Agent Procedure Run.

	Deliberately holds its own status/started_at/completed_at/output_json/error rather
	than a single cursor on the parent Run (GT-02, T-21 task card point 1) -- this is
	what lets Wave 3's bounded-parallel scheduler (T-30) mark several rows Ready/Running
	at once with no schema change.
	"""

	pass
