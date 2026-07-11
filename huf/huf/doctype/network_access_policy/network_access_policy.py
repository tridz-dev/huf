# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class NetworkAccessPolicy(Document):
	def has_permission(self, permission_type=None, verbose=False):
		from huf.permissions import has_capability
		user = frappe.session.user

		# System Manager always has full access (safety net).
		if "System Manager" in frappe.get_roles(user):
			return True

		# Strict capability checks for mutating actions.
		if permission_type == "create":
			return has_capability(user, "network_access_policy.manage")

		if permission_type in ("write", "save"):
			return has_capability(user, "network_access_policy.manage")

		if permission_type == "delete":
			return has_capability(user, "network_access_policy.manage")

		# Read / access is allowed so policies can be referenced by Execution Profiles.
		return True
