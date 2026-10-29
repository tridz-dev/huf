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
		self.gw = "GW-TEST"
		self.doc = frappe._dict(
			routing_rules=[], handoff_message="A human will help", handoff_target="helpdesk"
		)
		for agent_name in ("AgentX", "High", "Low", "Off", "Fb"):
			frappe.get_doc(
				{
					"doctype": "Agent",
					"agent_name": agent_name,
					"agent_modality": "Text",
					"instructions": "Routing test agent.",
				}
			).insert(ignore_permissions=True)

	def _rule(self, **kw):
		base = {"rule_type": "keyword", "target_type": "agent", "target": "AgentX", "priority": 10, "enabled": 1}
		row = frappe._dict({**base, **kw, "idx": len(self.doc.routing_rules) + 1, "attribute": None, "match_value": None})
		row.update(kw)
		self.doc.routing_rules.append(row)

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
		self.assertEqual(self._run("PRICES please").payload["agent"], "AgentX")  # prefix match
		self.assertIsNone(self._run("hello there"))

	def test_first_message(self):
		self._rule(rule_type="first_message")
		self.assertIsNotNone(self._run(conversation=frappe._dict(message_count=1, status="ai")))
		self.assertIsNone(self._run(conversation=frappe._dict(message_count=3, status="ai")))

	def test_contact_attribute(self):
		self._rule(rule_type="contact_attribute", attribute="channel", match_value="WhatsApp")
		c = frappe._dict(message_count=5, status="ai", channel="whatsapp", contact=None)
		self.assertIsNotNone(self._run(conversation=c))
		c2 = frappe._dict(message_count=5, status="ai", channel="slack", contact=None)
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
		self.doc.routing_rules = [frappe._dict(rule_type="keyword", target="A")]
		with patch.object(frappe, "get_doc", return_value=self.doc):
			self.assertEqual(rules_api.get_rules(self.gw)[0]["target"], "A")


frappe_get_doc = frappe.get_doc


class TestRoutingRuleTargets(IntegrationTestCase):
	"""Save-time target validation and runtime skipping of invalid targets."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.gw = "GW-TEST"
		self.live_agent = self._agent("fixrules-live-agent", disabled=0)
		self.disabled_agent = self._agent("fixrules-disabled-agent", disabled=1)
		self.doc = frappe._dict(routing_rules=[], handoff_message="", handoff_target="none")

	def _agent(self, name, disabled):
		doc = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": name,
				"agent_modality": "Text",
				"instructions": "Routing test agent.",
				"disabled": disabled,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _rule(self, **kw):
		base = {"rule_type": "keyword", "target_type": "agent", "target": self.live_agent, "priority": 10, "enabled": 1}
		row = frappe._dict({**base, **kw, "idx": len(self.doc.routing_rules) + 1, "attribute": None, "match_value": None})
		row.update(kw)
		self.doc.routing_rules.append(row)

	def _run(self, text="hi"):
		ctx = {"gateway": self.gw, "context": {"message_text": text, "sender_id": HANDLE}}
		with patch.object(
			frappe, "get_doc", side_effect=lambda *a, **k: self.doc if a and a[0] == "Gateway" else frappe_get_doc(*a, **k)
		), patch.object(rules, "_conversation", return_value=None), patch.object(
			rules, "_is_pinned", return_value=False
		), patch("huf.ai.gateway_service.resolve_gateway_route", return_value={"status": "Queued"}):
			return rules.routing_rules_hook(ctx)

	def _row(self, **kw):
		base = {"rule_type": "keyword", "match_value": "hi", "target_type": "agent", "target": self.live_agent, "enabled": 1}
		return {**base, **kw}

	def test_save_rejects_missing_agent(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			rules_api.save_rules(self.gw, [self._row(target="fixrules-no-such-agent")])
		self.assertIn("fixrules-no-such-agent", str(ctx.exception))

	def test_save_rejects_disabled_agent(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			rules_api.save_rules(self.gw, [self._row(target=self.disabled_agent)])
		self.assertIn(self.disabled_agent, str(ctx.exception))

	def test_save_rejects_missing_match_value(self):
		with self.assertRaises(frappe.ValidationError):
			rules_api.save_rules(self.gw, [self._row(match_value="")])
		# first_message ignores match_value, so it is not required
		from huf.ai.channels.rules import rule_errors

		self.assertEqual(rule_errors([self._row(rule_type="first_message", match_value=None)]), [])
		with self.assertRaises(frappe.ValidationError):
			rules_api.save_rules(self.gw, [self._row(rule_type="contact_attribute", attribute="", match_value="x")])

	def test_save_ignores_disabled_rows_and_checks_human_without_target(self):
		# A disabled bad row is not validated; a human handoff needs no target.
		bad_but_off = self._row(target="fixrules-no-such-agent", enabled=0)
		human = self._row(rule_type="keyword", target_type="human", target="")
		rule_errors = rules.rule_errors([bad_but_off, human])
		self.assertEqual(rule_errors, [])

	def test_runtime_skips_deleted_agent_and_falls_through(self):
		gone = self._agent("fixrules-gone-agent", disabled=0)
		frappe.delete_doc("Agent", gone, force=True, ignore_permissions=True)
		self._rule(match_value="hi", target=gone, priority=1)
		self._rule(match_value="hi", target=self.live_agent, priority=2)
		self.assertEqual(self._run("hi").payload["agent"], self.live_agent)

	def test_runtime_skips_disabled_agent_and_returns_none_when_no_fallthrough(self):
		self._rule(match_value="hi", target=self.disabled_agent, priority=1)
		self.assertIsNone(self._run("hi"))
