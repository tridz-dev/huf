# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Replayed provider events and status callbacks cause no second effect. The 10k load and timing run belongs to the pre-PR gate."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.ai import gateway_webhook
from huf.ai.gateway_adapters.tests.test_gateway_pairing_hardening import _GatewayFixture
from huf.patches.v1 import gateway_event_unique_provider_id as patch_module

TOTAL_POSTS = 50
DUPLICATE_EVERY = 10  # every 10th post replays an earlier event (10% duplicates)


class TestGatewayEventReplay(_GatewayFixture, IntegrationTestCase):
	def admitting_gateway(self, label="R"):
		name = self.make_gateway(label, policy="Allow list", inbound_sender_limit=0, pairing_reply_enabled=0)
		self.make_entry(name, "15551230001", state="Approved")
		return name

	def post(self, gateway, event_id):
		context = {"sender_id": "15551230001", "conversation_id": "15551230001", "message_text": "hi"}
		return gsvc.ingest_gateway_event(gateway, event_id, context, verified_sender=True, raw_payload={})

	def run_jobs(self):
		return [
			c.kwargs["event_name"]
			for c in self.enqueue.call_args_list
			if c.args and c.args[0] == "huf.ai.gateway_service.process_gateway_event"
		]

	def run_counts(self):
		return frappe.db.count("Agent Run"), frappe.db.count("Agent Flow Run")

	def test_posts_with_10_percent_duplicates_queue_each_event_once(self):
		gateway = self.admitting_gateway()
		runs_before = self.run_counts()
		sent, replays = [], 0
		for i in range(TOTAL_POSTS):
			if i % DUPLICATE_EVERY == DUPLICATE_EVERY - 1:
				event_id = sent[i // 2 % len(sent)]
				# a replay costs one indexed lookup and nothing else
				with self.assertQueryCount(1):
					result = self.post(gateway, event_id)
				replays += 1
				self.assertTrue(result["duplicate"])
				self.assertTrue(result["event_name"])
			else:
				sent.append(f"wamid.{self.suffix}.{i}")
				self.assertEqual(self.post(gateway, sent[-1])["status"], "Queued")

		jobs = self.run_jobs()
		self.assertEqual((len(sent), replays), (45, 5))
		self.assertEqual((len(jobs), len(set(jobs))), (45, 45))
		self.assertEqual(frappe.db.count("Gateway Event", {"gateway": gateway}), 45)
		# one run job per event and none for a replay; ingest itself creates no run
		self.assertEqual(self.run_counts(), runs_before)

	def test_key_is_derived_so_a_second_row_for_the_same_id_cannot_be_inserted(self):
		gateway = self.admitting_gateway()
		self.post(gateway, "wamid.ONE")
		with self.assertRaises(frappe.UniqueValidationError):
			frappe.get_doc(
				{"doctype": "Gateway Event", "gateway": gateway, "idempotency_key": "other-" + self.suffix,
				 "provider_event_id": "wamid.ONE"}
			).insert(ignore_permissions=True)

	def test_ids_differing_only_in_case_or_gateway_are_distinct_events(self):
		first, second = self.admitting_gateway("A"), self.admitting_gateway("B")
		results = [self.post(first, "wamid.Ab"), self.post(first, "wamid.aB"), self.post(second, "wamid.Ab")]
		self.assertEqual([r["status"] for r in results], ["Queued"] * 3)

	def test_dead_letter_after_a_stored_event_changes_nothing(self):
		gateway = self.admitting_gateway()
		name = self.post(gateway, "wamid.DL")["event_name"]
		self.assertEqual(gsvc.store_ingest_dead_letter(gateway, "wamid.DL", {}, {}, "boom"), name)
		self.assertEqual(frappe.db.get_value("Gateway Event", name, "status"), "Queued")

	def test_patch_rekeys_old_rows_and_keeps_duplicates(self):
		gateway = self.admitting_gateway()
		names = []
		for i in range(2):
			name = self.post(gateway, f"wamid.OLD{i}")["event_name"]
			frappe.db.set_value("Gateway Event", name, {"idempotency_key": f"old{i}-{self.suffix}", "provider_event_id": "wamid.OLD"})
			names.append(name)
		with patch.object(patch_module.frappe, "reload_doc"):
			patch_module.execute()
			patch_module.execute()
		keys = [frappe.db.get_value("Gateway Event", n, "idempotency_key") for n in names]
		self.assertEqual(sorted(k == gsvc._idempotency_key(gateway, "wamid.OLD") for k in keys), [False, True])
		self.assertTrue(self.post(gateway, "wamid.OLD")["duplicate"])

	def test_replayed_reply_status_fires_the_delivery_hook_once(self):
		gateway = self.admitting_gateway()
		name = self.post(gateway, "wamid.ST")["event_name"]
		frappe.db.set_value("Gateway Event", name, "reply_message_id", f"wamid.out.{self.suffix}")
		with patch.object(gateway_webhook, "fire_hook") as hook:
			for _i in range(100):
				gateway_webhook._update_reply_status(gateway, {"id": f"wamid.out.{self.suffix}", "status": "delivered"})
		hook.assert_called_once()

	def test_replayed_failed_status_alerts_once_after_commit(self):
		gateway = self.admitting_gateway()
		status = {"id": f"wamid.f.{self.suffix}", "status": "failed", "timestamp": "1700000000",
				  "errors": [{"code": 131026, "title": "Undeliverable"}]}
		with patch.object(gateway_webhook, "_set_gateway_error") as alert, patch.object(gateway_webhook.frappe, "log_error"):
			gateway_webhook._record_failed_status(gateway, status, "WhatsApp")
			frappe.db.after_commit.run()
			gateway_webhook._record_failed_status(gateway, status, "WhatsApp")
		alert.assert_called_once()
