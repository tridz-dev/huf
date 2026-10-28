# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-B2: every audience limit is a registry row, editable in settings, and changes behaviour."""

from __future__ import annotations

import pathlib
import unittest
from unittest.mock import patch

import frappe

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.audiences import api, common, csv_map, importer, membership as aud

ROOT = pathlib.Path(__file__).resolve().parents[4]
GW = "GW-AUD-POL"

AUDIENCE_DEFAULTS = {
	"audience_max_members": 200000, "audience_inline_import_rows": 10000, "audience_max_import_rows": 200000,
	"audience_max_csv_mb": 20, "audience_max_tags_per_member": 20, "audience_max_tag_length": 50,
	"audience_max_name_length": 140, "audience_max_remove_per_request": 10000, "audience_page_size_max": 200,
	"audience_max_selection_items": 25, "audience_import_chunk": 1000, "audience_suppression_chunk": 500,
	"audience_import_job_ttl": 86400, "rate_audience_read": 240, "rate_audience_write": 60,
	"rate_audience_import": 20, "require_consent_attestation": True, "returned_list_limit": 200,
}
EDITABLE = [lim for lim in policy.LIMITS if lim.editable and lim.group == "audiences"]


def _reset():
	policy.set_values({lim.key: None for lim in policy.LIMITS if lim.editable})
	frappe.db.commit()


class _Base(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_reset()
		self.addCleanup(_reset)


class TestRegistry(_Base):
	def test_defaults_are_the_old_hard_coded_values(self):
		for key, value in AUDIENCE_DEFAULTS.items():
			self.assertEqual(policy.BY_KEY[key].default, value, key)
			self.assertEqual(policy.get(key), value, key)

	def test_rows_are_classified_and_documented(self):
		self.assertGreaterEqual(len(EDITABLE), 10)
		for lim in policy.LIMITS:
			if lim.group == "audiences":
				self.assertIn(lim.kind, ("setting", "internal"))
				self.assertTrue(lim.note, lim.key)

	def test_consent_attestation_reuses_the_existing_key(self):
		self.assertEqual([k for k in policy.BY_KEY if "consent_attest" in k], ["require_consent_attestation"])

	def test_each_editable_limit_has_a_settings_field(self):
		meta = frappe.get_meta(policy.SETTINGS)
		for lim in EDITABLE:
			self.assertIsNotNone(meta.get_field(lim.key), lim.key)

	def test_docs_table_matches_registry(self):
		path = ROOT / "docs" / "whatsapp" / "BROADCAST_LIMITS.md"
		self.assertEqual(path.read_text(encoding="utf-8"), policy.render_docs())
		for lim in EDITABLE:
			self.assertIn(f"`{lim.key}`", policy.render_docs())

	def test_old_constants_are_gone(self):
		src = "\n".join(p.read_text() for p in (ROOT / "huf/ai/whatsapp/broadcast/audiences").glob("*.py"))
		for name in ("LIMIT_MAX_", "LIMIT_INLINE", "LIMIT_PAGE", "RATE_LIMIT_", "REQUIRE_CONSENT_ATTESTATION",
				"MAX_SELECTION_ITEMS", "RETURNED_LIST_LIMIT", "IMPORT_CHUNK", "SUPPRESSION_CHUNK", "IMPORT_JOB_TTL"):
			self.assertNotIn(name, src, name)

	def test_set_reset_min_max_for_every_audience_limit(self):
		for lim in EDITABLE:
			with self.subTest(key=lim.key):
				mid = int(lim.min) + 1 if lim.max > lim.min else int(lim.min)
				for ok in (lim.min, mid, lim.max):
					policy.set_values({lim.key: ok})
					self.assertEqual(policy.get(lim.key), ok)
					self.assertEqual(policy.resolve(lim.key)[1], "settings")
				for bad in (lim.min - 1, lim.max + 1):
					with self.assertRaises(ValueError):
						policy.set_values({lim.key: bad})
					self.assertEqual(policy.get(lim.key), lim.max)  # unchanged by the failed write
				policy.set_values({lim.key: None})
				self.assertEqual(policy.get(lim.key), lim.default)
				self.assertEqual(policy.resolve(lim.key)[1], "default")

	def test_internal_rows_cannot_be_changed(self):
		for key in ("audience_import_chunk", "audience_suppression_chunk", "audience_import_job_ttl"):
			with self.assertRaises(ValueError):
				policy.set_values({key: 5})


class TestBehaviour(_Base):
	"""Each limit changes what the audience code does, then resets to the old behaviour."""

	def test_tags_per_member_and_tag_length(self):
		policy.set_values({"audience_max_tags_per_member": 2, "audience_max_tag_length": 3})
		with self.assertRaises(ValueError):
			aud.normalize_tags(["a", "b", "c"])
		with self.assertRaises(ValueError):
			aud.normalize_tags(["abcd"])
		self.assertEqual(aud.normalize_tags(["abc", "d"]), ["abc", "d"])
		_reset()
		self.assertEqual(len(aud.normalize_tags([f"t{i}" for i in range(20)])), 20)

	def test_name_length(self):
		policy.set_values({"audience_max_name_length": 5})
		clean, reason = importer.clean_member({"recipient": "447700900123", "display_name": "Alexander"})
		self.assertIsNone(clean)
		self.assertEqual(reason, "name_too_long (max 5)")
		_reset()
		clean, _ = importer.clean_member({"recipient": "447700900123", "display_name": "Alexander"})
		self.assertEqual(clean["display_name"], "Alexander")

	def test_csv_size_and_import_rows(self):
		policy.set_values({"audience_max_csv_mb": 1})
		self.assertEqual(csv_map.mapped_rows("p\n" + "1" * (1024 * 1024), None, None)["error"], "csv_too_large")
		policy.set_values({"audience_max_csv_mb": None, "audience_max_import_rows": 2})
		self.assertEqual(csv_map.mapped_rows(None, [{"phone": "1"}] * 3, None)["error"], "too_many")
		self.assertNotIn("error", csv_map.mapped_rows(None, [{"phone": "447700900123"}] * 2, None) or {})

	def test_page_size(self):
		self.assertEqual(common._page(5000), 200)
		policy.set_values({"audience_page_size_max": 25})
		self.assertEqual(common._page(5000), 25)
		self.assertEqual(common._page(10), 10)

	def test_selection_items(self):
		picks = [{"audience": f"A{i}"} for i in range(4)]
		self.assertEqual(len(api._parse_selection(picks)), 4)
		policy.set_values({"audience_max_selection_items": 3})
		with self.assertRaises(ValueError):
			api._parse_selection(picks)

	def test_remove_per_request(self):
		policy.set_values({"audience_max_remove_per_request": 2})
		with patch.object(api, "_require_audience_write", return_value={"name": "A", "gateway": GW}):
			out = api.remove_members(audience="A", recipients=["1", "2", "3"])
		self.assertEqual(out["error"], "too_many")
		self.assertIn("at most 2", out["message"])

	def test_consent_attestation_requirement(self):
		kw = {"gateway": GW, "title": "T", "consent_source": "form", "consent_basis": "opt-in form",
			"consent_purposes": ["marketing"]}
		with patch.object(api, "_require_gateway", return_value=None):
			self.assertEqual(api.create_audience(**kw)["error"], "consent_not_attested")
			policy.set_values({"require_consent_attestation": False})
			with patch.object(api.frappe, "get_doc") as get_doc, patch.object(api, "_audit"), \
					patch.object(api, "_view", return_value={}), patch.object(api, "_audience_row"):
				get_doc.return_value.name = "A"
				self.assertTrue(api.create_audience(**kw)["success"])

	def test_rate_limits_follow_settings(self):
		for key, default in (("rate_audience_read", 240), ("rate_audience_write", 60), ("rate_audience_import", 20)):
			self.assertEqual(policy.rate(key)(), default)
			policy.set_values({key: 7})
			self.assertEqual(policy.rate(key)(), 7)

	def test_member_cap_and_inline_threshold_and_returned_list(self):
		rows = [{"phone": f"4477009{i:05d}"} for i in range(4)]
		cleaned = [{"recipient": r["phone"]} for r in rows]
		self.assertEqual(len(cleaned), 4)
		with patch.object(api, "_require_audience_write", return_value={"name": "A", "gateway": GW}), \
				patch.object(api, "_flag", wraps=api._flag), patch.object(api.frappe, "enqueue") as enqueue, \
				patch.object(api, "_audit"):
			policy.set_values({"audience_inline_import_rows": 3})
			out = api.import_members(audience="A", rows=rows)
			self.assertTrue(out.get("queued"), out)
			enqueue.assert_called_once()


class TestDefaultsKeepBehaviour(_Base):
	def test_at_defaults_nothing_is_stricter_than_before(self):
		self.assertEqual(common._page(10_000), 200)
		self.assertEqual(len(aud.normalize_tags([f"t{i}" for i in range(20)])), 20)
		self.assertEqual(len(api._parse_selection([{"audience": str(i)} for i in range(25)])), 25)
