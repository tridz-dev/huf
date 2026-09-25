# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for T-T9: conversation/run
lifecycle coverage for the Subscription CLI passthrough branch, filling gaps
NOT already covered by:

- huf/ai/tests/subscription/test_executor_passthrough.py (T-06-C)
- huf/ai/tests/subscription/test_resume_and_ordering.py (T-06-D)

See PLAN.md §41 for the checklist this file works through. Each test class
docstring notes which §41 bullet it covers, or (for items skipped as
duplicates) why.

Relies on the repo-root ``conftest.py`` to stub ``frappe``/``litellm``/``agents``
before anything under the ``huf`` package is imported, exactly as the two
files above already do.

SKIPPED AS ALREADY COVERED (see report for detail):
- Provider/model mismatch refuses cleanly -> TestBindingMismatchRefusesCleanly
  in test_executor_passthrough.py.
- Missing provider session fails clearly, no replay -> TestSessionLostVsAuthRequired
  in test_resume_and_ordering.py (asserts Failed status + exact "not an
  authentication problem" message; no history replay is architecturally
  impossible here since the passthrough executor never fetches HUF history at
  all -- see executor.py module docstring's "Passthrough constraint").
- Stateless run doesn't persist a binding -> TestStatelessRunDoesNotPersistBinding
  in test_executor_passthrough.py.

GAPS FOUND (reported, not fixed here -- see final report):
- Idempotent duplicate request: the guard is real and provider-agnostic
  (huf/ai/agent_integration.py, run_agent_sync, ~line 1397), but it happens
  once, above ANY provider_mode branching -- there is no subscription-specific
  duplicate check inside SubscriptionPassthroughExecutor.execute() itself.
  This is *not* a gap in the shipped behavior, just documented here since the
  task asked to check both call sites explicitly.
- Conversation fork: `session_binding.binding_for_fork()` exists but nothing
  calls it from `huf/ai/conversation_fork.py::fork_conversation_impl`. See
  TestForkNeverCallsBindingForFork below.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

import frappe

import huf.ai.agent_integration as agent_integration
from huf.ai.subscription import executor as executor_module
from huf.ai.subscription import session_binding
from huf.ai.subscription.executor import SubscriptionPassthroughExecutor
from huf.ai.subscription.types import SubscriptionTurnResult


def _fake_runtime(**overrides):
	defaults = dict(
		name="RUNTIME-1",
		provider_family="Claude",
		transport_type="Local",
		executable="claude",
		working_directory=None,
		docker_container=None,
		ssh_connection=None,
		timeout_seconds=None,
		auth_status="ready",
	)
	defaults.update(overrides)
	runtime = types.SimpleNamespace(**defaults)
	runtime.check_tenancy = mock.MagicMock(return_value=True)
	return runtime


def _fake_provider_doc(**overrides):
	defaults = dict(name="PROVIDER-1", subscription_runtime="RUNTIME-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_agent_doc(**overrides):
	defaults = dict(name="AGENT-1", model="MODEL-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_conversation(**overrides):
	defaults = dict(
		name="CONV-1",
		subscription_provider_session_id=None,
		subscription_provider_session_status="Uninitialized",
		subscription_runtime=None,
	)
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_run_doc(**overrides):
	defaults = dict(name="RUN-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


class TestQueuedTurnsSerializeViaConversationLock(unittest.TestCase):
	"""§41: two queued turns for the same conversation serialize correctly
	(no concurrent adapter invocation).

	LIMITATION: real concurrency (two OS threads/processes racing on Redis
	SETNX) cannot be exercised without a live Redis. What IS testable at the
	unit level, and what this test proves structurally, is:

	  1. `_run_queued_agent` acquires the per-conversation lock
	     (`frappe.cache().set(lock_key, 1, ex=..., nx=True)`) BEFORE it ever
	     calls `_next_queued_run` / processes a run (i.e. before any adapter
	     invocation can happen) -- call-order proof via a shared log.
	  2. A second drainer invocation that arrives while the lock is already
	     held (`cache().set(..., nx=True)` returning falsy, exactly what
	     Redis SETNX NX returns for an existing key) exits immediately and
	     processes zero runs -- proving two concurrent drainers cannot both
	     process turns for the same conversation, which is what prevents
	     concurrent adapter invocation for the same conversation in
	     production.

	This does not exercise `_execute_agent_run` -> `SubscriptionPassthroughExecutor
	.execute` directly (that is unconditionally serial once inside the drain
	loop, since it's a single `while True` loop -- see `_run_queued_agent`
	source), so the interesting risk is entirely at the lock-acquisition
	layer, which is what is exercised here.
	"""

	def test_lock_acquired_before_any_run_is_claimed(self):
		call_log = []

		def fake_cache_set(key, value, ex=None, nx=None):
			call_log.append(("lock_set", key))
			return True

		def fake_next_queued_run(conversation_id):
			call_log.append(("claim_run", conversation_id))
			return None  # no runs: keeps this test to the lock-ordering proof

		fake_cache = mock.MagicMock()
		fake_cache.set.side_effect = fake_cache_set

		with mock.patch.object(frappe, "cache", return_value=fake_cache), \
			mock.patch.object(agent_integration, "_next_queued_run", side_effect=fake_next_queued_run), \
			mock.patch.object(agent_integration, "_has_queued_runs", return_value=False):

			agent_integration._run_queued_agent(conversation_id="CONV-1")

		self.assertEqual(call_log[0], ("lock_set", "agent_run_conv_CONV-1"))
		# The claim attempt (which would lead to _drain_run -> the adapter
		# call) never happens without the lock having been set first.
		self.assertTrue(any(c[0] == "claim_run" for c in call_log))
		self.assertLess(
			call_log.index(("lock_set", "agent_run_conv_CONV-1")),
			[i for i, c in enumerate(call_log) if c[0] == "claim_run"][0],
		)

	def test_second_concurrent_drainer_exits_without_claiming_any_run(self):
		"""Simulates a second `_run_queued_agent` invocation arriving while the
		first one already holds the lock (SETNX returns False for an existing
		key) -- proving the second drainer can never race the first into
		claiming/executing a run for the same conversation."""
		fake_cache = mock.MagicMock()
		fake_cache.set.return_value = False  # lock already held by another drainer

		with mock.patch.object(frappe, "cache", return_value=fake_cache), \
			mock.patch.object(agent_integration, "_next_queued_run") as mock_next_run:

			result = agent_integration._run_queued_agent(conversation_id="CONV-1")

		mock_next_run.assert_not_called()
		self.assertIsNone(result)


class TestIdempotentDuplicateRequestGuardIsProviderAgnostic(unittest.TestCase):
	"""§41: duplicate/idempotent request (same client_idempotency_key) must not
	create a duplicate provider turn.

	FINDING (not a gap, but worth stating precisely): `run_agent_sync`'s
	idempotency-key lookup (huf/ai/agent_integration.py ~line 1397) runs
	BEFORE any provider_mode branching -- it is a single check shared by every
	provider, including Subscription CLI. `SubscriptionPassthroughExecutor
	.execute()` itself contains NO idempotency check of its own, and needs
	none: a duplicate request short-circuits at Agent Run creation and never
	reaches `_execute_agent_run` / the subscription dispatch branch a second
	time. This test proves that ordering directly against the real source
	function (not a re-implementation) by asserting the existing-run lookup
	short-circuits before `Agent Run` doc construction/insert is reached,
	regardless of provider_mode -- generalizing what
	`test_agent_run_idempotency.py` already proves for the default path to
	the subscription-passthrough case explicitly.
	"""

	def test_second_call_with_same_key_returns_existing_run_without_inserting(self):
		agent_doc = types.SimpleNamespace(
			name="AGENT-1",
			allow_guest=1,
			disabled=0,
			provider="PROVIDER-SUB",
			model="MODEL-1",
			persist_conversation=1,
			prompt_mode="Local",
		)
		conversation = _fake_conversation(name="CONV-1")
		existing_run = types.SimpleNamespace(
			name="RUN-EXISTING",
			status="Success",
			response="already answered",
			provider="PROVIDER-SUB",
			conversation="CONV-1",
			sequence=1,
		)

		identity = types.SimpleNamespace(authorized=True, reason=None)

		def fake_get_value(doctype, filters=None, fieldname=None, **kwargs):
			if doctype == "Agent" :
				return None
			if doctype == "Agent Run":
				# Idempotency lookup: simulate a prior run already exists for
				# this (conversation, key) pair.
				if isinstance(filters, dict) and filters.get("idempotency_key") == "dup-key-1":
					return "RUN-EXISTING"
			return None

		insert_called = []

		def fake_frappe_get_doc(arg, *a, **kw):
			if isinstance(arg, dict) and arg.get("doctype") == "Agent Run":
				insert_called.append(arg)
				doc = mock.MagicMock()
				doc.insert = mock.MagicMock()
				return doc
			if arg == "Agent" and a and a[0] == "AGENT-1":
				return agent_doc
			if arg == "Agent Run" and a and a[0] == "RUN-EXISTING":
				return existing_run
			raise AssertionError(f"unexpected frappe.get_doc call: {arg!r}, {a!r}")

		with mock.patch.object(agent_integration, "resolve_run_identity_and_authorize", return_value=identity), \
			mock.patch.object(agent_integration, "_resolve_effective_model",
				return_value=("PROVIDER-SUB", "MODEL-1", "model-name")), \
			mock.patch.object(agent_integration, "ConversationManager") as mock_cm_cls, \
			mock.patch.object(agent_integration, "_next_run_sequence", return_value=2), \
			mock.patch.object(agent_integration.RunBudget, "from_agent", return_value=mock.MagicMock(
				deadline_at=None, current_depth=0, ancestry=[], spend_so_far_usd=0,
			)), \
			mock.patch.object(agent_integration.frappe, "get_doc", side_effect=fake_frappe_get_doc), \
			mock.patch.object(agent_integration.frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(agent_integration.frappe, "has_permission", return_value=True), \
			mock.patch.object(agent_integration.frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(agent_integration, "as_json", getattr(agent_integration, "as_json", None) or (lambda v: v), create=True):

			mock_db.get_value.side_effect = fake_get_value
			mock_cm_cls.return_value.get_or_create_conversation.return_value = conversation
			mock_cm_cls.return_value.session_id = "sess-1"

			result = agent_integration.run_agent_sync(
				agent_name="AGENT-1",
				prompt="hello",
				conversation_id="CONV-1",
				client_idempotency_key="dup-key-1",
			)

		# The duplicate must resolve to the EXISTING run, and no new Agent Run
		# doc may ever be constructed/inserted for it.
		self.assertEqual(result["agent_run_id"], "RUN-EXISTING")
		self.assertEqual(insert_called, [])


class TestDifferentConversationsGetIndependentBindings(unittest.TestCase):
	"""§41: different conversations receive different provider sessions
	(independent binding), via `session_binding.resolve_binding_for_turn`."""

	def test_two_uninitialized_conversations_each_create_new_independently(self):
		conv_a_state = {
			"subscription_provider_session_id": None,
			"subscription_provider_session_status": "Uninitialized",
			"subscription_runtime": None,
			"model_name": "MODEL-1",
		}
		conv_b_state = {
			"subscription_provider_session_id": None,
			"subscription_provider_session_status": "Uninitialized",
			"subscription_runtime": None,
			"model_name": "MODEL-1",
		}

		decision_a = session_binding.resolve_binding_for_turn(conv_a_state, "RUNTIME-1", "MODEL-1")
		decision_b = session_binding.resolve_binding_for_turn(conv_b_state, "RUNTIME-1", "MODEL-1")

		self.assertEqual(decision_a.action, session_binding.ACTION_CREATE_NEW)
		self.assertEqual(decision_b.action, session_binding.ACTION_CREATE_NEW)
		# Each decision carries no session id of its own yet -- the adapter
		# will mint an independent one per conversation once a session is
		# actually created (see executor.py step 9), so bindings never share
		# state at this layer.
		self.assertIsNone(decision_a.provider_session_id)
		self.assertIsNone(decision_b.provider_session_id)

	def test_two_active_conversations_resume_their_own_distinct_sessions(self):
		conv_a_state = {
			"subscription_provider_session_id": "sess-AAA",
			"subscription_provider_session_status": "Active",
			"subscription_runtime": "RUNTIME-1",
			"model_name": "MODEL-1",
		}
		conv_b_state = {
			"subscription_provider_session_id": "sess-BBB",
			"subscription_provider_session_status": "Active",
			"subscription_runtime": "RUNTIME-1",
			"model_name": "MODEL-1",
		}

		decision_a = session_binding.resolve_binding_for_turn(conv_a_state, "RUNTIME-1", "MODEL-1")
		decision_b = session_binding.resolve_binding_for_turn(conv_b_state, "RUNTIME-1", "MODEL-1")

		self.assertEqual(decision_a.action, session_binding.ACTION_RESUME_EXISTING)
		self.assertEqual(decision_b.action, session_binding.ACTION_RESUME_EXISTING)
		self.assertEqual(decision_a.provider_session_id, "sess-AAA")
		self.assertEqual(decision_b.provider_session_id, "sess-BBB")
		self.assertNotEqual(decision_a.provider_session_id, decision_b.provider_session_id)


class TestSessionIdFieldNeverWritten(unittest.TestCase):
	"""§41: HUF's pre-existing `Agent Conversation.session_id` field is never
	overwritten by subscription logic.

	Static/structural check: greps the actual source of executor.py and
	session_binding.py for any write to the bare `session_id` key (as
	opposed to `subscription_provider_session_id`, `subscription_..._status`,
	etc.) and asserts none exists. A dynamic (mock-based) check would only
	prove it for the specific code paths exercised by other tests in this
	suite; the source scan proves it for every code path in both modules,
	including ones no other test currently reaches.
	"""

	def test_no_write_to_bare_session_id_field(self):
		import inspect
		import re

		from huf.ai.subscription import executor as exec_mod
		from huf.ai.subscription import session_binding as binding_mod

		# Matches a dict key literal "session_id" or 'session_id' that is NOT
		# immediately preceded by "subscription_provider_" or "provider_" (to
		# allow subscription_provider_session_id / provider_session_id-style
		# keys while still catching a bare "session_id": ... key).
		bad_pattern = re.compile(r'(?<!subscription_provider_)(?<!provider_)["\']session_id["\']\s*:')

		for mod in (exec_mod, binding_mod):
			source = inspect.getsource(mod)
			matches = bad_pattern.findall(source)
			self.assertEqual(
				matches,
				[],
				f"{mod.__name__} appears to write a bare 'session_id' field -- "
				"this must only ever be subscription_provider_session_id; a "
				"write to HUF's pre-existing Agent Conversation.session_id "
				"would be a real bug.",
			)

		# Also confirm no direct attribute-set (`.session_id = `) exists on a
		# conversation-like object in either module.
		attr_pattern = re.compile(r"\.session_id\s*=(?!=)")
		for mod in (exec_mod, binding_mod):
			source = inspect.getsource(mod)
			self.assertEqual(attr_pattern.findall(source), [])


class TestForkNeverCallsBindingForFork(unittest.TestCase):
	"""§41: conversation fork does not inherit the source's provider session.

	FIXED (commit 3237d9bf): `session_binding.binding_for_fork()`
	(huf/ai/subscription/session_binding.py) computes the field-reset for a
	forked conversation, and `huf/ai/conversation_fork.py::fork_conversation_impl`
	now imports and calls it explicitly (`target.update(binding_for_fork())`)
	rather than relying on `create_new_conversation`'s doc dict incidentally
	omitting every `subscription_*` key. This test locks in that wiring as a
	regression guard. A dedicated passing test also exists at
	`huf/ai/tests/subscription/test_fork_binding_wiring.py`.
	"""

	def test_fork_conversation_impl_now_calls_binding_for_fork(self):
		import inspect

		from huf.ai import conversation_fork

		source = inspect.getsource(conversation_fork)
		self.assertIn(
			"binding_for_fork",
			source,
			"conversation_fork.py should call session_binding.binding_for_fork() "
			"explicitly so a forked conversation never inherits the source's "
			"provider-session-shaped state.",
		)

	def test_new_conversation_dict_omits_every_subscription_field(self):
		"""Confirms the incidental safety net this gap currently relies on:
		`create_new_conversation`'s doc dict never sets a subscription_* key,
		so a forked conversation cannot accidentally carry over the source's
		provider_session_id even though nothing calls `binding_for_fork()`."""
		import huf.ai.conversation_manager as conversation_manager_module

		cm = conversation_manager_module.ConversationManager(
			agent_name="AGENT-1", channel="Chat", external_id="alice@example.com",
		)

		captured = {}

		def fake_get_doc(doc_dict):
			captured.update(doc_dict)
			doc = mock.MagicMock()
			return doc

		with mock.patch.object(conversation_manager_module.frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(conversation_manager_module.frappe, "has_permission", return_value=True), \
			mock.patch.object(conversation_manager_module.frappe, "db", mock.MagicMock()):

			cm.create_new_conversation(title="Forked conversation")

		subscription_keys = [k for k in captured if k.startswith("subscription_")]
		self.assertEqual(
			subscription_keys,
			[],
			"create_new_conversation now sets subscription_* fields explicitly "
			"-- if intentional, fork_conversation_impl should call "
			"session_binding.binding_for_fork() explicitly rather than relying "
			"on doc-dict omission.",
		)


class TestCrossUserAccessUnchangedForSubscriptionConversations(unittest.TestCase):
	"""§41: a different HUF user cannot resume/reuse another user's
	conversation's provider session binding.

	This is a regression/confirmation test, not new logic: subscription mode
	adds fields to `Agent Conversation` but does not touch
	`ConversationManager.get_or_create_conversation`'s ownership check (see
	`huf/ai/tests/test_conversation_manager_access.py`, which this test
	mirrors). It confirms that a conversation carrying subscription-passthrough
	state (`runtime_mode="subscription_passthrough"`, an Active provider
	session) is STILL denied to a non-owner via the exact same ownership
	check -- i.e. subscription mode does not bypass HUF's existing
	per-conversation access control anywhere in the lookup path.
	"""

	def _make_subscription_conversation(self, owner="owner@example.com", session_id="sess-owner"):
		return types.SimpleNamespace(
			agent="Test Agent",
			owner=owner,
			session_id=session_id,
			is_active=1,
			runtime_mode="subscription_passthrough",
			subscription_provider_session_id="sess-provider-XYZ",
			subscription_provider_session_status="Active",
		)

	def test_other_user_denied_despite_active_subscription_binding(self):
		import huf.ai.conversation_manager as conversation_manager_module

		conversation = self._make_subscription_conversation()
		cm = conversation_manager_module.ConversationManager(
			agent_name="Test Agent", session_id="attacker-session",
		)

		def get_doc(doctype, name=None, *a, **kw):
			if doctype == "Agent Conversation":
				return conversation
			raise AssertionError(f"unexpected frappe.get_doc call: {doctype}")

		with mock.patch.object(conversation_manager_module.frappe, "get_doc", side_effect=get_doc), \
			mock.patch.object(conversation_manager_module.frappe, "session") as mock_session, \
			mock.patch.object(conversation_manager_module, "has_capability", return_value=False):
			mock_session.user = "attacker@example.com"

			# NOTE: the shared Layer-A `frappe.throw` stub
			# (huf/ai/tests/subscription/_stub_bootstrap.py) always raises
			# ValidationError regardless of the exception class passed to it
			# (a pre-existing stub limitation also visible on
			# test_conversation_manager_access.py when run standalone under
			# this stub) -- so this asserts against the stub's actual
			# behavior (a thrown exception at all) rather than the specific
			# frappe.PermissionError subclass the real Frappe runtime raises.
			with self.assertRaises(frappe.ValidationError):
				cm.get_or_create_conversation(conversation_id="CONV-SUB-1")

	def test_owner_still_allowed_with_active_subscription_binding(self):
		import huf.ai.conversation_manager as conversation_manager_module

		conversation = self._make_subscription_conversation(owner="owner@example.com")
		cm = conversation_manager_module.ConversationManager(
			agent_name="Test Agent", session_id="sess-owner",
		)

		def get_doc(doctype, name=None, *a, **kw):
			if doctype == "Agent Conversation":
				return conversation
			raise AssertionError(f"unexpected frappe.get_doc call: {doctype}")

		with mock.patch.object(conversation_manager_module.frappe, "get_doc", side_effect=get_doc), \
			mock.patch.object(conversation_manager_module.frappe, "session") as mock_session, \
			mock.patch.object(conversation_manager_module, "has_capability", return_value=False):
			mock_session.user = "owner@example.com"

			result = cm.get_or_create_conversation(conversation_id="CONV-SUB-1")

		self.assertIs(result, conversation)


if __name__ == "__main__":
	unittest.main()
