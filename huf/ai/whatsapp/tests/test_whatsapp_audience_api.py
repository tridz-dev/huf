# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-B: audience API against the database (import, members, masking, consent, selection, delete guard)."""

import unittest
from unittest.mock import patch

import frappe

from huf.ai.whatsapp.broadcast import audience as aud
from huf.ai.whatsapp.broadcast import audience_api as api

GW = "GW-AUD-TEST"
BCAST = "WhatsApp Broadcast"


def _import(audience, **kw):
	return api.import_members(audience=audience, **kw)


class AudienceTestCase(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.flags.in_audience_api = False
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(lambda: setattr(frappe.flags, "in_audience_api", False))
		if not frappe.db.exists("Gateway", GW):
			frappe.get_doc({"doctype": "Gateway", "name": GW, "gateway_name": GW, "provider": "WhatsApp"}).db_insert()

	def make(self, title="List", purposes=("marketing",), **kw):
		out = api.create_audience(
			gateway=GW, title=title, consent_source="signup form", consent_basis="opt-in form",
			consent_purposes=list(purposes), consent_attested=True, **kw,
		)  # fmt: skip
		self.assertTrue(out.get("success"), out)
		return out["audience"]["name"]

	def members(self, audience):
		return frappe.get_all(aud.MEMBER, {"audience": audience}, pluck="recipient", order_by="recipient asc")

	def draft_broadcast(self, audience, status="Draft", template=None):
		frappe.flags.in_broadcast_api = True
		self.addCleanup(lambda: setattr(frappe.flags, "in_broadcast_api", False))
		doc = frappe.get_doc(
			{"doctype": BCAST, "title": "t", "gateway": GW, "status": status, "template": template or "tpl",
			 "template_name": "tpl", "whatsapp_account": "ACC"}
		)  # fmt: skip
		doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		frappe.get_doc(
			{"doctype": aud.BROADCAST_AUDIENCE, "parent": doc.name, "parenttype": BCAST, "parentfield": "audiences",
			 "audience": audience, "tag_filter_mode": "any", "idx": 1}
		).db_insert()  # fmt: skip
		return doc.name


class TestCreateAndConsent(AudienceTestCase):
	def test_create_sets_attestation_server_side(self):
		frappe.set_user("Administrator")
		out = api.create_audience(
			gateway=GW, title="Spring", consent_source="web form", consent_basis="checkout",
			consent_purposes="marketing,utility", consent_attested=True,
		)  # fmt: skip
		view = out["audience"]
		self.assertEqual(view["consent_attested_by"], "Administrator")
		self.assertTrue(view["consent_attested_at"])
		self.assertEqual(view["consent_purposes"], ["marketing", "utility"])

	def test_client_cannot_supply_attester(self):
		with self.assertRaises(TypeError):
			api.create_audience(gateway=GW, title="x", consent_attested_by="someone@x.com")

	def test_not_attested_is_refused(self):
		out = api.create_audience(
			gateway=GW, title="x", consent_source="s", consent_basis="checkout",
			consent_purposes=["marketing"], consent_attested=False,
		)  # fmt: skip
		self.assertEqual(out["error"], "consent_not_attested")

	def test_needs_purpose_and_known_gateway(self):
		kw = dict(title="x", consent_source="s", consent_basis="checkout", consent_attested=True)
		self.assertEqual(api.create_audience(gateway=GW, consent_purposes=[], **kw)["error"], "purposes_required")
		self.assertEqual(api.create_audience(gateway="nope", consent_purposes=["marketing"], **kw)["error"], "gateway_required")
		self.assertEqual(api.create_audience(gateway=GW, consent_purposes=["spam"], **kw)["error"], "invalid")

	def test_future_consent_date_refused(self):
		out = api.create_audience(
			gateway=GW, title="x", consent_source="s", consent_basis="checkout", consent_purposes=["marketing"],
			consent_attested=True, default_consent_at="2999-01-01",
		)  # fmt: skip
		self.assertEqual(out["error"], "invalid")

	def test_attestation_is_immutable_on_save(self):
		name = self.make()
		for field, value in (("consent_attested_by", "Guest"), ("consent_attested_at", "2020-01-01 00:00:00"),
							("default_consent_at", "2020-01-01 00:00:00"), ("consent_basis", "in-store")):
			with self.subTest(field=field):
				doc = frappe.get_doc(aud.AUDIENCE, name)
				doc.set(field, value)
				with self.assertRaises(frappe.ValidationError):
					doc.save(ignore_permissions=True)
				frappe.db.rollback()

	def test_update_audience_ignores_attestation_and_only_narrows_purposes(self):
		name = self.make(purposes=("marketing",))
		before = frappe.db.get_value(aud.AUDIENCE, name, ["consent_attested_by", "consent_attested_at"])
		out = api.update_audience(audience=name, title="Renamed", description="d")
		self.assertTrue(out["success"], out)
		self.assertEqual(frappe.db.get_value(aud.AUDIENCE, name, ["consent_attested_by", "consent_attested_at"]), before)
		widen = api.update_audience(audience=name, consent_purposes=["marketing", "events"])
		self.assertEqual(widen["error"], "invalid")
		self.assertEqual(api.update_audience(audience=name, consent_purposes=[])["error"], "purposes_required")

	def test_write_needs_gateway_authority(self):
		with patch.object(api, "_gateway_write_allowed", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.create_audience(gateway=GW, title="x")
			name = self.make()
			with self.assertRaises(frappe.PermissionError):
				api.delete_audience(audience=name)
			with self.assertRaises(frappe.PermissionError):
				_import(name, rows=[{"phone": "447700900123"}])


class TestImport(AudienceTestCase):
	def test_valid_invalid_duplicate_and_overlong_rows(self):
		name = self.make()
		rows = [
			{"phone": "+44 7700 900123", "name": "Ann", "tags": "vip,eu"},
			{"phone": "447700900123"},  # duplicate of row 1 inside the file
			{"phone": "12345"},  # too short
			{"phone": "1" * 16},  # too long for E.164
			{"phone": "447700900124", "name": "n" * 141},  # overlong name
			{"phone": "447700900125", "tags": "t" * 51},  # overlong tag
			{"phone": "IN.4608123"},  # BSUID
			{"phone": "447700900126"},
		]
		out = _import(name, rows=rows)
		self.assertTrue(out["success"], out)
		self.assertEqual((out["added"], out["skipped_total"], out["invalid_total"]), (2, 1, 6))
		self.assertEqual(out["skipped"][0]["reason"], "duplicate_in_file")
		reasons = [i["reason"] for i in out["invalid"]]
		self.assertEqual(reasons[:2], ["invalid_number", "invalid_number"])
		self.assertTrue(reasons[2].startswith("name_too_long"))
		self.assertTrue(reasons[3].startswith("invalid_tags"))
		self.assertEqual(reasons[4], "bsuid_not_supported")
		self.assertEqual(self.members(name), ["447700900123", "447700900126"])
		self.assertEqual(out["member_count"], 2)
		self.assertEqual(frappe.db.get_value(aud.AUDIENCE, name, "member_count"), 2)

	def test_csv_with_auto_detected_columns_and_mapping(self):
		name = self.make()
		csv_text = "Mobile,Full Name,Segment,Order\n447700900123,Ann,vip,A1\n447700900124,Bob,eu;vip,B2\n"
		out = _import(name, csv_text=csv_text, mapping={"phone": "Mobile", "name": "Full Name", "tags": "Segment", "params": ["Order"]})
		self.assertEqual(out["added"], 2, out)
		row = frappe.db.get_value(aud.MEMBER, f"{name}-447700900124", ["display_name", "tags", "params"], as_dict=True)
		self.assertEqual(row.display_name, "Bob")
		self.assertEqual(aud._as_list(row.tags), ["eu", "vip"])
		self.assertEqual(aud._as_dict(row.params), {"body": ["B2"]})
		auto = _import(self.make(title="B"), csv_text="phone,name,tags\n447700900123,Ann,x\n")
		self.assertEqual(auto["added"], 1)

	def test_mapping_errors(self):
		name = self.make()
		self.assertEqual(_import(name, csv_text="a,b\n1,2\n")["error"], "mapping_missing_phone")
		self.assertEqual(_import(name, csv_text="a,b\n1,2\n", mapping={"phone": "zzz"})["error"], "unknown_column")
		self.assertEqual(_import(name, csv_text="phone\n", mapping=None)["error"], "no_rows")
		self.assertEqual(_import(name, csv_text="x", rows=[{}])["error"], "invalid")

	def test_oversized_csv_refused(self):
		name = self.make()
		with patch.object(aud, "LIMIT_MAX_CSV_BYTES", 10):
			self.assertEqual(_import(name, csv_text="phone\n447700900123\n")["error"], "csv_too_large")

	def test_on_conflict_skip_update_fail(self):
		name = self.make()
		_import(name, rows=[{"phone": "447700900123", "name": "Ann", "tags": "a"}])
		skip = _import(name, rows=[{"phone": "447700900123", "name": "Changed"}])
		self.assertEqual((skip["added"], skip["updated"], skip["skipped"][0]["reason"]), (0, 0, "already_in_audience"))
		self.assertEqual(frappe.db.get_value(aud.MEMBER, f"{name}-447700900123", "display_name"), "Ann")
		upd = _import(name, rows=[{"phone": "447700900123", "name": "Changed", "tags": "b"}], on_conflict="update")
		self.assertEqual(upd["updated"], 1)
		row = frappe.db.get_value(aud.MEMBER, f"{name}-447700900123", ["display_name", "tags"], as_dict=True)
		self.assertEqual((row.display_name, aud._as_list(row.tags)), ("Changed", ["a", "b"]))
		fail = _import(name, rows=[{"phone": "447700900123"}, {"phone": "447700900124"}], on_conflict="fail")
		self.assertEqual(fail["error"], "conflicts")
		self.assertNotIn("447700900124", self.members(name))
		self.assertEqual(_import(name, rows=[{"phone": "447700900125"}], on_conflict="bogus")["error"], "invalid")

	def test_audience_member_limit(self):
		name = self.make()
		with patch.object(aud, "LIMIT_MAX_MEMBERS_PER_AUDIENCE", 1):
			out = _import(name, rows=[{"phone": "447700900123"}, {"phone": "447700900124"}])
		self.assertEqual((out["added"], out["skipped"][0]["reason"]), (1, "audience_full"))

	def test_large_import_is_queued_and_job_reports_progress(self):
		name = self.make()
		rows = [{"phone": f"4477009{i:05d}", "tags": "bulk"} for i in range(30)]
		with patch.object(aud, "LIMIT_INLINE_IMPORT_ROWS", 10), patch.object(api.frappe, "enqueue") as enqueue:
			out = _import(name, rows=rows)
		self.assertTrue(out["queued"])
		self.assertEqual(self.members(name), [])  # nothing written in the request
		kwargs = enqueue.call_args.kwargs
		self.assertEqual(enqueue.call_args.args[0], "huf.ai.whatsapp.broadcast.audience.run_import_job")
		self.assertEqual(aud.get_job_state(out["job_id"])["status"], "queued")
		events = []
		with patch.object(aud.frappe.db, "commit"), patch.object(aud, "IMPORT_CHUNK", 10), \
				patch.object(aud.frappe, "publish_realtime", side_effect=lambda *a, **k: events.append(a)), \
				patch("huf.ai.whatsapp.broadcast.progress.THROTTLE_SECONDS", 0):
			aud.run_import_job(**{k: kwargs[k] for k in ("audience", "rows", "on_conflict", "job_id", "user")})
		state = api.get_import_status(job_id=out["job_id"], audience=name)
		self.assertEqual((state["status"], state["result"]["added"]), ("done", 30))
		self.assertEqual(state["member_count"], 30)
		self.assertTrue(events and events[-1][0] == "wa_audience_import_progress")
		self.assertEqual(len(self.members(name)), 30)
		other = self.make(title="Other")
		self.assertEqual(api.get_import_status(job_id=out["job_id"], audience=other)["error"], "not_found")

	def test_import_over_row_limit_refused(self):
		name = self.make()
		with patch.object(aud, "LIMIT_MAX_IMPORT_ROWS", 2):
			self.assertEqual(_import(name, rows=[{"phone": "447700900123"}] * 3)["error"], "too_many")


class TestMembersAndMasking(AudienceTestCase):
	def seed(self):
		name = self.make()
		_import(name, rows=[
			{"phone": "447700900123", "name": "Ann", "tags": "vip,eu"},
			{"phone": "447700900124", "name": "Bob", "tags": "vip"},
			{"phone": "447700900125", "name": "Cy", "tags": "eu"},
		])  # fmt: skip
		return name

	def test_phone_masked_for_read_only_and_full_for_writers(self):
		name = self.seed()
		with patch.object(api, "_gateway_write_allowed", return_value=False), patch.object(api, "_gateway_read_allowed", return_value=True):
			out = api.list_members(audience=name)
			self.assertTrue(out["masked"])
			self.assertEqual([m["recipient"] for m in out["members"]], ["********0123", "********0124", "********0125"])
			self.assertFalse(api.get_audience(audience=name)["audience"]["can_see_numbers"])
		out = api.list_members(audience=name)
		self.assertFalse(out["masked"])
		self.assertEqual(out["members"][0]["recipient"], "447700900123")

	def test_read_requires_gateway_read(self):
		name = self.seed()
		with patch.object(api, "_gateway_read_allowed", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.list_members(audience=name)

	def test_tag_filters(self):
		name = self.seed()
		pick = lambda **kw: [m["display_name"] for m in api.list_members(audience=name, **kw)["members"]]  # noqa: E731
		self.assertEqual(pick(tags="vip"), ["Ann", "Bob"])
		self.assertEqual(pick(tags=["vip", "eu"], tag_mode="all"), ["Ann"])
		self.assertEqual(pick(tags=["vip", "eu"], tag_mode="any"), ["Ann", "Bob", "Cy"])
		self.assertEqual(api.list_members(audience=name, tags="vip")["total"], 2)

	def test_suppressed_filter_and_reasons_come_from_consent_records(self):
		name = self.seed()
		frappe.get_doc({"doctype": "Gateway Access Entry", "name": "GAE-AUD-1", "gateway": GW, "entry_type": "Sender",
						"external_id": "447700900124", "state": "opted_out"}).db_insert()  # fmt: skip
		frappe.get_doc({"doctype": "Gateway Consent", "name": "GC-AUD-1", "gateway": GW, "sender_id": "447700900125",
						"category": "marketing_messages", "value": "stop", "meta_timestamp": 5}).db_insert()  # fmt: skip
		frappe.get_doc({"doctype": "Gateway Consent", "name": "GC-AUD-2", "gateway": GW, "sender_id": "447700900123",
						"category": "marketing_messages", "value": "stop", "meta_timestamp": 5}).db_insert()  # fmt: skip
		frappe.get_doc({"doctype": "Gateway Consent", "name": "GC-AUD-3", "gateway": GW, "sender_id": "447700900123",
						"category": "marketing_messages", "value": "resume", "meta_timestamp": 9}).db_insert()  # fmt: skip
		sup = api.list_members(audience=name, suppressed=True)
		self.assertEqual({m["display_name"]: m["suppressed"] for m in sup["members"]}, {"Bob": "opted_out", "Cy": "marketing_opted_out"})
		self.assertEqual([m["display_name"] for m in api.list_members(audience=name, suppressed="false")["members"]], ["Ann"])
		self.assertEqual(aud.refresh_counts(name)["suppressed_count"], 2)

	def test_remove_members(self):
		name = self.seed()
		out = api.remove_members(audience=name, recipients=["+44 7700 900123", "nonsense", "447700900199"])
		self.assertEqual((out["removed"], out["member_count"]), (1, 2))
		self.assertNotIn("447700900123", self.members(name))

	def test_members_cannot_be_written_outside_the_api(self):
		name = self.make()
		frappe.flags.in_audience_api = False
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": aud.MEMBER, "audience": name, "recipient": "447700900123"}).insert(ignore_permissions=True)

	def test_member_is_unique_per_audience_and_recipient(self):
		a, b = self.make(title="A"), self.make(title="B")
		_import(a, rows=[{"phone": "447700900123"}])
		_import(b, rows=[{"phone": "447700900123"}])
		self.assertEqual(frappe.db.count(aud.MEMBER, {"recipient": "447700900123"}), 2)
		frappe.flags.in_audience_api = True
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": aud.MEMBER, "audience": a, "recipient": "447700900123"}).insert(ignore_permissions=True)


class TestSelectionPreview(AudienceTestCase):
	def test_overlap_exclude_suppression_and_purpose(self):
		a, b, c = self.make(title="A"), self.make(title="B", purposes=("utility",)), self.make(title="C")
		_import(a, rows=[{"phone": "447700900123"}, {"phone": "447700900124"}, {"phone": "447700900125"}])
		_import(b, rows=[{"phone": "447700900123"}, {"phone": "447700900126"}])
		_import(c, rows=[{"phone": "447700900125"}, {"phone": "447700900127"}])
		frappe.get_doc({"doctype": "Gateway Access Entry", "name": "GAE-AUD-2", "gateway": GW, "entry_type": "Sender",
						"external_id": "447700900124", "state": "opted_out"}).db_insert()  # fmt: skip
		bc = self.draft_broadcast(a)
		selection = [{"audience": a}, {"audience": b}, {"audience": c, "exclude": True, "tags": []}]
		with patch.object(aud, "template_category", return_value="MARKETING"):
			out = api.preview_audience_selection(broadcast=bc, selection=selection)
		self.assertTrue(out["success"], out)
		self.assertEqual(out["blocked"][0]["code"], "audience_purpose_mismatch")
		self.assertEqual(out["blocked"][0]["audience"], b)
		self.assertEqual(out["counts"], {"total": 5, "dupes": 0, "excluded": 1, "suppressed": 1,
										"blocked_by_purpose": 2, "final": 1})  # fmt: skip
		with patch.object(aud, "template_category", return_value="UTILITY"):
			out = api.preview_audience_selection(broadcast=bc, selection=[{"audience": b}, {"audience": a}])
		self.assertEqual(out["blocked"][0]["audience"], a)
		self.assertEqual(out["counts"]["final"], 2)

	def test_dupes_counted_across_included_lists(self):
		a, b = self.make(title="A"), self.make(title="B")
		_import(a, rows=[{"phone": "447700900123"}, {"phone": "447700900124"}])
		_import(b, rows=[{"phone": "447700900123"}])
		bc = self.draft_broadcast(a)
		with patch.object(aud, "template_category", return_value="MARKETING"):
			out = api.preview_audience_selection(broadcast=bc, selection=[{"audience": a}, {"audience": b}])
		self.assertEqual((out["counts"]["dupes"], out["counts"]["final"], out["counts"]["total"]), (1, 2, 3))

	def test_rejects_other_gateway_and_empty_selection(self):
		a = self.make()
		bc = self.draft_broadcast(a)
		self.assertEqual(api.preview_audience_selection(broadcast=bc, selection=[])["error"], "invalid")
		self.assertEqual(api.preview_audience_selection(broadcast=bc, selection=[{"audience": "WAUD-nope"}])["error"], "invalid")
		self.assertEqual(api.preview_audience_selection(broadcast="BCAST-none", selection=[{"audience": a}])["error"], "not_found")


class TestDeleteAndRenameGuard(AudienceTestCase):
	def test_delete_and_rename_blocked_while_unfinished_broadcast_uses_audience(self):
		for status in ("Draft", "Running"):
			with self.subTest(status=status):
				name = self.make(title=f"Used {status}")
				_import(name, rows=[{"phone": "447700900123"}])
				bc = self.draft_broadcast(name, status=status)
				self.assertEqual(api.delete_audience(audience=name)["error"], "audience_in_use")
				self.assertTrue(frappe.db.exists(aud.AUDIENCE, name))
				self.assertEqual(api.update_audience(audience=name, title="New name")["error"], "invalid")
				self.assertEqual(frappe.db.get_value(aud.AUDIENCE, name, "title"), f"Used {status}")
				self.assertEqual(api.update_audience(audience=name, description="ok")["success"], True)
				self.assertEqual([u["name"] for u in api.get_audience(audience=name)["audience"]["used_by"]], [bc])
				with self.assertRaises(frappe.ValidationError):
					frappe.delete_doc(aud.AUDIENCE, name, ignore_permissions=True)

	def test_delete_allowed_after_broadcast_finished_and_removes_members(self):
		name = self.make()
		_import(name, rows=[{"phone": "447700900123"}])
		self.draft_broadcast(name, status="Completed")
		self.assertTrue(api.delete_audience(audience=name)["success"])
		self.assertFalse(frappe.db.exists(aud.AUDIENCE, name))
		self.assertEqual(frappe.db.count(aud.MEMBER, {"audience": name}), 0)

	def test_list_audiences_hides_adhoc_unless_asked(self):
		keep, adhoc = self.make(title="Library"), self.make(title="Pasted", is_adhoc=1)
		names = lambda **kw: {a["name"] for a in api.list_audiences(gateway=GW, **kw)["audiences"]}  # noqa: E731
		self.assertIn(keep, names())
		self.assertNotIn(adhoc, names())
		self.assertIn(adhoc, names(include_adhoc=1))
		self.assertEqual(names(search="Libra"), {keep})
