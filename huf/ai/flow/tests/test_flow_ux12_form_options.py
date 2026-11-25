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
		limits = {"max_nodes": 20, "max_rows": 1000, "max_output_bytes": 100000, "max_parallel_calls": 1, "max_foreach_iterations": 10,
			"max_external_calls": 10, "max_writes": 5, "max_wall_time_ms": 60000, "fail_closed": True}
		return {
			"schema_version": "1.0.0", "profile": "flow", "fingerprint": "0" * 64, "entry": "t",
			"contract": {"input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"}, "limits": limits},
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


class TestUnknownFieldInUpdateDocument(IntegrationTestCase):
	def _node(self, values):
		return {"id": "u", "type": "doc.update", "config": {"doctype": "ToDo", "name": "x", "values": values}}

	def test_typo_is_named_with_the_document_type(self):
		from huf.ai.graph.validation.flow_validation import _unknown_field_issues

		issues = _unknown_field_issues(self._node({"description": "ok", "nope_field": "1"}))
		self.assertEqual([i.message for i in issues], ["nope_field is not a field of ToDo."])
		self.assertEqual(issues[0].field, "config.values")

	def test_real_fields_and_other_steps_pass(self):
		from huf.ai.graph.validation.flow_validation import _unknown_field_issues

		self.assertEqual(_unknown_field_issues(self._node({"description": "ok", "status": "Open"})), [])
		self.assertEqual(_unknown_field_issues({"id": "g", "type": "doc.get", "config": {"doctype": "ToDo", "values": {"zz": 1}}}), [])


class TestRunAnotherFlowChecks(IntegrationTestCase):
	def _node(self, target):
		return {"id": "c", "type": "flow.call", "config": {"flow_id": target, "input": {}, "mode": "wait"}}

	def test_self_call_is_refused(self):
		from huf.ai.graph.validation.flow_validation import _flow_call_issues

		issues = _flow_call_issues(self._node("me"), "me")
		self.assertEqual([i.message for i in issues], ["A flow cannot run itself."])

	def test_unpublished_target_names_the_flow(self):
		from huf.ai.graph.validation.flow_validation import _flow_call_issues

		name = frappe.db.get_value("Flow Definition", {"status": ["!=", "Active"]}, "name")
		if not name:
			self.skipTest("no unpublished flow on this site")
		label = frappe.db.get_value("Flow Definition", name, "flow_name")
		issues = _flow_call_issues(self._node(name), "other")
		self.assertEqual([i.message for i in issues], [f"Publish {label} before running it from here."])

	def test_published_or_missing_target_passes(self):
		from huf.ai.graph.validation.flow_validation import _flow_call_issues

		self.assertEqual(_flow_call_issues(self._node("does-not-exist"), "other"), [])


class TestLoopBodyChecks(IntegrationTestCase):
	def test_wait_and_retry_inside_a_loop_are_refused_with_spec_words(self):
		from huf.ai.graph.validation.flow_validation import _loop_body_issues

		nodes = [
			{"id": "l", "type": "foreach", "config": {"body": ["w", "t"]}},
			{"id": "w", "type": "wait", "config": {}},
			{"id": "t", "type": "tool.call", "config": {"retry": {"attempts": 3, "backoff": "fixed", "delay_seconds": 60}}},
			{"id": "o", "type": "wait", "config": {}},
		]
		issues = _loop_body_issues(nodes)
		self.assertEqual(
			[(i.node_id, i.message) for i in issues],
			[
				("w", "A Wait step cannot be inside Repeat for each item. Move it outside the loop."),
				("t", "Trying again is not available inside Repeat for each item."),
			],
		)

class TestRunIdentityResumeAt(IntegrationTestCase):
	def test_resume_at_only_for_a_timed_wait(self):
		import json
		from unittest import mock

		from huf.ai.flow import run_identity_api as ri

		timed = json.dumps({"type": "timer", "mode": "timed", "resume_at": "2026-11-27T11:30:00"})
		for raw, want in ((timed, "2026-11-27T11:30:00"), (json.dumps({"type": "timer", "mode": "resume"}), None), (None, None), ("not json", None)):
			with mock.patch.object(ri.frappe.db, "get_value", return_value=raw):
				self.assertEqual(ri._resume_at("x"), want)
