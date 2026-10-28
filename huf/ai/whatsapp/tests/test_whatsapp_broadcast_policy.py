# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Broadcast limits registry: defaults, validation, reset, behaviour of every wired limit, API, docs drift."""

from __future__ import annotations

import json
import pathlib
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.whatsapp.broadcast import api_limits, params, policy, recipients, runner, send

ROOT = pathlib.Path(__file__).resolve().parents[4]
EDITABLE = [lim for lim in policy.LIMITS if lim.editable]

# v2 amendment 1: defaults are today's code values
EXPECTED_DEFAULTS = {
	"max_recipients_default": 1000, "max_recipients_ceiling": 10000, "max_rows_per_broadcast": 50000,
	"max_rows_per_request": 10000, "max_csv_mb": 2, "min_phone_digits": 8, "default_mps": 20,
	"max_mps_cap": 80, "ramp_first_batch": 20, "max_batch": 200, "held_ratio_limit": 0.30,
	"held_window": 50, "min_held_sample": 10, "max_attempts": 5, "auth_defer_seconds": 300,
	"gateway_down_defer_seconds": 300, "require_typed_count": True, "require_consent_attestation": True,
	"one_active_per_gateway": True, "location_text_max": 1000, "url_suffix_max": 2000,
	"copy_code_max": 15, "header_text_max": 60, "returned_list_limit": 200, "tick_budget_seconds": 240,
	"lock_ttl": 600, "stale_sending_minutes": 10, "max_phone_digits": 15,
}


def _reset():
	policy.set_values({lim.key: None for lim in EDITABLE})
	frappe.db.commit()


class _Settings(unittest.TestCase):
	def setUp(self):
		_reset()
		self.addCleanup(_reset)


class TestRegistry(_Settings):
	def test_defaults_unchanged(self):
		for key, value in EXPECTED_DEFAULTS.items():
			self.assertEqual(policy.BY_KEY[key].default, value, key)
			self.assertEqual(policy.get(key), value, key)

	def test_kinds_and_editable(self):
		for lim in policy.LIMITS:
			self.assertIn(lim.kind, ("meta", "setting", "safety", "internal"))
			self.assertEqual(lim.editable, lim.kind in ("setting", "safety"))
		for key in ("location_text_max", "url_suffix_max", "copy_code_max", "require_typed_count"):
			self.assertIn(key, policy.BY_KEY)

	def test_every_editable_limit_has_a_typed_settings_field(self):
		meta = frappe.get_meta(policy.SETTINGS)
		for lim in EDITABLE:
			self.assertIsNotNone(meta.get_field(lim.key), lim.key)
		self.assertTrue(meta.issingle)

	def test_every_editable_limit_is_in_the_api(self):
		keys = {r["key"]: r for r in api_limits.build_rows()}
		for lim in policy.LIMITS:
			self.assertIn(lim.key, keys)
			self.assertEqual(keys[lim.key]["editable"], lim.editable)

	def test_docs_table_matches_registry(self):
		path = ROOT / "docs" / "whatsapp" / "BROADCAST_LIMITS.md"
		self.assertEqual(path.read_text(encoding="utf-8"), policy.render_docs())


class TestEveryEditableLimit(_Settings):
	def _valid(self, lim):
		if lim.boolean:
			return not lim.default
		mid = lim.default if lim.default and lim.min <= lim.default < lim.max else lim.min
		if isinstance(lim.default, float):
			return round(lim.min + (lim.max - lim.min) / 4, 2)
		return int(mid) + 1 if int(mid) + 1 <= lim.max else int(mid)

	def test_setting_changes_effective_value_and_reset_restores_default(self):
		for lim in EDITABLE:
			if lim.key in ("ramp_first_batch", "max_batch", "min_held_sample", "held_window",
					"max_recipients_default", "max_recipients_ceiling"):
				continue  # cross-field rules; covered below
			value = self._valid(lim)
			policy.set_values({lim.key: value})
			self.assertEqual(policy.get(lim.key), value, lim.key)
			self.assertEqual(policy.resolve(lim.key)[1], "settings")
			policy.set_values({lim.key: None})
			self.assertEqual(policy.get(lim.key), lim.default, lim.key)
			self.assertEqual(policy.resolve(lim.key)[1], "default")

	def test_min_max_validation_rejects_and_stores_nothing(self):
		for lim in EDITABLE:
			if lim.boolean:
				continue
			for bad in (lim.min - 1, lim.max + 1):
				if lim.zero_unlimited and bad == 0:
					continue
				with self.assertRaises(ValueError, msg=f"{lim.key}={bad}"):
					policy.set_values({lim.key: bad})
				self.assertEqual(policy.get(lim.key), lim.default)
			with self.assertRaises(ValueError):
				policy.set_values({lim.key: "abc"})

	def test_boundaries_accepted(self):
		for key in ("default_mps", "max_csv_mb", "min_phone_digits", "rate_start_broadcast"):
			lim = policy.BY_KEY[key]
			for ok in (lim.min, lim.max):
				policy.set_values({key: ok})
				self.assertEqual(policy.get(key), ok)

	def test_unknown_and_readonly_keys_rejected(self):
		for key in ("nope", "template_approved_only", "tick_budget_seconds", "copy_code_max"):
			with self.assertRaises(ValueError):
				policy.set_values({key: 1})

	def test_cross_field_rules(self):
		with self.assertRaises(ValueError):
			policy.set_values({"max_recipients_default": 20000})  # above default ceiling 10000
		with self.assertRaises(ValueError):
			policy.set_values({"ramp_first_batch": 500})  # above default max_batch 200
		with self.assertRaises(ValueError):
			policy.set_values({"min_held_sample": 100})  # above default held_window 50
		policy.set_values({"max_recipients_ceiling": 0, "max_recipients_default": 0})
		self.assertIsNone(policy.get("max_recipients_default"))
		self.assertIsNone(policy.get("max_recipients_ceiling"))


class TestBehaviour(_Settings):
	"""Each wired limit changes what the code does."""

	def _prepare(self, rows, cap=None, **counts):
		doc = MagicMock()
		doc.gateway, doc.category, doc.max_recipients = "GW", "UTILITY", cap
		inserted = []
		with patch.object(recipients, "_load_broadcast", return_value=doc), \
			patch.object(recipients, "_existing_names", return_value=set()), \
			patch.object(recipients, "_active_count", return_value=counts.get("active", 0)), \
			patch.object(recipients, "_total_count", return_value=counts.get("total", 0)), \
			patch.object(recipients, "_policy_reason", return_value=None), \
			patch.object(recipients, "_insert_row", side_effect=lambda *a: inserted.append(a)):
			res = recipients.prepare("B-1", [{"recipient": r} for r in rows])
		return res, inserted

	NUMS = ["1555000%04d" % i for i in range(5)]

	def test_max_recipients_default_and_per_broadcast_override(self):
		res, ins = self._prepare(self.NUMS)
		self.assertEqual(len(ins), 5)
		policy.set_values({"max_recipients_default": 2})
		res, ins = self._prepare(self.NUMS)
		self.assertEqual(len(ins), 2)
		self.assertEqual(res["skipped"][0]["reason"], "max_recipients")
		res, ins = self._prepare(self.NUMS, cap=4)  # per-broadcast override wins
		self.assertEqual(len(ins), 4)

	def test_ceiling_clamps_and_no_limit(self):
		policy.set_values({"max_recipients_default": 1, "max_recipients_ceiling": 3})
		_, ins = self._prepare(self.NUMS, cap=1000)
		self.assertEqual(len(ins), 3)
		policy.set_values({"max_recipients_ceiling": 0, "max_recipients_default": 0})
		_, ins = self._prepare(self.NUMS)
		self.assertEqual(len(ins), 5)

	def test_max_rows_per_broadcast(self):
		policy.set_values({"max_rows_per_broadcast": 3})
		res, ins = self._prepare(self.NUMS, total=2)
		self.assertEqual(len(ins), 1)
		self.assertEqual(res["skipped"][0]["reason"], "row_ceiling")

	def test_min_phone_digits(self):
		self.assertIsNone(recipients.normalize_recipient("1234567"))
		policy.set_values({"min_phone_digits": 7})
		self.assertEqual(recipients.normalize_recipient("1234567"), "1234567")
		policy.set_values({"min_phone_digits": 12})
		self.assertIsNone(recipients.normalize_recipient("15550000001"))

	def test_phone_digits_upper_bound_is_meta(self):
		self.assertIsNone(recipients.normalize_recipient("1" * 16))
		self.assertIsNotNone(recipients.normalize_recipient("1" * 15))

	def test_returned_list_limit_internal(self):
		res, _ = self._prepare(["bad%d" % i for i in range(300)])
		self.assertEqual(len(res["invalid"]), 200)
		self.assertEqual(res["invalid_total"], 300)

	def test_params_limits(self):
		self.assertIsNone(params.location_error({"latitude": 1, "longitude": 1, "name": "x" * 1000}))
		self.assertIn("1000", params.location_error({"latitude": 1, "longitude": 1, "name": "x" * 1001}))
		self.assertIsNone(params.header_error("x" * 60))
		self.assertIn("60", params.header_error("x" * 61))
		self.assertIsNone(params.button_error([{"sub_type": "copy_code", "code": "A" * 15}]))
		self.assertIn("15", params.button_error([{"sub_type": "copy_code", "code": "A" * 16}]))
		self.assertIsNone(params.button_error([{"sub_type": "url", "text": "a" * 2000}]))
		self.assertIn("2000", params.button_error([{"sub_type": "url", "text": "a" * 2001}]))

	def test_mps_default_cap_and_meta_reported(self):
		doc = MagicMock(gateway="GW", mps=None)
		with patch.object(runner.broadcast_limits, "get_messaging_limit", return_value={}):
			self.assertEqual(runner._effective_mps(doc), 20)
			policy.set_values({"default_mps": 50})
			self.assertEqual(runner._effective_mps(doc), 50)
			policy.set_values({"max_mps_cap": 30})
			self.assertEqual(runner._effective_mps(doc), 30)
			doc.mps = 10  # per-broadcast override
			self.assertEqual(runner._effective_mps(doc), 10)
		policy.set_values({"max_mps_cap": None, "default_mps": 1000})
		doc.mps = None
		with patch.object(runner.broadcast_limits, "get_messaging_limit", return_value={"mps": 200}):
			self.assertEqual(runner._effective_mps(doc), 200)  # Meta-reported replaces the default 80
			policy.set_values({"max_mps_cap": 40})
			self.assertEqual(runner._effective_mps(doc), 40)  # an explicit setting only lowers

	def test_batch_sizes(self):
		doc = MagicMock()
		self.assertEqual(runner._batch_size(doc, 0, False), 20)
		self.assertEqual(runner._batch_size(doc, 150, False), 150)
		self.assertEqual(runner._batch_size(doc, 900, False), 200)
		policy.set_values({"max_batch": 300, "ramp_first_batch": 5})
		self.assertEqual(runner._batch_size(doc, 0, False), 5)
		self.assertEqual(runner._batch_size(doc, 900, False), 300)

	def test_held_throttle(self):
		self.assertFalse(runner._is_throttled(0.5, 5))  # sample too small
		self.assertTrue(runner._is_throttled(0.31, 10))
		self.assertFalse(runner._is_throttled(0.30, 10))
		policy.set_values({"held_ratio_limit": 0.6})
		self.assertFalse(runner._is_throttled(0.5, 10))
		policy.set_values({"min_held_sample": 20, "held_ratio_limit": None})
		self.assertFalse(runner._is_throttled(0.9, 10))
		policy.set_values({"min_held_sample": None, "held_throttle_enabled": False})
		self.assertFalse(runner._is_throttled(0.9, 50))

	def _spy_sql(self, module, marker, result):
		real, seen = module.frappe.db.sql, []

		def fake(query, *args, **kwargs):
			if marker in str(query):
				seen.append(args[0] if args else None)
				return result
			return real(query, *args, **kwargs)

		return patch.object(module.frappe.db, "sql", side_effect=fake), seen

	def test_held_window_in_query(self):
		policy.set_values({"held_window": 25})
		ctx, seen = self._spy_sql(runner, "message_status", [])
		with ctx:
			runner._held_ratio("B-1")
		self.assertEqual(seen[0][1], 25)

	def test_max_attempts_in_claim_and_defers(self):
		policy.set_values({"max_attempts": 2})
		ctx, seen = self._spy_sql(send, "set status='sending'", [[1]])
		with ctx, patch.object(send.frappe.db, "commit"):
			send._claim("ROW")
		self.assertEqual(seen[0][2], 2)
		policy.set_values({"gateway_down_defer_seconds": 60, "auth_defer_seconds": 90})
		before = frappe.utils.now_datetime()
		self.assertLess((send._later(policy.get("gateway_down_defer_seconds")) - before).total_seconds(), 61)
		self.assertGreater((send._later(policy.get("auth_defer_seconds")) - before).total_seconds(), 85)

	def test_rate_limit_callables_follow_settings(self):
		self.assertEqual(policy.rate("rate_start_broadcast")(), 30)
		policy.set_values({"rate_start_broadcast": 5})
		self.assertEqual(policy.rate("rate_start_broadcast")(), 5)

	def test_endpoints_use_policy_rate_callables(self):
		from huf.ai.whatsapp.broadcast import api

		src = pathlib.Path(api.__file__).read_text()
		self.assertNotIn("rate_limit(limit=60", src)
		self.assertIn('policy.rate("rate_start_broadcast")', src)

	def test_add_recipients_request_limits(self):
		from huf.ai.whatsapp.broadcast import api

		row = {"gateway": "GW", "status": "Draft"}
		with patch.object(api, "_require_broadcast_write", return_value=row):
			policy.set_values({"max_csv_mb": 1})
			big = "phone\n" + "1" * (1024 * 1024 + 1)
			self.assertEqual(api.add_broadcast_recipients("B-1", csv_text=big)["error"], "csv_too_large")
			policy.set_values({"max_rows_per_request": 3})
			res = api.add_broadcast_recipients("B-1", recipients=json.dumps(["1"] * 4))
			self.assertEqual(res["error"], "too_many_recipients")

	def test_unwired_gates_are_registered_safeties(self):
		# enforced by the start step (WP-A2); here only that they exist, default on, and are switchable
		for key in ("require_typed_count", "require_consent_attestation", "one_active_per_gateway"):
			self.assertTrue(policy.get(key))
			policy.set_values({key: False})
			self.assertFalse(policy.get(key))
			policy.set_values({key: None})
			self.assertTrue(policy.get(key))


class TestApi(_Settings):
	def test_get_shape(self):
		rows = api_limits.get_broadcast_limits()["limits"]
		self.assertEqual(len(rows), len(policy.LIMITS))
		need = {"key", "label", "group", "kind", "value", "default", "effective", "source", "unit", "min", "max", "note", "editable"}
		for row in rows:
			self.assertTrue(need <= set(row), row["key"])
			self.assertIn(row["group"], ("meta", "recipients", "speed", "safety", "quality", "confirmation", "api"))
		by = {r["key"]: r for r in rows}
		self.assertEqual(by["max_batch"]["effective"], 200)
		self.assertEqual(by["max_batch"]["source"], "default")
		self.assertIsNone(by["max_batch"]["value"])

	def test_update_roundtrip_reset_and_validation(self):
		res = api_limits.update_broadcast_limits(json.dumps({"max_batch": 250, "default_mps": 33}))
		by = {r["key"]: r for r in res["limits"]}
		self.assertEqual((by["max_batch"]["value"], by["max_batch"]["source"]), (250, "settings"))
		self.assertEqual(by["default_mps"]["effective"], 33)
		res = api_limits.update_broadcast_limits(json.dumps({"max_batch": None}))
		by = {r["key"]: r for r in res["limits"]}
		self.assertEqual((by["max_batch"]["effective"], by["max_batch"]["source"]), (200, "default"))
		self.assertEqual(by["default_mps"]["effective"], 33)  # untouched
		bad = api_limits.update_broadcast_limits(json.dumps({"max_batch": 99999}))
		self.assertFalse(bad["success"])
		self.assertEqual(policy.get("max_batch"), 200)
		self.assertFalse(api_limits.update_broadcast_limits("not json")["success"])
		self.assertFalse(api_limits.update_broadcast_limits(json.dumps({"copy_code_max": 3}))["success"])

	def test_per_broadcast_override_source(self):
		doc = MagicMock(mps=7, max_recipients=None)
		self.assertEqual(policy.resolve("default_mps", doc), (7, "broadcast"))
		self.assertEqual(policy.resolve("max_recipients_default", doc), (1000, "default"))

	def test_update_requires_admin(self):
		user = "wa-lim-nonadmin@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "Lim", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		orig = frappe.session.user
		try:
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				api_limits.update_broadcast_limits(json.dumps({"max_batch": 100}))
		finally:
			frappe.set_user(orig)
		self.assertEqual(policy.get("max_batch"), 200)
