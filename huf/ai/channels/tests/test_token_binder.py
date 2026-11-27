# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Send-time token binder (H-W2-24, G4): fail closed, values only in the returned dict."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import guard, token_binder
from huf.ai.channels.token_binder import TokenUnbound, bind, bind_batch
from huf.ai.flow.support import reason_codes

SENTINEL = "zz-bound-value-sentinel-7f3a"
MEMBER = "member-1"
CTX = {"flow_id": "f", "flow_version": "1", "run_id": "r", "node_id": "n", "extra": "dropped"}
# where a send could leave a trace; the outbox (H-W2-15) does not exist yet
STORES = ("Agent Flow Run", "Flow Member State", "Flow Send Counter", "Error Log")


def values(**tokens):
	return lambda template, names, members, context: {member: dict(tokens) for member in members}


def failing(template, names, members, context):
	raise ValueError(SENTINEL)


class TestTokenBinder(IntegrationTestCase):
	def setUp(self):
		self.logger = patch.object(frappe, "logger").start()
		self.addCleanup(patch.stopall)

	def providers(self, *providers):
		registry = {f"app.tokens{i}": provider for i, provider in enumerate(providers)}
		get_hooks, get_attr = frappe.get_hooks, frappe.get_attr
		patch.object(
			frappe,
			"get_hooks",
			side_effect=lambda hook=None, *a, **k: (
				list(registry) if hook == token_binder.HOOK else get_hooks(hook, *a, **k)
			),
		).start()
		patch.object(
			frappe, "get_attr", side_effect=lambda path: registry.get(path) or get_attr(path)
		).start()

	def assertUnbound(self, names, tokens=("first_name",)):
		with self.assertRaises(TokenUnbound) as caught:
			bind("tpl", list(tokens), MEMBER, CTX)
		self.assertEqual(caught.exception.token_names, list(names))
		self.assertEqual(caught.exception.code, "token_unbound")
		self.assertEqual(str(caught.exception), f"token_unbound: {', '.join(names)}")
		self.assertIsNone(caught.exception.__context__)

	def test_hook_order_first_value_wins(self):
		self.providers(values(a="first"), values(a="second", b="two", unasked="x"))
		self.assertEqual(bind("tpl", ["a", "b"], MEMBER, CTX), {"a": "first", "b": "two"})

	def test_provider_gets_the_contract_arguments(self):
		seen = []

		def provider(*args):
			seen.append(args)
			return {member: {"a": "v"} for member in args[2]}

		self.providers(provider)
		bind_batch("tpl", ["a"], ["m1", "m2", "m1"], CTX)
		context = {key: CTX[key] for key in token_binder.CONTEXT_KEYS}
		self.assertEqual(seen, [("tpl", ["a"], ["m1", "m2"], context)])

	def test_batch_blocks_only_the_incomplete_member(self):
		self.providers(lambda *args: {"m1": {"a": "v"}})
		result = bind_batch("tpl", ["a"], ["m1", "m2"], {})
		self.assertEqual(result["m1"], {"a": "v"})
		self.assertEqual(result["m2"].token_names, ["a"])

	def test_missing_token_blocks(self):
		self.providers(values(a=SENTINEL))
		self.assertUnbound(["b"], tokens=("a", "b"))

	def test_no_provider_blocks(self):
		self.providers()
		self.assertUnbound(["first_name"])

	def test_non_str_value_blocks_and_is_not_replaced(self):
		self.providers(values(first_name=None), values(first_name="late"))
		self.assertUnbound(["first_name"])

	def test_bad_result_shape_blocks(self):
		for answer in (None, [], {MEMBER: None}):
			with self.subTest(answer=answer):
				self.providers(values(first_name="ok"), lambda *args, answer=answer: answer)
				self.assertUnbound(["first_name"])

	def test_provider_exception_blocks_and_logs_no_message(self):
		self.providers(values(first_name="ok"), failing)
		self.assertUnbound(["first_name"])
		self.assertNotIn(SENTINEL, str(self.logger.mock_calls))
		self.assertIn("ValueError", str(self.logger.mock_calls))

	def test_hook_lookup_failure_blocks(self):
		patch.object(frappe, "get_hooks", side_effect=RuntimeError(SENTINEL)).start()
		self.assertUnbound(["first_name"])

	def test_no_tokens_needs_no_provider(self):
		self.providers(failing)
		self.assertEqual(bind("tpl", [], MEMBER, CTX), {})

	def test_block_traceback_with_locals_holds_no_value(self):
		self.providers(values(a=SENTINEL))
		try:
			bind("tpl", ["a", "b"], MEMBER, CTX)
		except TokenUnbound:
			trace = frappe.get_traceback(with_context=True)
		self.assertIn("token_unbound", trace)
		self.assertNotIn(SENTINEL, trace)

	def test_bound_value_is_stored_nowhere(self):
		def rows():
			return {doctype: frappe.get_all(doctype, fields=["*"], limit=0) for doctype in STORES}

		before = {doctype: len(found) for doctype, found in rows().items()}
		self.providers(values(a=SENTINEL))
		sent = []
		bound = bind("tpl", ["a"], MEMBER, CTX)
		verdict = guard.evaluate({"token_names": ["a"]})
		if verdict.allowed:
			sent.append(bound)
		with self.assertRaises(TokenUnbound):
			bind("tpl", ["a", "b"], MEMBER, CTX)

		self.assertEqual(sent, [{"a": SENTINEL}])
		after = rows()
		self.assertEqual({doctype: len(found) for doctype, found in after.items()}, before)
		self.assertNotIn(SENTINEL, str(after))
		self.assertNotIn(SENTINEL, str(self.logger.mock_calls))

	def test_reason_code_is_registered(self):
		self.assertEqual(reason_codes.normalize(TokenUnbound.code), "token_unbound")
