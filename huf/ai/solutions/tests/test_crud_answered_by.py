from huf.ai.solutions import crud
from huf.ai.solutions.tests._crud_helpers import CrudCase, err, make_flow


class TestAnsweredBy(CrudCase):
	def test_intent_with_target(self):
		res = crud.create_solution(self.payload(existing_target={"type": "Agent", "name": self.agent}))
		self.assertEqual(res["status"], "Paused")
		self.assertEqual(res["primary"]["type"], "Agent")
		b = self.bindings(res["name"])[0]
		self.assertEqual((b.target_type, b.agent), ("Agent", self.agent))
		self.assertEqual(crud.go_live(res["name"])["status"], "Live")

	def test_blank_with_flow_target(self):
		flow = make_flow()
		res = crud.create_solution(self.payload(mode="blank", existing_target={"type": "Flow", "name": flow}))
		self.assertEqual(res["primary"]["type"], "Flow")
		b = self.bindings(res["name"])[0]
		self.assertEqual((b.target_type, b.flow), ("Flow", flow))

	def test_no_target_stays_paused_and_cannot_go_live(self):
		for mode in ("intent", "blank"):
			res = crud.create_solution(self.payload(mode=mode))
			self.assertEqual(res["status"], "Paused")
			self.assertIsNone(res["primary"])
			self.assertEqual(err(crud.go_live(res["name"])), "no_target")

	def test_invalid_target(self):
		self.assertEqual(err(crud.create_solution(self.payload(existing_target="agent-x"))), "invalid_payload")
		self.assertEqual(err(crud.create_solution(self.payload(existing_target={"type": "Bogus", "name": "x"}))), "invalid_payload")
		self.assertEqual(err(crud.create_solution(self.payload(mode="blank", existing_target={"type": "Agent", "name": "nope-x"}))), "not_found")
