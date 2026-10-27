import frappe

from huf.ai.solutions import crud
from huf.ai.solutions.tests._crud_helpers import CrudCase, err, make_flow
from huf.ai.solutions.tests._fixtures import make_agent


class TestUpdateAndLifecycle(CrudCase):
	def make(self, **kw):
		return crud.create_solution(self.payload(**kw))["name"]

	def test_update_fields_and_json(self):
		n = self.make()
		res = crud.update_solution(n, '{"title": "Renamed", "description": "d", "purpose": "support"}')
		self.assertEqual((res["title"], res["purpose"]), ("Renamed", "support"))

	def test_update_rejects_unknown_and_bad(self):
		n = self.make()
		self.assertEqual(err(crud.update_solution(n, {"status": "Live"})), "invalid_payload")
		self.assertEqual(err(crud.update_solution(n, {"purpose": "zz"})), "invalid_payload")
		self.assertEqual(err(crud.update_solution("nope", {"title": "x"})), "not_found")
		self.assertEqual(err(crud.update_solution(n, {"primary_target_type": "Agent", "primary_agent": "nope-agent"})), "not_found")

	def test_cascade_target_change_skips_triage(self):
		n = self.make(entries=[{"match_type": "Keyword", "match_values": ["a"]}, {"match_type": "Triage", "match_values": []}])
		crud.update_solution(n, {"primary_target_type": "Agent", "primary_agent": self.agent})
		by = {b.target_type: b for b in self.bindings(n)}
		self.assertEqual(by["Agent"].agent, self.agent)
		self.assertIsNone(by["Triage"].agent)
		flow = make_flow()
		crud.update_solution(n, {"primary_target_type": "Flow", "primary_flow": flow})
		by = {b.target_type: b for b in self.bindings(n)}
		self.assertEqual((by["Flow"].flow, by["Flow"].agent), (flow, None))
		self.assertEqual(set(by), {"Flow", "Triage"})

	def test_pause_resume(self):
		n = self.make(mode="existing", existing_target={"type": "Agent", "name": self.agent})
		self.assertEqual(crud.resume_solution(n)["status"], "Live")
		self.assertEqual(crud.pause_solution(n)["status"], "Paused")

	def test_resume_refusals(self):
		n = self.make()
		self.assertEqual(err(crud.resume_solution(n)), "no_target")
		m = self.make(mode="existing", existing_target={"type": "Agent", "name": self.agent}, test_mode=True)
		self.assertEqual(err(crud.resume_solution(m)), "invalid_payload")

	def test_go_live_no_target_stays_paused(self):
		n = self.make()
		self.assertEqual(err(crud.go_live(n)), "no_target")
		self.assertEqual(frappe.db.get_value("Solution", n, "status"), "Paused")

	def test_go_live_clears_test_mode(self):
		n = self.make(mode="existing", existing_target={"type": "Agent", "name": self.agent}, test_mode=True)
		res = crud.go_live(n)
		self.assertEqual((res["status"], res["test_mode"]), ("Live", False))

	def test_go_live_needs_entry_unless_updates(self):
		n = self.make(inbound=False, mode="existing", existing_target={"type": "Agent", "name": self.agent})
		self.assertEqual(err(crud.go_live(n)), "invalid_payload")
		u = self.make(purpose="updates", inbound=False, mode="existing", existing_target={"type": "Agent", "name": self.agent})
		self.assertEqual(crud.go_live(u)["status"], "Live")

	def test_go_live_after_late_target_cascades(self):
		n = self.make()
		crud.update_solution(n, {"primary_target_type": "Agent", "primary_agent": make_agent()})
		self.assertEqual(crud.go_live(n)["status"], "Live")

	def test_live_cannot_clear_target(self):
		n = self.make(mode="existing", existing_target={"type": "Agent", "name": self.agent})
		crud.go_live(n)
		self.assertEqual(err(crud.update_solution(n, {"primary_target_type": None})), "no_target")
