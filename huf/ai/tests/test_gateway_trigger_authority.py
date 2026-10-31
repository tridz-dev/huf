"""Chat triggers: Gateway write permission at save and publish, provider match, owner check, sensitive, double reply."""

from __future__ import annotations

import unittest
from unittest import mock

from huf.ai.flow import publish_guard
from huf.ai.flow.gateways import authority


class _Throw(Exception):
	pass


def _throw(msg, *a, **k):
	raise _Throw(msg)


def _flow(node_type="trigger.gateway", gateway="Support", extra=()):
	return {"nodes": [{"id": "t1", "type": node_type, "config": {"gateway": gateway, "params": []}}, *extra]}


class _Base(unittest.TestCase):
	providers = {"Support": "WhatsApp", "Bot": "Telegram"}
	can_write = {"alice": {"Support", "Bot"}, "bob": set()}

	def setUp(self):
		def perm(doctype, ptype=None, doc=None, user=None, **kw):
			return doc in self.can_write.get(user or "alice", set())

		for p in (
			mock.patch.object(authority.frappe, "throw", side_effect=_throw),
			mock.patch.object(authority, "_", lambda s: s),
			mock.patch.object(authority.frappe.db, "exists", side_effect=lambda dt, name: name in self.providers),
			mock.patch.object(authority.frappe.db, "get_value", side_effect=lambda dt, name, field=None: self.providers.get(name)),
			mock.patch.object(authority.frappe, "has_permission", side_effect=perm),
			mock.patch.object(authority.frappe, "session", mock.Mock(user="alice")),
		):
			p.start()
			self.addCleanup(p.stop)


class TestAuthority(_Base):
	def test_writer_can_save_and_publish(self):
		authority.check_gateway_authority(_flow(), "alice")

	def test_user_without_gateway_write_is_refused(self):
		with self.assertRaises(_Throw):
			authority.check_gateway_authority(_flow(), "bob")

	def test_unknown_gateway_refused_blank_allowed_in_draft(self):
		with self.assertRaises(_Throw):
			authority.check_gateway_authority(_flow(gateway="Nope"), "alice")
		authority.check_gateway_authority(_flow(gateway=""), "alice")

	def test_dedicated_node_needs_matching_provider(self):
		authority.check_gateway_authority(_flow("trigger.whatsapp", "Support"), "alice")
		with self.assertRaises(_Throw):
			authority.check_gateway_authority(_flow("trigger.telegram", "Support"), "alice")
		authority.check_gateway_authority(_flow("trigger.gateway", "Bot"), "alice")  # generic node: any channel

	def test_owner_must_also_be_able_to_use_the_gateway(self):
		with self.assertRaises(_Throw):
			authority.check_gateway_authority(_flow(), "alice", owner="bob")
		authority.check_gateway_authority(_flow(), "alice", owner="alice")

	def test_other_flows_unaffected(self):
		authority.check_gateway_authority({"nodes": [{"id": "x", "type": "trigger.webhook", "config": {}}]}, "bob")

	def test_double_reply_warning(self):
		send = {"id": "s", "type": "tool.call", "config": {"tool_id": "gateway_reply"}}
		end = {"id": "e", "type": "output", "config": {"value": "Thanks"}}
		self.assertIsNotNone(authority.double_reply_warning(_flow(extra=[send, end])))
		self.assertIsNone(authority.double_reply_warning(_flow(extra=[end])))
		self.assertIsNone(authority.double_reply_warning({"nodes": [send, end]}))

	def test_provider_aware_problems_for_generic_node(self):
		flow = _flow()
		flow["nodes"][0]["config"]["params"] = [{"key": "keywords", "value": ["order"]}]
		self.assertEqual(authority.trigger_problems(flow), [])
		flow["nodes"][0]["config"]["params"] = [{"key": "commands", "value": ["start"]}]  # a Telegram-node option
		self.assertTrue(authority.trigger_problems(flow))


class TestSensitive(_Base):
	def test_chat_triggers_are_sensitive(self):
		for node_type in ("trigger.gateway", "trigger.whatsapp", "trigger.telegram"):
			labels = publish_guard.sensitive_labels(_flow(node_type))
			self.assertEqual(labels, [publish_guard.CHAT_LABEL], node_type)

	def test_publish_needs_capability(self):
		with (
			mock.patch.object(publish_guard, "can_publish_sensitive", return_value=False),
			mock.patch.object(publish_guard.frappe, "throw", side_effect=_throw),
			mock.patch.object(publish_guard, "_", lambda s: s),
			mock.patch("huf.ai.flow.code_node.check_publish"),
			self.assertRaises(_Throw),
		):
			publish_guard.check_can_publish(_flow(), None, "alice")

	def test_publish_with_capability_still_needs_gateway_write(self):
		with (
			mock.patch.object(publish_guard, "can_publish_sensitive", return_value=True),
			mock.patch("huf.ai.flow.code_node.check_publish"),
			self.assertRaises(_Throw),
		):
			publish_guard.check_can_publish(_flow(), None, "bob")

	def test_unchanged_trigger_does_not_need_capability_again(self):
		with (
			mock.patch.object(publish_guard, "can_publish_sensitive", return_value=False),
			mock.patch("huf.ai.flow.code_node.check_publish"),
		):
			publish_guard.check_can_publish(_flow(), _flow(), "alice")

	def test_changed_filter_needs_capability_again(self):
		changed = _flow()
		changed["nodes"][0]["config"]["params"] = [{"key": "keywords", "value": ["order"]}]
		with (
			mock.patch.object(publish_guard, "can_publish_sensitive", return_value=False),
			mock.patch.object(publish_guard.frappe, "throw", side_effect=_throw),
			mock.patch.object(publish_guard, "_", lambda s: s),
			mock.patch("huf.ai.flow.code_node.check_publish"),
			self.assertRaises(_Throw),
		):
			publish_guard.check_can_publish(changed, _flow(), "alice")


if __name__ == "__main__":
	unittest.main()
