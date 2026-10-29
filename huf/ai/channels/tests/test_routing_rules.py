from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import conversation as conv, rules, rules_api

HANDLE = "15550001111"


class TestRoutingRules(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.gw = frappe.get_all("Gateway", pluck="name", limit=1)
		if not self.gw:
			self.skipTest("no Gateway available")
		self.gw = self.gw[0]
		self.doc = frappe.get_doc("Gateway", self.gw)
		self.doc.set("routing_rules", [])
		self.doc.handoff_message = "A human will help"
		self.doc.handoff_target = "helpdesk"

	def _rule(self, **kw):
		base = {"rule_type": "keyword", "target_type": "agent", "target": "AgentX", "priority": 10, "enabled": 1}
		self.doc.append("routing_rules", {**base, **kw})

	def _run(self, text="hello", conversation=None, pinned=False, resolver="Queued"):
		ctx = {"gateway": self.gw, "context": {"message_text": text, "sender_id": HANDLE}}
		with patch.object(
			frappe, "get_doc", side_effect=lambda *a, **k: self.doc if a and a[0] == "Gateway" else frappe_get_doc(*a, **k)
		), patch.object(rules, "_conversation", return_value=conversation), patch.object(
			rules, "_is_pinned", return_value=pinned
		), patch("huf.ai.gateway_service.resolve_gateway_route", return_value={"status": resolver}):
			return rules.routing_rules_hook(ctx)

	def test_keyword_whole_word(self):
		self._rule(match_value="price")
		self.assertEqual(self._run("what is the price?").payload["agent"], "AgentX")
		self.assertEqual(self._run("PRICES please").payload["agent"], "AgentX")  # prefix of text? no
		self.assertIsNone(self._run("hello there"))

	def test_first_message(self):
		self._rule(rule_type="first_message")
		self.assertIsNotNone(self._run(conversation=frappe._dict(message_count=1, status="ai")))
		self.assertIsNone(self._run(conversation=frappe._dict(message_count=3, status="ai")))

	def test_contact_attribute(self):
		self._rule(rule_type="contact_attribute", attribute="channel", match_value="WhatsApp")
		c = frappe._dict(message_count=5, status="ai", channel="whatsapp", contact=None)
		c.get = c.__getitem__
		self.assertIsNotNone(self._run(conversation=c))
		c2 = frappe._dict(message_count=5, status="ai", channel="slack", contact=None)
		c2.get = c2.__getitem__
		self.assertIsNone(self._run(conversation=c2))

	def test_priority_and_disabled(self):
		self._rule(match_value="hi", target="Low", priority=20)
		self._rule(match_value="hi", target="High", priority=1)
		self._rule(match_value="hi", target="Off", priority=0, enabled=0)
		self.assertEqual(self._run("hi").payload["agent"], "High")

	def test_fallback_only_when_unrouted(self):
		self._rule(rule_type="fallback", target="Fb")
		self.assertIsNone(self._run("zzz", resolver="Queued"))
		self.assertEqual(self._run("zzz", resolver="Unrouted").payload["agent"], "Fb")

	def test_bypass_pinned_and_handed_off(self):
		self._rule(match_value="hi")
		self.assertIsNone(self._run("hi", pinned=True))
		self.assertIsNone(self._run("hi", conversation=frappe._dict(message_count=1, status="handed_off")))

	def test_human_handoff(self):
		self._rule(match_value="agent", target_type="human", target="")
		d = self._run("agent")
		self.assertEqual(d.action, "handoff")
		self.assertEqual(d.payload, {"text": "A human will help", "target": "helpdesk"})

	def test_api_permission(self):
		user = "routing-rules-noperm@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "NoPerm", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			rules_api.get_rules(self.gw)
		with self.assertRaises(frappe.PermissionError):
			rules_api.save_rules(self.gw, [])
		frappe.set_user("Administrator")
		self.assertIsInstance(rules_api.get_rules(self.gw), list)


frappe_get_doc = frappe.get_doc
