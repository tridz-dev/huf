"""Reason-coded run trace (H-W2-11): every blocked, deferred or skipped step record carries a registered code.

The pure part runs without a bench (frappe is faked):

	python3 huf/ai/flow/tests/test_flow_reason_trace.py

The engine part needs a bench and is skipped without one.
"""

import importlib.util
import os
import sys
import unittest
from unittest import mock

try:
	from huf.ai.flow.support import reason_codes as rc
except ImportError:  # pragma: no cover - frappe-less environments
	_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "support", "reason_codes.py")
	_SPEC = importlib.util.spec_from_file_location("huf_reason_trace_standalone", _PATH)
	rc = importlib.util.module_from_spec(_SPEC)
	_SPEC.loader.exec_module(rc)

try:
	import frappe  # noqa: F401

	from huf.ai.flow import engine
	from huf.ai.graph.executor import Outcome
except ImportError:  # pragma: no cover
	engine = None


def fake_frappe(codes_by_app):
	fake = mock.MagicMock()
	fake.get_installed_apps.return_value = list(codes_by_app)
	fake.get_hooks.side_effect = lambda hook, app_name=None: codes_by_app[app_name]
	return fake


class TestStamp(unittest.TestCase):
	def setUp(self):
		patcher = mock.patch.dict(
			sys.modules, {"frappe": fake_frappe({"huf": [], "loyalty": ["tier_not_eligible"]})}
		)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_blocked_deferred_skipped_get_registered_codes(self):
		records = [
			{"status": "blocked", "reason": "freq_cap"},
			{"status": "blocked", "reason": "window_defer_exhausted"},
			{"status": "deferred", "reason": "send_window"},
			{"status": "skipped", "reason": "turned_off"},
			{"status": "success", "skipped": True},
		]
		for record in records:
			code = rc.stamp(record)["reason_code"]
			self.assertIn(code, rc.registered_codes())
			self.assertNotEqual(code, rc.UNKNOWN)

	def test_app_code_appears(self):
		self.assertEqual(
			rc.stamp({"status": "blocked", "reason": "tier_not_eligible"})["reason_code"], "tier_not_eligible"
		)

	def test_unknown_or_free_text_is_unknown_and_never_raises(self):
		for reason in ("Call +15551234567", None, 42, "QUIET_HOURS"):
			self.assertEqual(rc.stamp({"status": "blocked", "reason": reason})["reason_code"], rc.UNKNOWN)

	def test_other_records_unchanged(self):
		for value in (None, "text", {"status": "queued"}, {"status": "success", "x": 1}):
			self.assertIs(rc.stamp(value), value)

	def test_input_not_mutated(self):
		record = {"status": "blocked", "reason": "freq_cap"}
		rc.stamp(record)
		self.assertNotIn("reason_code", record)

	def test_deferred_park_reason_is_registered(self):
		self.assertIn("send_window", rc.HUF_CODES)  # runs.park.SEND_WINDOW_REASON


@unittest.skipIf(engine is None, "needs a bench")
class TestEngineStepRecord(unittest.TestCase):
	def test_blocked_send_record_gets_code(self):
		outcome = engine._with_reason_code(
			Outcome.from_mapping({"status": "success", "output": {"status": "blocked", "reason": "freq_cap"}})
		)
		self.assertEqual(outcome.output["reason_code"], "freq_cap")
		self.assertEqual(outcome.status, "success")

	def test_app_registered_code_in_trace(self):
		real = frappe.get_hooks

		def get_hooks(hook=None, *args, app_name=None, **kwargs):
			if hook == rc.HOOK and app_name == "huf":
				return ["tier_not_eligible"]
			return real(hook, *args, app_name=app_name, **kwargs)

		with mock.patch.object(frappe, "get_hooks", side_effect=get_hooks):
			outcome = engine._with_reason_code(
				Outcome.from_mapping(
					{"status": "success", "output": {"status": "blocked", "reason": "tier_not_eligible"}}
				)
			)
		self.assertEqual(outcome.output["reason_code"], "tier_not_eligible")

	def test_turned_off_step_keeps_none_output(self):
		from huf.ai.flow.support.turned_off import turned_off_result

		outcome = engine._with_reason_code(Outcome.from_mapping(turned_off_result()))
		self.assertIsNone(outcome.output)
		self.assertEqual(outcome.extra["reason_code"], "turned_off")

	def test_success_record_unchanged(self):
		outcome = engine._with_reason_code(
			Outcome.from_mapping({"status": "success", "output": {"status": "queued"}})
		)
		self.assertEqual(outcome.output, {"status": "queued"})


if __name__ == "__main__":
	unittest.main()
