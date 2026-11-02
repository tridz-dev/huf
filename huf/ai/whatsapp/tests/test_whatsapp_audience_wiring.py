# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-E1: audiences wired into a broadcast (set_broadcast_audiences, purpose check, consent cover, previews)."""

import json
from unittest.mock import patch

import frappe

from huf.ai.whatsapp.broadcast import limits, policy, recipients as br, runner
from huf.ai.whatsapp.broadcast.audiences import api, wiring
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_audience_api import GW, AudienceTestCase
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import USER, B, R, _Base, _preview

N = [f"4479000000{i:02d}" for i in range(1, 9)]


def _csv(*numbers, first="Ann"):
	lines = ["phone,name,tags,first"] + [f"{n},Name {n[-2:]},{'vip' if i % 2 == 0 else 'std'},{first}{i}" for i, n in enumerate(numbers)]
	return "\n".join(lines)


MAPPING = {"phone": "phone", "name": "name", "tags": "tags", "params": ["first"]}


class WiringCase(AudienceTestCase):
	def make(self, title="List", purposes=("marketing", "utility"), **kw):
		return super().make(title, purposes, **kw)

	def fill(self, audience, *numbers, **kw):
		out = api.import_members(audience=audience, csv_text=_csv(*numbers, **kw), mapping=MAPPING)
		self.assertTrue(out.get("success"), out)

	def bc(self, status="Draft", category="UTILITY", gateway=GW, **over):
		frappe.flags.in_broadcast_api = True
		self.addCleanup(lambda: setattr(frappe.flags, "in_broadcast_api", False))
		doc = frappe.get_doc(
			{"doctype": "WhatsApp Broadcast", "title": "t", "gateway": gateway, "status": status, "template": "tpl",
			 "template_name": "tpl", "whatsapp_account": "ACC", "category": category, **over}
		)  # fmt: skip
		doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		return doc.name

	def rows(self, b, **filters):
		return frappe.get_all(R, {"broadcast": b, **filters}, ["recipient", "status", "audience", "params", "consent_source", "skip_reason"],
			order_by="recipient asc")  # fmt: skip

	def wire(self, b, picks, category="UTILITY"):
		with patch.object(aud, "template_category", return_value=category):
			return wiring.set_broadcast_audiences(broadcast=b, selection=json.dumps(picks))


class TestSetBroadcastAudiences(WiringCase):
	def test_two_lists_exclude_dedupe_writes_rows_with_audience_params_consent(self):
		a, b_, ex = self.make("A"), self.make("B"), self.make("X")
		self.fill(a, N[0], N[1], N[2])
		self.fill(b_, N[2], N[3], N[4], first="Bob")
		self.fill(ex, N[1])
		b = self.bc()
		out = self.wire(b, [{"audience": a}, {"audience": b_}, {"audience": ex, "exclude": True}])
		self.assertTrue(out["success"], out)
		self.assertEqual(out["counts"]["final"], 4)
		self.assertEqual(out["counts"]["dupes"], 1)
		self.assertEqual(out["counts"]["excluded"], 1)
		rows = {r["recipient"]: r for r in self.rows(b)}
		self.assertEqual(sorted(rows), [N[0], N[2], N[3], N[4]])
		self.assertEqual(rows[N[2]]["audience"], a)  # first list wins
		self.assertEqual(rows[N[3]]["audience"], b_)
		self.assertEqual(rows[N[2]]["consent_source"], "signup form")
		self.assertEqual(json.loads(rows[N[0]]["params"]), {"body": ["Ann0"]})
		self.assertEqual(out["added"], 4)
		self.assertEqual(out["queued"], 4)
		self.assertEqual(frappe.db.get_value("WhatsApp Broadcast", b, "queued"), 4)
		stored = frappe.get_all(aud.BROADCAST_AUDIENCE, {"parent": b}, ["audience", "exclude"], order_by="idx asc", parent_doctype="WhatsApp Broadcast")
		self.assertEqual([(s["audience"], s["exclude"]) for s in stored], [(a, 0), (b_, 0), (ex, 1)])

	def test_tags_filter_is_stored_and_applied(self):
		a = self.make("A")
		self.fill(a, N[0], N[1], N[2])  # vip, std, vip
		b = self.bc()
		out = self.wire(b, [{"audience": a, "tags": ["VIP"], "tag_filter_mode": "all"}])
		self.assertEqual(sorted(r["recipient"] for r in self.rows(b)), [N[0], N[2]])
		self.assertEqual(out["selection"][0]["tags"], ["vip"])
		back = wiring.get_broadcast_audiences(broadcast=b)
		self.assertEqual(back["selection"][0]["tags"], ["vip"])
		self.assertEqual(back["selection"][0]["tag_filter_mode"], "all")

	def test_rerun_replaces_audience_rows_and_keeps_manual_rows(self):
		a, c = self.make("A"), self.make("C")
		self.fill(a, N[0], N[1])
		self.fill(c, N[5])
		b = self.bc()
		self.wire(b, [{"audience": a}])
		with patch.object(br, "_policy_reason", return_value=None):
			br.prepare(b, [{"recipient": N[6]}, {"recipient": N[1]}])  # N[1] already an audience row
		out = self.wire(b, [{"audience": c}, {"audience": a, "tags": ["nomatch"]}])
		self.assertEqual(out["replaced"], 2)
		rows = {r["recipient"]: r["audience"] for r in self.rows(b)}
		self.assertEqual(rows, {N[5]: c, N[6]: None})

	def test_manual_row_wins_over_the_same_number_in_a_list(self):
		a = self.make("A")
		self.fill(a, N[0], N[1])
		b = self.bc()
		br.prepare(b, [{"recipient": N[0]}])
		out = self.wire(b, [{"audience": a}])
		rows = {r["recipient"]: r["audience"] for r in self.rows(b)}
		self.assertEqual(rows, {N[0]: None, N[1]: a})
		self.assertEqual(out["skipped"], [{"recipient": N[0], "reason": "duplicate"}])

	def test_suppressed_member_goes_through_recipients_policy_and_keeps_audience(self):
		a = self.make("A")
		self.fill(a, N[0], N[1])
		b = self.bc()
		real = br._policy_reason
		with patch.object(br, "_policy_reason", side_effect=lambda g, r, m: "opted_out" if r == N[0] else real(g, r, m)):
			out = self.wire(b, [{"audience": a}])
		row = self.rows(b, recipient=N[0])[0]
		self.assertEqual((row["status"], row["skip_reason"], row["audience"]), ("skipped", "opted_out", a))
		self.assertEqual(out["skipped_total"], 1)
		self.assertEqual(out["queued"], 1)

	def test_refusals(self):
		a = self.make("A")
		self.fill(a, N[0])
		self.assertEqual(self.wire(self.bc(status="Running"), [{"audience": a}])["error"], "not_draft")
		b = self.bc()
		self.assertEqual(self.wire(b, [])["error"], "invalid")
		self.assertEqual(self.wire(b, [{"audience": a, "exclude": True}])["error"], "invalid")
		self.assertEqual(self.wire(b, [{"audience": "nope"}])["error"], "invalid")
		other = "GW-AUD-OTHER"
		if not frappe.db.exists("Gateway", other):
			frappe.get_doc({"doctype": "Gateway", "name": other, "gateway_name": other, "provider": "WhatsApp"}).db_insert()
		self.assertEqual(self.wire(self.bc(gateway=other), [{"audience": a}])["error"], "invalid")
		self.assertEqual(self.rows(b), [])

	def test_gateway_write_permission_required(self):
		a = self.make("A")
		b = self.bc()
		with patch("huf.ai.whatsapp.broadcast.api._gateway_write_allowed", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				self.wire(b, [{"audience": a}])

	def test_audit_comment_written(self):
		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc()
		self.wire(b, [{"audience": a}])
		texts = frappe.get_all("Comment", {"reference_doctype": "WhatsApp Broadcast", "reference_name": b}, pluck="content")
		self.assertTrue(any("audiences_set" in t and a in t for t in texts), texts)


class TestPurposeBlock(WiringCase):
	def test_marketing_template_with_utility_only_list_adds_no_rows_and_reports_blocked(self):
		a = self.make("Util", purposes=("utility",))
		self.fill(a, N[0], N[1])
		b = self.bc(category="MARKETING")
		out = self.wire(b, [{"audience": a}], category="MARKETING")
		self.assertEqual([x["code"] for x in out["blocked"]], ["audience_purpose_mismatch"])
		self.assertEqual(self.rows(b), [])
		self.assertEqual(out["counts"]["blocked_by_purpose"], 2)

	def _preview(self, b, category):
		with patch.object(limits, "_template_row", return_value={"status": "APPROVED", "category": category}), patch.object(
			limits, "get_messaging_limit", return_value={"tier": "TIER_UNLIMITED", "max_unique_24h": None, "quality": None, "mps": None}
		):
			return limits.preview(b)

	def test_preview_blocks_when_category_needs_a_purpose_the_list_lacks(self):
		a = self.make("Util", purposes=("utility",))
		self.fill(a, N[0])
		b = self.bc()
		self.wire(b, [{"audience": a}])
		self.assertNotIn("audience_purpose_mismatch", [x["code"] for x in self._preview(b, "UTILITY")["blocking"]])
		blocking = self._preview(b, "MARKETING")["blocking"]
		hit = [x for x in blocking if x["code"] == "audience_purpose_mismatch"]
		self.assertEqual(len(hit), 1)
		self.assertIn("Util", hit[0]["message"])

	def test_excluded_list_does_not_trigger_the_block(self):
		a, ex = self.make("Mkt", purposes=("marketing",)), self.make("Util", purposes=("utility",))
		self.fill(a, N[0])
		self.fill(ex, N[1])
		b = self.bc()
		self.wire(b, [{"audience": a}, {"audience": ex, "exclude": True}], category="MARKETING")
		self.assertEqual([x for x in self._preview(b, "MARKETING")["blocking"] if x["code"] == "audience_purpose_mismatch"], [])

	def test_no_audiences_no_block(self):
		self.assertEqual([x for x in self._preview(self.bc(), "MARKETING")["blocking"] if x["code"] == "audience_purpose_mismatch"], [])


class TestConsentCover(WiringCase):
	def test_attested_audiences_satisfy_broadcast_consent_and_record_which(self):
		a, c = self.make("Spring"), self.make("Autumn")
		self.fill(a, N[0])
		self.fill(c, N[1])
		b = self.bc()
		out = self.wire(b, [{"audience": a}, {"audience": c}])
		self.assertTrue(out["consent"]["satisfied"])
		self.assertTrue(out["consent"]["attested"])
		self.assertEqual(sorted(x["audience"] for x in out["consent"]["audiences"]), sorted([a, c]))
		v = frappe.db.get_value("WhatsApp Broadcast", b, ["consent_attested", "consent_attested_by", "consent_source"], as_dict=True)
		self.assertEqual(v["consent_attested"], 1)
		self.assertEqual(v["consent_attested_by"], "Administrator")
		self.assertIn("Spring", v["consent_source"])

	def test_manual_row_means_audiences_do_not_cover(self):
		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc()
		br.prepare(b, [{"recipient": N[5]}])
		out = self.wire(b, [{"audience": a}])
		self.assertFalse(out["consent"]["satisfied"])
		self.assertEqual(out["consent"]["manual_rows"], 1)
		self.assertFalse(frappe.db.get_value("WhatsApp Broadcast", b, "consent_attested"))

	def test_audience_without_attester_does_not_cover(self):
		a = self.make("A")
		self.fill(a, N[0])
		frappe.db.set_value(aud.AUDIENCE, a, "consent_attested_by", None)
		b = self.bc()
		self.assertFalse(self.wire(b, [{"audience": a}])["consent"]["satisfied"])

	def test_setting_off_keeps_current_semantics(self):
		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc()
		with limit_override(require_consent_attestation=False):
			self.wire(b, [{"audience": a}])
		self.assertFalse(frappe.db.get_value("WhatsApp Broadcast", b, "consent_attested"))

	def test_adding_a_manual_row_afterwards_resets_the_audience_based_attestation(self):
		from huf.ai.whatsapp.broadcast import api as bapi

		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc()
		self.wire(b, [{"audience": a}])
		self.assertTrue(frappe.db.get_value("WhatsApp Broadcast", b, "consent_attested"))
		with patch.object(bapi, "_bridge_guard", lambda f: f):
			bapi.add_broadcast_recipients(broadcast=b, recipients=json.dumps([N[6]]))
		self.assertFalse(frappe.db.get_value("WhatsApp Broadcast", b, "consent_attested"))

	def test_rerun_after_manual_attestation_resets_then_recomputes(self):
		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc(consent_attested=1, consent_source="mine")
		br.prepare(b, [{"recipient": N[6]}])
		self.wire(b, [{"audience": a}])
		self.assertFalse(frappe.db.get_value("WhatsApp Broadcast", b, "consent_attested"))


class TestSelectionPreviewForGateway(WiringCase):
	def test_counts_match_the_broadcast_preview_without_a_broadcast(self):
		a, c = self.make("A", purposes=("marketing",)), self.make("U", purposes=("utility",))
		self.fill(a, N[0], N[1])
		self.fill(c, N[1], N[2])
		picks = [{"audience": a}, {"audience": c}]
		b = self.bc(category="MARKETING")
		with patch.object(aud, "template_category", return_value="MARKETING"):
			via_broadcast = api.preview_audience_selection(broadcast=b, selection=json.dumps(picks))
		free = api.preview_audience_selection_for_gateway(gateway=GW, selection=json.dumps(picks), template_category="marketing")
		self.assertEqual(free["counts"], via_broadcast["counts"])
		self.assertEqual(free["blocked"], via_broadcast["blocked"])
		self.assertEqual(free["purpose_required"], "marketing")
		self.assertEqual(free["counts"]["blocked_by_purpose"], 2)

	def test_without_category_there_is_no_purpose_block(self):
		a = self.make("U", purposes=("utility",))
		self.fill(a, N[0])
		out = api.preview_audience_selection_for_gateway(gateway=GW, selection=[{"audience": a}])
		self.assertEqual((out["blocked"], out["counts"]["final"], out["category"]), ([], 1, None))

	def test_errors_and_permission(self):
		a = self.make("A")
		self.assertEqual(api.preview_audience_selection_for_gateway(gateway="nope", selection=[{"audience": a}])["error"], "gateway_required")
		self.assertEqual(api.preview_audience_selection_for_gateway(gateway=GW, selection=[{"audience": a, "exclude": True}])["error"], "invalid")
		with patch.object(api, "_gateway_read_allowed", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.preview_audience_selection_for_gateway(gateway=GW, selection=[{"audience": a}])


class TestImportExamples(WiringCase):
	def test_inline_result_lists_invalid_and_skipped_with_row_and_reason(self):
		a = self.make("A")
		text = "phone,name\n" + "\n".join([N[0], "abc", N[0], N[1]][i] + f",n{i}" for i in range(4))
		out = api.import_members(audience=a, csv_text=text)
		self.assertEqual((out["added"], out["invalid_total"], out["skipped_total"]), (2, 1, 1))
		self.assertEqual(out["invalid"], [{"row": 2, "recipient": "abc", "reason": "invalid_number"}])
		self.assertEqual(out["skipped"], [{"row": 3, "recipient": N[0], "reason": "duplicate_in_file"}])

	def test_lists_are_capped_but_totals_are_exact(self):
		a = self.make("A")
		text = "phone\n" + "\n".join(f"bad{i}" for i in range(7))
		with limit_override(returned_list_limit=3):
			out = api.import_members(audience=a, csv_text=text)
		self.assertEqual((len(out["invalid"]), out["invalid_total"]), (3, 7))

	def test_import_status_returns_examples_masked_for_readers(self):
		a = self.make("A")
		from huf.ai.whatsapp.broadcast.audiences import importer

		result = {"added": 1, "invalid_total": 2, "skipped_total": 1,
			"invalid": [{"row": 4, "recipient": "12345", "reason": "invalid_number"}],
			"skipped": [{"row": 2, "recipient": N[0], "reason": "already_in_audience"}]}  # fmt: skip
		importer.set_job_state("jobx", {"job_id": "jobx", "audience": a, "status": "done", "result": result})
		full = api.get_import_status(job_id="jobx", audience=a)
		self.assertEqual(full["skipped"][0], {"row": 2, "recipient": N[0], "reason": "already_in_audience"})
		self.assertEqual((full["invalid_total"], full["skipped_total"]), (2, 1))
		with patch.object(api, "_gateway_write_allowed", return_value=False):
			masked = api.get_import_status(job_id="jobx", audience=a)
		self.assertTrue(masked["skipped"][0]["recipient"].endswith(N[0][-4:]))
		self.assertTrue(masked["skipped"][0]["recipient"].startswith("*"))
		self.assertTrue(masked["result"]["skipped"][0]["recipient"].startswith("*"))
		self.assertEqual(masked["skipped"][0]["reason"], "already_in_audience")

	def test_running_import_status_has_empty_lists(self):
		a = self.make("A")
		from huf.ai.whatsapp.broadcast.audiences import importer

		importer.set_job_state("joby", {"job_id": "joby", "audience": a, "status": "running", "processed": 5, "total": 9})
		out = api.get_import_status(job_id="joby", audience=a)
		self.assertEqual((out["invalid"], out["skipped"], out["invalid_total"]), ([], [], 0))


class TestStartRechecksPurpose(_Base):
	"""Meta can recategorize an approved template; runner.start must see the new category."""

	def setUp(self):
		super().setUp()
		patch.stopall()  # use the real preview, not _Base's stub
		self.addCleanup(patch.stopall)
		patch.object(runner, "_enqueue_tick").start()
		patch.object(runner, "_gateway_write_ok", return_value=True).start()
		patch.object(limits, "get_messaging_limit", return_value={"tier": "TIER_UNLIMITED", "max_unique_24h": None, "quality": None, "mps": None}).start()
		self.audience = None
		self.addCleanup(self._drop_audience)

	def _drop_audience(self):
		if self.audience:
			frappe.db.delete(aud.BROADCAST_AUDIENCE, {"audience": self.audience})
			frappe.db.delete(aud.AUDIENCE, {"name": self.audience})
			frappe.db.commit()

	def test_start_refuses_after_recategorization_to_marketing(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Gateway", GW):
			frappe.get_doc({"doctype": "Gateway", "name": GW, "gateway_name": GW, "provider": "WhatsApp"}).db_insert()
		out = api.create_audience(gateway=GW, title="Util only", consent_source="s", consent_basis="checkout",
			consent_purposes=["utility"], consent_attested=True)  # fmt: skip
		self.audience = out["audience"]["name"]
		b = self.make(n=1)
		frappe.get_doc({"doctype": aud.BROADCAST_AUDIENCE, "parent": b, "parenttype": "WhatsApp Broadcast", "parentfield": "audiences",
			"audience": self.audience, "tag_filter_mode": "any", "idx": 1, "exclude": 0}).db_insert()  # fmt: skip
		frappe.db.commit()
		for category, expect in (("UTILITY", None), ("MARKETING", "audience_purpose_mismatch")):
			with patch.object(limits, "_template_row", return_value={"status": "APPROVED", "category": category}):
				if expect is None:
					self.assertNotIn(expect, [x["code"] for x in limits.preview(b)["blocking"]])
				else:
					with self.assertRaises(runner.StartRefused) as cm:
						runner.start(b, USER, [])
					self.assertEqual(cm.exception.code, "audience_purpose_mismatch")
					self.assertEqual(frappe.db.get_value("WhatsApp Broadcast", b, "status"), "Draft")
