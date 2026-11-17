# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""HUFCRM-07: externally managed audiences (upsert API, server-side read-only, refresh before start)."""

from unittest.mock import patch

import frappe

from huf.ai.whatsapp.broadcast import runner
from huf.ai.whatsapp.broadcast.audiences import api, external
from huf.ai.whatsapp.broadcast.audiences import importer as imp
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast.checks.start_gate import StartRefused
from huf.ai.whatsapp.tests.test_whatsapp_audience_api import GW, AudienceTestCase, _limits

CREATE = dict(
	gateway=GW, title="Loyal", consent_source="loyalty signup", consent_basis="opt-in form",
	consent_purposes=["marketing"], consent_attested=True,
)  # fmt: skip


def _m(n, **kw):
	return {"recipient": f"9198000000{n:02d}", "display_name": f"N{n}", "consent_source": "app", "consent_at": "2024-01-01", **kw}


class TestUpsertAtomicity(AudienceTestCase):
	def up(self, audience=None, members=None, **kw):
		kw.setdefault("source", "loyalty")
		return external.upsert_audience_members(audience=audience, members=members, **kw)

	def made(self):
		out = self.up(members=[_m(1), _m(2)], create=CREATE)
		self.assertTrue(out.get("success"), out)
		return out["audience"]

	def members(self, name):
		return set(frappe.get_all(aud.MEMBER, {"audience": name}, pluck="recipient"))

	def test_replace_with_no_members_is_refused(self):
		name = self.made()
		self.assertEqual(self.up(name, [], mode="replace")["error"], "empty_replace")
		self.assertEqual(len(self.members(name)), 2)

	def test_failure_mid_apply_rolls_back_and_keeps_members_and_key(self):
		name = self.made()
		before = self.members(name)
		with patch.object(imp, "import_rows", side_effect=RuntimeError("db gone")):
			with self.assertRaises(RuntimeError):
				self.up(name, [_m(7)], mode="replace", idempotency_key="k9")
		self.assertEqual(self.members(name), before)
		self.assertFalse(self.up(name, [_m(7)], mode="replace", idempotency_key="k9")["noop"])  # key was released

	def test_replace_inserts_new_and_removes_stale(self):
		name = self.made()
		out = self.up(name, [_m(2), _m(3)], mode="replace")
		self.assertEqual((out["added"], out["removed"]), (1, 1))
		self.assertEqual(self.members(name), {"919800000002", "919800000003"})

	def test_recent_keys_detect_a_b_a_replay(self):
		name = self.made()
		self.assertFalse(self.up(name, [_m(3)], mode="merge", idempotency_key="A")["noop"])
		self.assertFalse(self.up(name, [_m(4)], mode="merge", idempotency_key="B")["noop"])
		self.assertTrue(self.up(name, [_m(5)], mode="merge", idempotency_key="A")["noop"])
		self.assertNotIn("919800000005", self.members(name))

	def test_key_claim_takes_the_audience_lock_first(self):
		name = self.made()
		with patch.object(frappe.db, "get_value", wraps=frappe.db.get_value) as spy:
			self.up(name, [_m(3)], mode="merge", idempotency_key="L")
		self.assertTrue(any(c.kwargs.get("for_update") for c in spy.call_args_list))


class TestRefreshDeadline(AudienceTestCase):
	def test_timeout_fails_closed_and_does_not_hang(self):
		import threading
		import time

		release = threading.Event()
		started = time.monotonic()
		with self.assertRaises(TimeoutError):
			external._call_with_deadline(lambda **kw: release.wait(5), 1)
		release.set()
		self.assertLess(time.monotonic() - started, 3)

	def test_hook_result_and_error_cross_the_thread(self):
		calls = []
		external._call_with_deadline(lambda **kw: calls.append(kw), 5, audience="a")
		self.assertEqual(calls, [{"audience": "a"}])
		with self.assertRaises(ValueError):
			external._call_with_deadline(lambda **kw: (_ for _ in ()).throw(ValueError("x")), 5)

	def test_timeout_blocks_start(self):
		bc = self.draft_broadcast(self.make("Slow"))
		with patch.object(frappe, "get_hooks", side_effect=lambda key=None, *a, **k: ["app.slow"] if key == external.HOOK else []), \
			patch.object(external, "_call_with_deadline", side_effect=TimeoutError("no answer within 1s")), \
			patch.object(external, "external_audiences", return_value=[{"name": "x", "managed_by": "loyalty"}]):
			with self.assertRaises(StartRefused) as ctx:
				runner._refresh_external_audiences(bc)
		self.assertEqual(ctx.exception.code, "audience_refresh_failed")


class TestUpsert(AudienceTestCase):
	def up(self, audience=None, members=None, **kw):
		kw.setdefault("source", "loyalty")
		return external.upsert_audience_members(audience=audience, members=members, **kw)

	def made(self):
		out = self.up(members=[_m(1), _m(2)], create=CREATE)
		self.assertTrue(out.get("success"), out)
		return out["audience"]

	def test_create_flags_audience_and_keeps_member_consent(self):
		name = self.made()
		row = frappe.db.get_value(aud.AUDIENCE, name, ["externally_managed", "managed_by"], as_dict=True)
		self.assertEqual((row.externally_managed, row.managed_by), (1, "loyalty"))
		member = frappe.get_all(aud.MEMBER, {"audience": name}, ["consent_source", "source"])[0]
		self.assertEqual((member.consent_source, member.source), ("app", "loyalty"))

	def test_replace_removes_stale_merge_keeps(self):
		name = self.made()
		self.up(name, [_m(2), _m(3)], mode="merge")
		self.assertEqual(len(self.members(name)), 3)
		out = self.up(name, [_m(3)], mode="replace")
		self.assertEqual(out["removed"], 2)
		self.assertEqual(len(self.members(name)), 1)

	def test_other_source_and_manual_audience_refused(self):
		name = self.made()
		self.assertEqual(self.up(name, [_m(1)], source="crm")["error"], "source_mismatch")
		manual = self.make("Manual")
		self.assertEqual(self.up(manual, [_m(1)])["error"], "not_externally_managed")

	def test_idempotency_key_makes_repeat_a_noop(self):
		name = self.made()
		first = self.up(name, [_m(5)], mode="merge", idempotency_key="k1")
		self.assertFalse(first["noop"])
		again = self.up(name, [_m(6)], mode="merge", idempotency_key="k1")
		self.assertTrue(again["noop"])
		self.assertNotIn("919800000006", self.members(name))
		self.assertFalse(self.up(name, [_m(6)], mode="merge", idempotency_key="k2")["noop"])

	def test_size_cap_and_empty_feed_guard(self):
		name = self.made()
		with _limits(audience_external_max_members=1):
			self.assertEqual(self.up(name, [_m(1), _m(2)])["error"], "too_many")
		out = self.up(name, [{"recipient": "abc"}])
		self.assertEqual(out["error"], "no_valid_members")
		self.assertEqual(len(self.members(name)), 2)

	def test_source_and_mode_validated(self):
		self.assertEqual(self.up(members=[], source="", create=CREATE)["error"], "source_required")
		self.assertEqual(self.up(members=[], mode="x", create=CREATE)["error"], "invalid")


class TestReadOnly(AudienceTestCase):
	def test_manual_paths_refused_server_side(self):
		name = external.upsert_audience_members(audience=None, members=[_m(1)], source="loyalty", create=CREATE)["audience"]
		for out in (
			api.update_audience(audience=name, title="x"),
			api.delete_audience(audience=name),
			api.import_members(audience=name, rows=[{"phone": "919811111111"}]),
			api.remove_members(audience=name, recipients=["919800000001"]),
		):
			self.assertEqual(out["error"], "invalid")
			self.assertIn("managed by loyalty", out["message"] if "message" in out else str(out))
		with self.assertRaises(frappe.ValidationError):
			imp.import_rows(name, [_m(9)])
		self.assertEqual(len(self.members(name)), 1)


class TestRefreshBeforeStart(AudienceTestCase):
	def setUp(self):
		super().setUp()
		name = external.upsert_audience_members(audience=None, members=[_m(1)], source="loyalty", create=CREATE)["audience"]
		self.audience = name
		self.broadcast = self.draft_broadcast(name)

	def hooks(self, paths):
		real = frappe.get_hooks
		return patch.object(frappe, "get_hooks", side_effect=lambda key=None, *a, **k: paths if key == external.HOOK else real(key, *a, **k))

	def test_no_hook_fails_closed(self):
		with self.hooks([]), self.assertRaises(external.RefreshFailed):
			external.run_refresh_hooks(self.broadcast)

	def test_hook_called_with_audience(self):
		fake = patch.object(frappe, "get_attr", return_value=lambda **kw: calls.append(kw))
		calls = []
		with self.hooks(["app.refresh"]), fake:
			self.assertTrue(external.run_refresh_hooks(self.broadcast))
		self.assertEqual(calls, [{"audience": self.audience, "managed_by": "loyalty"}])

	def test_hook_error_blocks_start(self):
		def boom(**kw):
			raise RuntimeError("down")

		with self.hooks(["app.refresh"]), patch.object(frappe, "get_attr", return_value=boom):
			with self.assertRaises(StartRefused) as ctx:
				runner._refresh_external_audiences(self.broadcast)
		self.assertEqual(ctx.exception.code, "audience_refresh_failed")

	def test_manual_audience_needs_no_hook(self):
		other = self.draft_broadcast(self.make("Plain"))
		self.assertFalse(external.run_refresh_hooks(other))
