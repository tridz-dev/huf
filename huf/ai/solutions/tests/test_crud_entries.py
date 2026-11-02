import frappe

from huf.ai.solutions import crud
from huf.ai.solutions.tests._crud_helpers import CrudCase, err


class TestEntries(CrudCase):
	def setUp(self):
		super().setUp()
		self.sol = crud.create_solution(self.payload(mode="existing", existing_target={"type": "Agent", "name": self.agent}))["name"]

	def test_create_entry_returns_entrypoint(self):
		e = crud.save_entry_point(self.sol, {"gateway": self.gw, "match_type": "Ad or link tag", "match_values": ["x1"], "cap_per_day": 5})
		self.assertEqual((e["match_type"], e["match_values"], e["priority"], e["cap_per_day"]), ("Ad or link tag", ["x1"], 2, 5))
		self.assertEqual(e["agent"], self.agent)

	def test_update_entry_json_string(self):
		name = self.bindings(self.sol)[0].name
		e = crud.save_entry_point(self.sol, '{"name": "%s", "match_values": ["zz"], "allow_first_message": true}' % name)
		self.assertEqual(e["name"], name)
		self.assertEqual(e["match_values"], ["zz"])
		self.assertTrue(e["allow_first_message"])

	def test_cap_and_scope_errors(self):
		frappe.db.set_value("Gateway", self.gw, "agent_send_cap_per_day", 10)
		frappe.db.set_value("Gateway", self.gw, "agent_recipient_scope", "Current contact")
		bad = {"match_type": "Catch-all", "match_values": [], "cap_per_day": 99}
		self.assertEqual(err(crud.save_entry_point(self.sol, bad)), "cap_exceeds_ceiling")
		bad = {"match_type": "Catch-all", "match_values": [], "scope_override": "Allow list"}
		self.assertEqual(err(crud.save_entry_point(self.sol, bad)), "scope_loosening")
		self.assertEqual(len(self.bindings(self.sol)), 1)

	def test_invalid_entries(self):
		self.assertEqual(err(crud.save_entry_point(self.sol, {"match_type": "Keyword", "match_values": []})), "invalid_payload")
		self.assertEqual(err(crud.save_entry_point(self.sol, {"match_type": "Sender"})), "invalid_payload")
		self.assertEqual(err(crud.save_entry_point(self.sol, {"name": "nope", "match_type": "Catch-all"})), "not_found")
		self.assertEqual(err(crud.save_entry_point("nope", {"match_type": "Catch-all"})), "not_found")

	def test_triage_entry(self):
		e = crud.save_entry_point(self.sol, {"match_type": "Triage", "match_values": []})
		self.assertEqual((e["target_type"], e["priority"]), ("Triage", 9))

	def test_team_solution_forces_allow_list(self):
		frappe.db.set_value("Gateway", self.gw, "agent_recipient_scope", "Any number")
		t = crud.create_solution(self.payload(purpose="team", entries=[]))["name"]
		e = crud.save_entry_point(t, {"gateway": self.gw, "match_type": "Catch-all"})
		self.assertEqual(e["scope_override"], "Allow list")

	def test_delete_entry(self):
		extra = crud.save_entry_point(self.sol, {"match_type": "Catch-all"})
		self.assertEqual(crud.delete_entry_point(extra["name"]), {"deleted": extra["name"]})
		self.assertEqual(err(crud.delete_entry_point("nope")), "not_found")

	def test_cannot_delete_last_entry_of_live_solution(self):
		crud.go_live(self.sol)
		last = self.bindings(self.sol)[0].name
		self.assertEqual(err(crud.delete_entry_point(last)), "invalid_payload")
		self.assertTrue(frappe.db.exists("Gateway Binding", last))
		crud.pause_solution(self.sol)
		self.assertEqual(crud.delete_entry_point(last), {"deleted": last})


class TestBindingValidate(CrudCase):
	def _binding(self, **kw):
		return frappe.get_doc({"doctype": "Gateway Binding", "gateway": self.gw, "priority": 5, "match_type": "Catch-all",
			"target_type": "Agent", **kw})

	def test_paused_solution_binding_may_lack_target(self):
		sol = crud.create_solution(self.payload(entries=[]))["name"]
		self._binding(solution=sol).insert(ignore_permissions=True)

	def test_live_solution_binding_needs_target(self):
		sol = crud.create_solution(self.payload(mode="existing", existing_target={"type": "Agent", "name": self.agent}))["name"]
		crud.go_live(sol)
		with self.assertRaises(frappe.ValidationError):
			self._binding(solution=sol).insert(ignore_permissions=True)

	def test_binding_without_solution_needs_target(self):
		with self.assertRaises(frappe.ValidationError):
			self._binding().insert(ignore_permissions=True)
