"""Pure tests for the Schedule trigger rules (UX-10): cron wording, zones and the clock a schedule is read on.

  python -m pytest huf/ai/flow/tests/test_flow_ux10_schedule.py   (needs croniter, which Frappe ships)
"""

import unittest
from datetime import datetime

from huf.ai.flow import triggers as T
from huf.ai.flow.support.schedule_rules import cron_problem, schedule_problems, time_zone_problem
from huf.huf.doctype.flow_definition.activation_rules import collect_activation_problems


class TestCronProblem(unittest.TestCase):
	def test_business_hours_cron_is_valid(self):
		# B7: this valid expression was reported as "needs 5 parts".
		self.assertIsNone(cron_problem("*/5 9-17 * * 1-5"))

	def test_common_shapes_are_valid(self):
		for cron in ("0 9 * * *", "*/15 * * * *", "0 0,15 * * *", "0 9 L * *", "0 9 31 * *", "0 9 * * mon-fri", "30 18 1 * *", "0 9 * * 7", "0 9 * * 1,3,5"):
			self.assertIsNone(cron_problem(cron), cron)

	def test_wrong_part_count_says_what_to_do(self):
		self.assertIn("5 parts", cron_problem("* * * *"))
		self.assertIn("5 parts", cron_problem("* * * * * *"))
		self.assertEqual(cron_problem("   "), "Choose when this flow should run.")
		self.assertEqual(cron_problem(None), "Choose when this flow should run.")

	def test_out_of_range_and_garbage(self):
		for bad in ("61 * * * *", "* 24 * * *", "* * 32 * *", "* * 0 * *", "* * * 13 *", "* * * * 8", "5-1 * * * *", "*/0 * * * *"):
			self.assertIn("out of range", cron_problem(bad) or "", bad)
		self.assertIn("not valid", cron_problem("a b c d e"))
		self.assertIn("not valid", cron_problem("0 9 * * 1;"))


class TestTimezone(unittest.TestCase):
	def test_valid_empty_and_invalid(self):
		self.assertIsNone(time_zone_problem(None))
		self.assertIsNone(time_zone_problem(""))
		self.assertIsNone(time_zone_problem("Asia/Kolkata"))
		self.assertIn("not a time zone", time_zone_problem("Mars/Base"))
		self.assertIn("name", time_zone_problem(5))

	def test_schedule_problems_names_the_trigger(self):
		defn = {"nodes": [{"id": "t", "type": "trigger.schedule", "config": {"cron": "* * *", "time_zone": "Mars/Base"}}]}
		found = schedule_problems(defn)
		self.assertEqual(len(found), 2)
		self.assertTrue(all(p.startswith("trigger 't':") for p in found))

	def test_activation_reports_a_bad_schedule_once(self):
		def defn(cron, tz=None):
			cfg = {"cron": cron, **({"time_zone": tz} if tz else {})}
			return {"entry": "t", "nodes": [{"id": "t", "type": "trigger.schedule", "config": cfg, "next": "e"}, {"id": "e", "type": "output", "config": {}}]}

		self.assertEqual(collect_activation_problems(defn("*/5 9-17 * * 1-5", "Asia/Kolkata")), [])
		bad = collect_activation_problems(defn("61 * * * *"))
		self.assertEqual(len(bad), 1)
		self.assertIn("out of range", bad[0])
		blank = collect_activation_problems(defn(""))
		self.assertEqual(len(blank), 1)  # the blank rule only; no second sentence
		self.assertIn("required config", blank[0])


class TestMinuteInZone(unittest.TestCase):
	def test_no_zone_or_unknown_zone_keeps_the_site_clock(self):
		m = datetime(2026, 10, 30, 9, 0)
		self.assertEqual(T.minute_in_zone(m, None, "Asia/Kolkata"), m)
		self.assertEqual(T.minute_in_zone(m, "", "Asia/Kolkata"), m)
		self.assertEqual(T.minute_in_zone(m, "Mars/Base", "Asia/Kolkata"), m)

	def test_converts_wall_clock(self):
		site_now = datetime(2026, 10, 30, 14, 30)  # Kolkata
		self.assertEqual(T.minute_in_zone(site_now, "UTC", "Asia/Kolkata"), datetime(2026, 10, 30, 9, 0))
		self.assertEqual(T.minute_in_zone(site_now, "Asia/Kolkata", "Asia/Kolkata"), site_now)

	def test_daily_nine_in_other_zone_fires_at_the_right_site_minute(self):
		# 09:00 UTC is 14:30 in Kolkata: the schedule is due when the site clock reads 14:30.
		due = T.latest_due_minute("0 9 * * *", T.minute_in_zone(datetime(2026, 10, 30, 14, 30), "UTC", "Asia/Kolkata"))
		self.assertEqual(due, datetime(2026, 10, 30, 9, 0))
		self.assertIsNone(T.latest_due_minute("0 9 * * *", T.minute_in_zone(datetime(2026, 10, 30, 9, 0), "UTC", "Asia/Kolkata")))


class TestSchema(unittest.TestCase):
	def test_schedule_config_accepts_a_zone(self):
		import json
		from pathlib import Path

		schema = json.loads((Path(T.__file__).parents[1] / "graph" / "graph_ir.schema.json").read_text())
		config = schema["$defs"]["TriggerScheduleNode"]["allOf"][1]["properties"]["config"]
		self.assertEqual(set(config["properties"]), {"cron", "time_zone"})
		self.assertEqual(config["required"], ["cron"])
		self.assertFalse(config["additionalProperties"])
