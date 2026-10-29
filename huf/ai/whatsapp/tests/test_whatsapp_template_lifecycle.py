# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Template review state, edit rules and approval drafts, against the fake Graph server.

State and draft tests run on any site; edit, sync and submit tests need frappe_whatsapp and are
skipped without it. The fake server enforces Meta's edit rules itself, so a Huf bug that sends an
edit Meta would refuse shows up as a recorded violation.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe

from huf.ai.whatsapp import management as mgmt
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.testing import fake_graph_server as fake
from huf.ai.whatsapp.tests import test_whatsapp_fake_graph as fgc
from huf.ai.tools import whatsapp as wa_tool

STATE = "WhatsApp Template State"
DRAFT = "WhatsApp Template Draft"


def _payload(**overrides):
	payload = {
		"template_name": "lc_promo",
		"category": "UTILITY",
		"language_code": "en_US",
		"body": "Hi {{1}}, your order shipped",
		"sample_values": "Ann",
	}
	payload.update(overrides)
	return payload


class TestPureHelpers(unittest.TestCase):
	def test_derive_quality_handles_unknown_shapes(self):
		for raw, expected in (
			("GREEN", "GREEN"), ("high", "GREEN"), ("MEDIUM", "YELLOW"), ("LOW", "RED"), ("UNKNOWN", "UNKNOWN"),
			({"score": "YELLOW", "date": 1}, "YELLOW"), ({"quality": {"value": "RED"}}, "RED"),
			({"weird": 1}, "UNKNOWN"), (None, "UNKNOWN"), (5, "UNKNOWN"), ([], "UNKNOWN"),
		):
			self.assertEqual(bridge.derive_quality(raw), expected, raw)

	def test_edit_quota_rules(self):
		now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
		iso = lambda **kw: (now - timedelta(**kw)).isoformat()  # noqa: E731
		q = bridge.edit_quota("APPROVED", [], now)
		self.assertEqual((q["editable"], q["edits_left"]), (True, 10))
		q = bridge.edit_quota("APPROVED", [iso(hours=2)], now)
		self.assertEqual((q["editable"], q["editable_reason"], q["edits_left"]), (False, "edit_limit_24h", 9))
		self.assertTrue(q["next_edit_at"].startswith("2026-10-15T10"))
		q = bridge.edit_quota("APPROVED", [iso(hours=25)], now)
		self.assertEqual((q["editable"], q["edits_left"]), (True, 9))
		q = bridge.edit_quota("APPROVED", [iso(days=d) for d in range(2, 12)], now)
		self.assertEqual((q["editable"], q["editable_reason"], q["edits_left"]), (False, "edit_limit_30d", 0))
		# edits older than 30 days no longer count
		q = bridge.edit_quota("APPROVED", [iso(days=d) for d in range(31, 45)], now)
		self.assertEqual((q["editable"], q["edits_left"]), (True, 10))
		# REJECTED / PAUSED are unlimited whatever the log says
		for status in ("REJECTED", "PAUSED"):
			q = bridge.edit_quota(status, [iso(hours=1)] * 20, now)
			self.assertEqual((q["editable"], q["edits_left"]), (True, None))
		for status in ("PENDING", "DISABLED", "IN_APPEAL", "LIMIT_EXCEEDED", "PENDING_DELETION", "DELETED", ""):
			q = bridge.edit_quota(status, [], now)
			self.assertEqual((q["editable"], q["editable_reason"]), (False, "status_not_editable"), status)

	def test_manager_url_has_no_invented_params(self):
		self.assertEqual(
			bridge.manager_url("123"), "https://business.facebook.com/latest/whatsapp_manager/message_templates"
		)

	def test_record_state_never_raises(self):
		with patch.object(frappe, "get_doc", side_effect=RuntimeError("boom")):
			self.assertIsNone(bridge.record_template_state(name="x", language="en", status="APPROVED"))
		self.assertIsNone(bridge.record_template_state())  # nothing to identify the template
		self.assertIsNone(bridge.record_template_webhook({"unexpected": object()}))


class LifecycleCase(fgc.FakeGraphCase):
	def setUp(self):
		super().setUp()
		patcher = patch.object(frappe, "publish_realtime")
		self.realtime = patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(lambda: setattr(frappe.flags, "huf_current_agent_run_id", None))

	def _state(self, docname, account=None):
		"""State rows are keyed per account; sites without frappe_whatsapp use the unscoped bucket."""
		account = self.account.name if account is None and self.account else account
		return frappe.get_doc(STATE, bridge.state_key(account, docname))

	def _agent(self, action, **kwargs):
		"""Call the agent tool the way a run does: the run's gateway is bound server-side (never a tool argument)."""
		# these tool actions manage the gateway's bridge account: point the run's gateway at it (rolled back with the test)
		frappe.db.set_value("Gateway", self.direct_gateway.name, "whatsapp_account", self.account.name)
		with wa_tool.trusted_gateway(self.direct_gateway.name):
			return wa_tool.handle_action(action, **kwargs)

	def _acct(self):
		return {"account": self.account.name} if self.account else {}

	def _statuses(self):
		return [c.args[1] for c in self.realtime.call_args_list if c.args[0] == "whatsapp_template_status"]

	def _created(self, name="lc_edit", **overrides):
		"""A template created through Huf and approved on Meta (fw row + state APPROVED)."""
		self._need_bridge()
		made = self._make_template(
			template_name=name, body="Hi {{1}}, order shipped", sample_values="Ann",
			header_type=None, header=None, sample=None, footer=None, buttons=None, **overrides,
		)
		self.assertTrue(made["success"], made)
		self.server.approve(name)
		synced = mgmt.sync_templates(account=self.account.name)
		self.assertTrue(synced["success"], synced)
		docname = made["name"]
		self.assertEqual(self._state(docname).status, "APPROVED")
		return docname

	def _edit_posts(self):
		return [r for r in self.server.requests if r["method"] == "POST" and r["path"].rstrip("/").rsplit("/", 1)[-1].isdigit()]


class TestWebhookState(LifecycleCase):
	def _hook(self, payload):
		result = self._deliver_webhook(self.direct_gateway, payload)
		self.assertTrue(result["success"], result)

	def test_status_reason_quality_category_events_are_stored(self):
		srv = self.server
		tid = "900000000000777"
		self._hook(fake.template_status_webhook(
			srv.waba_id, tid, "lc_hook", "en_US", "REJECTED", reason="INVALID_FORMAT",
			rejection_info={"reason": "INVALID_FORMAT", "recommendation": "Remove the leading variable."},
			other_info={"title": "Review", "description": "Reviewed by Meta"},
		))
		st = self._state("lc_hook-en_US")
		self.assertEqual((st.status, st.rejected_reason, st.last_event, st.template_id), ("REJECTED", "INVALID_FORMAT", "REJECTED", tid))
		self.assertEqual(st.rejection_recommendation, "Remove the leading variable.")
		self.assertIn("Reviewed by Meta", st.other_info)
		self.assertTrue(st.last_event_at)
		self.realtime.assert_any_call(
			"whatsapp_template_status", {"template": "lc_hook-en_US", "status": "REJECTED", "reason": "INVALID_FORMAT"}
		)

		self._hook(fake.template_quality_webhook(srv.waba_id, tid, "lc_hook", "en_US", "GREEN", "RED"))
		st = self._state("lc_hook-en_US")
		self.assertEqual((st.quality_score, st.status), ("RED", "REJECTED"))
		self.assertIn("RED", st.quality_raw)

		self._hook(fake.template_category_webhook(srv.waba_id, tid, "lc_hook", "en_US", "UTILITY", "MARKETING"))
		st = self._state("lc_hook-en_US")
		self.assertEqual((st.category, st.previous_category), ("MARKETING", "UTILITY"))

		# FLAGGED is not a status: only last_event moves
		self._hook(fake.template_status_webhook(srv.waba_id, tid, "lc_hook", "en_US", "FLAGGED"))
		st = self._state("lc_hook-en_US")
		self.assertEqual((st.status, st.last_event), ("REJECTED", "FLAGGED"))

		# approval clears the rejection details and publishes the change
		self._hook(fake.template_status_webhook(srv.waba_id, tid, "lc_hook", "en_US", "APPROVED"))
		st = self._state("lc_hook-en_US")
		self.assertEqual((st.status, st.rejected_reason, st.rejection_recommendation), ("APPROVED", "", ""))
		self.assertEqual(self._statuses()[-1], {"template": "lc_hook-en_US", "status": "APPROVED", "reason": ""})

	def test_all_documented_status_events_map_to_status(self):
		for i, event in enumerate(
			("APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "IN_APPEAL", "LIMIT_EXCEEDED", "PENDING_DELETION", "DELETED")
		):
			self._hook(fake.template_status_webhook(self.server.waba_id, str(900000000001000 + i), f"lc_ev{i}", "en_US", event))
			self.assertEqual(self._state(f"lc_ev{i}-en_US").status, event)

	def test_duplicate_event_does_not_republish(self):
		args = (self.server.waba_id, "900000000000778", "lc_dup", "en_US", "PAUSED")
		self._hook(fake.template_status_webhook(*args))
		self._hook(fake.template_status_webhook(*args))
		self.assertEqual(len(self._statuses()), 1)

	def test_webhook_state_uses_existing_template_id(self):
		# an event that omits the name still lands on the right row through its Meta id
		self._hook(fake.template_status_webhook(self.server.waba_id, "900000000000779", "lc_id", "en_US", "PENDING"))
		payload = fake.template_status_webhook(self.server.waba_id, "900000000000779", "", "", "APPROVED")
		self._hook(payload)
		self.assertEqual(self._state("lc_id-en_US").status, "APPROVED")


class TestDrafts(LifecycleCase):
	def test_user_draft_lifecycle_reject_never_calls_meta(self):
		made = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload()))
		self.assertTrue(made["success"], made)
		self.assertEqual(made["status"], "Pending Review")
		self.assertEqual(self.server.requests, [])
		listed = mgmt.list_template_drafts(**self._acct(), status="Pending Review")["drafts"]
		row = next(d for d in listed if d["name"] == made["name"])
		self.assertEqual((row["template_name"], row["requested_via"], row["payload"]["body"]), ("lc_promo", "User", _payload()["body"]))
		rejected = mgmt.reject_template_draft(name=made["name"], note="wrong tone")
		self.assertEqual((rejected["success"], rejected["status"]), (True, "Rejected"))
		doc = frappe.get_doc(DRAFT, made["name"])
		self.assertEqual((doc.reviewed_by, doc.review_note), ("Administrator", "wrong tone"))
		self.assertTrue(doc.reviewed_at)
		self.assertEqual(self.server.requests, [])
		again = mgmt.approve_template_draft(name=made["name"])  # a rejected draft cannot be submitted afterwards
		self.assertEqual(again["error"], "already_processed")
		self.assertEqual(self.server.requests, [])

	def test_draft_validation_matches_create_template(self):
		bad = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload(body="Hi {{1}} and {{2}}", sample_values="Ann")))
		self.assertEqual(bad["error"], "validation_failed")
		self.assertEqual(mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload(category="X")))["error"], "invalid_category")
		self.assertEqual(mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload(template_name="Bad Name")))["error"], "invalid_name")
		self.assertEqual(frappe.db.count(DRAFT, {"template_name": ["in", ["lc_promo", "Bad Name"]]}), 0)

	def test_non_admin_cannot_approve_reject_or_create(self):
		made = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload()))
		frappe.set_user(fgc.EXEC_USER)
		try:
			for call in (
				lambda: mgmt.approve_template_draft(name=made["name"]),
				lambda: mgmt.reject_template_draft(name=made["name"]),
				lambda: bridge.approve_draft(made["name"]),
				lambda: mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload(template_name="lc_other"))),
				lambda: mgmt.list_template_drafts(**self._acct()),
			):
				with self.assertRaises(frappe.PermissionError):
					call()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DRAFT, made["name"], "status"), "Pending Review")
		self.assertEqual(self.server.requests, [])

	def test_approval_submits_exactly_once(self):
		self._need_bridge()
		made = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload()))
		approved = mgmt.approve_template_draft(name=made["name"], note="ok")
		self.assertTrue(approved["success"], approved)
		self.assertEqual(approved["status"], "Approved & Submitted")
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), 1)
		self.assertIn(("lc_promo", "en_US"), self.server.templates)
		doc = frappe.get_doc(DRAFT, made["name"])
		self.assertEqual((doc.submitted_template, doc.review_note, doc.reviewed_by), ("lc_promo-en_US", "ok", "Administrator"))
		self.assertEqual(self._state("lc_promo-en_US").status, "PENDING")
		# a second approval (double click, retry) never reaches Meta again
		second = mgmt.approve_template_draft(name=made["name"])
		self.assertEqual(second["error"], "already_processed")
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), 1)

	def test_meta_refusal_marks_draft_failed(self):
		self._need_bridge()
		made = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload()))
		refusal = {"success": False, "error": "create_failed", "message": "(100) Invalid parameter"}
		with patch.object(bridge, "create_template", return_value=refusal):
			out = mgmt.approve_template_draft(name=made["name"])
		self.assertFalse(out["success"])
		self.assertEqual(out["status"], "Failed")
		self.assertIn("Invalid parameter", out["submit_error"])
		retry = mgmt.reject_template_draft(name=made["name"], note="give up")  # failed drafts can still be closed
		self.assertEqual(retry["status"], "Rejected")

	def test_draft_is_submitting_and_committed_before_the_graph_post(self):
		self._need_bridge()
		made = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload()))
		seen = {}
		original = bridge.create_template
		before = frappe.db.commit.call_count

		def spy(*a, **kw):
			seen["status"] = frappe.db.get_value(DRAFT, made["name"], "status")
			seen["committed"] = frappe.db.commit.call_count - before
			return original(*a, **kw)

		with patch.object(bridge, "create_template", side_effect=spy):
			out = mgmt.approve_template_draft(name=made["name"])
		self.assertTrue(out["success"], out)
		self.assertEqual(seen, {"status": "Submitting", "committed": 1})
		self.assertGreaterEqual(frappe.db.commit.call_count - before, 3)  # + right after Meta accepted, + draft status

	def test_second_approval_after_a_crash_adopts_the_meta_template(self):
		"""Meta accepted the submit but the worker died before the draft was recorded: approving again must
		not Fail on Meta's 'already exists' but adopt the template and mark the draft submitted."""
		self._need_bridge()
		made = mgmt.create_template_draft(**self._acct(), payload=json.dumps(_payload()))
		first = mgmt.approve_template_draft(name=made["name"])
		self.assertTrue(first["success"], first)
		# simulate the crash: draft left in Submitting (stale), local mirror lost
		frappe.db.set_value(DRAFT, made["name"], {"status": "Submitting", "submitted_template": ""})
		frappe.db.sql("update `tabWhatsApp Template Draft` set modified = %s where name = %s", (frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-10), made["name"]))
		frappe.db.delete("WhatsApp Templates", {"name": "lc_promo-en_US"})
		again = mgmt.approve_template_draft(name=made["name"])
		self.server.violations.clear()  # the duplicate POST is the expected refusal
		self.assertTrue(again["success"], again)
		self.assertEqual(again["status"], "Approved & Submitted")
		self.assertEqual(again["submitted_template"], "lc_promo-en_US")
		self.assertTrue(frappe.db.exists("WhatsApp Templates", "lc_promo-en_US"))
		# a fresh Submitting draft (another approver mid-flight) is not submitted twice
		frappe.db.set_value(DRAFT, made["name"], "status", "Submitting")
		self.assertEqual(mgmt.approve_template_draft(name=made["name"])["error"], "already_processed")

	def test_agent_create_template_only_drafts(self):
		self._need_bridge()
		frappe.flags.huf_current_agent_run_id = "RUN-LC-1"
		with patch.object(wa_tool, "_server_flag", side_effect=lambda g, n: n == "allow_whatsapp_management"):
			out = json.loads(self._agent(
				"create_template", auto_submit_templates=True, allow_whatsapp_management=True, **_payload(),
			))  # LLM-supplied flags are discarded
		self.assertTrue(out["success"], out)
		self.assertEqual(out["data"]["status"], "pending_review")
		self.assertIn("NOT been sent", out["data"]["message"])
		self.assertEqual(self.server.requests, [])
		doc = frappe.get_doc(DRAFT, out["data"]["draft"])
		self.assertEqual((doc.status, doc.requested_via, doc.agent_run, doc.whatsapp_account), ("Pending Review", "Agent run", "RUN-LC-1", self.account.name))
		status = json.loads(self._agent("get_template_status", template_name=doc.name))
		self.assertEqual(status["data"]["draft"]["status"], "Pending Review")

	def test_agent_create_template_still_needs_management_flag(self):
		self._need_bridge()
		with patch.object(wa_tool, "_server_flag", return_value=False):
			out = json.loads(self._agent("create_template", **_payload()))
		self.assertEqual(out["error"], "management_not_permitted")
		self.assertEqual(frappe.db.count(DRAFT, {"template_name": "lc_promo"}), 0)  # scoped: a live bench may hold other drafts

	def test_agent_auto_submit_server_flag_submits_directly(self):
		self._need_bridge()
		with patch.object(wa_tool, "_server_flag", return_value=True):
			out = json.loads(self._agent("create_template", **_payload()))
		self.assertTrue(out["success"], out)
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), 1)
		self.assertEqual(frappe.db.count(DRAFT, {"template_name": "lc_promo"}), 0)

	def test_agent_get_template_status_reports_reason_and_quality(self):
		self._need_bridge()
		self.server.add_template("lc_rej", "en_US", "UTILITY", "REJECTED", rejected_reason="INVALID_FORMAT",
			quality_score={"score": "RED"})
		mgmt.sync_templates(account=self.account.name)
		out = json.loads(self._agent("get_template_status", template_name="lc_rej-en_US"))["data"]
		self.assertEqual((out["status"], out["reason"], out["quality"]), ("REJECTED", "INVALID_FORMAT", "RED"))
		missing = json.loads(self._agent("get_template_status", template_name="nope"))
		self.assertEqual(missing["error"], "not_found")
		rows = json.loads(self._agent("list_templates"))["data"]
		row = next(r for r in rows if r["name"] == "lc_rej-en_US")
		self.assertEqual((row["status"], row["rejected_reason"]), ("REJECTED", "INVALID_FORMAT"))


class TestSyncState(LifecycleCase):
	def test_sync_requests_fields_and_stores_state(self):
		self._need_bridge()
		self.server.add_template(
			"lc_sync", "en_US", "UTILITY", "REJECTED", rejected_reason="INCORRECT_CATEGORY",
			quality_score={"score": "YELLOW", "date": 1700000000}, previous_category="MARKETING", correct_category="MARKETING",
		)
		out = mgmt.sync_templates(account=self.account.name)
		self.assertTrue(out["success"], out)
		query = self.server.requests_to("GET", "/message_templates")[0]["query"]
		fields = query["fields"][0] if isinstance(query["fields"], list) else query["fields"]
		for needed in ("id", "rejected_reason", "quality_score", "previous_category", "correct_category", "components", "parameter_format"):
			self.assertIn(needed, fields.split(","))
		st = self._state("lc_sync-en_US")
		self.assertEqual(
			(st.status, st.rejected_reason, st.quality_score, st.category, st.previous_category, st.correct_category),
			("REJECTED", "INCORRECT_CATEGORY", "YELLOW", "UTILITY", "MARKETING", "MARKETING"),
		)
		self.assertEqual(json.loads(st.quality_raw)["score"], "YELLOW")
		self.assertTrue(st.last_meta_update)
		detail = mgmt.get_template(name="lc_sync-en_US")
		self.assertTrue(detail["category_change_pending"])
		listed = next(t for t in mgmt.list_templates(account=self.account.name)["templates"] if t["name"] == "lc_sync-en_US")
		self.assertEqual((listed["rejected_reason"], listed["quality_score"], listed["correct_category"]), ("INCORRECT_CATEGORY", "YELLOW", "MARKETING"))
		self.assertTrue(listed["last_meta_update"])

	def test_sync_status_change_publishes_and_clears_reason(self):
		self._need_bridge()
		self.server.add_template("lc_flip", "en_US", "UTILITY", "REJECTED", rejected_reason="SCAM")
		mgmt.sync_templates(account=self.account.name)
		self.assertEqual(self._state("lc_flip-en_US").rejected_reason, "SCAM")
		self.realtime.reset_mock()
		self.server.set_template_status("lc_flip", "APPROVED")
		self.server.templates[("lc_flip", "en_US")]["rejected_reason"] = "NONE"
		mgmt.sync_templates(account=self.account.name)
		self.assertEqual((self._state("lc_flip-en_US").status, self._state("lc_flip-en_US").rejected_reason), ("APPROVED", ""))
		self.assertEqual(self._statuses(), [{"template": "lc_flip-en_US", "status": "APPROVED", "reason": ""}])

	def test_sync_refreshes_components_changed_on_meta_only_when_different(self):
		self._need_bridge()
		self.server.add_template("lc_comp", "en_US", "UTILITY", "APPROVED", components=[
			{"type": "BODY", "text": "Old body"},
			{"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Yes"}]},
		])
		mgmt.sync_templates(account=self.account.name)
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", "lc_comp-en_US", "template"), "Old body")
		same = mgmt.sync_templates(account=self.account.name)
		self.assertEqual((same["updated"], same["unchanged"]), (0, 1))  # equal on both sides: untouched
		tpl = self.server.templates[("lc_comp", "en_US")]
		tpl["components"] = [
			{"type": "HEADER", "format": "TEXT", "text": "New header"},
			{"type": "BODY", "text": "New body {{1}} ok", "example": {"body_text": [["Ann"]]}},
			{"type": "FOOTER", "text": "Bye"},
			{"type": "BUTTONS", "buttons": [
				{"type": "URL", "text": "Open", "url": "https://shop.example.com/x"},
				{"type": "PHONE_NUMBER", "text": "Call", "phone_number": "+15550001234"},
			]},
		]
		changed = mgmt.sync_templates(account=self.account.name)
		self.assertEqual((changed["updated"], changed["unchanged"]), (1, 0))
		row = frappe.get_doc("WhatsApp Templates", "lc_comp-en_US")
		self.assertEqual((row.header_type, row.header, row.template, row.footer, row.sample_values), ("TEXT", "New header", "New body {{1}} ok", "Bye", "Ann"))
		self.assertEqual([(b.button_type, b.button_label) for b in row.buttons], [("Visit Website", "Open"), ("Call Phone", "Call")])
		self.assertEqual(json.loads(self._state("lc_comp-en_US").components)[1]["text"], "New body {{1}} ok")
		self.assertEqual(self.server.requests_to("POST", "/message_templates"), [])  # never pushed back to Meta
		again = mgmt.sync_templates(account=self.account.name)
		self.assertEqual((again["updated"], again["unchanged"]), (0, 1))


class TestEditTemplate(LifecycleCase):
	def _set_log(self, docname, stamps):
		frappe.db.set_value(STATE, bridge.state_key(self.account.name, docname), "edit_log", json.dumps(stamps))

	def _ago(self, **kw):
		return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()

	def test_get_template_detail(self):
		docname = self._created("lc_detail")
		detail = mgmt.get_template(name=docname)
		self.assertTrue(detail["success"], detail)
		self.assertEqual((detail["status"], detail["category"], detail["editable"], detail["edits_left"]), ("APPROVED", "UTILITY", True, 10))
		self.assertEqual(detail["components"]["body"], {"text": "Hi {{1}}, order shipped", "sample_values": ["Ann"]})
		self.assertIsNone(detail["components"]["header"])
		self.assertEqual(detail["business_id"], self.server.waba_id)
		self.assertEqual(detail["manager_url"], "https://business.facebook.com/latest/whatsapp_manager/message_templates")
		self.assertEqual(detail["state"]["quality_score"], "UNKNOWN")
		self.assertTrue(detail["template_id"])
		self.assertEqual(mgmt.get_template(name="nope-en_US")["error"], "not_found")
		listing = mgmt.list_templates(account=self.account.name)
		self.assertEqual((listing["business_id"], listing["manager_url"]), (self.server.waba_id, detail["manager_url"]))

	def test_edit_sends_full_components_and_goes_pending(self):
		docname = self._created("lc_full")
		out = mgmt.edit_template(name=docname, payload=json.dumps({
			"body": "Hello {{1}}, it left today", "footer": "Thanks", "buttons": [{"type": "QUICK_REPLY", "text": "Got it"}],
		}))
		self.assertTrue(out["success"], out)
		self.assertEqual((out["status"], out["edits_left"]), ("PENDING", 9))
		(post,) = self._edit_posts()
		tid = self.server.templates[("lc_full", "en_US")]["id"]
		self.assertTrue(post["path"].endswith(f"/{tid}"))
		sent = json.loads(post["raw"])
		self.assertEqual(set(sent), {"components"})  # name/language never sent, category unchanged so omitted
		self.assertEqual([c["type"] for c in sent["components"]], ["BODY", "FOOTER", "BUTTONS"])
		self.assertEqual(sent["components"][0], {"type": "BODY", "text": "Hello {{1}}, it left today", "example": {"body_text": [["Ann"]]}})
		row = frappe.get_doc("WhatsApp Templates", docname)
		self.assertEqual((row.status, row.template, row.footer), ("PENDING", "Hello {{1}}, it left today", "Thanks"))
		self.assertEqual([(b.button_type, b.button_label) for b in row.buttons], [("Quick Reply", "Got it")])
		st = self._state(docname)
		self.assertEqual(st.status, "PENDING")
		self.assertEqual(len(json.loads(st.edit_log)), 1)
		self.assertEqual(self._statuses()[-1]["status"], "PENDING")
		self.assertEqual(self.server.templates[("lc_full", "en_US")]["status"], "PENDING")

	def _extra(self, docname):
		from huf.ai.gateway_adapters import whatsapp_template_guard as guard

		return guard.get_extra(self.account.name, docname)

	def _seed_and_sync(self, name, components, status="REJECTED", **extra):
		self._need_bridge()
		self.server.add_template(name, "en_US", "UTILITY", status, components=components, **extra)
		synced = mgmt.sync_templates(account=self.account.name)
		self.assertTrue(synced["success"], synced)
		self.assertEqual(synced["skipped"], 0, synced)
		return f"{name}-en_US"

	def test_body_only_edit_keeps_buttons_huf_cannot_rebuild(self):
		flow = {"type": "FLOW", "text": "Open form", "flow_id": "123456", "flow_action": "navigate", "navigate_screen": "S1"}
		docname = self._seed_and_sync("lc_flow", [
			{"type": "BODY", "text": "Hi {{1}}, fill the form", "example": {"body_text": [["Ann"]]}},
			{"type": "BUTTONS", "buttons": [flow]},
		])
		out = mgmt.edit_template(name=docname, payload=json.dumps({"body": "Hello {{1}}, please fill the form", "sample_values": "Ann"}))
		self.assertTrue(out["success"], out)
		sent = json.loads(self._edit_posts()[-1]["raw"])["components"]
		self.assertEqual(sent[0]["text"], "Hello {{1}}, please fill the form")
		self.assertEqual(sent[-1], {"type": "BUTTONS", "buttons": [flow]})
		# the local FLOW row is not wiped either
		self.assertEqual(frappe.db.count("WhatsApp Button", {"parent": docname}), 1)

	def test_editing_buttons_of_a_flow_template_is_refused(self):
		flow = {"type": "FLOW", "text": "Open form", "flow_id": "123456"}
		docname = self._seed_and_sync("lc_flow2", [{"type": "BODY", "text": "Fill the form"}, {"type": "BUTTONS", "buttons": [flow]}])
		out = mgmt.edit_template(name=docname, payload=json.dumps({"buttons": [{"type": "QUICK_REPLY", "text": "Hi"}]}))
		self.assertEqual(out["error"], "edit_would_drop_buttons")
		self.assertEqual(out["button_types"], ["FLOW"])
		self.assertEqual(self._edit_posts(), [])

	def test_without_extra_an_edit_that_would_drop_buttons_is_refused(self):
		from huf.ai.gateway_adapters import whatsapp_template_guard as guard

		flow = {"type": "FLOW", "text": "Open form", "flow_id": "123456"}
		docname = self._seed_and_sync("lc_flow3", [{"type": "BODY", "text": "Fill the form"}, {"type": "BUTTONS", "buttons": [flow]}])
		guard.delete_extra(self.account.name, docname)
		out = mgmt.edit_template(name=docname, payload=json.dumps({"body": "Please fill the form"}))
		self.assertEqual(out["error"], "edit_would_drop_buttons")
		self.assertEqual(self._edit_posts(), [])

	def test_imported_dynamic_url_and_copy_code_buttons_survive_a_body_edit(self):
		buttons = [
			{"type": "URL", "text": "Track", "url": "https://example.com/t/{{1}}", "example": ["https://example.com/t/abc"]},
			{"type": "COPY_CODE", "example": "SAVE20"},
		]
		docname = self._seed_and_sync("lc_cta", [{"type": "BODY", "text": "Your offer"}, {"type": "BUTTONS", "buttons": buttons}])
		out = mgmt.edit_template(name=docname, payload=json.dumps({"body": "Your new offer"}))
		self.assertTrue(out["success"], out)
		self.assertEqual(json.loads(self._edit_posts()[-1]["raw"])["components"][-1]["buttons"], buttons)

	def test_imported_media_header_edit_reuploads_the_cdn_url(self):
		url = self.server.add_file("cdn/hero.png", "image/png", fgc.PNG)
		docname = self._seed_and_sync("lc_cdn", [
			{"type": "HEADER", "format": "IMAGE", "example": {"header_handle": [url]}},
			{"type": "BODY", "text": "Big news"},
		])
		out = mgmt.edit_template(name=docname, payload=json.dumps({"body": "Bigger news"}))
		self.assertTrue(out["success"], out)
		self.assertEqual(len(self.server.requests_to("POST", "/uploads")), 1)
		header = json.loads(self._edit_posts()[-1]["raw"])["components"][0]
		self.assertEqual(header["format"], "IMAGE")
		self.assertTrue(header["example"]["header_handle"][0].startswith("4:"))
		self.assertNotIn("http", header["example"]["header_handle"][0])

	def test_imported_media_header_that_cannot_be_fetched_is_refused(self):
		docname = self._seed_and_sync("lc_cdn2", [
			{"type": "HEADER", "format": "IMAGE", "example": {"header_handle": [f"{self.server.url}/files/cdn/gone.png"]}},
			{"type": "BODY", "text": "Big news"},
		])
		out = mgmt.edit_template(name=docname, payload=json.dumps({"body": "Bigger news"}))
		self.assertEqual(out["error"], "media_header_edit_unsupported")
		self.assertEqual(self._edit_posts(), [])
		self.server.violations.clear()

	def test_named_header_sample_change_is_a_real_edit(self):
		self._need_bridge()
		made = self._make_template(
			template_name="lc_nh", body="Hi {{name}}, welcome", parameter_format="NAMED", named_samples={"name": "Ann"},
			sample_values=None, header_type="TEXT", header="Order {{order}}", sample="A100", footer=None, buttons=None,
		)
		self.assertTrue(made["success"], made)
		self.server.approve("lc_nh")
		mgmt.sync_templates(account=self.account.name)
		same = mgmt.edit_template(name=made["name"], payload=json.dumps({"sample": "A100"}))
		self.assertEqual(same.get("error"), "no_changes", same)
		changed = mgmt.edit_template(name=made["name"], payload=json.dumps({"sample": "B200"}))
		self.assertTrue(changed["success"], changed)
		header = json.loads(self._edit_posts()[-1]["raw"])["components"][0]
		self.assertEqual(header["example"]["header_text_named_params"][0]["example"], "B200")

	def test_imported_video_and_location_headers_are_not_mislabelled(self):
		url = self.server.add_file("cdn/clip.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42")
		v = self._seed_and_sync("lc_vid", [{"type": "HEADER", "format": "VIDEO", "example": {"header_handle": [url]}}, {"type": "BODY", "text": "Watch"}], status="APPROVED")
		loc = self._seed_and_sync("lc_loc", [{"type": "HEADER", "format": "LOCATION"}, {"type": "BODY", "text": "Visit us"}], status="APPROVED")
		for docname, fmt in ((v, "VIDEO"), (loc, "LOCATION")):
			row = frappe.db.get_value("WhatsApp Templates", docname, ["header_type", "header"])
			self.assertEqual((row[0] or "", row[1] or ""), ("", ""))
			self.assertEqual(self._extra(docname)["header_format"], fmt)
			self.assertEqual(mgmt.get_template(name=docname)["header_format"], fmt)
			self.assertEqual(mgmt.get_template(name=docname)["components"]["header"]["type"], fmt)
		listed = {t["name"]: t for t in mgmt.list_templates(account=self.account.name)["templates"]}
		self.assertEqual((listed[v]["header_format"], listed[loc]["header_format"]), ("VIDEO", "LOCATION"))
		# a second sync does not flip them back and forth
		again = mgmt.sync_templates(account=self.account.name)
		self.assertEqual(again["updated"], 0, again)

	def test_upload_session_uses_documented_query_params(self):
		sample = self.server.add_file("samples/doc.png", "image/png", fgc.PNG)
		self._need_bridge()
		made = self._make_template(template_name="lc_up", header_type="IMAGE", sample=sample, header=None, body="Hi there", sample_values=None, footer=None, buttons=None)
		self.assertTrue(made["success"], made)
		(opened,) = self.server.requests_to("POST", "/uploads")
		self.assertEqual(set(opened["query"]), {"file_length", "file_type", "file_name"})
		self.assertEqual(opened["query"]["file_name"], "doc.png")
		self.assertEqual(opened["raw"], b"")
		self.assertNotIn(b"messaging_product", opened["raw"])
		self.assertNotIn("messaging_product", opened["query"])

	def test_category_and_ttl_are_passed_through(self):
		docname = self._created("lc_cat")
		self.assertEqual(mgmt.edit_template(name=docname, payload=json.dumps({"category": "AUTHENTICATION"}))["error"], "invalid_category")
		self.assertEqual(self._edit_posts(), [])
		# a TTL only exists on UTILITY templates: a MARKETING edit carrying one is refused before Meta is called
		refused = mgmt.edit_template(name=docname, payload=json.dumps({"category": "MARKETING", "message_send_ttl_seconds": 3600}))
		self.assertIn("ttl_not_allowed", [e["code"] for e in refused["errors"]])
		self.assertEqual(self._edit_posts(), [])
		out = mgmt.edit_template(name=docname, payload=json.dumps({"category": "MARKETING"}))
		self.assertTrue(out["success"], out)
		sent = json.loads(self._edit_posts()[0]["raw"])
		self.assertEqual(sent["category"], "MARKETING")
		self.assertNotIn("message_send_ttl_seconds", sent)
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", docname, "category"), "MARKETING")

	def test_24h_and_30d_quota(self):
		docname = self._created("lc_quota")
		self.assertTrue(mgmt.edit_template(name=docname, payload={"body": "One {{1}} ok"})["success"])
		# PENDING again: not editable until review finishes
		blocked = mgmt.edit_template(name=docname, payload={"body": "Two {{1}} ok"})
		self.assertEqual(blocked["error"], "status_not_editable")
		# review done (approved) but the 24h window is still closed
		self.server.approve("lc_quota")
		mgmt.sync_templates(account=self.account.name)
		blocked = mgmt.edit_template(name=docname, payload={"body": "Two {{1}} ok"})
		self.assertEqual(blocked["error"], "edit_limit_24h")
		self.assertTrue(blocked["next_edit_at"])
		self.assertEqual(len(self._edit_posts()), 1)  # refused locally, Meta never asked
		self.assertFalse(mgmt.get_template(name=docname)["editable"])
		# 25h later the next edit is allowed
		self._set_log(docname, [self._ago(hours=25)])
		self.server.template_by_id(frappe.db.get_value("WhatsApp Templates", docname, "id"))["edit_times"].clear()
		self.assertEqual(mgmt.get_template(name=docname)["edits_left"], 9)
		self.assertTrue(mgmt.edit_template(name=docname, payload={"body": "Two {{1}} ok"})["success"])
		self.assertEqual(len(json.loads(self._state(docname).edit_log)), 2)
		# ten edits within 30 days exhaust the allowance
		self.server.approve("lc_quota")
		mgmt.sync_templates(account=self.account.name)
		self._set_log(docname, [self._ago(days=2 + 2 * i) for i in range(10)])
		out = mgmt.edit_template(name=docname, payload={"body": "Three {{1}} ok"})
		self.assertEqual((out["error"], out["edits_left"]), ("edit_limit_30d", 0))
		self.assertEqual(len(self._edit_posts()), 2)

	def test_rejected_and_paused_edits_are_unlimited_and_not_counted(self):
		docname = self._created("lc_rej")
		for i, status in enumerate(("REJECTED", "PAUSED", "REJECTED")):
			self.server.set_template_status("lc_rej", status)
			mgmt.sync_templates(account=self.account.name)
			detail = mgmt.get_template(name=docname)
			self.assertEqual((detail["status"], detail["editable"], detail["edits_left"]), (status, True, None))
			out = mgmt.edit_template(name=docname, payload={"body": f"Try {i} {{{{1}}}} ok"})
			self.assertTrue(out["success"], out)
			self.assertEqual(out["status"], "PENDING")
		self.assertEqual(len(self._edit_posts()), 3)
		self.assertEqual(json.loads(self._state(docname).edit_log), [])

	def test_not_editable_statuses(self):
		docname = self._created("lc_status")
		for status in ("PENDING", "DISABLED", "IN_APPEAL", "LIMIT_EXCEEDED", "PENDING_DELETION", "DELETED"):
			self.server.set_template_status("lc_status", status)
			mgmt.sync_templates(account=self.account.name)
			out = mgmt.edit_template(name=docname, payload={"body": "x {{1}} ok"})
			self.assertEqual(out["error"], "status_not_editable", status)
			self.assertFalse(mgmt.get_template(name=docname)["editable"])
		self.assertEqual(self._edit_posts(), [])

	def test_name_and_language_are_immutable_and_no_op_is_refused(self):
		docname = self._created("lc_imm")
		for key, value in (("template_name", "lc_renamed"), ("name", "lc_renamed"), ("language_code", "fr")):
			out = mgmt.edit_template(name=docname, payload={key: value, "body": "x {{1}} ok"})
			self.assertEqual((out["error"], out["field"]), ("immutable_field", key))
		same = mgmt.edit_template(name=docname, payload={"template_name": "lc_imm", "language_code": "en_US", "body": "Hi {{1}}, order shipped"})
		self.assertEqual(same["error"], "no_changes")
		invalid = mgmt.edit_template(name=docname, payload={"body": "Hi {{1}} and {{2}}"})
		self.assertEqual(invalid["error"], "validation_failed")
		self.assertEqual(mgmt.edit_template(name="ghost-en_US", payload={"body": "x"})["error"], "not_found")
		self.assertEqual(mgmt.edit_template(name=docname, payload="[1]")["error"], "invalid_payload")
		self.assertEqual(self._edit_posts(), [])
		self.assertEqual(self._state(docname).status, "APPROVED")

	def test_meta_refusal_leaves_template_and_quota_untouched(self):
		docname = self._created("lc_meta_no")
		tid = frappe.db.get_value("WhatsApp Templates", docname, "id")
		self.server.template_by_id(tid)["edit_times"].append(__import__("time").time() - 60)  # Meta saw an edit we did not
		out = mgmt.edit_template(name=docname, payload={"body": "Changed {{1}} ok"})
		self.assertEqual(out["error"], "edit_failed")
		self.assertIn("once in 24 hours", out["message"])
		self.server.violations.clear()  # expected refusal
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", docname, "template"), "Hi {{1}}, order shipped")
		self.assertEqual((self._state(docname).status, self._state(docname).edit_log in (None, "", "[]")), ("APPROVED", True))

	def test_unchanged_category_is_never_sent_and_meta_reclassification_is_synced(self):
		docname = self._created("lc_cat")
		self.server.reclassify("lc_cat", "MARKETING")
		synced = mgmt.sync_templates(account=self.account.name)
		self.assertTrue(synced["success"], synced)
		detail = mgmt.get_template(name=docname)
		self.assertEqual((detail["category"], detail["previous_category"], detail["category_changed_by_meta"]), ("MARKETING", "UTILITY", True))
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", docname, "category"), "MARKETING")
		# the form echoes the category it loaded: it is Meta's current one, so it must not be re-sent
		out = mgmt.edit_template(name=docname, payload={"body": "Hello {{1}}, edited", "category": "MARKETING"})
		self.assertTrue(out["success"], out)
		(post,) = self._edit_posts()
		self.assertEqual(set(json.loads(post["raw"])), {"components"})
		self.assertEqual(self.server.violations, [])

	def test_stale_local_category_is_not_resent_after_a_category_webhook(self):
		docname = self._created("lc_stale")
		self.server.reclassify("lc_stale", "MARKETING")
		tid = self.server.templates[("lc_stale", "en_US")]["id"]
		bridge.record_template_state(docname=docname, template_id=tid, account=self.account.name, category="MARKETING", previous_category="UTILITY", event="CATEGORY_UPDATE")
		self.assertEqual(mgmt.get_template(name=docname)["category"], "MARKETING")
		out = mgmt.edit_template(name=docname, payload={"body": "Hello {{1}}, edited"})  # row still says UTILITY
		self.assertTrue(out["success"], out)
		self.assertEqual(set(json.loads(self._edit_posts()[0]["raw"])), {"components"})

	def test_changed_category_is_sent(self):
		docname = self._created("lc_chg")
		out = mgmt.edit_template(name=docname, payload={"category": "MARKETING"})
		self.assertTrue(out["success"], out)
		sent = json.loads(self._edit_posts()[0]["raw"])
		self.assertEqual(sent["category"], "MARKETING")
		self.assertEqual(mgmt.get_template(name=docname)["category"], "MARKETING")

	def test_meta_refusal_2388039_is_structured_and_sets_a_retry_hint(self):
		docname = self._created("lc_blk")
		self.addCleanup(lambda: frappe.cache().delete_value(bridge._edit_blocked_key(self.account.name, docname)))
		self.server.refuse_edits("lc_blk")
		out = mgmt.edit_template(name=docname, payload={"footer": "Thanks"})
		self.assertEqual((out["success"], out["error"]), (False, "edit_failed"))
		self.server.violations.clear()  # the refusal is the point of this test
		self.assertEqual((out["graph_code"], out["subcode"], out["kind"], out["retryable"]), (100, 2388039, "edit_blocked", False))
		self.assertEqual(out["user_title"], "Message template status can't be changed")
		self.assertIn("You can only delete or add templates", out["user_msg"])
		self.assertTrue(out["trace_id"])
		self.assertTrue(out["message"].startswith("Meta won't let this template be edited right now"))
		self.assertTrue(out["edit_blocked_until"])
		# quota consumed only on success
		self.assertEqual(json.loads(self._state(docname).edit_log or "[]"), [])
		detail = mgmt.get_template(name=docname)
		print("DBG", repr(docname), repr(self.account.name), frappe.cache().get_value(bridge._edit_blocked_key(self.account.name, docname)), out["edit_blocked_until"], detail["editable"], detail["whatsapp_account"], detail["status"], bridge._edit_blocked_until(detail["whatsapp_account"], docname), frappe.get_all("WhatsApp Templates", fields=["name","whatsapp_account"]))
		self.assertEqual((detail["editable"], detail["editable_reason"], detail["edits_left"]), (False, "edit_blocked", 10))
		self.assertTrue(detail["edit_blocked_until"])
		# no retry loop: the next attempt is refused locally
		again = mgmt.edit_template(name=docname, payload={"footer": "Again"})
		self.assertEqual(again["error"], "edit_blocked")
		self.assertEqual(len(self._edit_posts()), 1)

	def test_expired_hint_allows_editing_again(self):
		docname = self._created("lc_exp")
		self.addCleanup(lambda: frappe.cache().delete_value(bridge._edit_blocked_key(self.account.name, docname)))
		past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
		frappe.cache().set_value(bridge._edit_blocked_key(self.account.name, docname), past, expires_in_sec=60)
		self.assertTrue(mgmt.get_template(name=docname)["editable"])

	def test_edit_requires_write_permission(self):
		docname = self._created("lc_perm")
		frappe.set_user(fgc.EXEC_USER)
		try:
			with self.assertRaises(frappe.PermissionError):
				mgmt.edit_template(name=docname, payload={"body": "x {{1}} ok"})
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(self._edit_posts(), [])
