"""Handoff node (flow/nodes/handoff.py): handoff parks, automated send blocked while handed off, release resumes."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import conversation as conv
from huf.ai.channels import handoff as channel_handoff
from huf.ai.flow.nodes import handoff as node_handoff


class TestHandoffNode(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		sfx = frappe.generate_hash(length=6)
		phone = "556" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
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
				"gateway_name": f"HandNode {sfx}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": settings.name,
				"execution_user": "Administrator",
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True)
		self.contact = "15550007777"
		self.conv = conv.get_or_create_conversation(self.gw.name, self.contact)
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-handoff-{sfx}",
				"flow_name": "Handoff Node Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "h1", "type": "handoff"}]}),
			}
		)
		self.flow.flags.ignore_validate = True
		self.flow.insert(ignore_permissions=True)
		self.run_doc = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
			}
		).insert(ignore_permissions=True)

	def _node(self, **config):
		return {"id": "h1", "type": "handoff", "next": "n2", "config": config}

	def _run(self, node):
		with patch.object(channel_handoff, "send_free_text"):
			return node_handoff.exec_handoff(self.run_doc, node, node["config"], {})

	def _guard(self):
		return node_handoff.handed_off_guard({"gateway": self.gw.name, "recipient": self.contact})

	def test_handoff_parks_blocks_send_and_release_resumes(self):
		node = self._node(gateway=self.gw.name, recipient=self.contact, summary="needs a person")
		self.assertEqual(self._guard(), {"allow": True})
		out = self._run(node)
		self.assertTrue(out.is_paused)
		self.assertEqual(frappe.db.get_value("Agent Flow Run", self.run_doc.name, "status"), "Waiting Timer")
		self.assertEqual(frappe.db.get_value("Channel Conversation", self.conv.name, "status"), "handed_off")
		self.assertEqual(self._guard(), {"allow": False, "reason": "handed_off"})

		with patch("frappe.enqueue"):
			woken = node_handoff.release_handoff(self.conv.name)
		self.assertEqual(woken, [self.run_doc.name])
		self.assertEqual(self._guard(), {"allow": True})
		self.run_doc.reload()
		again = self._run(node)
		self.assertEqual(again["status"], "success")
		self.assertTrue(again["output"]["released"])
		self.assertEqual(again["output"]["conversation"], self.conv.name)
		self.assertEqual(again["next_node_id"], "n2")

	def test_timeout_routes_by_timeout_edge(self):
		from huf.ai.flow.runs import park

		node = self._node(conversation=self.conv.name, timeout_ms=60000, timeout_next="late")
		self.assertTrue(self._run(node).is_paused)
		with patch("frappe.enqueue"):
			self.assertTrue(park.wake_run(self.run_doc.name, "elapsed"))
		self.run_doc.reload()
		out = self._run(node)
		self.assertEqual(out["next_node_id"], "late")
		self.assertFalse(out["output"]["released"])

	def test_missing_conversation_fails(self):
		out = self._run(self._node(conversation="no-such-conversation"))
		self.assertEqual(out["status"], "failed")
