# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""H-W2-19: per-batch template/consent cache of the pre-send guard.

The throughput target (3k guarded sends/min on 4 workers) is deferred; this module checks the query budget
and that the cache never stretches a consent allow past its batch or past an opt-out.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import channel_consent
from huf.ai.channels.outbound import guard, guard_steps
from huf.ai.whatsapp import account_events, outbound_policy

MAX_QUERIES_PER_SEND = 3


def email_request(address, **over):
	return {
		"member_key": address,
		"channel": "email",
		"category": "marketing",
		"recipient": address,
		"template": None,
		"token_names": [],
		**over,
	}


def wa_request(**over):
	return {
		"member_key": "m1",
		"gateway": "gw",
		"channel": "whatsapp",
		"category": "service",
		"recipient": "+15550001234",
		"template": "tpl",
		"token_names": ["first_name"],
		**over,
	}


TEMPLATE = (
	"tpl-en",
	{
		"tpl": {"status": "APPROVED", "whatsapp_account": "acct", "category": "UTILITY", "sample": None},
		"tv": {"header_type": "", "carousel": None},
		"body": [{"index": 1}],
		"header": None,
		"buttons": [],
	},
)


class QueryCounter:
	def __init__(self):
		self.count = 0
		self._sql = frappe.db.sql

	def __enter__(self):
		def sql(*args, **kwargs):
			self.count += 1
			return self._sql(*args, **kwargs)

		self._patch = patch.object(frappe.db, "sql", side_effect=sql)
		self._patch.start()
		return self

	def __exit__(self, *exc):
		self._patch.stop()


class TestGuardBatchCache(IntegrationTestCase):
	def setUp(self):
		patcher = patch.object(guard, "_hook_paths", return_value=[])
		patcher.start()
		self.addCleanup(patcher.stop)

	def opted_in(self, n):
		addresses = [f"h-w2-19-{i}-{frappe.generate_hash(length=6)}@example.com" for i in range(n)]
		for address in addresses:
			channel_consent.record_opt_in("email", address, source="api")
		return addresses

	def test_query_budget_per_guarded_send(self):
		addresses = self.opted_in(4)
		with guard.batch():
			self.assertTrue(guard.evaluate(email_request(addresses[0])).allowed)  # warm-up
			with QueryCounter() as counter:
				for address in addresses[1:]:
					self.assertTrue(guard.evaluate(email_request(address)).allowed)
		per_send = counter.count / (len(addresses) - 1)
		self.assertLessEqual(per_send, MAX_QUERIES_PER_SEND, f"{counter.count} queries for 3 sends")

	def test_template_read_once_per_batch(self):
		loads, states = [], []
		with (
			patch.object(outbound_policy, "check_recipient"),
			patch.object(account_events, "is_marketing_allowed", return_value=True),
			patch.object(guard_steps, "_load_template", side_effect=lambda *a: loads.append(a) or TEMPLATE),
			patch.object(guard_steps, "_state_blocks", side_effect=lambda *a: states.append(a) or False),
		):
			with guard.batch():
				for _ in range(5):
					self.assertTrue(guard.evaluate(wa_request()).allowed)
			self.assertEqual((len(loads), len(states)), (1, 1))
			for _ in range(2):
				self.assertTrue(guard.evaluate(wa_request()).allowed)
			self.assertEqual((len(loads), len(states)), (3, 3), "outside a batch nothing is reused")

	def test_template_block_is_never_cached(self):
		blocks = iter([True, False])
		with (
			patch.object(outbound_policy, "check_recipient"),
			patch.object(account_events, "is_marketing_allowed", return_value=True),
			patch.object(guard_steps, "_load_template", return_value=TEMPLATE),
			patch.object(guard_steps, "_state_blocks", side_effect=lambda *a: next(blocks)),
			guard.batch(),
		):
			self.assertEqual(guard.evaluate(wa_request()).reason, "template_not_approved")
			self.assertTrue(guard.evaluate(wa_request()).allowed)

	def test_opt_out_invalidates_the_cached_allow(self):
		(address,) = self.opted_in(1)
		with guard.batch():
			self.assertTrue(guard.evaluate(email_request(address)).allowed)
			channel_consent.record_opt_out("email", address)
			guard.invalidate_consent(address)
			result = guard.evaluate(email_request(address))
		self.assertEqual((result.allowed, result.reason), (False, "opted_out"))

	def test_allow_never_outlives_its_batch(self):
		(address,) = self.opted_in(1)
		with guard.batch():
			self.assertTrue(guard.evaluate(email_request(address)).allowed)
		channel_consent.record_opt_out("email", address)  # no invalidation: the batch is over
		with guard.batch():
			self.assertEqual(guard.evaluate(email_request(address)).reason, "opted_out")

	def test_consent_block_drops_the_recipients_allows(self):
		(address,) = self.opted_in(1)
		with guard.batch():
			self.assertTrue(guard.evaluate(email_request(address)).allowed)
			channel_consent.record_opt_out("email", address)
			# the utility read sees the opt-out and drops the marketing allow cached above
			self.assertEqual(guard.evaluate(email_request(address, category="service")).reason, "opted_out")
			self.assertEqual(guard.evaluate(email_request(address)).reason, "opted_out")
