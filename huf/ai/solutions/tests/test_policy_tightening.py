import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe

from huf.ai.whatsapp import send_scope as scope

GW = "GW-TIGHT"
CONTACT = "15550001111"
OTHER = "15559998888"
OTHER2 = "15557776666"


def _gw(**over):
	base = {"scope": "Approved contacts", "allowlist": [OTHER2], "per_run": 20, "per_day": 100}
	base.update(over)
	return base


def _binding(solution="sol-a", cap=None, scope_override=None):
	return {"solution": solution, "cap_per_day": cap, "scope_override": scope_override}


class TestSettingsTightening(unittest.TestCase):
	def _settings(self, gw, bindings, solution="sol-a"):
		with patch.object(scope, "_gateway_settings", return_value=gw), patch.object(scope, "_binding_rows", return_value=bindings):
			return scope.settings(GW, solution=solution)

	def test_no_solution_is_gateway_unchanged(self):
		with patch.object(scope, "_gateway_settings", return_value=_gw()), patch.object(scope, "_binding_rows", side_effect=AssertionError("must not be read")):
			self.assertEqual(scope.settings(GW), _gw())

	def test_no_bindings_leaves_gateway_values(self):
		out = self._settings(_gw(), [])
		self.assertEqual(out["scope"], "Approved contacts")
		self.assertEqual(out["per_day"], 100)
		self.assertIsNone(out["solution_per_day"])

	def test_tighter_cap_and_scope_apply(self):
		out = self._settings(_gw(), [_binding(cap=30, scope_override="Allow list")])
		self.assertEqual(out["scope"], "Allow-list")
		self.assertEqual(out["solution_per_day"], 30)
		self.assertEqual(out["per_day"], 100)

	def test_tightest_across_bindings(self):
		out = self._settings(_gw(scope="Any number"), [_binding(cap=50, scope_override="Only approved contacts"), _binding(cap=20, scope_override="Allow list")])
		self.assertEqual(out["scope"], "Allow-list")
		self.assertEqual(out["solution_per_day"], 20)

	def test_looser_scope_ignored(self):
		out = self._settings(_gw(scope="Allow-list"), [_binding(scope_override="Only approved contacts")])
		self.assertEqual(out["scope"], "Allow-list")
		out = self._settings(_gw(scope="Current contact"), [_binding(scope_override="Allow list")])
		self.assertEqual(out["scope"], "Current contact")

	def test_looser_cap_is_clamped_to_gateway_cap(self):
		out = self._settings(_gw(per_day=100), [_binding(cap=500)])
		self.assertEqual(out["solution_per_day"], 100)

	def test_cap_over_unlimited_gateway_applies_per_solution(self):
		out = self._settings(_gw(per_day=0), [_binding(cap=40)])
		self.assertEqual(out["solution_per_day"], 40)
		self.assertEqual(out["per_day"], 0)

	def test_zero_or_null_binding_cap_is_unset(self):
		out = self._settings(_gw(), [_binding(cap=0), _binding(cap=None)])
		self.assertIsNone(out["solution_per_day"])

	def test_binding_lookup_failure_fails_closed(self):
		with patch.object(scope, "_gateway_settings", return_value=_gw(scope="Any number")), patch.object(scope, "_binding_rows", side_effect=RuntimeError):
			out = scope.settings(GW, solution="sol-a")
		self.assertEqual(out["scope"], "Current contact")


class TestCheckRecipientTightening(unittest.TestCase):
	def _check(self, gw, bindings, recipient, solution="sol-a"):
		with patch.object(scope, "_gateway_settings", return_value=gw), patch.object(scope, "_binding_rows", return_value=bindings), \
			patch.object(scope, "current_contact", return_value=CONTACT), patch.object(scope, "_is_approved", return_value=True):
			return scope.check_recipient(GW, "RUN", recipient, solution=solution)

	def test_override_narrows_approved_to_allowlist(self):
		self.assertIsNone(self._check(_gw(), [], OTHER))
		refusal = json.loads(self._check(_gw(), [_binding(scope_override="Allow list")], OTHER))
		self.assertEqual(refusal["error"], "recipient_not_permitted")
		self.assertIsNone(self._check(_gw(), [_binding(scope_override="Allow list")], OTHER2))

	def test_current_contact_always_allowed(self):
		self.assertIsNone(self._check(_gw(), [_binding(scope_override="Allow list")], CONTACT))

	def test_looser_override_is_ignored(self):
		gw = _gw(scope="Current contact")
		refusal = json.loads(self._check(gw, [_binding(scope_override="Only approved contacts")], OTHER))
		self.assertEqual(refusal["error"], "recipient_not_permitted")

	def test_missing_solution_is_gateway_behaviour(self):
		with patch.object(scope, "_gateway_settings", return_value=_gw()), patch.object(scope, "_binding_rows", side_effect=AssertionError), \
			patch.object(scope, "current_contact", return_value=CONTACT), patch.object(scope, "_is_approved", return_value=True):
			self.assertIsNone(scope.check_recipient(GW, "RUN", OTHER))


class TestCheckCapsTightening(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.db.delete("WhatsApp Send Key", {"gateway": GW})
		frappe.db.commit()

	def _claim(self, solution, n, run="RUN-X"):
		for _ in range(n):
			frappe.get_doc({
				"doctype": "WhatsApp Send Key", "key_hash": frappe.generate_hash(length=40), "gateway": GW, "agent_run": run,
				"status": "Sent", "claimed_at": frappe.utils.now_datetime() - timedelta(minutes=5), "solution": solution or None,
			}).insert(ignore_permissions=True, ignore_links=True)

	def _check(self, bindings, solution, gw=None):
		with patch.object(scope, "_gateway_settings", return_value=gw or _gw(per_day=100, per_run=0)), patch.object(scope, "_binding_rows", return_value=bindings):
			return scope.check_caps(GW, "RUN-X", solution=solution)

	def test_solution_cap_exhausted_while_gateway_has_room(self):
		self._claim("sol-a", 4)  # the 4th claim is the send being checked: over a cap of 3
		self._claim("sol-b", 2)
		out = json.loads(self._check([_binding(cap=3)], "sol-a"))
		self.assertEqual(out["error"], "send_cap_exceeded")
		self.assertEqual(out["cap"], "solution_day")
		self.assertEqual(out["limit"], 3)
		self.assertIsNone(self._check([_binding(cap=3)], "sol-b"))

	def test_under_solution_cap_is_ok(self):
		self._claim("sol-a", 3)
		self.assertIsNone(self._check([_binding(cap=3)], "sol-a"))

	def test_other_solutions_rows_do_not_count_toward_solution_cap(self):
		self._claim("sol-b", 10)
		self.assertIsNone(self._check([_binding(cap=3)], "sol-a"))

	def test_gateway_cap_still_applies_to_all_rows(self):
		self._claim("sol-b", 4)
		self._claim("sol-a", 1)
		out = json.loads(self._check([_binding(cap=50)], "sol-a", gw=_gw(per_day=4, per_run=0)))
		self.assertEqual(out["cap"], "day")

	def test_looser_solution_cap_does_not_raise_gateway_cap(self):
		self._claim("sol-a", 5)
		out = json.loads(self._check([_binding(cap=500)], "sol-a", gw=_gw(per_day=4, per_run=0)))
		self.assertEqual(out["cap"], "day")

	def test_missing_solution_unchanged(self):
		self._claim("sol-a", 5)
		self.assertIsNone(self._check([_binding(cap=1)], None))


class TestBindingValidate(unittest.TestCase):
	def _doc(self, **over):
		vals = {"doctype": "Gateway Binding", "gateway": GW, "match_type": "Catch-all", "target_type": "Triage"}
		vals.update(over)
		return frappe.get_doc(vals)

	def _validate(self, doc, gateway_scope="Approved contacts", ceil=(1000, "meta_tier")):
		from huf.huf.doctype.gateway_binding import gateway_binding as mod

		with patch.object(mod, "_gateway_scope", return_value=gateway_scope), patch.object(mod, "ceiling_for_gateway", return_value=ceil):
			doc.validate()

	def test_valid_tightening_passes(self):
		self._validate(self._doc(cap_per_day=500, scope_override="Allow list"))

	def test_unset_overrides_pass(self):
		self._validate(self._doc())

	def test_cap_over_ceiling_rejected(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			self._validate(self._doc(cap_per_day=1001))
		self.assertTrue(str(cm.exception).startswith("cap_exceeds_ceiling"))

	def test_cap_equal_ceiling_ok_and_no_ceiling_ok(self):
		self._validate(self._doc(cap_per_day=1000))
		self._validate(self._doc(cap_per_day=10**7), ceil=(None, "none"))

	def test_negative_cap_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(self._doc(cap_per_day=-1))

	def test_scope_loosening_rejected(self):
		with self.assertRaises(frappe.ValidationError) as cm:
			self._validate(self._doc(scope_override="Only approved contacts"), gateway_scope="Allow-list")
		self.assertTrue(str(cm.exception).startswith("scope_loosening"))
		with self.assertRaises(frappe.ValidationError):
			self._validate(self._doc(scope_override="Allow list"), gateway_scope="Current contact")

	def test_same_scope_ok(self):
		self._validate(self._doc(scope_override="Allow list"), gateway_scope="Allow-list")
