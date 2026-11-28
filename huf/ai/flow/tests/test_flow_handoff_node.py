"""Handoff node (flow/nodes/handoff.py): handoff parks, automated send blocked while handed off, release resumes."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import conversation as conv
from huf.ai.channels.outbound import guard, recipient_binder
from huf.ai.channels import handoff as channel_handoff
from huf.ai.flow.nodes import handoff as node_handoff
from huf.ai.flow.testrun import gate
from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.permissions import iter_reachable_nodes
from huf.ai.graph.validator import _control_flow_targets


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

	def _run(self, node, live=True, verdict=None):
		with (
			patch.object(channel_handoff, "send_free_text") as self.send,
			patch.object(gate, "is_live", return_value=live),
			patch.object(guard, "evaluate", return_value=verdict or guard.GuardResult(True)) as self.guard_mock,
		):
			return node_handoff.exec_handoff(self.run_doc, node, node["config"], {})

	def _status(self):
		return frappe.db.get_value("Channel Conversation", self.conv.name, "status")

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

	def test_not_live_hands_nothing_over_and_sends_nothing(self):
		before = self._status()
		out = self._run(self._node(conversation=self.conv.name, message="hello"), live=False)
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["output"]["status"], "previewed")
		self.assertEqual(out["next_node_id"], "n2")
		self.assertEqual(self._status(), before)
		self.send.assert_not_called()

	def test_test_run_simulates_handoff_and_doc_update(self):
		for node in (
			self._node(conversation=self.conv.name),
			{"id": "u", "type": "doc.update", "config": {"doctype": "ToDo", "name": "x", "values": {"a": 1}}},
		):
			self.assertTrue(gate.simulate_node(node, lambda v: v)["simulated"], node["type"])

	def test_message_goes_through_the_guard_chain(self):
		node = self._node(conversation=self.conv.name, message="hello")
		out = self._run(node, verdict=guard.GuardResult(False, "opted_out", "consent"))
		self.assertTrue(out.is_paused)
		self.assertEqual(self._status(), "handed_off")
		self.send.assert_not_called()
		request = self.guard_mock.call_args.args[0]
		self.assertEqual(request["recipient"], "+" + self.contact)
		self.assertEqual(request["category"], "service")

	def test_allowed_message_is_sent_once(self):
		self._run(self._node(conversation=self.conv.name, message="hello"))
		self.assertEqual(self.send.call_count, 1)

	def test_a_run_cancelled_during_the_handoff_sends_nothing(self):
		def cancel(*args):
			frappe.db.set_value("Agent Flow Run", self.run_doc.name, "status", "Cancelled")
			return None, None

		with patch.object(channel_handoff.adapters, "get_adapter") as adapter:
			adapter.return_value.handoff.side_effect = cancel
			self._run(self._node(conversation=self.conv.name, message="hello"))
		self.send.assert_not_called()

	def test_member_recipient_is_bound_and_not_stored(self):
		node = self._node(gateway=self.gw.name, recipient="$member")
		with patch.object(recipient_binder, "resolve", return_value="+" + self.contact):
			out = self._run(node)
		self.assertTrue(out.is_paused)
		self.assertEqual(self._status(), "handed_off")
		self.assertNotIn(self.contact, frappe.db.get_value("Agent Flow Run", self.run_doc.name, "waiting"))

	def test_guard_matches_plus_digits(self):
		self._run(self._node(conversation=self.conv.name))
		request = {"gateway": self.gw.name, "recipient": "+" + self.contact}
		self.assertEqual(node_handoff.handed_off_guard(request), {"allow": False, "reason": "handed_off"})

	def test_run_of_an_unpublished_flow_is_not_live(self):
		defn = json.loads(self.flow.definition_json)
		run = frappe._dict(flow_id=self.flow.name, pinned_fingerprint=PinnedVersion.pin(defn).fingerprint)
		for status, expected in (("Active", True), ("Draft", False), ("Archived", False)):
			frappe.db.set_value("Flow Definition", self.flow.name, {"status": status, "live_send": 1})
			self.assertIs(gate.is_live(run), expected, status)

	def test_timeout_next_is_a_graph_edge(self):
		node = {"id": "h1", "type": "handoff", "config": {"timeout_next": "late"}}
		self.assertIn(("config.timeout_next", "late"), _control_flow_targets(node))
		graph = {"entry": "h1", "nodes": [node, {"id": "late", "type": "stop"}]}
		self.assertEqual({n["id"] for n in iter_reachable_nodes(graph)}, {"h1", "late"})
