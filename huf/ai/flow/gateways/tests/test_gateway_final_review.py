"""Opus review fixes for the chat triggers, run as a real non-admin user where permissions matter.

Administrator always passes ``has_permission``, so the permission and TOCTOU checks here use a Huf Manager (may edit
flows, may not write Gateways).
"""

from __future__ import annotations

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow.engine import create_flow_run
from huf.ai.flow.gateways import samples_api

LIMITS = {
	"max_nodes": 20, "max_rows": 1000, "max_output_bytes": 100_000, "max_parallel_calls": 1, "max_foreach_iterations": 1,
	"max_external_calls": 5, "max_writes": 0, "max_wall_time_ms": 5000, "fail_closed": True,
}


def _graph(gateway: str) -> dict:
	return {
		"schema_version": "1.0.0", "profile": "flow", "fingerprint": "0" * 64, "entry": "t1",
		"nodes": [
			{"id": "t1", "type": "trigger.whatsapp", "config": {"gateway": gateway, "params": []}, "next": "done"},
			{"id": "done", "type": "output", "config": {"value": "ok"}},
		],
		"contract": {
			"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"}, "limits": LIMITS,
		},
	}


class TestNonAdminGatewayChecks(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._users: list[str] = []
		self.gateway = f"GWFINAL {frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{"doctype": "Gateway", "gateway_name": self.gateway, "provider": "WhatsApp", "is_enabled": 0, "direct_policy": "Pairing"}
		).insert(ignore_permissions=True)
		self.flow_id = f"_test-gwfinal-{frappe.generate_hash(length=8)}"
		flow_api.save_flow_definition(self.flow_id, _graph(self.gateway))
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Run", {"flow_id": self.flow_id})
		if frappe.db.exists("Flow Definition", self.flow_id):
			frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.delete("Gateway", {"name": self.gateway})
		for email in self._users:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user(self, *roles) -> str:
		email = f"gwfinal-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Gwfinal", "send_welcome_email": 0, "roles": [{"role": r} for r in roles]}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return email

	def test_last_real_message_needs_gateway_write(self):
		manager = self._user("Huf Manager")
		frappe.set_user(manager)
		self.assertTrue(frappe.has_permission("Flow Definition", "write", doc=self.flow_id))
		self.assertFalse(frappe.has_permission("Gateway", "write", doc=self.gateway))
		with self.assertRaises(frappe.PermissionError):
			samples_api.get_last_gateway_message(self.flow_id, "t1")
		# the invented sample shows no customer text, so a flow editor still gets it
		self.assertFalse(samples_api.get_gateway_sample(self.flow_id, "t1")["real"])

	def test_last_real_message_for_a_gateway_writer(self):
		frappe.set_user(self._user("Huf Manager", "System Manager"))
		out = samples_api.get_last_gateway_message(self.flow_id, "t1")
		self.assertTrue(out["real"])
		self.assertFalse(out["found"])

	def test_create_flow_run_rechecks_active_for_a_gateway_message(self):
		payload = {"gateway": self.gateway, "gateway_event": "GWE-1", "text": "hi", "provider": "WhatsApp"}
		self.assertNotEqual(frappe.db.get_value("Flow Definition", self.flow_id, "status"), "Active")
		with self.assertRaises(frappe.ValidationError):
			create_flow_run(flow_id=self.flow_id, payload=payload, trigger_type="Gateway", ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Flow Run", {"flow_id": self.flow_id}))


class TestGatewayStates(TestNonAdminGatewayChecks):
	"""A view-only person's card must know a channel is switched off (gw-wp4-01 gap)."""

	def test_states_report_off_and_only_what_was_asked(self):
		from huf.ai.flow.gateways.api import get_gateway_states

		rows = get_gateway_states(json.dumps([self.gateway, "no-such-channel"]))
		self.assertEqual([r["name"] for r in rows], [self.gateway])
		self.assertIs(rows[0]["enabled"], False)
		self.assertEqual(set(rows[0]), {"name", "label", "provider", "enabled", "connection_state"})
		self.assertEqual(get_gateway_states([]), [])

	def test_states_refuse_guests(self):
		from huf.ai.flow.gateways.api import get_gateway_states

		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				get_gateway_states([self.gateway])
		finally:
			frappe.set_user("Administrator")
