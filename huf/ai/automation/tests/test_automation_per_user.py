# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""Per-user conversation routing for Dedicated Automations (no bench needed).

Drives ``runner.run_automation`` with a fake frappe session and records the
routing ``_execute`` would hand to ``run_agent_sync``.
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
	import frappe
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	sys.modules["frappe"] = frappe_mock
if "frappe.utils" not in sys.modules:
	utils_mock = MagicMock()
	sys.modules["frappe.utils"] = utils_mock
	sys.modules["frappe"].utils = utils_mock

from huf.ai.automation import per_user, runner


class FakeFrappe:
	"""Minimal frappe: a session whose user follows set_user."""

	class DoesNotExistError(Exception):
		pass

	class ValidationError(Exception):
		pass

	def __init__(self, automation=None, session_user="Administrator", agent_flag=1):
		self.session = SimpleNamespace(user=session_user)
		self.db = SimpleNamespace(get_value=lambda *a, **k: agent_flag)
		self._automation = automation

	def get_doc(self, *a, **k):
		return self._automation

	def set_user(self, user):
		self.session.user = user

	def throw(self, msg, exc=None):
		raise (exc or Exception)(msg)


def _automation(mode="Dedicated", run_as_user=None, conversation=None):
	fields = {"target_type": "Agent", "conversation_mode": mode, "agent": "Agent-1"}
	return SimpleNamespace(
		name="AUT-1",
		disabled=0,
		status="Active",
		agent="Agent-1",
		procedure=None,
		run_as_user=run_as_user,
		conversation_mode=mode,
		conversation=conversation,
		get=lambda k, d=None: fields.get(k, d),
	)


def run(automation, session_user="Administrator", initiating_user=None, trigger_name=None, agent_flag=1):
	"""Return the routing and per-user state seen inside the run."""
	fake = FakeFrappe(automation, session_user, agent_flag)
	seen = {}

	def fake_execute(auto, *a, **k):
		seen["routing"] = runner._resolve_conversation_routing(auto)
		seen["active"] = per_user.is_active(auto)
		seen["user"] = fake.session.user

	with (
		patch.object(runner, "frappe", fake),
		patch.object(per_user, "frappe", fake),
		patch.object(runner, "_check_run_as_user_permission"),
		patch.object(runner, "_execute", fake_execute),
	):
		runner.run_automation(
			"AUT-1", trigger_name=trigger_name, initiating_user=initiating_user, commit=False
		)
	return seen


class TestPerUserRouting(unittest.TestCase):
	def test_two_users_get_separate_keys(self):
		a = run(_automation(), initiating_user="a@x.com")
		b = run(_automation(), initiating_user="b@x.com")
		self.assertNotEqual(a["routing"][2], b["routing"][2])
		self.assertIn("a@x.com", a["routing"][2])
		self.assertIsNone(a["routing"][0])

	def test_same_user_reuses_key(self):
		self.assertEqual(
			run(_automation(), initiating_user="a@x.com")["routing"][2],
			run(_automation(), initiating_user="a@x.com")["routing"][2],
		)

	def test_stored_link_ignored_in_per_user_mode(self):
		r = run(_automation(conversation="CONV-1"), initiating_user="a@x.com")
		self.assertIsNone(r["routing"][0])
		self.assertTrue(r["active"])

	def test_doc_event_uses_changer_not_owner(self):
		# Doc Event passes frappe.session.user captured at enqueue time as
		# initiating_user; the doc's owner/modified_by never enters the key.
		r = run(_automation(), initiating_user="changer@x.com", trigger_name="T1")
		self.assertEqual(r["routing"][2], "automation:AUT-1:user:changer@x.com")

	def test_run_now_and_app_event_use_passed_user(self):
		r = run(_automation(), initiating_user="me@x.com")
		self.assertTrue(r["routing"][2].endswith(":user:me@x.com"))

	def test_schedule_webhook_with_run_as(self):
		r = run(_automation(run_as_user="bot@x.com"), trigger_name="T1")
		self.assertTrue(r["routing"][2].endswith(":user:bot@x.com"))

	def test_schedule_webhook_without_run_as_uses_session_user(self):
		r = run(_automation(), session_user="worker@x.com", trigger_name="T1")
		self.assertTrue(r["routing"][2].endswith(":user:worker@x.com"))

	def test_run_as_consistent_across_runs(self):
		auto = _automation(run_as_user="bot@x.com")
		self.assertEqual(
			run(auto, session_user="Administrator", trigger_name="T1")["routing"][2],
			run(auto, session_user="other@x.com", trigger_name="T1")["routing"][2],
		)

	def test_guest_session_never_reuses(self):
		a = run(_automation(conversation="CONV-1"), session_user="Guest", trigger_name="T1")
		b = run(_automation(conversation="CONV-1"), session_user="Guest", trigger_name="T1")
		self.assertIsNone(a["routing"][0])
		self.assertNotEqual(a["routing"][2], b["routing"][2])
		self.assertNotIn("Guest", a["routing"][2])

	def test_guest_initiator_never_reuses(self):
		r = run(_automation(), initiating_user="Guest")
		self.assertTrue(r["routing"][2].startswith("automation-new:"))

	def test_empty_identity_starts_new(self):
		with patch.object(per_user, "frappe", FakeFrappe(None, "")):
			_, _, ext, _ = per_user.resolve_routing(_automation())
		self.assertTrue(ext.startswith("automation-new:"))

	def test_flag_off_keeps_single_dedicated(self):
		r = run(_automation(conversation="CONV-1"), initiating_user="a@x.com", agent_flag=0)
		self.assertFalse(r["active"])
		self.assertEqual(r["routing"], ("CONV-1", "automation", "automation:AUT-1", False))

	def test_new_and_no_ui_unchanged(self):
		new = run(_automation("New"), initiating_user="a@x.com")
		noui = run(_automation("No-UI"), initiating_user="a@x.com")
		self.assertFalse(new["active"])
		self.assertTrue(new["routing"][2].startswith("automation-new:"))
		self.assertTrue(noui["routing"][2].startswith("automation-noui:"))
		self.assertTrue(noui["routing"][3])


if __name__ == "__main__":
	unittest.main()
