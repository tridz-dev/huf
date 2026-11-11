"""Tests for the external-app gateway hook helpers (fire_hook notify, gate_hook fail-closed)."""

import unittest
from unittest.mock import patch

from huf.ai import gateway_hooks
from huf.ai.whatsapp.outbound_policy import OutboundRefused

HOOK = "huf_test_gateway_hook"
CALLS: list[str] = []


def _ok_a(**payload):
	CALLS.append("a")
	return {"handler": "a", "to": payload.get("to")}


def _ok_b(**payload):
	CALLS.append("b")
	return {"handler": "b"}


def _raises(**payload):
	CALLS.append("raises")
	raise RuntimeError("boom")


def _allow(**payload):
	CALLS.append("allow")
	return None


def _refuse_dict(**payload):
	CALLS.append("refuse")
	return {"reason": "not allowed"}


def _refuse_str(**payload):
	CALLS.append("refuse_str")
	return "no"


MODULE = "huf.ai.gateway_adapters.tests.test_gateway_hooks"


class _Base(unittest.TestCase):
	def setUp(self):
		CALLS.clear()
		self.log_patch = patch("huf.ai.gateway_hooks.frappe.log_error")
		self.log_error = self.log_patch.start()
		self.addCleanup(self.log_patch.stop)

	def hooks(self, value):
		patcher = patch("huf.ai.gateway_hooks.frappe.get_hooks", return_value=value)
		patcher.start()
		self.addCleanup(patcher.stop)


class TestFireHook(_Base):
	def test_multiple_handlers_run_in_order_and_return_results(self):
		self.hooks([f"{MODULE}._ok_a", f"{MODULE}._ok_b"])

		results = gateway_hooks.fire_hook(HOOK, to="15551234567")

		self.assertEqual(CALLS, ["a", "b"])
		self.assertEqual(
			results,
			[{"handler": "a", "to": "15551234567"}, {"handler": "b"}],
		)
		self.log_error.assert_not_called()

	def test_single_string_hook_is_accepted(self):
		self.hooks(f"{MODULE}._ok_a")

		results = gateway_hooks.fire_hook(HOOK, to="1")

		self.assertEqual(CALLS, ["a"])
		self.assertEqual(results, [{"handler": "a", "to": "1"}])

	def test_raising_handler_is_logged_and_others_still_run(self):
		self.hooks([f"{MODULE}._raises", f"{MODULE}._ok_b"])

		results = gateway_hooks.fire_hook(HOOK)

		self.assertEqual(CALLS, ["raises", "b"])
		self.assertEqual(results, [{"handler": "b"}])
		self.log_error.assert_called_once()
		kwargs = self.log_error.call_args.kwargs
		self.assertEqual(kwargs.get("title"), f"gateway hook {HOOK} failed")
		self.assertIn("boom", kwargs.get("message", ""))

	def test_bad_dotted_path_is_logged_and_skipped(self):
		self.hooks(["huf.ai.does_not_exist.handler", f"{MODULE}._ok_b"])

		results = gateway_hooks.fire_hook(HOOK)

		self.assertEqual(CALLS, ["b"])
		self.assertEqual(results, [{"handler": "b"}])
		self.log_error.assert_called_once()
		self.assertEqual(self.log_error.call_args.kwargs.get("title"), f"gateway hook {HOOK} failed")

	def test_no_hooks_returns_empty_list(self):
		self.hooks([])
		self.assertEqual(gateway_hooks.fire_hook(HOOK, to="1"), [])
		self.assertEqual(CALLS, [])

	def test_none_hooks_returns_empty_list(self):
		self.hooks(None)
		self.assertEqual(gateway_hooks.fire_hook(HOOK), [])


class TestGateHook(_Base):
	def test_no_hooks_allows(self):
		self.hooks([])
		self.assertIsNone(gateway_hooks.gate_hook(HOOK, to="1"))
		self.assertEqual(CALLS, [])

	def test_none_hooks_allows(self):
		self.hooks(None)
		self.assertIsNone(gateway_hooks.gate_hook(HOOK))

	def test_all_handlers_allowing_runs_every_handler(self):
		self.hooks([f"{MODULE}._allow", f"{MODULE}._allow"])
		self.assertIsNone(gateway_hooks.gate_hook(HOOK, to="1"))
		self.assertEqual(CALLS, ["allow", "allow"])

	def test_dict_refusal_stops_and_raises(self):
		self.hooks([f"{MODULE}._refuse_dict", f"{MODULE}._ok_b"])

		with self.assertRaises(OutboundRefused) as ctx:
			gateway_hooks.gate_hook(HOOK, to="1")

		self.assertEqual(ctx.exception.code, "blocked_by_hook")
		self.assertEqual(CALLS, ["refuse"])

	def test_string_refusal_stops_and_raises(self):
		self.hooks([f"{MODULE}._refuse_str", f"{MODULE}._ok_b"])

		with self.assertRaises(OutboundRefused) as ctx:
			gateway_hooks.gate_hook(HOOK)

		self.assertEqual(ctx.exception.code, "blocked_by_hook")
		self.assertEqual(CALLS, ["refuse_str"])

	def test_exception_stops_and_raises(self):
		self.hooks([f"{MODULE}._raises", f"{MODULE}._ok_b"])

		with self.assertRaises(OutboundRefused) as ctx:
			gateway_hooks.gate_hook(HOOK)

		self.assertEqual(ctx.exception.code, "blocked_by_hook")
		self.assertEqual(CALLS, ["raises"])

	def test_allow_then_refusal_stops_at_refusal(self):
		self.hooks([f"{MODULE}._allow", f"{MODULE}._refuse_dict", f"{MODULE}._ok_b"])

		with self.assertRaises(OutboundRefused):
			gateway_hooks.gate_hook(HOOK)

		self.assertEqual(CALLS, ["allow", "refuse"])

	def test_bad_dotted_path_fails_closed(self):
		self.hooks(["huf.ai.does_not_exist.handler"])

		with self.assertRaises(OutboundRefused) as ctx:
			gateway_hooks.gate_hook(HOOK)

		self.assertEqual(ctx.exception.code, "blocked_by_hook")
