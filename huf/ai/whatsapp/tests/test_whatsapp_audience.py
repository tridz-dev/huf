# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-B: audience membership logic that needs no database (expansion, tag filters, validation, masking)."""

import unittest
from unittest.mock import patch

from huf.ai.whatsapp.broadcast import audience as aud
from huf.ai.whatsapp.broadcast.audience_parts import importer as imp


def _aud(name, marketing=1, utility=0, source="form", default_at="2026-01-01 00:00:00"):
	return {
		"name": name,
		"title": name,
		"purpose_marketing": marketing,
		"purpose_utility": utility,
		"purpose_events": 0,
		"consent_source": source,
		"default_consent_at": default_at,
		"consent_attested_at": "2026-02-01 00:00:00",
	}


def _m(recipient, tags=(), params=None, source=None, consent_at=None, name=None):
	return {
		"recipient": recipient,
		"tags": list(tags),
		"params": params,
		"consent_source": source,
		"consent_at": consent_at,
		"display_name": name,
	}


def _sel(audience, exclude=False, tags=(), mode="any"):
	return {"audience": audience, "exclude": exclude, "tags": list(tags), "tag_filter_mode": mode}


A = _aud("A", source="a-form")
B = _aud("B", source="b-form", default_at=None)
AUDS = {"A": A, "B": B}
MEMBERS = {
	"A": [_m("911", ["vip", "eu"], {"body": ["a"]}), _m("912", ["vip"]), _m("913", ["eu"], source="own", consent_at="2026-03-01")],
	"B": [_m("912", [], {"body": ["b"]}), _m("914", ["vip"]), _m("915")],
}


class TestTags(unittest.TestCase):
	def test_normalize_splits_lowers_and_dedupes(self):
		self.assertEqual(aud.normalize_tags("VIP; eu, vip |  New  York"), ["vip", "eu", "new york"])
		self.assertEqual(aud.normalize_tags(["A", " a ", ""]), ["a"])
		self.assertEqual(aud.normalize_tags('["X","y"]'), ["x", "y"])
		self.assertEqual(aud.normalize_tags(None), [])

	def test_overlong_and_too_many_tags_rejected(self):
		with self.assertRaises(ValueError):
			aud.normalize_tags(["x" * (aud.LIMIT_MAX_TAG_LENGTH + 1)])
		with self.assertRaises(ValueError):
			aud.normalize_tags([f"t{i}" for i in range(aud.LIMIT_MAX_TAGS_PER_MEMBER + 1)])

	def test_any_and_all_modes(self):
		self.assertTrue(aud.tags_match(["vip"], ["vip", "eu"], "any"))
		self.assertFalse(aud.tags_match(["vip"], ["vip", "eu"], "all"))
		self.assertTrue(aud.tags_match(["vip", "eu", "x"], ["vip", "eu"], "all"))
		self.assertFalse(aud.tags_match([], ["vip"], "any"))
		self.assertTrue(aud.tags_match([], [], "all"))  # no filter keeps everyone


class TestExpandSelection(unittest.TestCase):
	def run_sel(self, selection, suppressed=None, category=None, auds=AUDS):
		return aud.expand_selection(selection, auds, MEMBERS, suppressed, category)

	def recipients(self, result):
		return [r["recipient"] for r in result["rows"]]

	def test_overlap_is_deduped_and_first_list_wins(self):
		out = self.run_sel([_sel("A"), _sel("B")])
		self.assertEqual(self.recipients(out), ["911", "912", "913", "914", "915"])
		dup = next(r for r in out["rows"] if r["recipient"] == "912")
		self.assertEqual(dup["audience"], "A")
		self.assertIsNone(dup["params"])  # A's 912 has none; B's params must not leak in
		self.assertEqual(out["counts"]["dupes"], 1)
		self.assertEqual(out["counts"]["total"], 6)
		self.assertEqual(out["counts"]["final"], 5)

	def test_first_list_params_and_consent_win(self):
		out = self.run_sel([_sel("B"), _sel("A")])
		row = next(r for r in out["rows"] if r["recipient"] == "912")
		self.assertEqual(row["audience"], "B")
		self.assertEqual(row["params"], {"body": ["b"]})
		self.assertEqual(row["consent_source"], "b-form")
		# B has no default date, so the attestation time is the fallback
		self.assertEqual(row["consent_at"], "2026-02-01 00:00:00")

	def test_member_consent_overrides_audience_default(self):
		row = next(r for r in self.run_sel([_sel("A")])["rows"] if r["recipient"] == "913")
		self.assertEqual((row["consent_source"], row["consent_at"]), ("own", "2026-03-01"))
		row = next(r for r in self.run_sel([_sel("A")])["rows"] if r["recipient"] == "911")
		self.assertEqual((row["consent_source"], row["consent_at"]), ("a-form", "2026-01-01 00:00:00"))

	def test_exclude_list_removes_contacts_even_when_listed_first_or_last(self):
		for selection in ([_sel("A"), _sel("B", exclude=True)], [_sel("B", exclude=True), _sel("A")]):
			out = self.run_sel(selection)
			self.assertEqual(self.recipients(out), ["911", "913"])
			self.assertEqual(out["counts"]["excluded"], 1)

	def test_exclude_with_tag_filter_only_excludes_matches(self):
		out = self.run_sel([_sel("A"), _sel("B", exclude=True, tags=["vip"])])
		self.assertEqual(self.recipients(out), ["911", "912", "913"])
		self.assertEqual(out["counts"]["excluded"], 0)

	def test_tag_filters_on_include(self):
		self.assertEqual(self.recipients(self.run_sel([_sel("A", tags=["vip"])])), ["911", "912"])
		self.assertEqual(self.recipients(self.run_sel([_sel("A", tags=["vip", "eu"], mode="all")])), ["911"])
		self.assertEqual(self.recipients(self.run_sel([_sel("A", tags=["vip", "eu"], mode="any")])), ["911", "912", "913"])

	def test_suppressed_rows_stay_flagged_and_do_not_count_as_final(self):
		out = self.run_sel([_sel("A")], suppressed={"912": "opted_out"})
		self.assertEqual(len(out["rows"]), 3)
		self.assertEqual({r["recipient"]: r["suppressed"] for r in out["rows"]}["912"], "opted_out")
		self.assertEqual((out["counts"]["suppressed"], out["counts"]["final"]), (1, 2))

	def test_marketing_template_blocks_audience_without_marketing_purpose(self):
		auds = {"A": _aud("A", marketing=0, utility=1), "B": B}
		out = self.run_sel([_sel("A"), _sel("B")], category="MARKETING", auds=auds)
		self.assertEqual(out["blocked_audiences"], ["A"])
		self.assertEqual(out["counts"]["blocked_by_purpose"], 3)
		self.assertEqual(self.recipients(out), ["912", "914", "915"])

	def test_utility_template_accepts_utility_audience_and_rejects_marketing_only(self):
		auds = {"A": _aud("A", marketing=0, utility=1), "B": B}
		out = self.run_sel([_sel("A"), _sel("B")], category="UTILITY", auds=auds)
		self.assertEqual(out["blocked_audiences"], ["B"])
		self.assertEqual(len(out["rows"]), 3)

	def test_unknown_category_does_not_block(self):
		self.assertEqual(self.run_sel([_sel("A")], category=None)["blocked_audiences"], [])

	def test_counts_identity(self):
		auds = {"A": A, "B": _aud("B", marketing=0, utility=1)}
		out = self.run_sel([_sel("A"), _sel("B"), _sel("A", exclude=True, tags=["eu"])], category="MARKETING", auds=auds)
		c = out["counts"]
		self.assertEqual(c["total"], c["excluded"] + c["dupes"] + c["blocked_by_purpose"] + len(out["rows"]))

	def test_unknown_audience_raises(self):
		with self.assertRaises(ValueError):
			self.run_sel([_sel("NOPE")])

	def test_does_not_touch_database(self):
		with patch.object(aud, "frappe") as fr:
			self.run_sel([_sel("A"), _sel("B", exclude=True)], suppressed={"911": "opted_out"}, category="MARKETING")
			self.assertEqual(fr.method_calls, [])


class TestCleanMember(unittest.TestCase):
	def test_valid_row_is_normalised(self):
		clean, reason = imp.clean_member({"recipient": "+44 7700 900123", "display_name": " Ann ", "tags": "VIP,eu"})
		self.assertIsNone(reason)
		self.assertEqual((clean["recipient"], clean["display_name"], clean["tags"]), ("447700900123", "Ann", ["vip", "eu"]))

	def test_invalid_numbers(self):
		for bad in ("", None, "abc", "1234567", "1" * 16):
			self.assertEqual(imp.clean_member({"recipient": bad})[1], "invalid_number", bad)

	def test_bsuid_refused(self):
		self.assertEqual(imp.clean_member({"recipient": "IN.4608123"})[1], "bsuid_not_supported")

	def test_overlong_name_and_tags(self):
		self.assertIn("name_too_long", imp.clean_member({"recipient": "447700900123", "display_name": "n" * 141})[1])
		self.assertIn("invalid_tags", imp.clean_member({"recipient": "447700900123", "tags": "x" * 60})[1])

	def test_future_consent_date_refused(self):
		self.assertEqual(
			imp.clean_member({"recipient": "447700900123", "consent_at": "2999-01-01"})[1], "consent_date_in_future"
		)
		self.assertEqual(imp.clean_member({"recipient": "447700900123", "consent_at": "not a date"})[1], "invalid_consent_date")


class TestMaskAndPurpose(unittest.TestCase):
	def test_mask_keeps_last_four(self):
		self.assertEqual(aud.mask_phone("447700900123"), "********0123")
		self.assertEqual(aud.mask_phone("123"), "123")
		self.assertIsNone(aud.mask_phone(None))

	def test_category_to_purpose(self):
		self.assertEqual(aud.purpose_for_category("marketing"), "marketing")
		self.assertEqual(aud.purpose_for_category("UTILITY"), "utility")
		self.assertIsNone(aud.purpose_for_category("???"))
