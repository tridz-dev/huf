from unittest.mock import patch

import frappe

from huf.ai.solutions import read_models as rm
from huf.ai.solutions.tests._fixtures import make_binding, make_gateway, make_solution, uid
from huf.ai.solutions.tests.test_read_models import ReadModelCase, make_event

USER = "b2-plain-user@example.com"


def _ensure_user():
	if not frappe.db.exists("User", USER):
		frappe.get_doc({
			"doctype": "User", "email": USER, "first_name": "Plain", "send_welcome_email": 0, "enabled": 1,
		}).insert(ignore_permissions=True)


class TestReadModelPermissions(ReadModelCase):
	def test_plain_user_is_not_permitted_everywhere(self):
		_ensure_user()
		frappe.set_user(USER)
		calls = [
			lambda: rm.list_solutions(),
			lambda: rm.get_solution_overview(self.orders),
			lambda: rm.list_entry_points(self.orders),
			lambda: rm.get_number_summary(self.gw),
			lambda: rm.list_solution_conversations(None),
			lambda: rm.list_solution_conversations(self.orders),
			lambda: rm.get_intents(),
			lambda: rm.simulate_route({"gateway": self.gw, "text": "order", "state": {}}),
		]
		for call in calls:
			out = call()
			self.assertEqual(out["error"]["code"], "not_permitted")

	def _only(self, allowed):
		return patch.object(rm, "_gateway_read_allowed", side_effect=lambda g: g in allowed)

	def test_other_gateways_are_never_returned(self):
		gw2 = make_gateway().name
		secret = make_solution(title=f"Secret {uid()}").name
		make_binding(gw2, self.agent, match_type="Catch-all", solution=secret)
		make_event(gw2, "hidden-chat", "private", secret)
		make_event(self.gw, "visible-chat", "ok", self.orders)
		self.cached.append(gw2)
		with self._only({self.gw}):
			names = {r["name"] for r in rm.list_solutions()}
			self.assertIn(self.orders, names)
			self.assertNotIn(secret, names)
			self.assertEqual(rm.get_solution_overview(secret)["error"]["code"], "not_permitted")
			self.assertEqual(rm.list_entry_points(secret), [])
			self.assertEqual(rm.get_number_summary(gw2)["error"]["code"], "not_permitted")
			self.assertEqual(
				rm.simulate_route({"gateway": gw2, "text": "x", "state": {}})["error"]["code"], "not_permitted"
			)
			self.assertEqual({r["contact"] for r in rm.list_solution_conversations(None)}, {"visible-chat"})
			self.assertEqual(rm.list_solution_conversations(secret), [])

	def test_solution_on_two_gateways_hides_the_unreadable_one(self):
		gw2 = make_gateway().name
		make_binding(gw2, self.agent, match_type="Keyword", match_value="zzz", solution=self.orders)
		with self._only({self.gw}):
			row = next(r for r in rm.list_solutions() if r["name"] == self.orders)
			self.assertEqual([r["gateway"] for r in row["runs_on"]], [self.gw])
			self.assertEqual(row["entry_count"], 1)
			self.assertEqual({e["gateway"] for e in rm.list_entry_points(self.orders)}, {self.gw})

	def test_no_readable_gateway_means_empty(self):
		with self._only(set()):
			self.assertEqual(rm.list_solutions(), [])
			self.assertEqual(rm.list_solution_conversations(None), [])
