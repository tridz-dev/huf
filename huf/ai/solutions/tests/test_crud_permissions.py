import frappe

from huf.ai.solutions import crud
from huf.ai.solutions.tests._crud_helpers import CrudCase, err


class TestCrudPermissions(CrudCase):
	def setUp(self):
		super().setUp()
		self.sol = crud.create_solution(self.payload(mode="existing", existing_target={"type": "Agent", "name": self.agent}))["name"]
		self.entry = self.bindings(self.sol)[0].name
		email = "crud-nobody@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Nobody", "send_welcome_email": 0, "roles": []}).insert(ignore_permissions=True)
		self.email = email

	def test_non_admin_refused_everywhere(self):
		frappe.set_user(self.email)
		calls = [
			lambda: crud.create_solution(self.payload(title="Nope")),
			lambda: crud.update_solution(self.sol, {"title": "x"}),
			lambda: crud.pause_solution(self.sol),
			lambda: crud.resume_solution(self.sol),
			lambda: crud.go_live(self.sol),
			lambda: crud.save_entry_point(self.sol, {"match_type": "Catch-all"}),
			lambda: crud.delete_entry_point(self.entry),
		]
		for call in calls:
			self.assertEqual(err(call()), "not_permitted")
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("Solution", {"title": "Nope"}))
		self.assertTrue(frappe.db.exists("Gateway Binding", self.entry))

	def test_error_shape(self):
		res = crud.update_solution("nope", {})
		self.assertEqual(res, {"error": {"code": "not_found", "message": "Solution not found."}})
		res = crud.create_solution({"title": ""})
		self.assertEqual(set(res["error"]), {"code", "message"})
