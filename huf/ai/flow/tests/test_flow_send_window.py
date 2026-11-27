"""Send window wiring (H-W2-06): resolver hook, guard chain step and the deferral park path."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import guard, guard_steps
from huf.ai.flow.runs import park

NODE = {"id": "s1", "type": "send.message"}
DAYTIME = {"zone": "Asia/Kolkata", "windows": [{"start": "09:00", "end": "21:00"}]}


def utc(*parts):
	return datetime(*parts, tzinfo=timezone.utc)


class TestSendWindowStep(IntegrationTestCase):
	def setUp(self):
		self.now = utc(2030, 1, 7, 2, 0)  # Monday 07:30 in Kolkata
		self.resolvers = {"app.window": lambda request: DAYTIME}
		self.app_hooks = {}
		clock = patch.object(guard_steps, "datetime", wraps=datetime)
		clock.start().now.side_effect = lambda tz=None: self.now
		self.addCleanup(clock.stop)
		for patcher in (
			patch.object(guard, "BUILTIN_STEPS", []),
			patch.object(guard, "_hook_paths", side_effect=lambda: list(self.app_hooks)),
			patch.object(guard_steps, "window_resolvers", side_effect=lambda: list(self.resolvers)),
			patch.object(frappe, "get_attr", side_effect=lambda p: {**self.resolvers, **self.app_hooks}[p]),
			patch.object(guard_steps, "resolve_caps", return_value=[]),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def send(self, category="marketing"):
		return guard.evaluate({"category": category, "channel": "whatsapp", "member_key": "m1", "live": True})

	def assertDeferred(self, until, result):
		self.assertEqual(result, guard.GuardResult(False, None, "send_window", until))

	def assertBlocked(self, result):
		self.assertEqual(result, guard.GuardResult(False, "hook_error", "send_window"))

	def test_before_the_window_defers_to_the_opening_and_skips_hooks_and_caps(self):
		later = []
		self.app_hooks = {"app.step": lambda request: later.append(1)}
		self.assertDeferred(utc(2030, 1, 7, 3, 30), self.send())
		self.assertEqual(later, [])
		guard_steps.resolve_caps.assert_not_called()

	def test_open_window_boundaries(self):
		for moment, allowed in (
			(utc(2030, 1, 7, 3, 29), False),
			(utc(2030, 1, 7, 3, 30), True),
			(utc(2030, 1, 7, 15, 29), True),
			(utc(2030, 1, 7, 15, 30), False),
		):
			with self.subTest(moment=moment):
				self.now = moment
				self.assertEqual(self.send().allowed, allowed)

	def test_no_opinion_is_always_open_and_the_first_answer_wins(self):
		self.resolvers = {"app.none": lambda request: None}
		self.assertTrue(self.send().allowed)
		self.resolvers["app.window"] = lambda request: DAYTIME
		self.resolvers["app.open"] = lambda request: {
			**DAYTIME,
			"windows": [{"start": "00:00", "end": "00:00"}],
		}
		self.assertFalse(self.send().allowed)

	def test_exempt_category_sends(self):
		self.resolvers = {"app.window": lambda request: {**DAYTIME, "exempt_categories": ["service"]}}
		self.assertTrue(self.send("service").allowed)
		self.assertFalse(self.send("marketing").allowed)

	def test_no_windows_retries_in_an_hour(self):
		self.resolvers = {"app.window": lambda request: {"zone": "UTC", "windows": []}}
		self.assertDeferred(self.now + timedelta(hours=1), self.send())

	def test_resolver_exception_blocks(self):
		def boom(request):
			raise RuntimeError

		self.resolvers = {"app.window": boom}
		self.assertBlocked(self.send())

	def test_malformed_answers_block_even_for_an_exempt_category(self):
		exempt = {"exempt_categories": ["marketing"]}
		window = {"start": "09:00", "end": "21:00"}
		for answer in (
			False,
			{},
			{"zone": "Nowhere/City", "windows": [window], **exempt},
			{"zone": "UTC", "windows": None},
			{"zone": "UTC", "windows": [{"start": "9:00", "end": "21:00"}]},
			{"zone": "UTC", "windows": [{**window, "weekdays": [7]}]},
			{"zone": "UTC", "windows": [{**window, "weekdays": ["0"]}]},
			{"zone": "UTC", "windows": [window], "exempt_categories": "marketing"},
			{"zone": "UTC", "windows": [window], "extra": 1},
		):
			with self.subTest(answer=answer):
				self.resolvers = {"app.window": lambda request, a=answer: a}
				self.assertBlocked(self.send())

	def test_dst_skipped_opening_time(self):
		# 2030-03-10: New York jumps from 02:00 to 03:00, so a 02:30 opening opens at the jump
		self.now = utc(2030, 3, 10, 6, 0)
		self.resolvers = {
			"app.window": lambda request: {
				"zone": "America/New_York",
				"windows": [{"start": "02:30", "end": "05:00"}],
			}
		}
		self.assertDeferred(utc(2030, 3, 10, 7, 0), self.send())


class TestDeferSend(IntegrationTestCase):
	def setUp(self):
		self.run_doc = frappe._dict(name="_test-defer", status="Running", waiting=None, member_key="m1")
		self.parked = []

		def transition(flow_run, values, **kwargs):
			flow_run.update(values)
			self.parked.append(values)
			return True

		for patcher in (
			patch("huf.ai.flow.engine._transition_run", side_effect=transition),
			patch.object(park, "commit_if_background"),
			patch.dict(frappe.conf, {"huf_flow_send_max_defers": 2}),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def wake(self):
		waiting = frappe.parse_json(self.run_doc.waiting)
		waiting["woke"] = {"reason": "elapsed"}
		self.run_doc.update(status="Running", waiting=frappe.as_json(waiting))

	def defer(self):
		return park.defer_send(self.run_doc, NODE, utc(2030, 1, 7, 3, 30))

	def test_parks_until_the_opening_then_gives_up_after_the_limit(self):
		for count in (1, 2):
			self.assertTrue(self.defer().is_paused)
			self.assertEqual(self.run_doc.status, "Waiting Timer")
			self.assertEqual(self.run_doc.resume_at, datetime(2030, 1, 7, 3, 30))
			self.assertEqual(frappe.parse_json(self.run_doc.waiting)["extra"], {"defers": count})
			self.wake()
		self.assertIsNone(self.defer())
		self.assertEqual(len(self.parked), 2)

	def test_another_wait_does_not_count_and_bad_config_uses_the_default(self):
		self.run_doc.waiting = frappe.as_json(
			{"node_id": "s1", "reason": "retry", "woke": {"reason": "elapsed"}, "extra": {"defers": 9}}
		)
		self.assertTrue(self.defer().is_paused)
		for bad in (None, "x", -1):
			with self.subTest(bad=bad), patch.dict(frappe.conf, {"huf_flow_send_max_defers": bad}):
				self.assertEqual(park.max_send_defers(), 24)
