"""Shared base for the crud tests (real DB, rolled back per test)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.solutions import crud
from huf.ai.solutions.tests._fixtures import make_agent, make_gateway, uid

ACCT = "acct-crud"


def make_flow():
	doc = frappe.get_doc({"doctype": "Flow Definition", "flow_id": f"fl-{uid()}", "flow_name": f"Flow {uid()}"})
	doc.flags.ignore_validate = True
	return doc.insert(ignore_permissions=True, ignore_mandatory=True).name


def err(res):
	"""Return the error code of a contract-shaped error, asserting the shape."""
	assert set(res) == {"error"} and set(res["error"]) == {"code", "message"}, res
	return res["error"]["code"]


class CrudCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.gw = make_gateway().name
		self.agent = make_agent()
		p = patch.object(crud, "_account", return_value=ACCT)
		p.start()
		self.addCleanup(p.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def payload(self, **kw):
		base = {"title": f"Sol {uid()}", "purpose": "orders", "mode": "intent", "gateway": self.gw,
			"entries": [{"match_type": "Keyword", "match_values": ["order", "menu"]}],
			"inbound": True, "templates": [], "test_mode": False}
		base.update(kw)
		return base

	def bindings(self, solution):
		return frappe.get_all("Gateway Binding", filters={"solution": solution},
			fields=["*"], order_by="priority asc")
