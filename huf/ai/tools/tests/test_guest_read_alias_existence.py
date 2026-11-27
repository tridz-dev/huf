"""A Guest calling a read tool alias must not learn whether a record exists."""

import unittest

import frappe

from huf.ai.tools.invocation import invoke_tool_sync

MISSING = "huf-no-such-record"


class TestGuestReadAliasExistence(unittest.TestCase):
	def setUp(self):
		self.todo = self._todo("existence probe")
		self.report = frappe.get_all("Report", pluck="name", limit=1)[0]
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, frappe.session.user)

	def _todo(self, text):
		return frappe.get_doc({"doctype": "ToDo", "description": text}).insert(ignore_permissions=True).name

	def _call(self, alias, args):
		frappe.clear_messages()
		out = invoke_tool_sync(alias, args).as_dict()
		# Text only (each entry carries a random exception id); the alias row lookup is about the tool.
		texts = [m.get("message") for m in frappe.local.message_log]
		return out, [m for m in texts if not str(m).startswith("Agent Tool Function ")]

	def _probes(self, name):
		return {
			"get_value by name": ("get_value", {"doctype": "ToDo", "filters": name, "fieldname": "status"}),
			"get_value by filters": (
				"get_value",
				{"doctype": "ToDo", "filters": {"name": name}, "fieldname": "status"},
			),
			"get_document by id": ("get_document", {"reference_doctype": "ToDo", "document_id": name}),
			"get_documents": ("get_documents", {"reference_doctype": "ToDo", "document_ids": [name]}),
			"get_list": ("get_list", {"reference_doctype": "ToDo", "filters": {"name": name}}),
		}

	def _assert_indistinguishable(self, label, alias, existing_args, missing_args):
		existing, existing_log = self._call(alias, existing_args)
		missing, missing_log = self._call(alias, missing_args)
		# get_value echoes nothing about the record; the whole answer must match.
		self.assertEqual(existing, missing, label)
		self.assertEqual(existing_log, missing_log, label)
		self.assertFalse(existing.get("result", {}).get("success", False), label)
		self.assertNotIn(self.todo, str(existing) + str(existing_log), label)

	def _assert_todo_probes(self):
		missing = self._probes(MISSING)
		for label, (alias, args) in self._probes(self.todo).items():
			with self.subTest(label):
				self._assert_indistinguishable(label, alias, args, missing[label][1])

	def test_guest_without_doctype_permission(self):
		frappe.set_user("Guest")
		self._assert_todo_probes()
		with self.subTest("get_document by filters"):
			self._assert_indistinguishable(
				"get_document by filters",
				"get_document",
				{"reference_doctype": "ToDo", "description": "existence probe"},
				{"reference_doctype": "ToDo", "description": MISSING},
			)

	def test_guest_with_a_share_on_another_record(self):
		"""Doctype-level read passes, so the record-level denial must also hide existence."""
		frappe.share.add_docshare("ToDo", self._todo("shared"), "Guest", read=1, flags={"ignore_share_permission": True})
		frappe.set_user("Guest")
		# get_list legitimately returns only shared rows, so both probes are empty successes.
		missing = self._probes(MISSING)
		for label, (alias, args) in self._probes(self.todo).items():
			with self.subTest(label):
				existing, existing_log = self._call(alias, args)
				other, other_log = self._call(alias, missing[label][1])
				self.assertEqual(existing.get("result", {}).get("result"), other.get("result", {}).get("result"))
				if alias != "get_list":
					self.assertEqual(existing, other)
					self.assertFalse(existing["result"]["success"])
				self.assertEqual(existing_log, other_log)

	def test_permitted_reads_still_work(self):
		shared = self._todo("shared")
		frappe.share.add_docshare("ToDo", shared, "Guest", read=1, flags={"ignore_share_permission": True})
		frappe.set_user("Guest")
		for label, (alias, args) in self._probes(shared).items():
			with self.subTest(label):
				out, _ = self._call(alias, args)
				self.assertTrue(out["result"]["success"], out)

	def test_guest_report_alias(self):
		frappe.set_user("Guest")
		self._assert_indistinguishable(
			"get_report_result",
			"get_report_result",
			{"report_name": self.report},
			{"report_name": MISSING},
		)
