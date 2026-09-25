# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

# Default challenge lifetime when `expires_at` is not explicitly set by the
# caller. 15 minutes matches the typical device-code / browser-auth window
# used by subscription CLI providers (see PLAN.md sec 61) - long enough for a
# human to notice and act on the challenge, short enough that a stale,
# forgotten challenge doesn't linger as a live credential.
DEFAULT_CHALLENGE_LIFETIME_MINUTES = 15


class SubscriptionAuthChallenge(Document):
	def validate(self):
		self._ensure_expiry()

	def _ensure_expiry(self):
		if not self.expires_at:
			self.expires_at = add_to_date(now_datetime(), minutes=DEFAULT_CHALLENGE_LIFETIME_MINUTES)

	def has_permission(self, permission_type=None, verbose=False):
		"""
		Restrict access to:
		  - the user who created this challenge,
		  - the owner of the linked Subscription Runtime,
		  - a user holding the `subscription_runtime.manage` capability.

		Per PLAN.md sec 61: "challenge access must be scoped to the runtime
		owner/authorized user plus managers" - a challenge can carry a live,
		short-lived credential (`user_code`) and must not be readable by
		arbitrary Huf users.
		"""
		from huf.permissions import has_capability

		user = frappe.session.user

		if "System Manager" in frappe.get_roles(user):
			return True

		if has_capability(user, "subscription_runtime.manage"):
			return True

		if self.created_by and self.created_by == user:
			return True

		owner_user = self._get_runtime_owner_user()
		if owner_user and owner_user == user:
			return True

		return False

	def _get_runtime_owner_user(self):
		if not self.runtime:
			return None
		try:
			return frappe.db.get_value("Subscription Runtime", self.runtime, "owner_user")
		except Exception:
			# Never let a lookup failure leak the document; fail closed.
			frappe.log_error(
				title=_("Subscription Auth Challenge: failed to resolve runtime owner"),
				message=frappe.get_traceback(),
			)
			return None


def get_permission_query_conditions(user=None):
	"""
	List/report-view counterpart to `SubscriptionAuthChallenge.has_permission()`.

	`has_permission()` only gates opening a *specific* document by name; it is
	never consulted for the SQL used to build list views, report views, or the
	`frappe.client.get_list` API. Without this hook every Huf User could list
	every challenge row - including `user_code` and `verification_url`, which
	are live, short-lived credentials - regardless of who created it or which
	runtime it belongs to. Mirrors the exact three-way check in
	`has_permission()`:
	  - the user who created the challenge,
	  - the owner of the linked Subscription Runtime,
	  - a user holding the `subscription_runtime.manage` capability.
	"""
	from huf.permissions import has_capability

	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None

	if has_capability(user, "subscription_runtime.manage"):
		return None

	user_escaped = frappe.db.escape(user)

	return f"""(
		`tabSubscription Auth Challenge`.`created_by` = {user_escaped}
		OR `tabSubscription Auth Challenge`.`runtime` IN (
			SELECT `name` FROM `tabSubscription Runtime`
			WHERE `tabSubscription Runtime`.`owner_user` = {user_escaped}
		)
	)"""
