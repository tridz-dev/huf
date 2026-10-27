"""R2: list_message_log / list_message_log_filters carry the solution (derived, never stored on WhatsApp Message)."""

from unittest.mock import patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_solution, uid
from huf.ai.solutions.tests.test_stamping import make_run
from huf.ai.whatsapp import management as mgmt
from huf.ai.whatsapp.tests import test_whatsapp_message_log as L


class _Mixin:
	def mk_solutions(self):
		self.a = make_solution(title=f"Alpha {uid()}")
		self.b = make_solution(title=f"Beta {uid()}")

	def ref(self, sol):
		return {"name": sol.name, "title": sol.title}

	def tag(self, event, sol):
		frappe.db.set_value("Gateway Event", event.name, "solution", sol.name, update_modified=False)

	def by_id(self, result):
		return {i["message_id"]: i for i in result["items"]}


class TestDirectLogSolution(_Mixin, L._Base):
	"""Gateway-Event-only log: runs on a site without frappe_whatsapp."""

	def setUp(self):
		super().setUp()
		p = patch.object(bridge, "is_available", return_value=False)
		p.start()
		self.addCleanup(p.stop)
		self.gw = self.make_gateway("S")
		self.mk_solutions()

	def log(self, **kw):
		kw.setdefault("gateway_name", self.gw.name)
		return mgmt.list_message_log(**kw)

	def test_rows_carry_solution_inbound_and_outbound(self):
		e = self.make_event(self.gw, "wamid.S1", 0, agent="Agent X", reply="wamid.SR1", reply_status="sent")
		self.tag(e, self.a)
		self.make_event(self.gw, "wamid.S2", 5)
		rows = self.by_id(self.log())
		self.assertEqual(rows["wamid.S1"]["solution"], self.ref(self.a))
		self.assertEqual(rows["wamid.SR1"]["solution"], self.ref(self.a))
		self.assertIsNone(rows["wamid.S2"]["solution"])

	def test_outbound_falls_back_to_agent_run_solution(self):
		run = make_run(make_agent(), self.b.name)
		self.make_event(self.gw, "wamid.S3", 0, run=run, reply="wamid.SR3", reply_status="sent")
		rows = self.by_id(self.log())
		self.assertEqual(rows["wamid.SR3"]["solution"], self.ref(self.b))
		self.assertEqual(rows["wamid.S3"]["solution"], self.ref(self.b))

	def test_solution_filter(self):
		self.tag(self.make_event(self.gw, "wamid.F1", 0, reply="wamid.FR1", reply_status="sent"), self.a)
		self.tag(self.make_event(self.gw, "wamid.F2", 5), self.b)
		self.make_event(self.gw, "wamid.F3", 9)
		self.assertEqual(self.ids(self.log(solution=self.a.name)), ["wamid.FR1", "wamid.F1"])
		self.assertEqual(self.ids(self.log(solution=self.b.name)), ["wamid.F2"])
		self.assertEqual(self.ids(self.log(solution="nope-" + uid())), [])
		self.assertEqual(len(self.log()["items"]), 4)
		self.assertEqual(self.ids(self.log(solution=self.a.name, direction="out")), ["wamid.FR1"])

	def test_filter_with_paging(self):
		for i in range(5):
			self.tag(self.make_event(self.gw, f"wamid.P{i}", i), self.a)
		self.make_event(self.gw, "wamid.PX", 2)
		seen, cursor = [], None
		while True:
			page = self.log(solution=self.a.name, limit=2, cursor=cursor)
			seen += self.ids(page)
			if not page["has_more"]:
				break
			cursor = page["next_cursor"]
		self.assertEqual(sorted(seen), sorted(f"wamid.P{i}" for i in range(5)))

	def test_filters_payload_lists_solutions(self):
		self.tag(self.make_event(self.gw, "wamid.L1", 0), self.a)
		make_binding(self.gw.name, make_agent(), match_type="Keyword", match_value="k", solution=self.b.name)
		other_gw = self.make_gateway("T")
		unrelated = make_solution(title=f"Zed {uid()}")
		self.tag(self.make_event(other_gw, "wamid.L2", 0), unrelated)
		out = mgmt.list_message_log_filters(self.gw.name)
		self.assertTrue(out["success"])
		self.assertEqual({s["name"] for s in out["solutions"]}, {self.a.name, self.b.name})
		self.assertIn(self.ref(self.a), out["solutions"])
		self.assertIn("agents", out)

	def test_no_solution_leaves_default_payload_working(self):
		self.make_event(self.gw, "wamid.N1", 0)
		self.assertEqual(self.log()["items"][0]["solution"], None)
		self.assertEqual(mgmt.list_message_log_filters(self.gw.name)["solutions"], [])

	def test_permissions_unchanged(self):
		self.make_event(self.gw, "wamid.A1", 0)
		if not frappe.db.exists("User", L.PLAIN_USER):
			frappe.get_doc(
				{"doctype": "User", "email": L.PLAIN_USER, "first_name": "Plain", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(L.PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			self.log(solution=self.a.name)
		with self.assertRaises(frappe.PermissionError):
			mgmt.list_message_log_filters(self.gw.name)


class TestBridgeLogSolution(_Mixin, L._Base):
	"""WhatsApp Message based log; skipped without frappe_whatsapp."""

	make_account = L.TestBridgeModeMessageLog.make_account
	make_message = L.TestBridgeModeMessageLog.make_message

	def setUp(self):
		super().setUp()
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site")
		pa, pb = self.rand_phone(), self.rand_phone()
		self.acct_a = self.make_account("A", pa)
		self.acct_b = self.make_account("B", pb)
		self.gw = self.make_gateway("A", self.acct_a.name, phone=pa)
		self.mk_solutions()

	def log(self, **kw):
		kw.setdefault("gateway_name", self.gw.name)
		return mgmt.list_message_log(**kw)

	def send_key(self, wamid, sol, run=None):
		frappe.get_doc(
			{
				"doctype": "WhatsApp Send Key", "key_hash": uid() * 4, "gateway": self.gw.name, "status": "Sent",
				"message_id": wamid, "solution": sol.name, "agent_run": run or "",
				"claimed_at": frappe.utils.now_datetime(),
			}
		).insert(ignore_permissions=True)

	def test_solution_from_event_and_send_key(self):
		self.make_message(self.acct_a, "wamid.B1", 0)
		self.tag(self.make_event(self.gw, "wamid.B1", 0, reply="wamid.B2"), self.a)
		self.make_message(self.acct_a, "wamid.B2", 5, direction="Outgoing", status="sent")
		self.make_message(self.acct_a, "wamid.B3", 6, direction="Outgoing", status="sent", template="tpl")
		self.send_key("wamid.B3", self.b)
		self.make_message(self.acct_a, "wamid.B4", 7, direction="Outgoing", status="sent")
		rows = self.by_id(self.log())
		self.assertEqual(rows["wamid.B1"]["solution"], self.ref(self.a))
		self.assertEqual(rows["wamid.B2"]["solution"], self.ref(self.a))
		self.assertEqual(rows["wamid.B3"]["solution"], self.ref(self.b))
		self.assertIsNone(rows["wamid.B4"]["solution"])

	def test_bridge_solution_filter(self):
		self.make_message(self.acct_a, "wamid.C1", 0)
		self.tag(self.make_event(self.gw, "wamid.C1", 0), self.a)
		self.make_message(self.acct_a, "wamid.C3", 6, direction="Outgoing", status="sent")
		self.send_key("wamid.C3", self.b)
		self.make_message(self.acct_a, "wamid.C4", 7)
		self.assertEqual(self.ids(self.log(solution=self.a.name)), ["wamid.C1"])
		self.assertEqual(self.ids(self.log(solution=self.b.name)), ["wamid.C3"])
