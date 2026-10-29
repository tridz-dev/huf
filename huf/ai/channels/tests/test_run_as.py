"""Gateway run-as identity + channel audit stamp."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service
from huf.ai.channels import conversation as conv, run_as

RUN_USER = "runas-svc@example.com"


class TestRunAs(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		run_as.ensure_channel_audit_field("ToDo")
		frappe.clear_cache(doctype="ToDo")
		if not frappe.db.exists("User", RUN_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": RUN_USER,
					"first_name": "RunAs",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "System Manager"}],
				}
			).insert(ignore_permissions=True)
		sfx = frappe.generate_hash(length=6)
		phone = "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
		settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": phone},
					{"key": "access_token", "value": "tok"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": "sec"},
				],
			}
		).insert(ignore_permissions=True)
		self.gw = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"RunAs {sfx}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": settings.name,
				"execution_user": "Administrator",
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True)

	def _event(self):
		c = conv.get_or_create_conversation(self.gw.name, "15550002222", channel="whatsapp")
		event = frappe.get_doc(
			{
				"doctype": "Gateway Event",
				"gateway": self.gw.name,
				"idempotency_key": frappe.generate_hash(length=12),
				"status": "Queued",
				"target_type": "Agent",
				"target_agent": "Fake Agent",
				"message_text": "hi",
				"sender_id": "15550002222",
				"channel_conversation": c.name,
			}
		)
		event.insert(ignore_permissions=True, ignore_links=True)
		return event, c

	def _process(self, event, runner):
		real_get_doc = frappe.get_doc

		def get_doc(*args, **kw):
			if args and args[0] == "Agent":
				return MagicMock()
			return real_get_doc(*args, **kw)

		ok = MagicMock(authorized=True)
		with (
			patch("huf.ai.agent.integration.run_agent_sync", runner),
			patch("huf.ai.agent.access.resolve_run_identity_and_authorize", return_value=ok),
			patch.object(frappe, "get_doc", side_effect=get_doc),
		):
			gateway_service._process_gateway_event(event.name)

	def _set_run_as(self, user):
		self.gw.run_as_user = user
		self.gw.save(ignore_permissions=True)

	def test_administrator_and_guest_rejected(self):
		for user in ("Administrator", "Guest"):
			self.gw.run_as_user = user
			with self.assertRaises(frappe.ValidationError):
				self.gw.save(ignore_permissions=True)

	def test_role_profile_must_match(self):
		self.gw.run_as_user = RUN_USER
		self.gw.run_as_role_profile = "Nonexistent Profile"
		with self.assertRaises(frappe.ValidationError):
			self.gw.save(ignore_permissions=True)

	def test_inbound_run_executes_as_run_as_user_and_stamps_docs(self):
		self._set_run_as(RUN_USER)
		event, c = self._event()
		seen = {}

		def runner(**kwargs):
			seen["user"] = frappe.session.user
			todo = frappe.get_doc({"doctype": "ToDo", "description": "audit test"}).insert()
			seen["todo"] = todo.name
			return {"response": "", "delivered_reply": True}

		self._process(event, runner)
		self.assertEqual(seen["user"], RUN_USER)
		row = frappe.db.get_value("ToDo", seen["todo"], ["owner", run_as.AUDIT_FIELD], as_dict=True)
		self.assertEqual(row.owner, RUN_USER)
		self.assertEqual(row[run_as.AUDIT_FIELD], c.name)
		self.assertIsNone(run_as.current_conversation())

	def test_unset_run_as_uses_execution_user(self):
		event, _c = self._event()
		seen = {}

		def runner(**kwargs):
			seen["user"] = frappe.session.user
			return {"response": "", "delivered_reply": True}

		self._process(event, runner)
		self.assertEqual(seen["user"], "Administrator")
