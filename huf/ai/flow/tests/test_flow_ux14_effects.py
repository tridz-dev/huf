# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-14: the tool classification (reads / changes / sends) and the "Would ..." wording of a skipped step.

Pure logic, no site needed.
"""

import re
import unittest
from pathlib import Path

from huf.ai.flow.testrun import MODE_REAL, MODE_TEST, normalize_mode, stored_mode
from huf.ai.flow.testrun.effects import CHANGES, EFFECTS, READS, SENDS, TOOL_EFFECTS, tool_effect
from huf.ai.flow.testrun.simulate import simulated_code, simulated_document, simulated_output


def _registered_tool_names() -> set[str]:
	"""Every tool_name the app registers (huf_tools hook): read from source so the test needs no site."""
	root = Path(__file__).resolve().parents[2]
	names: set[str] = set()
	for rel in ("tools/_registry.py", "tools/gateways/send.py", "tools/gateways/reply.py", "tools/gateways/handoff.py"):
		names |= set(re.findall(r'"tool_name":\s*"([^"]+)"', (root / rel).read_text()))
	return names


class TestClassification(unittest.TestCase):
	def test_every_registered_tool_is_classified_explicitly(self):
		missing = sorted(_registered_tool_names() - set(TOOL_EFFECTS))
		self.assertEqual(missing, [], "classify these tools in testrun/effects.py")

	def test_effects_are_one_of_the_three_words(self):
		self.assertTrue(set(TOOL_EFFECTS.values()) <= set(EFFECTS))

	def test_the_named_examples(self):
		for sends in ("slack_send_message", "slack_send_thread_reply", "gmail_send_email"):
			self.assertEqual(tool_effect(sends), SENDS, sends)
		for reads in ("gsheets_read", "gdrive_list_files", "gdrive_search_files", "gdrive_get_file", "frappe_get_record", "frappe_list_records", "gmail_get_emails"):
			self.assertEqual(tool_effect(reads), READS, reads)
		for changes in ("gsheets_update", "gsheets_create", "frappe_create_record", "frappe_update_record", "gcalendar_create_event"):
			self.assertEqual(tool_effect(changes), CHANGES, changes)

	def test_unclassified_tools_count_as_changes(self):
		self.assertEqual(tool_effect("my_custom_tool"), CHANGES)
		self.assertEqual(tool_effect(None), CHANGES)
		self.assertEqual(tool_effect(""), CHANGES)

	def test_http_request_reads_only_for_get_and_head(self):
		self.assertEqual(tool_effect("http_request", {"url": "https://x.example"}), READS)
		self.assertEqual(tool_effect("http_request", {"method": "get"}), READS)
		self.assertEqual(tool_effect("http_request", {"method": "HEAD"}), READS)
		for method in ("POST", "PUT", "PATCH", "DELETE", "post"):
			self.assertEqual(tool_effect("http_request", {"method": method}), CHANGES, method)

	def test_multi_action_tools_follow_their_action(self):
		self.assertEqual(tool_effect("frappe_crm", {"action": "list_leads"}), READS)
		self.assertEqual(tool_effect("frappe_crm", {"action": "create_lead"}), CHANGES)
		self.assertEqual(tool_effect("erpnext", {"action": "get_sales_invoice"}), READS)
		self.assertEqual(tool_effect("telegram", {"action": "send_message"}), SENDS)
		self.assertEqual(tool_effect("raven", {"action": "send_message"}), SENDS)
		self.assertEqual(tool_effect("raven", {"action": "list_channels"}), READS)
		self.assertEqual(tool_effect("erpnext_inventory", {"action": "stock_balance"}), READS)
		self.assertEqual(tool_effect("helpdesk"), CHANGES)  # no action named: assume the worst

	def test_custom_tools_are_classified_by_their_type(self):
		self.assertEqual(tool_effect("my_lookup", None, "Get List"), READS)
		self.assertEqual(tool_effect("my_lookup", None, "GET"), READS)
		self.assertEqual(tool_effect("my_post", None, "POST"), CHANGES)
		self.assertEqual(tool_effect("my_mail", None, "Send Email"), SENDS)
		self.assertEqual(tool_effect("my_fn", None, "Custom Function"), CHANGES)
		# the table wins over the type
		self.assertEqual(tool_effect("slack_send_message", None, "Get List"), SENDS)


class TestSimulatedOutput(unittest.TestCase):
	def test_email_says_who_it_would_go_to(self):
		out = simulated_output("gmail_send_email", SENDS, {"to": "ada@example.com", "subject": "Hi", "body": "x"})
		self.assertTrue(out["simulated"])
		self.assertEqual(out["summary"], "Would send email to ada@example.com")
		self.assertIn("nothing was sent", out["note"].lower())
		self.assertEqual(out["labelIds"], ["SENT"])

	def test_slack_http_and_sheets_wording(self):
		self.assertEqual(simulated_output("slack_send_message", SENDS, {"channel": "#sales"})["summary"], "Would post a Slack message in #sales")
		post = simulated_output("http_request", CHANGES, {"method": "post", "url": "https://api.example.com/x"})
		self.assertEqual(post["summary"], "Would send a POST request to https://api.example.com/x")
		self.assertEqual(post["status_code"], 200)
		self.assertEqual(simulated_output("gsheets_update", CHANGES, {"range": "A1:B2"})["summary"], "Would update the sheet range A1:B2")
		self.assertEqual(simulated_output("frappe_create_record", CHANGES, {"doctype": "ToDo"})["summary"], "Would create a ToDo record")

	def test_unknown_tool_still_gets_a_sentence_and_missing_args_do_not_break_it(self):
		self.assertEqual(simulated_output("gmail_send_email", SENDS, None)["summary"], "Would send email")
		self.assertTrue(simulated_output("some_custom_tool", CHANGES, {})["summary"].startswith("Would run"))

	def test_a_long_recipient_is_shortened(self):
		out = simulated_output("gmail_send_email", SENDS, {"to": "x" * 200 + "@example.com"})
		self.assertLess(len(out["summary"]), 100)

	def test_document_and_code_samples(self):
		doc = simulated_document("ToDo")
		self.assertEqual((doc["simulated"], doc["summary"], doc["doctype"]), (True, "Would create a ToDo record", "ToDo"))
		self.assertTrue(doc["name"].startswith("(sample)"))
		code = simulated_code("Some Profile")
		self.assertTrue(code["simulated"])
		self.assertEqual(code["exit_status"], "ok")


class TestModes(unittest.TestCase):
	def test_normalize(self):
		self.assertEqual(normalize_mode("TEST"), MODE_TEST)
		self.assertEqual(normalize_mode(None), MODE_REAL)
		self.assertEqual(normalize_mode(" real "), MODE_REAL)
		with self.assertRaises(ValueError):
			normalize_mode("dry")

	def test_stored_value(self):
		self.assertEqual(stored_mode("test"), "Test")
		self.assertEqual(stored_mode("real"), "Real")
