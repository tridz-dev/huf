# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-A2: gating/warning contract in ``limits.preview`` and ``api.start_broadcast`` / ``preview_broadcast``.

Mock-based (no bench state): DB helpers, Graph and the runner are patched.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.PermissionError = PermissionError

from huf.ai.whatsapp.broadcast import api as mgmt  # noqa: E402
from huf.ai.whatsapp.broadcast import limits as bl  # noqa: E402
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override  # noqa: E402
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_limits import (  # noqa: E402
	LIMIT_OK, _codes, _FakeCache, _PreviewBase,
)
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_management import BC, GW, _Base, _Refused, _row  # noqa: E402

FROZEN_BLOCKING = {
	"template_not_approved", "consent_not_attested", "another_broadcast_running", "no_recipients",
	"missing_params", "gateway_disconnected", "audience_purpose_mismatch", "template_unavailable",
}
FROZEN_WARNINGS = {"quality_red", "quality_yellow", "over_budget", "tier_unknown", "other_broadcast_running"}


class TestIssueShape(_PreviewBase):
	def _all_issues(self):
		out = []
		with patch.object(bl, "_template_row", return_value={"status": "PAUSED", "category": "MARKETING"}), \
			patch.object(bl, "_running_others", return_value=["B2"]), \
			patch.object(bl, "_used_24h", return_value=245), \
			patch.object(bl, "_gateway_disconnected", return_value="down"), \
			patch.object(bl, "_broadcast_row", return_value={"gateway": "G", "template": "t", "consent_attested": 0}), \
			patch.object(bl, "get_messaging_limit", return_value=dict(LIMIT_OK, quality="RED")):
			self.counts = {}
			out.append(self._preview())
		return out[0]

	def test_every_entry_is_code_message_limit_key(self):
		out = self._all_issues()
		self.assertTrue(out["blocking"] and out["warnings"])
		for issue in out["blocking"] + out["warnings"]:
			self.assertEqual(set(issue), {"code", "message", "limit_key"})
			self.assertTrue(issue["message"])

	def test_only_frozen_codes(self):
		out = self._all_issues()
		self.assertEqual(set(_codes(out["blocking"])) - FROZEN_BLOCKING, set())
		self.assertEqual(set(_codes(out["warnings"])) - FROZEN_WARNINGS, set())
		self.assertEqual(
			set(_codes(out["blocking"])),
			{"template_not_approved", "consent_not_attested", "another_broadcast_running", "no_recipients", "gateway_disconnected"},
		)

	def test_no_recipients_blocks(self):
		self.counts = {"skipped": 3}
		self.assertEqual(_codes(self._preview()["blocking"]), ["no_recipients"])

	def test_missing_template_is_template_unavailable(self):
		with patch.object(bl, "_template_row", return_value=None):
			self.assertEqual(_codes(self._preview()["blocking"]), ["template_unavailable"])

	def test_gateway_disconnected_blocks(self):
		with patch.object(bl, "_gateway_disconnected", return_value="Reconnect it"):
			out = self._preview()
		self.assertEqual(_codes(out["blocking"]), ["gateway_disconnected"])
		self.assertEqual(out["blocking"][0]["message"], "Reconnect it")


class TestPreviewBehaviourChanges(_PreviewBase):
	"""Deliberate v2 changes: RED quality and over-budget no longer block."""

	def test_red_quality_does_not_block(self):
		with patch.object(bl, "get_messaging_limit", return_value=dict(LIMIT_OK, quality="RED")):
			out = self._preview()
		self.assertEqual(out["blocking"], [])
		self.assertEqual(_codes(out["warnings"]), ["quality_red"])
		self.assertEqual(out["warnings"][0]["limit_key"], "quality_rating")

	def test_over_budget_does_not_block(self):
		with patch.object(bl, "_used_24h", return_value=250):
			out = self._preview()
		self.assertEqual(out["blocking"], [])
		self.assertEqual(_codes(out["warnings"]), ["over_budget"])
		self.assertEqual(out["remaining_24h"], 0)
		self.assertFalse(out["within_limit"])


class TestSettingsWiring(_PreviewBase):
	def test_one_active_on_blocks(self):
		with patch.object(bl, "_running_others", return_value=["B9"]):
			out = self._preview()
		self.assertEqual(_codes(out["blocking"]), ["another_broadcast_running"])
		self.assertEqual(out["blocking"][0]["limit_key"], "one_active_per_gateway")
		self.assertEqual(out["warnings"], [])

	def test_one_active_off_downgrades_to_warning(self):
		with limit_override(one_active_per_gateway=False), patch.object(bl, "_running_others", return_value=["B9"]):
			out = self._preview()
		self.assertEqual(out["blocking"], [])
		self.assertEqual(_codes(out["warnings"]), ["other_broadcast_running"])
		self.assertNotIn("one_active_per_gateway", out["limits_in_effect"])

	def test_consent_attestation_off_does_not_block(self):
		row = {"gateway": "GW-1", "template": "tpl-1", "consent_attested": 0}
		with limit_override(require_consent_attestation=False), patch.object(bl, "_broadcast_row", return_value=row):
			out = self._preview()
		self.assertEqual(out["blocking"], [])
		self.assertNotIn("require_consent_attestation", out["limits_in_effect"])

	def test_consent_attestation_on_blocks(self):
		row = {"gateway": "GW-1", "template": "tpl-1", "consent_attested": 0}
		with patch.object(bl, "_broadcast_row", return_value=row):
			out = self._preview()
		self.assertEqual(_codes(out["blocking"]), ["consent_not_attested"])
		self.assertEqual(out["blocking"][0]["limit_key"], "require_consent_attestation")

	def test_limits_in_effect_lists_the_keys_that_applied(self):
		out = self._preview()
		self.assertEqual(
			out["limits_in_effect"],
			["messaging_tier_24h", "one_active_per_gateway", "quality_rating", "require_consent_attestation", "template_approved_only"],
		)

	def test_limits_in_effect_has_broadcast_cap_when_set(self):
		row = {"gateway": "GW-1", "template": "tpl-1", "consent_attested": 1, "max_recipients": 50}
		with patch.object(bl, "_broadcast_row", return_value=row):
			self.assertIn("max_recipients_default", self._preview()["limits_in_effect"])


class TestCacheTtl(unittest.TestCase):
	def test_cache_ttl_comes_from_policy(self):
		cache = _FakeCache()
		seen = {}
		cache.set_value = lambda key, value, expires_in_sec=None: seen.update(ttl=expires_in_sec)
		with limit_override(limits_cache_ttl_seconds=42), patch.object(bl.frappe, "cache", return_value=cache), \
			patch.object(bl.frappe.db, "exists", return_value=True), \
			patch.object(bl, "_fetch", return_value=dict(LIMIT_OK)):
			bl.get_messaging_limit("GW-1")
		self.assertEqual(seen["ttl"], 42)
		self.assertFalse(hasattr(bl, "CACHE_TTL_SECONDS"))


class TestStartApi(_Base):
	def setUp(self):
		super().setUp()
		self.row = _row(consent_attested=1)
		self.runner.StartRefused = _Refused
		self.runner.start.return_value = {"status": "Running"}

	def _start(self, count="3", ow=None):
		return mgmt.start_broadcast(BC, count, ow)

	def test_override_warnings_json_string_is_parsed_and_forwarded(self):
		self.assertTrue(self._start("3", '["over_budget", "quality_red"]')["success"])
		self.assertEqual(self.runner.start.call_args.kwargs["override_warnings"], ["over_budget", "quality_red"])

	def test_override_warnings_list_accepted(self):
		self._start("3", ["quality_yellow"])
		self.assertEqual(self.runner.start.call_args.kwargs["override_warnings"], ["quality_yellow"])

	def test_override_warnings_blank_means_none(self):
		self._start("3", "[]")
		self._start("3", None)
		self.assertEqual([c.kwargs["override_warnings"] for c in self.runner.start.call_args_list], [[], []])

	def test_malformed_override_warnings_refused(self):
		for bad in ("not json", '{"a": 1}', "[1, 2]"):
			self.assertEqual(self._start("3", bad)["error"], "invalid_override_warnings")
		self.runner.start.assert_not_called()

	def test_warnings_changed_is_relayed_with_new_warnings(self):
		new = [{"code": "over_budget", "message": "m", "limit_key": "messaging_tier_24h"}]
		self.runner.start.side_effect = _Refused("warnings_changed", "review again", warnings=new)
		res = self._start("3", "[]")
		self.assertEqual((res["success"], res["error"], res["warnings"]), (False, "warnings_changed", new))
		self.doc.add_comment.assert_not_called()

	def test_runner_refusals_become_structured_errors(self):
		self.runner.start.side_effect = _Refused("another_broadcast_running", "busy")
		res = self._start()
		self.assertEqual((res["success"], res["error"], res["message"]), (False, "another_broadcast_running", "busy"))

	def test_typed_count_required_by_default(self):
		self.assertEqual(self._start("2")["error"], "confirm_mismatch")
		self.runner.start.assert_not_called()

	def test_typed_count_not_needed_when_setting_off(self):
		with limit_override(require_typed_count=False):
			self.assertTrue(self._start(None)["success"])
		self.runner.start.assert_called_once()

	def test_api_key_caller_skips_typed_count_but_still_passes_warnings(self):
		self.frappe.get_request_header.return_value = "token abc:def"
		self.assertTrue(self._start(None, '["over_budget"]')["success"])
		self.assertEqual(self.runner.start.call_args.kwargs["override_warnings"], ["over_budget"])
		self.assertEqual(mgmt._is_api_key_caller(), True)

	def test_browser_session_is_not_api_key(self):
		self.frappe.get_request_header.return_value = None
		self.assertFalse(mgmt._is_api_key_caller())

	def test_api_does_not_check_consent_itself(self):
		self.row = _row(consent_attested=0)
		self.assertTrue(self._start()["success"])  # the runner is the single enforcement point

	def test_no_queued_recipients(self):
		self.frappe.db.count.return_value = 0
		self.assertEqual(self._start()["error"], "no_recipients")


class TestPreviewApi(_Base):
	def _preview(self, limits, token="3"):
		cost = MagicMock()
		cost.estimate.return_value = {"total": 1.5}
		cost.confirm_token.return_value = token
		lim = MagicMock()
		lim.preview.return_value = limits
		self.frappe.db.count.return_value = int(token)
		with patch.dict(sys.modules, {"huf.ai.whatsapp.broadcast.cost": cost, "huf.ai.whatsapp.broadcast.limits": lim}), \
			patch("huf.ai.whatsapp.broadcast.cost", cost, create=True), patch("huf.ai.whatsapp.broadcast.limits", lim, create=True):
			return mgmt.preview_broadcast(BC)

	def test_limits_in_effect_at_top_level_and_inside_limits(self):
		lim = {"warnings": [], "blocking": [], "limits_in_effect": ["messaging_tier_24h"]}
		res = self._preview(lim)
		self.assertEqual(res["limits_in_effect"], ["messaging_tier_24h"])
		self.assertEqual(res["limits"]["limits_in_effect"], ["messaging_tier_24h"])

	def test_confirm_required_follows_setting(self):
		self.assertTrue(self._preview({})["confirm_required"])
		with limit_override(require_typed_count=False):
			self.assertFalse(self._preview({})["confirm_required"])


if __name__ == "__main__":
	unittest.main()
