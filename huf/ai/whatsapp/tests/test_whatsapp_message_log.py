# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Message log API, reply-delivery tracking, app tile and migrate indexes (N2).

Direct-mode tests run on both sites (``bridge.is_available`` is forced off);
bridge-mode tests need frappe_whatsapp and skip otherwise.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf import install
from huf.ai import gateway_webhook
from huf.ai.whatsapp import management as mgmt
from huf.ai.gateway_adapters import GatewayInboundRequest, whatsapp_bridge as bridge
from huf.ai.gateway_service import process_gateway_event

EXEC_USER = "wa-log-exec@example.com"
PLAIN_USER = "wa-log-plain@example.com"
SENDER = "15551234567"
BASE = datetime(2026, 3, 1, 10, 0, 0)


class _Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.suffix = frappe.generate_hash(length=6)
		for role in ("Huf Gateway User",):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", EXEC_USER):
			frappe.get_doc(
				{"doctype": "User", "email": EXEC_USER, "first_name": "WA Log", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("Huf Gateway User")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")

	@staticmethod
	def rand_phone():
		return "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)

	# fixtures --------------------------------------------------------------
	def make_gateway(self, label, account="", phone=None, secret="log-secret", enabled=1):
		phone = phone or self.rand_phone()
		settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": phone},
					{"key": "access_token", "value": f"tok-{label}"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": secret},
				],
			}
		).insert(ignore_permissions=True)
		gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"Log {label} {self.suffix}",
				"provider": "WhatsApp",
				"is_enabled": enabled,
				"integration_settings": settings.name,
				"whatsapp_account": account,
				"execution_user": EXEC_USER,
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True)
		gateway.phone = phone
		gateway.secret = secret
		return gateway

	def make_event(self, gateway, wamid, offset=0, *, agent=None, run=None, status="Succeeded", sender=SENDER,
		text="hello", reply=None, reply_status=None, error=None, delivery_error=None):
		event = frappe.get_doc(
			{
				"doctype": "Gateway Event",
				"gateway": gateway.name,
				"idempotency_key": f"{gateway.name}:{wamid}",
				"provider_event_id": wamid,
				"status": status,
				"sender_id": sender,
				"message_text": text,
				"target_agent": agent,
				"agent_run": run,
				"reply_message_id": reply,
				"reply_status": reply_status,
				"error_message": error,
				"delivery_error": delivery_error,
			}
		)
		event.flags.ignore_links = True
		event.insert(ignore_permissions=True)
		self.stamp("Gateway Event", event.name, offset)
		return event

	@staticmethod
	def stamp(doctype, name, offset):
		frappe.db.set_value(doctype, name, "creation", BASE + timedelta(seconds=offset), update_modified=False)

	def ids(self, result):
		return [i["message_id"] for i in result["items"]]


class TestDirectModeMessageLog(_Base):
	"""Gateway-Event-only log; runs on every site."""

	def setUp(self):
		super().setUp()
		patcher = patch.object(bridge, "is_available", return_value=False)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.gw = self.make_gateway("A")
		self.other = self.make_gateway("B")

	def log(self, **kw):
		kw.setdefault("gateway_name", self.gw.name)
		return mgmt.list_message_log(**kw)

	def test_events_and_replies_form_the_log(self):
		self.make_event(self.gw, "wamid.IN1", 0, agent="Agent X", run="RUN-1", reply="wamid.OUT1", reply_status="read")
		self.make_event(self.gw, "wamid.IN2", 10, status="Failed", error="boom")
		result = self.log()
		self.assertTrue(result["success"])
		self.assertEqual(self.ids(result), ["wamid.IN2", "wamid.OUT1", "wamid.IN1"])
		self.assertFalse(result["has_more"])
		self.assertIsNone(result["next_cursor"])
		failed, reply, inbound = result["items"]
		self.assertEqual((failed["direction"], failed["sent_by"], failed["status"], failed["error"]), ("in", "customer", "Failed", "boom"))
		self.assertEqual((reply["direction"], reply["sent_by"], reply["status"], reply["agent"], reply["agent_run"]), ("out", "agent", "read", "Agent X", "RUN-1"))
		self.assertEqual((inbound["phone"], inbound["text"], inbound["gateway"]), (SENDER, "hello", self.gw.name))
		self.assertTrue(inbound["event"] and inbound["creation"].startswith("2026-03-01T10:00:00"))
		for key in ("name", "message_id", "direction", "phone", "profile_name", "content_type", "text", "status", "error",
			"template", "creation", "gateway", "agent", "agent_run", "event", "sent_by"):
			self.assertIn(key, inbound)

	def test_keyset_paging_with_identical_creation_timestamps(self):
		for i in range(7):
			self.make_event(self.gw, f"wamid.T{i}", 0, reply=f"wamid.TR{i}" if i % 2 == 0 else None)
		everything = self.log(limit=100)
		self.assertEqual(len(everything["items"]), 11)
		seen, cursor, pages = [], None, 0
		while True:
			page = self.log(limit=4, cursor=cursor)
			pages += 1
			seen += [i["name"] for i in page["items"]]
			self.assertLessEqual(len(page["items"]), 4)
			if not page["has_more"]:
				self.assertIsNone(page["next_cursor"])
				break
			cursor = page["next_cursor"]
		self.assertEqual(pages, 3)
		self.assertEqual(seen, [i["name"] for i in everything["items"]])
		self.assertEqual(len(seen), len(set(seen)))
		decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
		self.assertEqual(set(decoded), {"c", "n"})

	def test_filters(self):
		self.make_event(self.gw, "wamid.F1", 0, agent="Agent X", sender="15550000001", text="order status please", reply="wamid.FR1", reply_status="delivered")
		self.make_event(self.gw, "wamid.F2", 100, agent="Agent Y", sender="15550000002", text="refund", status="Failed")
		self.assertEqual(self.ids(self.log(direction="out")), ["wamid.FR1"])
		self.assertEqual(self.ids(self.log(direction="in")), ["wamid.F2", "wamid.F1"])
		self.assertEqual(self.ids(self.log(status="delivered")), ["wamid.FR1"])
		self.assertEqual(self.ids(self.log(status="Failed")), ["wamid.F2"])
		self.assertEqual(self.ids(self.log(agent="Agent Y")), ["wamid.F2"])
		self.assertEqual(self.ids(self.log(phone="+1 (555) 000-0001")), ["wamid.FR1", "wamid.F1"])
		self.assertEqual(self.ids(self.log(q="refund")), ["wamid.F2"])
		self.assertEqual(self.ids(self.log(q="100%")), [])
		self.assertEqual(self.ids(self.log(template="anything")), [])
		self.assertEqual(self.ids(self.log(date_from="2026-03-01", date_to="2026-03-01")), ["wamid.F2", "wamid.FR1", "wamid.F1"])
		self.assertEqual(self.ids(self.log(date_from="2026-03-02")), [])
		self.assertEqual(self.ids(self.log(date_to="2026-03-01T10:00:00")), ["wamid.FR1", "wamid.F1"])

	def test_validation_errors_and_limit_clamp(self):
		self.assertEqual(self.log(cursor="not-a-cursor")["error"], "invalid_cursor")
		self.assertEqual(self.log(date_from="garbage")["error"], "invalid_date")
		self.assertEqual(self.log(direction="sideways")["error"], "invalid_direction")
		self.assertEqual(mgmt.list_message_log()["error"], "gateway_required")
		self.assertEqual(mgmt.list_message_log(gateway_name="nope")["error"], "not_found")
		for i in range(3):
			self.make_event(self.gw, f"wamid.L{i}", i)
		self.assertEqual(len(self.log(limit=0)["items"]), 1)  # clamped up to 1
		self.assertEqual(len(self.log(limit=-5)["items"]), 1)
		# `limit: int` is type-checked on the whitelisted API where Frappe enforces annotations (it raises
		# FrappeTypeError); where it does not, the unparsable value falls back to the default.
		try:
			fallback = self.log(limit="x")
		except frappe.exceptions.FrappeTypeError:
			pass
		else:
			self.assertEqual(len(fallback["items"]), 3)
		self.assertEqual(len(self.log(limit=10_000)["items"]), 3)

	def test_gateways_are_isolated(self):
		self.make_event(self.gw, "wamid.G1", 0, agent="Agent X")
		self.make_event(self.other, "wamid.G2", 1, agent="Agent Z")
		self.assertEqual(self.ids(self.log()), ["wamid.G1"])
		self.assertEqual(self.ids(mgmt.list_message_log(gateway_name=self.other.name)), ["wamid.G2"])
		self.assertEqual([a["name"] for a in mgmt.list_message_log_filters(self.gw.name)["agents"]], ["Agent X"])

	def test_filters_endpoint_shape(self):
		self.make_event(self.gw, "wamid.H1", 0, agent="Agent X", reply="wamid.HR1", reply_status="sent")
		out = mgmt.list_message_log_filters(self.gw.name)
		self.assertTrue(out["success"])
		self.assertEqual(out["agents"], [{"name": "Agent X", "title": "Agent X"}])
		self.assertEqual(out["templates"], [])
		self.assertEqual(out["directions"], ["in", "out"])
		self.assertIn("Succeeded", out["statuses"])
		self.assertIn("sent", out["statuses"])
		self.assertEqual(mgmt.list_message_log_filters()["error"], "gateway_required")

	def test_authorization(self):
		self.make_event(self.gw, "wamid.A1", 0)
		if not frappe.db.exists("User", PLAIN_USER):
			frappe.get_doc(
				{"doctype": "User", "email": PLAIN_USER, "first_name": "Plain", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			mgmt.list_message_log(gateway_name=self.gw.name)
		with self.assertRaises(frappe.PermissionError):
			mgmt.list_message_log_filters(self.gw.name)
		frappe.set_user("Administrator")
		self.assertTrue(mgmt.list_message_log(gateway_name=self.gw.name)["success"])

	def test_non_whatsapp_gateway_is_refused(self):
		with patch.object(mgmt.frappe.db, "get_value", return_value="Telegram"):
			self.assertEqual(self.log()["error"], "not_whatsapp")

	def test_event_query_count_does_not_grow_with_rows(self):
		def count(limit):
			calls = []
			real = frappe.db.sql

			def spy(*a, **k):
				calls.append(a[0] if a else None)
				return real(*a, **k)

			self.log(limit=limit)  # warm per-process caches (meta, roles) so only the page queries are counted
			with patch.object(frappe.db, "sql", spy):
				self.log(limit=limit)
			return len(calls)

		for i in range(20):
			self.make_event(self.gw, f"wamid.Q{i}", i, reply=f"wamid.QR{i}")
		self.assertEqual(count(2), count(40))


class TestBridgeModeMessageLog(_Base):
	"""WhatsApp Message based log; needs frappe_whatsapp."""

	def setUp(self):
		super().setUp()
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site")
		def no_network(*args, **kwargs):
			raise AssertionError("tests must never call Meta")

		blocker = patch("frappe.integrations.utils.get_request_session", no_network)
		blocker.start()
		self.addCleanup(blocker.stop)
		pa, pb = self.rand_phone(), self.rand_phone()
		self.acct_a = self.make_account("A", pa)
		self.acct_b = self.make_account("B", pb)
		self.gw = self.make_gateway("A", self.acct_a.name, phone=pa)
		self.other = self.make_gateway("B", self.acct_b.name, phone=pb)

	def make_account(self, label, phone):
		return frappe.get_doc(
			{
				"doctype": "WhatsApp Account",
				"account_name": f"Log {label} {self.suffix}",
				"status": "Active",
				"url": "https://graph.facebook.com",
				"version": "v21.0",
				"phone_id": phone,
				"business_id": f"biz-{label}",
				"app_id": "app",
				"token": f"t-{label}-{self.suffix}",
				"webhook_verify_token": f"v-{label}-{self.suffix}",
			}
		).insert(ignore_permissions=True)

	def make_message(self, account, wamid, offset, *, direction="Incoming", phone=SENDER, text="hi", status=None,
		template=None, profile=None):
		values = {
			"doctype": "WhatsApp Message",
			"type": direction,
			"message": text,
			"message_id": wamid,
			"content_type": "text",
			"whatsapp_account": account.name,
			"profile_name": profile,
			"status": status,
		}
		# Insert as Incoming (an Outgoing insert would hit Meta), then flip the direction in the DB.
		values["type"] = "Incoming"
		values["from"] = phone
		doc = frappe.get_doc(values)
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		if direction == "Outgoing":
			frappe.db.set_value(
				"WhatsApp Message", doc.name, {"type": "Outgoing", "from": None, "to": phone}, update_modified=False
			)
		if template:
			frappe.db.set_value("WhatsApp Message", doc.name, "template", template, update_modified=False)
		self.stamp("WhatsApp Message", doc.name, offset)
		return doc

	def log(self, **kw):
		kw.setdefault("gateway_name", self.gw.name)
		return mgmt.list_message_log(**kw)

	def test_classification_and_agent_join(self):
		self.make_message(self.acct_a, "wamid.C1", 0, profile="Ann", text="<b>where</b> is my order")
		self.make_event(self.gw, "wamid.C1", 0, agent="Agent X", run="RUN-9", reply="wamid.C2")
		self.make_message(self.acct_a, "wamid.C2", 5, direction="Outgoing", text="on its way", status="sent")
		self.make_message(self.acct_a, "wamid.C3", 6, direction="Outgoing", text="promo", status="Success", template="promo_tpl")
		self.make_message(self.acct_a, "wamid.C4", 7, direction="Outgoing", text="manual hi", status="Success")
		by_id = {i["message_id"]: i for i in self.log()["items"]}
		self.assertEqual(self.ids(self.log()), ["wamid.C4", "wamid.C3", "wamid.C2", "wamid.C1"])
		c1, c2, c3, c4 = (by_id[f"wamid.C{n}"] for n in (1, 2, 3, 4))
		self.assertEqual((c1["direction"], c1["sent_by"], c1["agent"], c1["agent_run"], c1["profile_name"]), ("in", "customer", "Agent X", "RUN-9", "Ann"))
		self.assertEqual(c1["text"], "where is my order")
		self.assertEqual((c2["direction"], c2["sent_by"], c2["agent"], c2["agent_run"]), ("out", "agent", "Agent X", "RUN-9"))
		self.assertEqual((c3["sent_by"], c3["template"], c3["agent"], c3["event"]), ("template", "promo_tpl", None, None))
		self.assertEqual((c4["sent_by"], c4["template"]), ("manual", None))
		self.assertEqual(c4["phone"], SENDER)

	def test_text_preview_is_capped(self):
		self.make_message(self.acct_a, "wamid.BIG", 0, text="x" * 900)
		self.assertEqual(len(self.log()["items"][0]["text"]), 300)

	def test_paging_with_identical_timestamps_and_filters(self):
		for i in range(9):
			self.make_message(self.acct_a, f"wamid.P{i}", 0, direction="Incoming" if i % 3 else "Outgoing",
				phone="15557770000" if i < 5 else "15558880000", status="read" if i % 3 == 0 else None,
				text="alpha" if i < 4 else "beta", template="tpl_one" if i == 0 else None)
		everything = self.log(limit=100)
		self.assertEqual(len(everything["items"]), 9)
		seen, cursor, pages = [], None, 0
		while True:
			page = self.log(limit=4, cursor=cursor)
			pages += 1
			seen += [i["name"] for i in page["items"]]
			if not page["has_more"]:
				break
			cursor = page["next_cursor"]
		self.assertEqual((pages, seen), (3, [i["name"] for i in everything["items"]]))
		self.assertEqual(len(self.log(direction="out")["items"]), 3)
		self.assertEqual(len(self.log(direction="in")["items"]), 6)
		self.assertEqual(len(self.log(status="read")["items"]), 3)
		self.assertEqual(self.ids(self.log(template="tpl_one")), ["wamid.P0"])
		self.assertEqual(len(self.log(phone="+1 555 777 0000")["items"]), 5)
		self.assertEqual(len(self.log(q="beta")["items"]), 5)
		self.assertEqual(len(self.log(date_from="2026-03-01", date_to="2026-03-01")["items"]), 9)
		self.assertEqual(self.log(date_to="2026-02-28")["items"], [])

	def test_agent_filter_matches_inbound_and_reply(self):
		self.make_message(self.acct_a, "wamid.AG1", 0)
		self.make_message(self.acct_a, "wamid.AG2", 1, direction="Outgoing", status="sent")
		self.make_message(self.acct_a, "wamid.AG3", 2)
		self.make_event(self.gw, "wamid.AG1", 0, agent="Agent X", reply="wamid.AG2")
		self.make_event(self.gw, "wamid.AG3", 2, agent="Agent Y")
		self.assertEqual(sorted(self.ids(self.log(agent="Agent X"))), ["wamid.AG1", "wamid.AG2"])
		self.assertEqual(self.ids(self.log(agent="Agent Y")), ["wamid.AG3"])
		# an event status / reply status is searchable too
		frappe.db.set_value("Gateway Event", self.make_event(self.gw, "wamid.AG4", 3, reply="wamid.AG5", reply_status="failed", delivery_error="error 131047: window").name, "status", "Succeeded")
		self.make_message(self.acct_a, "wamid.AG4", 3)
		self.make_message(self.acct_a, "wamid.AG5", 4, direction="Outgoing", status="Success")
		failed = self.log(status="failed")["items"]
		self.assertEqual([i["message_id"] for i in failed], ["wamid.AG5"])
		self.assertEqual((failed[0]["status"], failed[0]["error"]), ("failed", "error 131047: window"))

	def test_accounts_are_isolated(self):
		self.make_message(self.acct_a, "wamid.I1", 0)
		self.make_message(self.acct_b, "wamid.I2", 1)
		self.make_event(self.other, "wamid.I2", 1, agent="Agent Z")
		self.assertEqual(self.ids(self.log()), ["wamid.I1"])
		self.assertEqual(self.ids(mgmt.list_message_log(gateway_name=self.other.name)), ["wamid.I2"])
		# an event of the other gateway never enriches this gateway's rows
		self.make_message(self.acct_a, "wamid.I3", 2)
		self.make_event(self.other, "wamid.I3", 2, agent="Agent Z")
		row = [i for i in self.log()["items"] if i["message_id"] == "wamid.I3"][0]
		self.assertIsNone(row["agent"])
		self.assertEqual(mgmt.list_message_log_filters(self.gw.name)["agents"], [])

	def test_filters_endpoint(self):
		self.make_message(self.acct_a, "wamid.D1", 0, direction="Outgoing", status="Success", template="tpl_z")
		self.make_message(self.acct_b, "wamid.D2", 0, direction="Outgoing", status="Odd", template="tpl_other")
		out = mgmt.list_message_log_filters(self.gw.name)
		self.assertEqual(out["templates"], ["tpl_z"])
		self.assertIn("Success", out["statuses"])
		self.assertNotIn("Odd", out["statuses"])

	def test_gateway_without_account_and_permissions(self):
		bare = self.make_gateway("bare", "")
		self.assertEqual(mgmt.list_message_log(gateway_name=bare.name)["error"], "no_account")
		if not frappe.db.exists("User", PLAIN_USER):
			frappe.get_doc(
				{"doctype": "User", "email": PLAIN_USER, "first_name": "Plain", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(PLAIN_USER)
		with self.assertRaises(frappe.PermissionError):
			self.log()

	def test_query_count_does_not_grow_with_rows(self):
		def count(limit):
			calls = []
			real = frappe.db.sql

			def spy(*a, **k):
				calls.append(1)
				return real(*a, **k)

			self.log(limit=limit)  # warm per-process caches (meta, roles) so only the page queries are counted
			with patch.object(frappe.db, "sql", spy):
				self.log(limit=limit)
			return len(calls)

		for i in range(30):
			self.make_message(self.acct_a, f"wamid.N{i}", i)
			self.make_event(self.gw, f"wamid.N{i}", i, agent="Agent X")
		self.assertEqual(count(3), count(30))

	def test_migrate_indexes_are_idempotent(self):
		install.ensure_whatsapp_message_indexes()
		install.ensure_whatsapp_message_indexes()
		for name, _cols in install.WHATSAPP_MESSAGE_INDEXES:
			self.assertTrue(frappe.db.has_index("tabWhatsApp Message", name), name)


class TestIndexesWithoutBridge(IntegrationTestCase):
	def test_missing_doctype_never_fails(self):
		with patch.object(install.frappe.db, "exists", return_value=False), patch.object(
			install.frappe.db, "add_index"
		) as add:
			install.ensure_whatsapp_message_indexes()
		add.assert_not_called()
		with patch.object(install.frappe.db, "exists", side_effect=RuntimeError("db gone")):
			install.ensure_whatsapp_message_indexes()


class TestReplyDeliveryTracking(_Base):
	def setUp(self):
		super().setUp()
		# unique per run so a committed leftover gateway can never collide on phone_number_id
		uniq = f"{int(self.suffix, 16):08d}"[-8:]
		self.gw = self.make_gateway("D", secret="d-secret", phone=f"5559{uniq}1")
		self.other = self.make_gateway("E", secret="e-secret", phone=f"5559{uniq}2")
		self.agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"WA Log Agent {self.suffix}",
				"agent_modality": "Both",
				"instructions": "fixture",
				"allowed_users": [{"user": EXEC_USER}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Gateway", self.gw.name, {"default_target_type": "Agent", "default_agent": self.agent.name})
		frappe.get_doc(
			{"doctype": "Gateway Access Entry", "gateway": self.gw.name, "entry_type": "Sender", "provider": "WhatsApp",
				"external_id": SENDER, "state": "Approved"}
		).insert(ignore_permissions=True)
		for target, new in (
			("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None),
			("huf.ai.gateway_service._throttle_outbound_send", lambda *a, **k: None),
			("huf.ai.agent.integration.run_agent_sync", lambda **k: {"response": "ok", "agent_run_id": "RUN-X"}),
		):
			patcher = patch(target, new)
			patcher.start()
			self.addCleanup(patcher.stop)

	def post(self, gateway, payload):
		raw = json.dumps(payload).encode()
		sig = "sha256=" + hmac.new(gateway.secret.encode(), raw, hashlib.sha256).hexdigest()
		request = GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query={}, method="POST")
		frappe.local.request = SimpleNamespace(args={"gateway_name": gateway.name})
		with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
			return gateway_webhook.handle_gateway_webhook()

	def status_payload(self, gateway, wamid, state, errors=None):
		status = {"id": wamid, "status": state, "recipient_id": SENDER}
		if errors:
			status["errors"] = errors
		value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": gateway.phone}, "statuses": [status]}
		return {"entry": [{"id": "biz", "changes": [{"field": "messages", "value": value}]}]}

	def inbound(self, wamid):
		value = {
			"messaging_product": "whatsapp",
			"metadata": {"phone_number_id": self.gw.phone},
			"messages": [{"from": SENDER, "id": wamid, "type": "text", "text": {"body": "hello"}}],
			"contacts": [{"wa_id": SENDER, "profile": {"name": "Ann"}}],
		}
		self.assertTrue(self.post(self.gw, {"entry": [{"id": "biz", "changes": [{"field": "messages", "value": value}]}]})["success"])
		return frappe.db.get_value("Gateway Event", {"gateway": self.gw.name, "provider_event_id": wamid}, "name")

	def reply_state(self, event):
		return frappe.db.get_value("Gateway Event", event, ["reply_message_id", "reply_status", "delivery_error"], as_dict=True)

	def test_reply_id_stored_after_send_and_fallback_send(self):
		for wamid, fallback in (("wamid.RS1", False), ("wamid.RS2", True)):
			event = self.inbound(wamid)
			delivery = SimpleNamespace(
				provider_message_id=f"wamid.OUT.{wamid}",
				provider_response={"fallback_template_sent": True} if fallback else {},
			)
			with patch("huf.ai.gateway_webhook.send_gateway_parts", return_value=delivery):
				result = process_gateway_event(event)
			frappe.set_user("Administrator")
			self.assertEqual(result["status"], "Succeeded", result)
			state = self.reply_state(event)
			self.assertEqual((state.reply_message_id, state.reply_status), (f"wamid.OUT.{wamid}", "sent"))

	def test_status_webhook_updates_only_the_receiving_gateways_event(self):
		mine = self.make_event(self.gw, "wamid.M1", 0, reply="wamid.SAME", reply_status="sent")
		theirs = self.make_event(self.other, "wamid.M2", 0, reply="wamid.SAME", reply_status="sent")
		self.assertTrue(self.post(self.gw, self.status_payload(self.gw, "wamid.SAME", "delivered"))["success"])
		self.assertEqual(self.reply_state(mine.name).reply_status, "delivered")
		self.assertEqual(self.reply_state(theirs.name).reply_status, "sent")
		self.post(self.gw, self.status_payload(self.gw, "wamid.SAME", "read"))
		self.assertEqual(self.reply_state(mine.name).reply_status, "read")
		# out-of-order "delivered" after "read" must not regress
		self.post(self.gw, self.status_payload(self.gw, "wamid.SAME", "delivered"))
		self.assertEqual(self.reply_state(mine.name).reply_status, "read")

	def test_failed_status_records_redacted_delivery_error_and_gateway_error(self):
		event = self.make_event(self.gw, "wamid.FL", 0, reply="wamid.FLR", reply_status="sent")
		errors = [{"code": 131047, "title": "Re-engagement Bearer abc123secretvalue"}]
		self.assertTrue(self.post(self.gw, self.status_payload(self.gw, "wamid.FLR", "failed", errors))["success"])
		state = self.reply_state(event.name)
		self.assertEqual(state.reply_status, "failed")
		self.assertIn("131047", state.delivery_error)
		self.assertNotIn("abc123secretvalue", state.delivery_error)
		self.assertIn("131047", frappe.db.get_value("Gateway", self.gw.name, "last_error") or "")

	def test_unknown_or_unsupported_statuses_never_raise(self):
		gateway_webhook._update_reply_status(self.gw.name, {"id": "wamid.NOPE", "status": "delivered"})
		gateway_webhook._update_reply_status(self.gw.name, {"id": "", "status": "delivered"})
		gateway_webhook._update_reply_status(self.gw.name, {"id": "x", "status": "weird"})
		gateway_webhook._update_reply_status(self.gw.name, {"status": None, "errors": "bad"})
		with patch.object(gateway_webhook.frappe.db, "get_value", side_effect=RuntimeError("db")):
			gateway_webhook._update_reply_status(self.gw.name, {"id": "x", "status": "sent"})


class TestWhatsAppAppTile(_Base):
	def setUp(self):
		super().setUp()
		frappe.db.delete("HUF App", {"app_id": install.WHATSAPP_APP_ID})

	def test_seeding_is_idempotent_and_keeps_admin_enabled_flag(self):
		install.create_whatsapp_app()
		install.create_whatsapp_app()
		self.assertEqual(frappe.db.count("HUF App", {"app_id": "whatsapp"}), 1)
		doc = frappe.get_doc("HUF App", {"app_id": "whatsapp"})
		self.assertEqual(
			(doc.title, doc.route, doc.source_app, doc.launch_mode, doc.category, doc.enabled),
			("WhatsApp", "/huf/whatsapp", "huf", "Route", "Communicate", 1),
		)
		self.assertEqual(doc.permission_method, "huf.ai.whatsapp.management.can_launch_whatsapp_app")
		self.assertEqual(doc.description, "Manage WhatsApp templates and see messages handled by your agents.")
		frappe.db.set_value("HUF App", doc.name, {"enabled": 0, "title": "Hand edited"})
		install.create_whatsapp_app()
		again = frappe.get_doc("HUF App", doc.name)
		self.assertEqual((again.enabled, again.title), (0, "WhatsApp"))
		self.assertTrue(frappe.get_attr(again.permission_method))

	def test_migrate_sync_keeps_the_tile(self):
		install.create_whatsapp_app()
		from huf.ai.app_seeding.apps_loader import sync_huf_apps

		sync_huf_apps()
		self.assertTrue(frappe.db.exists("HUF App", {"app_id": "whatsapp"}))

	def test_permission_method_truth_table(self):
		can = mgmt.can_launch_whatsapp_app
		frappe.db.set_value("Gateway", {"provider": "WhatsApp"}, "is_enabled", 0)
		self.assertTrue(can("Administrator", {}), "admins can launch with zero enabled gateways (setup lives in the app)")
		gw = self.make_gateway("T")
		self.assertTrue(can("Administrator", {}))
		self.assertTrue(can(user="Administrator", app={"app_id": "whatsapp"}))
		self.assertFalse(can("Guest", {}))
		self.assertFalse(can(None, {}) if frappe.session.user == "Guest" else False)
		if not frappe.db.exists("User", PLAIN_USER):
			frappe.get_doc(
				{"doctype": "User", "email": PLAIN_USER, "first_name": "Plain", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		self.assertFalse(can(PLAIN_USER, {}), "no admin role")
		with patch("huf.permissions.has_capability", return_value=True):
			self.assertTrue(can(PLAIN_USER, {}), "integrations capability")
		frappe.db.set_value("Gateway", gw.name, "is_enabled", 0)
		self.assertTrue(can("Administrator", {}), "disabled gateway does not hide the tile from admins")
		frappe.db.set_value("Gateway", gw.name, {"is_enabled": 1, "provider": "Telegram"})
		self.assertTrue(can("Administrator", {}), "gateway provider is irrelevant to the admin gate")
		self.assertFalse(can(PLAIN_USER, {}), "non-admin without the capability stays out, gateways or not")

	def test_permission_method_never_raises(self):
		with patch.object(mgmt.frappe, "get_roles", side_effect=RuntimeError("boom")):
			self.assertFalse(mgmt.can_launch_whatsapp_app("Administrator", {}))

	def test_launcher_uses_the_permission_method(self):
		from huf.ai import apps_api

		self.assertFalse(apps_api._call_permission_method(
			"huf.ai.whatsapp.management.can_launch_whatsapp_app", "Guest", {"app_id": "whatsapp"}))
