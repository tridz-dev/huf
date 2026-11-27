"""Reason-code registry (H-W2-11).

The module imports frappe only inside functions and frappe is faked here, so this also runs without a bench:

	python3 huf/ai/flow/tests/test_flow_reason_codes.py
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
	_SPEC = importlib.util.spec_from_file_location("huf_reason_codes_standalone", _PATH)
	rc = importlib.util.module_from_spec(_SPEC)
	_SPEC.loader.exec_module(rc)


def fake_frappe(hooks_by_app):
	"""A frappe whose apps declare ``hooks_by_app[app]``; an Exception value makes reading that app fail."""

	def get_hooks(hook, app_name=None):
		if hook != "huf_flow_reason_codes":
			raise AssertionError(hook)
		value = hooks_by_app[app_name]
		if isinstance(value, Exception):
			raise value
		return value

	fake = mock.MagicMock()
	fake.get_installed_apps.return_value = list(hooks_by_app)
	fake.get_hooks.side_effect = get_hooks
	return fake


class TestReasonCodes(unittest.TestCase):
	def use(self, hooks_by_app):
		fake = fake_frappe(hooks_by_app)
		patcher = mock.patch.dict(sys.modules, {"frappe": fake})
		patcher.start()
		self.addCleanup(patcher.stop)
		return fake

	def warnings(self, fake):
		return [call.args[0] for call in fake.logger.return_value.warning.call_args_list]

	def test_huf_codes_are_registered(self):
		fake = self.use({"huf": []})
		for code in ("hook_error", "hook_timeout", "window_defer_exhausted", "freq_cap", "bad_recipient", "unknown"):
			self.assertEqual(rc.normalize(code), code)
		self.assertEqual(self.warnings(fake), [])

	def test_app_codes_from_list_and_mapping(self):
		self.use({"huf": [], "loyalty": ["tier_not_eligible"], "other": {"points_low": ["Not enough points"]}})
		self.assertEqual(rc.normalize("tier_not_eligible"), "tier_not_eligible")
		self.assertEqual(rc.normalize("points_low"), "points_low")
		self.assertEqual(rc.registered_codes(), rc.HUF_CODES | {"tier_not_eligible", "points_low"})

	def test_unknown_code_is_logged_without_its_value(self):
		fake = self.use({"huf": []})
		for value in ("+919876543210", "jane@example.com", "jane_doe", "", None, 7, ["freq_cap"], {"a": 1}):
			self.assertEqual(rc.normalize(value), "unknown")
		logged = self.warnings(fake)
		self.assertEqual(len(logged), 8)
		self.assertEqual(set(logged), {"unregistered flow reason code stored as unknown"})

	def test_malformed_app_codes_are_ignored(self):
		bad = ["+919876543210", "jane@example.com", "Has Space", "9lives", "ok_code\n", "a" * 65, 5]
		fake = self.use({"loyalty": [*bad, "good_code"]})
		self.assertEqual(rc.registered_codes() - rc.HUF_CODES, {"good_code"})
		self.assertEqual(len(self.warnings(fake)), len(bad))
		self.assertNotIn("jane@example.com", " ".join(self.warnings(fake)))

	def test_one_broken_app_keeps_the_others(self):
		self.use({"broken": RuntimeError("boom"), "loyalty": ["tier_not_eligible"]})
		self.assertEqual(rc.normalize("tier_not_eligible"), "tier_not_eligible")

	def test_never_raises_when_frappe_fails(self):
		fake = self.use({"huf": []})
		fake.get_installed_apps.side_effect = RuntimeError("no site")
		fake.logger.side_effect = RuntimeError("no logger")
		self.assertEqual(rc.normalize("tier_not_eligible"), "unknown")
		self.assertEqual(rc.normalize("freq_cap"), "freq_cap")
		self.assertEqual(rc.registered_codes(), rc.HUF_CODES)


if __name__ == "__main__":
	unittest.main()
