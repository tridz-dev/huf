"""Delete leftover Scheduled Job Type rows from the removed schedule_flow feature.

Flow schedules now live on an Automation (set_flow_trigger). The old rows would keep
invoking huf.ai.flow_api.execute_scheduled_flow, which no longer exists.
"""

import frappe


def execute():
	names = set(
		frappe.get_all(
			"Scheduled Job Type",
			filters={"method": ["like", "huf.ai.flow_api.execute_scheduled_flow%"]},
			pluck="name",
		)
	)
	names.update(
		frappe.get_all("Scheduled Job Type", filters={"name": ["like", "huf.flow.schedule.%"]}, pluck="name")
	)
	for name in names:
		frappe.delete_doc("Scheduled Job Type", name, force=True, ignore_permissions=True)
