"""Plain-language data text (``support/humanize.py``): table-driven, no site needed."""

import unittest

from huf.ai.flow.support import humanize as hz


class TestLabels(unittest.TestCase):
	def test_label_for(self):
		cases = [
			("customer_name", "Customer name"),
			("orderTotal", "Order total"),
			("order_url", "Order URL"),
			("sku", "SKU"),
			("due-date", "Due date"),
			("id", "ID"),
			("Total", "Total"),
			("", ""),
		]
		for key, expected in cases:
			with self.subTest(key=key):
				self.assertEqual(hz.label_for(key), expected)

	def test_label_override(self):
		self.assertEqual(hz.label_for("amt", {"amt": "Order amount"}), "Order amount")

	def test_internal_keys(self):
		for key in ("_trigger", "docstatus", "owner", "api_key", "password", "access_token", "Authorization"):
			with self.subTest(key=key):
				self.assertTrue(hz.is_internal_key(key))
		for key in ("customer", "total", "status"):
			self.assertFalse(hz.is_internal_key(key))


class TestScalars(unittest.TestCase):
	def test_format_scalar(self):
		cases = [
			(None, None),
			(True, "Yes"),
			(False, "No"),
			(450, "450"),
			(450.0, "450"),
			(12.5, "12.5"),
			(1.005, "1"),  # two decimals at most
			("", None),
			("  Ada   Lovelace ", "Ada Lovelace"),
			("<p>Hello <b>there</b></p>", "Hello there"),
			("2026-10-29", "29 Oct 2026"),
			("2026-10-29T10:42:00Z", "29 Oct 2026, 10:42 UTC"),
			("2026-10-29 10:42:00", "29 Oct 2026, 10:42"),
			("2026-10-29T00:00:00", "29 Oct 2026"),
			("2026-10-29T10:42:00+05:30", "29 Oct 2026, 10:42 (+05:30)"),
			("2026-13-45", "2026-13-45"),  # not a real date: left alone
			("x" * 300, "x" * 119 + "…"),
		]
		for value, expected in cases:
			with self.subTest(value=value):
				self.assertEqual(hz.format_scalar(value), expected)


class TestSummaries(unittest.TestCase):
	def test_summarize(self):
		cases = [
			({"name": "Ada Lovelace", "email": "a@x.com"}, "Ada Lovelace"),
			({"total": 450, "status": "paid", "owner": "x", "note": None}, "Total: 450, Status: paid"),
			({"a": 1, "b": 2, "c": 3, "d": 4}, "A: 1, B: 2, C: 3"),
			([], None),
			([None, ""], None),
			(["A"], "1 item: A"),
			(["A", "B"], "2 items: A and B"),
			(["A", "B", "C"], "3 items: A, B and 1 more"),
			([{"name": "Widget"}, {"name": "Gadget"}, {"name": "Gizmo"}, {"name": "Doohickey"}], "4 items: Widget, Gadget and 2 more"),
			([{"sku": 1}, {"sku": 2}], "2 items"),
			({"customer": {"name": "Ada"}}, "Customer: Ada"),
			(True, "Yes"),
		]
		for value, expected in cases:
			with self.subTest(value=value):
				self.assertEqual(hz.summarize(value), expected)

	def test_humanize_value_object_is_label_value_lines(self):
		value = {"customer_name": "Ada", "created_at": "2026-10-29T10:42:00Z", "paid": True, "note": None, "_x": 1, "lines": [1, 2]}
		self.assertEqual(
			hz.humanize_value(value),
			"Customer name: Ada\nCreated at: 29 Oct 2026, 10:42 UTC\nPaid: Yes\nLines: 2 items: 1 and 2",
		)

	def test_never_json_or_python_syntax(self):
		text = hz.humanize_value({"a": {"b": [1, {"c": None}], "d": "x"}, "e": [{"f": 1}]})
		for junk in ("{", "}", "[", "]", '"', "None", "null", "true"):
			self.assertNotIn(junk, text)


class TestKeyFacts(unittest.TestCase):
	NESTED = {
		"order": {"id": 1042, "customer": {"name": "Ada Lovelace", "email": "ada@x.com"}, "total": 450, "status": "pending"},
		"items": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
		"_trigger": {"x": 1},
		"api_token": "sk-123",
		"note": None,
		"doctype": "Order",
	}

	def test_nested_payload_facts(self):
		facts = hz.key_facts(self.NESTED)
		self.assertEqual(
			facts,
			[
				{"label": "Customer", "value": "Ada Lovelace"},
				{"label": "Order ID", "value": "1042"},
				{"label": "Total", "value": "450"},
				{"label": "Status", "value": "pending"},
			],
		)

	def test_limit_and_secrets_and_internal(self):
		facts = hz.key_facts(self.NESTED, n=10)
		labels = [f["label"] for f in facts]
		self.assertNotIn("Api token", labels)
		self.assertNotIn("Doctype", labels)
		self.assertIn("Items", labels)
		self.assertLessEqual(len(hz.key_facts(self.NESTED, n=2)), 2)

	def test_not_a_mapping(self):
		for value in (None, "x", [1], 3):
			self.assertEqual(hz.key_facts(value), [])

	def test_id_with_parent_reads_as_order_id(self):
		self.assertEqual(hz.key_facts({"order": {"id": 7}}), [{"label": "Order ID", "value": "7"}])

	def test_duplicate_labels_dropped(self):
		facts = hz.key_facts({"order": {"id": 1}, "order_id": 2})
		self.assertEqual(facts, [{"label": "Order ID", "value": "1"}])


class TestApprovalWording(unittest.TestCase):
	def test_headline(self):
		self.assertEqual(hz.approval_headline("Refund review"), "Approval needed: Refund review")
		self.assertEqual(hz.approval_headline(""), "Approval needed")
		self.assertEqual(hz.approval_headline(None), "Approval needed")

	def test_sentence(self):
		facts = [{"label": "Customer", "value": "Ada Lovelace"}, {"label": "Total", "value": "450"}]
		cases = [
			(("Refund", "Approve", "Please check this refund", facts), "Please check this refund. Customer: Ada Lovelace, Total: 450."),
			(("Refund", "Approve", "Check it?", facts), "Check it? Customer: Ada Lovelace, Total: 450."),
			(("Refund", "Approve", "", facts), "Refund is waiting for your decision. Customer: Ada Lovelace, Total: 450."),
			((None, None, None, []), "A flow is waiting for your decision."),
			(("Refund", "Approve", "  Go   on ", None), "Go on."),
		]
		for args, expected in cases:
			with self.subTest(args=args):
				self.assertEqual(hz.approval_sentence(*args), expected)
		self.assertTrue(hz.approval_sentence("F", "S", "M", [], ask=True).endswith("Approve or reject."))
