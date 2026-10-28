# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-I: fixes from the Opus re-review (start snapshot race, gateway bucket, resume, fallback pacing)."""

from __future__ import annotations

import threading
from unittest.mock import patch

import frappe

from huf.ai.whatsapp.broadcast import limits as bl, runner
from huf.ai.whatsapp.broadcast.checks import start_gate
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import GW, R, USER, B, _Base

REAL_PREVIEW = bl.preview


def in_second_connection(fn):
	"""Run ``fn`` on its own thread with its own database connection and commit; re-raise its error."""
	site, sites_path = frappe.local.site, frappe.local.sites_path
	errors: list[BaseException] = []

	def work():
		try:
			frappe.init(site=site, sites_path=sites_path)
			frappe.connect()
			frappe.set_user("Administrator")
			fn()
			frappe.db.commit()
		except BaseException as exc:  # noqa: BLE001 - surfaced to the test thread
			errors.append(exc)
		finally:
			frappe.destroy()

	t = threading.Thread(target=work)
	t.start()
	t.join(60)
	assert not t.is_alive(), "second connection hung"
	if errors:
		raise errors[0]


class TestStartSeesOtherStartsOnItsOwnConnection(_Base):
	def setUp(self):
		super().setUp()
		self.preview.side_effect = REAL_PREVIEW
		patch.object(bl, "get_messaging_limit", return_value={"tier": "TIER_250", "max_unique_24h": 10, "quality": None, "mps": 1000}).start()
		patch.object(bl, "_template_row", return_value={"status": "APPROVED", "category": "UTILITY"}).start()

	def _add_rows(self, broadcast, prefix, n):
		for i in range(n):
			self.row(broadcast, f"{prefix}{i:04d}")

	def test_second_start_sees_the_first_starts_reservation(self):
		"""A's rows and Running state commit on another connection after B has taken its first read.

		B's pre-lock reads are a REPEATABLE READ snapshot that predates A's rows; after the Gateway lock B
		must read current data, or both starts claim the same 24h budget."""
		a = self.make(n=0)
		b = self.make(n=0)
		self._add_rows(b, "1555222", 8)
		frappe.db.commit()
		real_check = start_gate.check_preview
		fired = []

		def check_then_race(*args, **kw):
			out = real_check(*args, **kw)
			if not fired:
				fired.append(1)

				def first_start():
					self._add_rows(a, "1555111", 8)
					frappe.db.commit()
					runner.start(a, USER, [])

				in_second_connection(first_start)
			return out

		with limit_override(one_active_per_gateway=False), patch.object(start_gate, "check_preview", check_then_race):
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(b, USER, [])
		self.assertEqual(cm.exception.code, "warnings_changed")
		codes = {w["code"] for w in cm.exception.extra["warnings"]}
		self.assertEqual(codes, {"over_budget", "other_broadcast_running"})
		self.assertEqual(frappe.db.get_value(B, a, "status"), "Running")
		self.assertEqual(frappe.db.get_value(B, b, "status"), "Draft")

	def test_recipients_changed_sees_a_concurrent_commit(self):
		b = self.make(n=3)
		real_check = start_gate.check_preview
		fired = []

		def check_then_race(*args, **kw):
			out = real_check(*args, **kw)
			if not fired:
				fired.append(1)
				in_second_connection(lambda: frappe.db.sql(
					f"update `tab{R}` set status='skipped', skip_reason='opted_out' where broadcast=%s limit 1", b))
			return out

		with patch.object(start_gate, "check_preview", check_then_race):
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(b, USER, [], expected_count=3)
		self.assertEqual(cm.exception.code, "recipients_changed")
