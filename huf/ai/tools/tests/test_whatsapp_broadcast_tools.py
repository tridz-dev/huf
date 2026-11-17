"""Generic WhatsApp audience/broadcast agent tools: flags, consent rule, user-bound permissions, and the
park -> approve -> execute path. Run: bench run-tests --module huf.ai.tools.tests.test_whatsapp_broadcast_tools"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import tool_confirmation as tc
from huf.ai.gateways import tool_policy
from huf.ai.tools import whatsapp_broadcast_tools as wbt
from huf.ai.tools.confirmation_summaries import whatsapp_broadcast_start as summarize
from huf.ai.tools.registry import sync_discovered_tools
from huf.huf.doctype.agent_tool_function.agent_tool_function import OTP_TOOL_DENYLIST
from huf.ai.whatsapp.broadcast import api as bapi
from huf.ai.whatsapp.broadcast import schedule as bsched

BC = "BCAST-TOOLS-1"
NAMES = {t["tool_name"]: t for t in wbt.WHATSAPP_BROADCAST_TOOLS}
ROW = {"name": BC, "gateway": "GW", "status": "Draft", "title": "Promo", "template": "promo-en",
	"template_name": "promo", "consent_attested": 1, "consent_attested_by": "owner@example.com"}


def _run(fn, **kw):
	return json.loads(fn(**kw))


class TestDeclarations(IntegrationTestCase):
	def test_tool_set_and_flags(self):
		self.assertEqual(set(NAMES), {
			"whatsapp_list_templates", "whatsapp_audience_upsert", "whatsapp_broadcast_create",
			"whatsapp_broadcast_start", "whatsapp_broadcast_status", "whatsapp_broadcast_retry_failed"})
		for name, t in NAMES.items():
			self.assertEqual(bool(t.get("is_outbound")), name == "whatsapp_broadcast_start", name)
			self.assertIn("System Manager", t["required_roles"])
			self.assertIn(wbt.ROLE, t["required_roles"])
			self.assertTrue(frappe.get_attr(t["function_path"]))
		self.assertTrue(NAMES["whatsapp_broadcast_start"]["confirmation_summary_path"])

	def test_no_otp_tool(self):
		for t in NAMES.values():
			self.assertNotIn(t["function_path"], OTP_TOOL_DENYLIST)
			self.assertNotIn("otp", t["tool_name"])

	def test_no_ignore_permissions(self):
		import inspect
		self.assertNotIn("ignore_permissions=True", inspect.getsource(wbt))
		self.assertNotIn("upsert_audience_members", inspect.getsource(wbt).split("def _out")[1])

	def test_synced_with_flags_and_role(self):
		sync_discovered_tools(use_cache=False)
		row = frappe.db.get_value("Agent Tool Function", {"tool_name": "whatsapp_broadcast_start"},
			["is_outbound", "required_roles", "confirmation_summary_path"], as_dict=True)
		self.assertEqual(row.is_outbound, 1)
		self.assertIn(wbt.ROLE, row.required_roles)
		self.assertTrue(frappe.db.exists("Role", wbt.ROLE))


class TestStartRules(IntegrationTestCase):
	def _start(self, row=None, **kw):
		with patch.object(bapi, "_require_broadcast_write", return_value={**ROW, **(row or {})}), \
			patch.object(bapi, "_queued_count", return_value=5), \
			patch.object(bapi, "start_broadcast", return_value={"success": True, "queued": 5}) as st, \
			patch.object(bsched, "schedule_broadcast", return_value={"success": True, "status": "Scheduled"}) as sc:
			out = _run(wbt.handle_broadcast_start, broadcast=BC, **kw)
		return out, st, sc

	def test_refuses_without_human_attestation(self):
		for row in ({"consent_attested": 0}, {"consent_attested_by": None}):
			out, st, sc = self._start(row, expected_recipient_count=5)
			self.assertEqual(out["error"], "consent_not_attested")
			self.assertIn("HUF broadcast screen", out["next_step"])
			st.assert_not_called()
			sc.assert_not_called()

	def test_count_must_match(self):
		out, st, _ = self._start(expected_recipient_count=4)
		self.assertEqual(out["error"], "recipient_count_changed")
		st.assert_not_called()
		out, st, _ = self._start()
		self.assertEqual(out["error"], "expected_recipient_count_required")

	def test_start_and_schedule(self):
		out, st, sc = self._start(expected_recipient_count=5)
		self.assertTrue(out["success"])
		st.assert_called_once()
		sc.assert_not_called()
		out, st, sc = self._start(expected_recipient_count=5, scheduled_at="2099-01-01 10:00:00")
		sc.assert_called_once()
		st.assert_not_called()

	def test_permission_error_is_refusal(self):
		with patch.object(bapi, "_require_broadcast_write", side_effect=frappe.PermissionError):
			out = _run(wbt.handle_broadcast_start, broadcast=BC, expected_recipient_count=1)
		self.assertEqual(out["error"], "permission_denied")

	def test_summary_resolves_or_refuses(self):
		with patch.object(bapi, "_require_broadcast_read", return_value=ROW), patch.object(bapi, "_queued_count", return_value=7):
			s = summarize({"broadcast": BC})
		self.assertEqual((s["recipient_count"], s["template"], s["channel"]), (7, "promo", "whatsapp"))
		self.assertIn("attested", s["sample"])
		with patch.object(bapi, "_require_broadcast_read", return_value={"error": "not_found"}):
			self.assertIsNone(summarize({"broadcast": "nope"})["recipient_count"])
		with patch.object(bapi, "_require_broadcast_read", side_effect=frappe.PermissionError):
			self.assertIsNone(summarize({"broadcast": BC})["recipient_count"])


class TestOtherTools(IntegrationTestCase):
	def test_audience_upsert_never_attests(self):
		from huf.ai.whatsapp.broadcast.audiences import api as aapi
		with patch.object(aapi, "create_audience", return_value={"success": False, "error": "consent_not_attested", "message": "x"}) as ca:
			out = _run(wbt.handle_audience_upsert, gateway="GW", title="T", members=[{"recipient": "+15551230000"}])
		self.assertEqual(ca.call_args.kwargs["consent_attested"], 0)
		self.assertEqual(out["error"], "consent_not_attested")
		self.assertIn("next_step", out)

	def test_audience_upsert_imports_mapped_rows(self):
		from huf.ai.whatsapp.broadcast.audiences import api as aapi
		with patch.object(aapi, "import_members", return_value={"success": True, "added": 1, "queued": False}) as im:
			out = _run(wbt.handle_audience_upsert, audience="AUD-1", mode="merge", members=json.dumps(
				[{"recipient": "+15551230000", "display_name": "A", "params": ["x", "y"], "consent_source": "form", "consent_at": "2026-01-01"}]))
		self.assertTrue(out["success"])
		kw = im.call_args.kwargs
		self.assertEqual(kw["mapping"]["params"], ["p1", "p2"])
		self.assertEqual(kw["rows"][0]["p2"], "y")

	def test_retry_failed_is_draft_only(self):
		with patch.object(bsched, "retry_failed_recipients", return_value={"success": True, "broadcast": "B2", "added": 2}):
			out = _run(wbt.handle_broadcast_retry_failed, broadcast=BC)
		self.assertIn("Nothing was sent", out["next_step"])

	def test_create_requires_audience(self):
		self.assertEqual(_run(wbt.handle_broadcast_create, audience="nope", template="t", title="x")["error"], "not_found")


class TestParkApproveExecute(IntegrationTestCase):
	"""Agent run parks whatsapp_broadcast_start; the owner approves; the background job executes it."""

	def setUp(self):
		frappe.set_user("Administrator")
		sync_discovered_tools(use_cache=False)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_e2e(self):
		args = {"broadcast": BC, "expected_recipient_count": 5}
		with patch.object(bapi, "_require_broadcast_read", return_value=ROW), patch.object(bapi, "_queued_count", return_value=5):
			parked = json.loads(tool_policy.check_tool_call("whatsapp_broadcast_start", dict(args), None, True,
				conversation_id=None, agent_name=None, tool_call_id="call_wbt_1"))
		self.assertEqual(parked["type"], "confirmation_request")
		self.assertEqual(parked["summary"]["recipient_count"], 5)
		self.assertEqual(parked["summary"]["template"], "promo")
		with patch.object(frappe, "enqueue") as enq:
			tc.decide(parked["id"], True)
		self.assertEqual(enq.call_args.args[0], "huf.ai.tool_confirmation.run_approved")
		with patch.object(bapi, "_require_broadcast_write", return_value=ROW), patch.object(bapi, "_queued_count", return_value=5), \
			patch.object(bapi, "start_broadcast", return_value={"success": True, "queued": 5}) as st:
			tc.run_approved(parked["id"], "Administrator")
		st.assert_called_once()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, parked["id"], "state"), "executed")

	def test_unresolvable_broadcast_is_not_parked(self):
		with patch.object(bapi, "_require_broadcast_read", return_value={"error": "not_found"}):
			out = json.loads(tool_policy.check_tool_call("whatsapp_broadcast_start", {"broadcast": "x", "expected_recipient_count": 1},
				None, True, conversation_id=None, agent_name=None, tool_call_id="call_wbt_2"))
		self.assertNotEqual(out.get("type"), "confirmation_request")
