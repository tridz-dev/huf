# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-13: template status/quality/category webhooks pause Running broadcasts."""

from __future__ import annotations

import json
import pathlib
import unittest
from unittest.mock import patch

from huf.ai.gateway_adapters import whatsapp_bridge as bridge

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
RUNNER = "huf.ai.whatsapp.broadcast_runner.pause_for_template"


def value(name, **over):
	v = json.loads((FIXTURES / name).read_text())["entry"][0]["changes"][0]["value"]
	v.update(over)
	return v


class TemplatePauseTest(unittest.TestCase):
	def run_hook(self, update, account="ACC"):
		with patch.object(bridge, "_record_template_webhook", return_value="T") as rec, patch(RUNNER) as pause:
			out = bridge.record_template_webhook(update, account)
		rec.assert_called_once()
		self.assertEqual(out, "T")
		return pause

	def test_rejected_pauses(self):
		self.run_hook(value("template_status_rejected.json")).assert_called_once_with("ACC", "payslip_ready", "rejected")

	def test_paused_and_disabled_pause(self):
		for ev in ("PAUSED", "DISABLED"):
			self.run_hook(value("template_status_approved.json", event=ev)).assert_called_once_with(
				"ACC", "leave_approved", ev.lower())

	def test_approved_does_not_pause(self):
		self.run_hook(value("template_status_approved.json")).assert_not_called()

	def test_quality_red_pauses_green_does_not(self):
		self.run_hook(value("template_quality_update.json")).assert_called_once_with(
			"ACC", "leave_approved", "quality_red")
		self.run_hook(value("template_quality_update.json", new_quality_score="GREEN")).assert_not_called()

	def test_category_marketing_pauses_utility_does_not(self):
		self.run_hook(value("template_category_update.json")).assert_called_once_with(
			"ACC", "leave_approved", "category_marketing")
		self.run_hook(value("template_category_update.json", new_category="UTILITY")).assert_not_called()

	def test_pause_failure_never_breaks_ingest(self):
		with patch.object(bridge, "_record_template_webhook", return_value="T"), patch(RUNNER, side_effect=RuntimeError("x")):
			self.assertEqual(bridge.record_template_webhook(value("template_status_rejected.json"), "ACC"), "T")

	def test_no_name_skips(self):
		self.run_hook({"event": "REJECTED"}).assert_not_called()
