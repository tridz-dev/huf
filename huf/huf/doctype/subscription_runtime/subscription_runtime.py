# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class SubscriptionRuntime(Document):
	def validate(self):
		self._validate_transport_requirements()

	def has_permission(self, permission_type=None, verbose=False):
		from huf.permissions import has_capability

		user = frappe.session.user
		if "System Manager" in frappe.get_roles(user):
			return True

		if permission_type in ("create", "write", "save", "delete"):
			return has_capability(user, "subscription_runtime.manage")

		return True

	def _validate_transport_requirements(self):
		if self.transport_type == "SSH":
			if not self.ssh_connection:
				frappe.throw(_("SSH Connection is required when Transport Type is SSH."), frappe.ValidationError)
			return

		if self.transport_type == "Docker":
			if not self.docker_container:
				frappe.throw(_("Docker Container is required when Transport Type is Docker."), frappe.ValidationError)
			return

		if self.transport_type == "Local":
			# Local transports don't require an explicit working directory up front;
			# default to the invoking user's home directory placeholder so downstream
			# adapters always have a concrete value to resolve against.
			if not self.working_directory:
				self.working_directory = self.working_directory or "~"
			return

	def probe(self):
		"""
		Probe the runtime's CLI installation (version detection, auth status,
		capability negotiation) and persist the result onto the doc.

		NOT IMPLEMENTED HERE. This task (T-02-runtime-doctype) only creates the
		DocType shape and its tenancy/validation logic. The actual probing and
		provider-adapter wiring lands in a later task (see PLAN.md sec 25:
		Provider Connection Test Integration).
		"""
		raise NotImplementedError(
			"SubscriptionRuntime.probe() is wired up by a later task - this task only "
			"creates the DocType shape, not the probing/adapter logic."
		)

	# ------------------------------------------------------------------
	# Tenancy
	#
	# Interim storage decision: `allowed_users_json` / `allowed_roles_json` are
	# plain JSON-array-in-Long-Text fields rather than two dedicated child
	# tables (e.g. "Subscription Runtime Allowed User" / "...Allowed Role").
	# This keeps this task's scope tight (no extra DocTypes to define/migrate)
	# while the tenancy model is still expected to change shape. If child
	# tables replace this later, only `_get_allowed_users` / `_get_allowed_roles`
	# need to change - callers of `check_tenancy` never see the storage format,
	# so this is not an incompatible API change.
	# ------------------------------------------------------------------

	def check_tenancy(self, huf_user):
		"""Return True if `huf_user` is authorized to use this runtime."""
		policy = self.tenancy_policy

		if policy == "owner_only":
			return huf_user == self.owner_user

		if policy == "system_managed_shared":
			return True

		if policy == "explicit_users":
			return huf_user in self._get_allowed_users()

		if policy == "explicit_roles":
			allowed_roles = set(self._get_allowed_roles())
			if not allowed_roles:
				return False
			user_roles = set(self.get_user_roles(huf_user))
			return bool(allowed_roles & user_roles)

		# Unknown/unset policy: fail closed.
		return False

	def get_user_roles(self, huf_user):
		"""Fetch `huf_user`'s roles. Factored out so tests can override this
		single method instead of needing a live Frappe/DB connection."""
		return frappe.get_roles(huf_user)

	def _get_allowed_users(self):
		return self._parse_json_list(self.allowed_users_json)

	def _get_allowed_roles(self):
		return self._parse_json_list(self.allowed_roles_json)

	@staticmethod
	def _parse_json_list(raw):
		if not raw:
			return []
		try:
			parsed = json.loads(raw)
		except (json.JSONDecodeError, TypeError):
			return []
		if not isinstance(parsed, list):
			return []
		return parsed
