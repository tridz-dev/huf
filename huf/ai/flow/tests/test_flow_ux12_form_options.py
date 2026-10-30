"""UX-12 form pickers: record types and fields for "Create document", and people for approvals."""

import types

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.catalog import form_options_api as api


def df(fieldname, fieldtype="Data", label=None, **kw):
	return types.SimpleNamespace(fieldname=fieldname, fieldtype=fieldtype, label=label, read_only=kw.get("read_only", 0), hidden=kw.get("hidden", 0), reqd=kw.get("reqd", 0), options=kw.get("options"))


class TestCreateDocumentOptions(IntegrationTestCase):
	def test_types_are_the_allow_list_the_person_may_create(self):
		conf = {"huf_flow_create_doc_doctypes": ["ToDo", "Note", "Customer"]}
		rows = api.create_document_types(conf, lambda dt: dt != "Customer")
		self.assertEqual([r["name"] for r in rows], ["Note", "ToDo"])
		self.assertEqual(rows[1]["label"], "To-do")

	def test_default_allow_list_is_todo(self):
		self.assertEqual([r["name"] for r in api.create_document_types({}, lambda dt: True)], ["ToDo"])

	def test_settable_fields_follow_the_step_rules(self):
		fields = api.settable_fields([
			df("section", "Section Break"), df("name", "Data"), df("owner", "Link"), df("status", "Select", "Status", options="Open\nClosed"),
			df("description", "Text Editor", "Description", reqd=1), df("done", "Check", "Done"), df("secret", "Data", read_only=1),
			df("hidden_one", "Data", hidden=1), df("when", "Date", "Due date"), df("file", "Attach"),
		])
		self.assertEqual([f["fieldname"] for f in fields], ["description", "status", "done", "when"])
		by = {f["fieldname"]: f for f in fields}
		self.assertTrue(by["description"]["required"])
		self.assertEqual(by["status"]["options"], ["Open", "Closed"])
		self.assertEqual(by["done"]["kind"], "yesno")

	def test_fields_of_a_type_that_is_not_allowed_are_refused(self):
		with self.assertRaises(frappe.PermissionError):
			api.get_create_document_fields("Customer")

	def test_todo_fields_exist(self):
		names = [f["fieldname"] for f in api.get_create_document_fields("ToDo")]
		self.assertIn("description", names)
		self.assertNotIn("owner", names)


class TestFlowUsers(IntegrationTestCase):
	def test_search_finds_a_real_person_and_never_guest(self):
		names = [u["name"] for u in api.search_flow_users("")]
		self.assertNotIn("Guest", names)
		found = api.search_flow_users("Administrator")
		self.assertTrue(any(u["name"] == "Administrator" for u in found))

	def test_a_typo_is_not_found(self):
		result = api.check_flow_users(["Administrator", "Administrtor", "nobody@example.com"])
		self.assertEqual([r["found"] for r in result], [True, False, False])

	def test_check_accepts_comma_text(self):
		self.assertEqual([r["name"] for r in api.check_flow_users("Administrator, ")], ["Administrator"])


class TestApproverCheckOnPublish(IntegrationTestCase):
	def _graph(self, users):
		return {
			"nodes": [
				{"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": "s" * 32}, "next": "ask"},
				{
					"id": "ask", "type": "human.approval", "_label": "Wait for approval",
					"config": {"message": "ok?", "approver_type": "user", "approver_users": users, "approve_next": "e1", "reject_next": "e2"},
				},
				{"id": "e1", "type": "output", "config": {"value": None}},
				{"id": "e2", "type": "output", "config": {"value": None}},
			],
		}

	def test_a_typo_is_listed_as_something_to_finish_with_a_plain_sentence(self):
		from huf.ai.graph.validation.flow_validation import _unknown_approver_issues

		issues = _unknown_approver_issues(self._graph(["Administrator", "Administrtor"])["nodes"][1])
		self.assertEqual(len(issues), 1)
		self.assertIn('no one here is called "Administrtor"', issues[0].message)
		self.assertNotIn("ask", issues[0].message.replace("Wait for approval", ""))  # no step id

	def test_real_people_and_roles_pass(self):
		from huf.ai.graph.validation.flow_validation import _unknown_approver_issues

		self.assertEqual(_unknown_approver_issues(self._graph(["Administrator"])["nodes"][1]), [])
		role = self._graph(["x"])["nodes"][1]
		role["config"].update(approver_type="role", approver_role="System Manager")
		self.assertEqual(_unknown_approver_issues(role), [])

	def test_running_a_flow_does_not_re_check_people(self):
		"""A test run of a draft may name anyone; only saving and publishing look people up."""
		from huf.ai.graph.validation.flow_validation import validate_flow

		defn = self._graph(["nobody.at.all@example.com"])
		with_people = validate_flow(defn, "publish")
		without = validate_flow(defn, "publish", check_people=False)
		self.assertTrue(any(i.code == "UNKNOWN_APPROVER" for i in with_people.issues))
		self.assertFalse(any(i.code == "UNKNOWN_APPROVER" for i in without.issues))
