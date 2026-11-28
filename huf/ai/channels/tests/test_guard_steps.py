# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Built-in pre-send steps (H-W2-02). Template rows are faked: frappe_whatsapp need not be installed."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import guard, guard_steps
from huf.ai.whatsapp import account_events, outbound_policy

RECIPIENT = "+15550001234"
LINK = "https://media.example.com/a.png"


def template(status="APPROVED", header="", sample=None):
	return (
		"tpl-en",
		{
			"tpl": {"status": status, "whatsapp_account": "acct", "category": "UTILITY", "sample": sample},
			"tv": {"header_type": header, "carousel": None},
			"body": [{"index": 1}],
			"header": None,
			"buttons": [],
		},
	)


def request(**over):
	return {
		"member_key": "m1",
		"gateway": "gw",
		"channel": "whatsapp",
		"category": "service",
		"recipient": RECIPIENT,
		"template": "tpl",
		"token_names": ["first_name"],
		**over,
	}


class TestGuardSteps(IntegrationTestCase):
	def setUp(self):
		self.found = template()
		self.state_blocks = False
		for patcher in (
			patch.object(guard, "_hook_paths", return_value=[]),
			patch.object(outbound_policy, "check_recipient"),
			patch.object(account_events, "is_marketing_allowed", return_value=True),
			patch.object(guard_steps, "_load_template", side_effect=lambda *a: self.found),
			patch.object(guard_steps, "_state_blocks", side_effect=lambda *a: self.state_blocks),
			patch.dict(frappe.conf, {guard_steps.MEDIA_HOSTS_CONF: "media.example.com"}),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def assertBlocked(self, reason, step, header=None, **over):
		self.assertEqual(
			guard.evaluate(request(**over), header=header), guard.GuardResult(False, reason, step)
		)

	def test_good_send_is_allowed(self):
		self.assertEqual(guard.evaluate(request()), guard.GuardResult(True))

	def test_non_e164_recipient(self):
		for bad in ("15550001234", "+0155500012", "+1555", "+1555\n0001234", None):
			with self.subTest(bad=bad):
				self.assertBlocked("bad_recipient", "recipient", recipient=bad)
		self.assertEqual(guard_steps.normalise_recipient("00 1 (555) 000-1234"), RECIPIENT)
		self.assertBlocked("bsuid_recipient", "recipient", recipient="IN.4608123")

	def test_opt_outs_block(self):
		refused = outbound_policy.OutboundRefused("x", "opted_out")
		with patch.object(outbound_policy, "check_recipient", side_effect=refused):
			self.assertBlocked("opted_out", "consent")
		with patch.object(account_events, "is_marketing_allowed", return_value=False):
			self.assertBlocked("marketing_opted_out", "consent", category="marketing")
		self.assertBlocked("blocked_by_hook", "consent", gateway=None)

	def test_sms_marketing_needs_opt_in(self):
		self.assertBlocked("no_opt_in", "consent", channel="sms", category="marketing", template=None)

	def test_g5_unknown_row_empty_or_other_status_and_bad_state_block(self):
		self.found = None
		self.assertBlocked("template_not_approved", "template")
		for status in ("", None, "PENDING", "PAUSED", "REJECTED", "DISABLED"):
			with self.subTest(status=status):
				self.found = template(status=status)
				self.assertBlocked("template_not_approved", "template")
		self.found, self.state_blocks = template(), True
		self.assertBlocked("template_not_approved", "template")

	def test_variable_count(self):
		for names in ([], ["a", "b"], None):
			with self.subTest(names=names):
				self.assertBlocked("template_params_invalid", "template", token_names=names)

	def test_header_and_media_host(self):
		self.found = template(header="IMAGE")
		self.assertTrue(guard.evaluate(request(), header={"type": "image", "link": LINK}).allowed)
		for header in (None, "x", {"type": "video", "link": LINK}, {"type": "image"}):
			with self.subTest(header=header):
				self.assertBlocked("header_invalid", "template", header=header)
		for link in (
			"http://media.example.com/a.png",
			"https://evil.example.com/a.png",
			"https://media.example.com@evil.example.com/a",
			"https://media.example.com:8443/a",
		):
			with self.subTest(link=link):
				self.assertBlocked(
					"media_host_not_allowed", "template", header={"type": "image", "link": link}
				)
		self.found = template(header="IMAGE", sample="https://evil.example.com/s.png")
		self.assertBlocked("media_host_not_allowed", "template")
		self.found = template()
		self.assertBlocked("header_invalid", "template", header={"type": "image", "link": LINK})

	def test_app_hooks_do_not_see_the_header(self):
		seen = []

		def hook(req):
			seen.append(sorted(req))
			return {"allow": True}

		with (
			patch.object(guard, "_hook_paths", return_value=["app.hook"]),
			patch.object(frappe, "get_attr", return_value=hook),
		):
			self.assertTrue(guard.evaluate(request()).allowed)
		self.assertEqual(seen, [sorted(request())])


class TestTemplateReads(IntegrationTestCase):
	def test_gateway_without_account_finds_no_template(self):
		self.assertIsNone(guard_steps._load_template(None, "tpl"))
		self.assertIsNone(guard_steps._load_template("no-such-gateway", "tpl"))

	def test_state_row_that_contradicts_approved_blocks(self):
		cases = (
			(None, False),
			({"status": "APPROVED"}, False),
			({"status": "", "last_event": "REINSTATED"}, False),
			({"status": "PAUSED"}, True),
			({"status": "APPROVED", "last_event": "FLAGGED"}, True),
		)
		for state, blocks in cases:
			with (
				self.subTest(state=state),
				patch.object(frappe.db, "exists", return_value=True),
				patch.object(frappe.db, "get_value", return_value=state),
			):
				self.assertEqual(guard_steps._state_blocks("acct", "tpl-en"), blocks)
