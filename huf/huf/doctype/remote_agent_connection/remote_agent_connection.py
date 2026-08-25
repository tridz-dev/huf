# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from __future__ import annotations

import asyncio
import json
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


class RemoteAgentConnection(Document):
	def validate(self):
		self._validate_protocol_specifics()
		self._validate_role_access()
		self._validate_limits()

	def _validate_protocol_specifics(self) -> None:
		if self.protocol_type != "acp_stdio":
			return

		if not self.acp_registry_entry:
			frappe.throw(_("ACP Registry Entry is required for ACP stdio connections"))

		if self.base_url:
			frappe.throw(_("Base URL must be blank for ACP stdio connections"))

		registry = self._load_registry_entry()
		if not registry.enabled:
			frappe.throw(_("Selected ACP Command Registry entry is disabled"))

		if registry.auth_required and not self.auth_secret:
			frappe.throw(_("Auth Secret is required for the selected ACP registry entry"))

	def _validate_role_access(self) -> None:
		if self.protocol_type != "acp_stdio" or not self.acp_registry_entry:
			return

		registry = self._load_registry_entry()
		allowed_roles = {row.role for row in (registry.allowed_roles or []) if row.role}
		user_roles = set(frappe.get_roles(frappe.session.user))
		if "System Manager" in user_roles or user_roles & allowed_roles:
			return
		frappe.throw(_("You do not have a role allowed to use this ACP Registry Entry"))

	def _validate_limits(self) -> None:
		if self.max_concurrent_sessions is not None:
			self.max_concurrent_sessions = max(1, min(50, int(self.max_concurrent_sessions)))
		if self.session_ttl_seconds is not None:
			self.session_ttl_seconds = max(60, min(86400, int(self.session_ttl_seconds)))

	def _load_registry_entry(self):
		if not self.acp_registry_entry:
			return None
		return frappe.get_doc("ACP Command Registry", self.acp_registry_entry)

	def as_dict(self, *args, no_nulls=False, no_default_fields=False, convert_dates_to_str=False, no_private=False, **kwargs):
		out = super().as_dict(
			*args,
			no_nulls=no_nulls,
			no_default_fields=no_default_fields,
			convert_dates_to_str=convert_dates_to_str,
			**kwargs,
		)
		# Never leak the password field over the API.
		out.pop("auth_secret", None)
		return out

	def get_launch_spec(self) -> dict[str, Any]:
		"""Return the scrubbed launch context for this connection."""
		if self.protocol_type != "acp_stdio":
			frappe.throw(_("Launch spec is only available for ACP stdio connections"))
		if not self.enabled:
			frappe.throw(_("Remote Agent Connection is disabled"))

		registry = self._load_registry_entry()
		if not registry or not registry.enabled:
			frappe.throw(_("ACP Command Registry entry is disabled or missing"))

		return registry.get_launch_spec(auth_secret=self.auth_secret)

	@frappe.whitelist()
	def test_connection(self) -> dict[str, Any]:
		"""Run the ACP initialize handshake and return health information."""
		if self.protocol_type != "acp_stdio" or not self.enabled:
			return {"status": "failed", "error": "Connection is not enabled or not ACP stdio"}

		async def _run() -> dict[str, Any]:
			from huf.ai.acp.client import AcpClient

			spec = self.get_launch_spec()
			async with AcpClient(
				command=spec["cmd"],
				cwd=spec["cwd"],
				env=spec["env"],
				timeout=spec.get("max_wall_time_seconds", 300),
			) as client:
				return await client.start()

		try:
			capabilities = asyncio.run(_run())
			self.health_status = "healthy"
			self.last_error = ""
			result = {"status": "healthy", "capabilities": capabilities, "error": ""}
		except Exception as exc:  # noqa: BLE001
			self.health_status = "failed"
			self.last_error = str(exc)
			result = {"status": "failed", "capabilities": {}, "error": str(exc)}
		finally:
			self.last_health_check = frappe.utils.now()
			self.save(ignore_permissions=True)

		return result
