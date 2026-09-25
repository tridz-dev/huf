# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) integration-style test proving that
`huf.ai.conversation_fork.fork_conversation_impl` actually wires
`huf.ai.subscription.session_binding.binding_for_fork()` onto the newly
created forked conversation.

Only the Frappe doc layer is mocked (`frappe.get_doc`, `frappe.get_all`,
`frappe.has_permission`, `frappe.session`, `assert_agent_access`) - the real
`fork_conversation_impl` and the real `binding_for_fork` are both exercised,
so this is testing the wiring between them, not re-testing the pure
`binding_for_fork` function (which already has its own unit tests).
"""

import types
import unittest
from unittest import mock

import frappe

from huf.ai import conversation_fork
from huf.ai.subscription.session_binding import binding_for_fork


def _fake_conversation_doc(**overrides):
	"""Stand-in for an `Agent Conversation` Document.

	Mimics enough of the Document surface (`.update`, `.save`, `.insert`,
	`.db_set`, attribute access) for `fork_conversation_impl` and
	`ConversationManager.create_new_conversation`.
	"""
	defaults = dict(
		name="AC-FORK-0001",
		title="Source Chat",
		agent="AGENT-1",
		model=None,
		project=None,
		session_id="Chat:alice@example.com",
		channel="Chat",
		external_id="alice@example.com",
		owner="alice@example.com",
		# The source conversation had an active provider session bound to it.
		subscription_provider_session_id="native-session-abc123",
		subscription_provider_session_status="Active",
		subscription_provider_session_created_at="2026-01-01 00:00:00",
		subscription_provider_session_last_verified_at="2026-01-01 00:05:00",
	)
	defaults.update(overrides)
	doc = types.SimpleNamespace(**defaults)

	def _update(values):
		for k, v in values.items():
			setattr(doc, k, v)
		return doc

	doc.update = _update
	doc.save = mock.MagicMock()
	doc.insert = mock.MagicMock()
	doc.db_set = mock.MagicMock()
	return doc


class TestForkBindingWiring(unittest.TestCase):
	"""fork_conversation_impl must explicitly reset subscription fields on the
	forked conversation, never inheriting them from the source."""

	def test_fork_clears_subscription_session_fields_on_new_conversation(self):
		source = _fake_conversation_doc()
		agent_doc = types.SimpleNamespace(name="AGENT-1", provider="Anthropic", model="claude-x")
		# The forked conversation, as constructed fresh by
		# ConversationManager.create_new_conversation. Its DocType defaults
		# happen to already be clean, but this test must prove that
		# fork_conversation_impl explicitly enforces that rather than relying
		# on the incidental default.
		target = _fake_conversation_doc(
			name="AC-FORK-0002",
			title="Source Chat (Fork)",
			subscription_provider_session_id=None,
			subscription_provider_session_status="Uninitialized",
			subscription_provider_session_created_at=None,
			subscription_provider_session_last_verified_at=None,
		)

		frappe.session = types.SimpleNamespace(user="alice@example.com")

		def fake_get_doc(*args, **kwargs):
			if args and args[0] == "Agent Conversation":
				return source
			if args and args[0] == "Agent":
				return agent_doc
			if args and isinstance(args[0], dict):
				# ConversationManager.create_new_conversation building the new doc.
				return target
			raise AssertionError(f"Unexpected frappe.get_doc call: {args!r} {kwargs!r}")

		with mock.patch.object(frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(frappe, "has_permission", return_value=True), \
			mock.patch.object(frappe, "get_all", return_value=[]), \
			mock.patch.object(conversation_fork, "_can_fork", return_value=True), \
			mock.patch("huf.ai.agent_access.assert_agent_access", create=True), \
			mock.patch.object(conversation_fork, "_update_total_messages"):

			result = conversation_fork.fork_conversation_impl(
				conversation_id="AC-FORK-0001",
				mode="last_output",
			)

		self.assertTrue(result["success"])
		self.assertEqual(result["conversation_id"], "AC-FORK-0002")

		# The wiring under test: binding_for_fork() was actually applied to
		# the new conversation doc, and target.save() was called to persist it.
		target.save.assert_called_once()
		self.assertEqual(
			{
				"subscription_provider_session_id": target.subscription_provider_session_id,
				"subscription_provider_session_status": target.subscription_provider_session_status,
				"subscription_provider_session_created_at": target.subscription_provider_session_created_at,
				"subscription_provider_session_last_verified_at": (
					target.subscription_provider_session_last_verified_at
				),
			},
			binding_for_fork(),
		)

		# And explicitly: the forked conversation must not carry over the
		# source's active native session id.
		self.assertIsNone(target.subscription_provider_session_id)
		self.assertEqual(target.subscription_provider_session_status, "Uninitialized")
		self.assertNotEqual(
			target.subscription_provider_session_id,
			source.subscription_provider_session_id,
		)


if __name__ == "__main__":
	unittest.main()
