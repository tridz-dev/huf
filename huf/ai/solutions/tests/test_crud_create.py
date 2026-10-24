import json
from unittest.mock import patch

import frappe

from huf.ai.solutions import crud, template_usage as tu
from huf.ai.solutions.tests._crud_helpers import ACCT, CrudCase, err, make_flow


class TestCreateSolution(CrudCase):
	def test_intent_creates_paused_solution_and_keyword_entry(self):
		res = crud.create_solution(self.payload())
		self.assertEqual(res["status"], "Paused")
		self.assertEqual(res["purpose"], "orders")
		self.assertIsNone(res["primary"])
		b = self.bindings(res["name"])
		self.assertEqual(len(b), 1)
		self.assertEqual((b[0].priority, b[0].match_type, b[0].match_value), (1, "Keyword", "order, menu"))
		self.assertEqual(b[0].gateway, self.gw)

	def test_json_string_payload(self):
		res = crud.create_solution(json.dumps(self.payload()))
		self.assertEqual(res["status"], "Paused")

	def test_existing_agent_copies_target_to_entries(self):
		res = crud.create_solution(self.payload(mode="existing", existing_target={"type": "Agent", "name": self.agent}))
		self.assertEqual(res["primary"]["type"], "Agent")
		b = self.bindings(res["name"])[0]
		self.assertEqual((b.target_type, b.agent), ("Agent", self.agent))

	def test_existing_flow(self):
		flow = make_flow()
		res = crud.create_solution(self.payload(mode="existing", existing_target={"type": "Flow", "name": flow}))
		b = self.bindings(res["name"])[0]
		self.assertEqual((b.target_type, b.flow), ("Flow", flow))

	def test_existing_missing_target(self):
		self.assertEqual(err(crud.create_solution(self.payload(mode="existing"))), "invalid_payload")
		bad = self.payload(mode="existing", existing_target={"type": "Agent", "name": "nope-x"})
		self.assertEqual(err(crud.create_solution(bad)), "not_found")

	def test_blank_is_custom(self):
		res = crud.create_solution(self.payload(mode="blank", purpose="orders"))
		self.assertEqual(res["purpose"], "custom")

	def test_bad_purpose_and_mode(self):
		self.assertEqual(err(crud.create_solution(self.payload(purpose="zzz"))), "invalid_payload")
		self.assertEqual(err(crud.create_solution(self.payload(mode="x"))), "invalid_payload")
		self.assertEqual(err(crud.create_solution("{not json")), "invalid_payload")

	def test_no_inbound_creates_no_entries(self):
		res = crud.create_solution(self.payload(inbound=False))
		self.assertEqual(self.bindings(res["name"]), [])

	def test_team_forces_allow_list(self):
		frappe.db.set_value("Gateway", self.gw, "agent_recipient_scope", "Any number")
		res = crud.create_solution(self.payload(purpose="team", entries=[{"match_type": "Catch-all", "match_values": []}]))
		self.assertEqual(self.bindings(res["name"])[0].scope_override, "Allow list")

	def test_triage_and_priorities(self):
		entries = [{"match_type": "Triage", "match_values": []}, {"match_type": "Catch-all", "match_values": []},
			{"match_type": "Ad or link tag", "match_values": ["spring"]}, {"match_type": "Keyword", "match_values": ["a"]}]
		res = crud.create_solution(self.payload(entries=entries, mode="existing", existing_target={"type": "Agent", "name": self.agent}))
		b = self.bindings(res["name"])
		self.assertEqual([x.priority for x in b], [1, 2, 8, 9])
		tri = b[-1]
		self.assertEqual((tri.target_type, tri.agent), ("Triage", None))

	def test_cap_validated_by_ceiling(self):
		frappe.db.set_value("Gateway", self.gw, "agent_send_cap_per_day", 100)
		ok = self.payload(entries=[{"match_type": "Keyword", "match_values": ["a"], "cap_per_day": 50}])
		self.assertEqual(self.bindings(crud.create_solution(ok)["name"])[0].cap_per_day, 50)
		bad = self.payload(entries=[{"match_type": "Keyword", "match_values": ["a"], "cap_per_day": 500}])
		self.assertEqual(err(crud.create_solution(bad)), "cap_exceeds_ceiling")

	def test_failure_creates_nothing(self):
		bad = self.payload(title="Atomic one", entries=[
			{"match_type": "Keyword", "match_values": ["a"]}, {"match_type": "Keyword", "match_values": []}])
		self.assertEqual(err(crud.create_solution(bad)), "invalid_payload")
		self.assertFalse(frappe.db.exists("Solution", {"title": "Atomic one"}))
		frappe.db.set_value("Gateway", self.gw, "agent_send_cap_per_day", 10)
		bad = self.payload(title="Atomic two", entries=[
			{"match_type": "Keyword", "match_values": ["a"]}, {"match_type": "Catch-all", "match_values": [], "cap_per_day": 99}])
		self.assertEqual(err(crud.create_solution(bad)), "cap_exceeds_ceiling")
		self.assertFalse(frappe.db.exists("Solution", {"title": "Atomic two"}))
		self.assertEqual(frappe.db.count("Gateway Binding", {"gateway": self.gw}), 0)

	def test_duplicate_title(self):
		p = self.payload(title="Dup title")
		crud.create_solution(p)
		self.assertEqual(err(crud.create_solution(p)), "invalid_payload")

	def test_test_mode_kept(self):
		res = crud.create_solution(self.payload(test_mode=True))
		self.assertTrue(res["test_mode"])
		self.assertEqual(res["status"], "Paused")

	def test_templates_declared_first_is_owner(self):
		a = crud.create_solution(self.payload(templates=["hello_tpl"]))
		b = crud.create_solution(self.payload(templates=["hello_tpl"]))
		u = tu.usage_for(ACCT, "hello_tpl", "")
		self.assertEqual(u["owner"]["solution"], a["name"])
		self.assertEqual(len(u["used_by"]), 2)
		self.assertTrue(u["shared"])
		self.assertTrue(b["name"])

	def test_draft_template_path(self):
		draft = {"name": "shop_quote", "language": "en", "category": "UTILITY", "status": "Draft"}
		with patch("huf.ai.whatsapp.management.create_template_draft", return_value={"success": True, "name": "d1"}) as m:
			res = crud.create_solution(self.payload(draft_template=draft))
		kwargs = m.call_args.kwargs
		self.assertEqual(kwargs["payload"]["template_name"], "shop_quote")
		self.assertEqual(kwargs["gateway_name"], self.gw)
		self.assertEqual(kwargs["submit_for_review"], 0)
		self.assertEqual(tu.usage_for(ACCT, "shop_quote", "en")["used_by"][0]["solution"], res["name"])

	def test_draft_failure_rolls_back(self):
		draft = {"name": "bad name", "language": "en", "category": "UTILITY", "status": "Draft"}
		with patch("huf.ai.whatsapp.management.create_template_draft", return_value={"success": False, "error": "invalid_name"}):
			res = crud.create_solution(self.payload(title="Draft fail", draft_template=draft))
		self.assertEqual(err(res), "invalid_payload")
		self.assertFalse(frappe.db.exists("Solution", {"title": "Draft fail"}))
