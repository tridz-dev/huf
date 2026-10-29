# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""QA-S1S12: the broadcast live-verification scenarios S1-S12 (docs/whatsapp/broadcast-live-verification.md)
as scripted bench checks.

The real code paths run against the real bench database: whitelisted broadcast API as real users, the runner tick,
``send_one`` and the WhatsApp bridge. Only the outside world is replaced:

* the Graph HTTP post (``bridge._default_post``) is a stub that records every would-be call and refuses any recipient
  outside the fictional ``44 7700 900xxx`` range (``AllowListViolation``, a BaseException so product code cannot
  swallow it); ``requests`` is blocked outright, so nothing can reach Meta;
* Meta's tier/quality read, the queue (``frappe.enqueue``) and the pacing sleep.

Status callbacks are real signed webhooks: an HMAC-SHA256 (``X-Hub-Signature-256``) with a test app secret posted to
``gateway_webhook.handle_gateway_webhook``. Parts that need a real handset or the Meta console are marked
``OWNER-LIVE`` (see docs/WHATSAPP_BROADCAST_LIVE_CHECKS.md).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import pathlib
import re
import unittest
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service, gateway_webhook
from huf.ai.gateway_adapters import GatewayInboundRequest, whatsapp_bridge as bridge
from huf.ai.whatsapp.broadcast import api as bapi, limits as blimits, runner, send as bsend, stale

PREFIX = "S1S12"
ACCOUNT = f"{PREFIX} Account"
FAKE_URL = "http://s1s12-fake-graph.invalid"
FAKE_TOKEN = "FAKE-TOKEN-NOT-A-META-TOKEN"
PHONE_ID = "s1s12-fake-phone-id"
APP_SECRET = "s1s12-test-app-secret"
ALLOWED = re.compile(r"^447700900\d{3}$")
WRITER, ADMIN = (f"s1s12-{r}@example.com" for r in ("writer", "admin"))
B, R = "WhatsApp Broadcast", "WhatsApp Broadcast Recipient"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
STATE: dict = {}


class AllowListViolation(BaseException):
	"""Raised by the stubs; BaseException so no ``except Exception`` in product code can hide it."""


def num(i: int) -> str:
	return f"447700900{i:03d}"


# ------------------------------------------------------------------ stand-in doctypes
# This bench may not have frappe_whatsapp. The broadcast code reads WhatsApp Account / Templates / Button / Message
# through the bridge, so when they are missing the module creates minimal custom stand-ins (only the columns the
# code touches) and drops them again in tearDownModule. Nothing is created when the real app is installed.

_STUBS = {
	"WhatsApp Account": ("field:account_name", 0, [
		("account_name", "Data"), ("status", "Data"), ("url", "Data"), ("version", "Data"), ("phone_id", "Data"),
		("business_id", "Data"), ("app_id", "Data"), ("token", "Password"), ("webhook_verify_token", "Data"),
		("is_default_outgoing", "Check")]),
	"WhatsApp Templates": ("prompt", 0, [
		("template_name", "Data"), ("actual_name", "Data"), ("template", "Small Text"), ("sample_values", "Data"),
		("sample", "Data"), ("header_type", "Data"), ("header", "Data"), ("language", "Data"),
		("language_code", "Data"), ("category", "Data"), ("status", "Data"), ("whatsapp_account", "Data")]),
	"WhatsApp Button": ("hash", 1, [
		("button_type", "Data"), ("button_label", "Data"), ("url_type", "Data"), ("website_url", "Data")]),
	"WhatsApp Message": ("hash", 0, [
		("type", "Data"), ("to", "Data"), ("use_template", "Check"), ("template", "Data"), ("whatsapp_account", "Data"),
		("content_type", "Data"), ("message_id", "Data"), ("status", "Data"), ("template_parameters", "Small Text"),
		("body_param", "Small Text"), ("template_header_parameters", "Small Text"), ("attach", "Data")]),
}


def _ensure_stub_doctypes() -> None:
	STATE["stubs"] = []
	for name, (autoname, istable, fields) in _STUBS.items():
		if frappe.db.exists("DocType", name):
			continue
		frappe.get_doc(
			{
				"doctype": "DocType", "name": name, "module": "Huf", "custom": 1, "autoname": autoname, "istable": istable,
				"fields": [{"fieldname": f, "label": f, "fieldtype": t} for f, t in fields],
				"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
			}
		).insert(ignore_permissions=True)
		STATE["stubs"].append(name)
	frappe.db.commit()


def _drop_stub_doctypes() -> None:
	for name in reversed(STATE.get("stubs", [])):
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
	frappe.db.commit()


# ------------------------------------------------------------------ fixtures


def _purge() -> None:
	for gw in frappe.get_all("Gateway", {"gateway_name": f"{PREFIX} Gateway"}, pluck="name"):
		bcs = frappe.get_all(B, {"gateway": gw}, pluck="name")
		if bcs:
			frappe.db.delete(R, {"broadcast": ["in", bcs]})
			frappe.db.delete("WhatsApp Broadcast Audience", {"parent": ["in", bcs]})
			frappe.db.delete("Comment", {"reference_doctype": B, "reference_name": ["in", bcs]})
			frappe.db.delete(B, {"name": ["in", bcs]})
		frappe.db.delete("Gateway Consent", {"gateway": gw})
		frappe.db.delete("Gateway Access Entry", {"gateway": gw})
		frappe.db.delete("DocShare", {"share_doctype": "Gateway", "share_name": gw})
		frappe.db.delete("Gateway", {"name": gw})
	for dt, field in (("WhatsApp Templates", "whatsapp_account"), ("WhatsApp Message", "whatsapp_account"), ("WhatsApp Account", "name")):
		if frappe.db.exists("DocType", dt):
			frappe.db.delete(dt, {field: ACCOUNT})
	if STATE.get("integration"):
		frappe.db.delete("Integration Settings", {"name": STATE["integration"]})
	for user in (WRITER, ADMIN):
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	frappe.db.commit()


def _template(name: str, category: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Templates", "name": f"{name}-en", "template_name": name, "actual_name": name,
			"template": "Hello {{1}}, here is your update.", "sample_values": "Ann", "language": "en",
			"language_code": "en", "category": category, "status": "APPROVED", "whatsapp_account": ACCOUNT,
		}
	)  # fmt: skip
	doc.db_insert()  # the controller's after_insert would submit it to Meta
	return f"{name}-en"


def _user(email: str, roles: tuple[str, ...] = ()) -> None:
	user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0})
	user.insert(ignore_permissions=True)
	if roles:
		user.add_roles(*roles)


def setUpModule() -> None:
	frappe.set_user("Administrator")
	_ensure_stub_doctypes()
	_purge()
	frappe.get_doc(
		{
			"doctype": "WhatsApp Account", "account_name": ACCOUNT, "status": "Active", "url": FAKE_URL,
			"version": "v21.0", "phone_id": PHONE_ID, "business_id": "s1s12-biz", "app_id": "s1s12-app",
			"token": FAKE_TOKEN, "webhook_verify_token": "s1s12-verify", "is_default_outgoing": 0,
		}
	).insert(ignore_permissions=True)  # fmt: skip
	_user(ADMIN, ("System Manager",))
	if not frappe.db.exists("Role", "Huf Gateway User"):
		frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
	_user(WRITER, ("Huf Gateway User",))
	integration = frappe.get_doc(
		{
			"doctype": "Integration Settings", "service": "whatsapp",
			"credentials": [
				{"key": "phone_number_id", "value": PHONE_ID}, {"key": "access_token", "value": FAKE_TOKEN},
				{"key": "webhook_verify_token", "value": "s1s12-verify"}, {"key": "app_secret", "value": APP_SECRET},
			],
		}
	).insert(ignore_permissions=True)  # fake values only
	STATE["integration"] = integration.name
	gw = frappe.get_doc(
		{"doctype": "Gateway", "gateway_name": f"{PREFIX} Gateway", "provider": "WhatsApp", "is_enabled": 1, "integration_settings": integration.name, "whatsapp_account": ACCOUNT, "execution_user": WRITER}
	).insert(ignore_permissions=True)  # fmt: skip
	STATE["gateway"] = gw.name
	STATE["util"], STATE["mkt"] = _template("s1s12_util", "UTILITY"), _template("s1s12_mkt", "MARKETING")
	frappe.share.add("Gateway", gw.name, WRITER, read=1, write=1, share=0, notify=0, flags={"ignore_share_permission": True})
	frappe.db.commit()


def tearDownModule() -> None:
	frappe.set_user("Administrator")
	_purge()
	_drop_stub_doctypes()
	frappe.db.commit()


# ------------------------------------------------------------------ stubs


class _Resp:
	def __init__(self, body: dict, status: int = 200):
		self._body, self.status_code, self.text = body, status, json.dumps(body)
		self.headers = {"content-type": "application/json"}

	def json(self):
		return self._body


class GraphStub:
	"""Replaces ``bridge._default_post``. Records every would-be Graph call; refuses non-allow-listed recipients.

	``responder(n, to)`` may return a ``_Resp`` (an error answer) or raise (a timeout); None means success."""

	def __init__(self):
		self.calls: list[dict] = []
		self.violations: list[str] = []
		self.responder = None
		self.message_status = "accepted"

	def __call__(self, url, json=None, headers=None, timeout=None, **kw):
		if not str(url).startswith(FAKE_URL) or (headers or {}).get("Authorization") != f"Bearer {FAKE_TOKEN}":
			self.violations.append(f"unexpected target {url}")
			raise AllowListViolation(f"unexpected target {url}")
		to = str((json or {}).get("to"))
		if not ALLOWED.match(to):
			self.violations.append(to)
			raise AllowListViolation(f"recipient {to} is not in the allow-list")
		self.calls.append({"to": to, "payload": json})
		if self.responder and (out := self.responder(len(self.calls), to)) is not None:
			return out
		return _Resp({"messages": [{"id": f"wamid.S1S12.{len(self.calls)}.{to}", "message_status": self.message_status}]})

	@property
	def recipients(self) -> list[str]:
		return [c["to"] for c in self.calls]


def graph_error(code: int, status: int = 400, message: str = "stubbed Graph error") -> _Resp:
	return _Resp({"error": {"message": message, "type": "OAuthException", "code": code, "fbtrace_id": "s1s12"}}, status)


def _no_network(*a, **kw):
	raise AllowListViolation("a real HTTP request was attempted")


@contextmanager
def as_user(user: str):
	prev = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(prev)


def meta(quality: str | None = "GREEN", cap: int | None = 250):
	tier = "TIER_250" if cap == 250 else ("TIER_UNLIMITED" if cap is None else "TIER_TEST")
	return patch.object(blimits, "get_messaging_limit", return_value={"tier": tier, "max_unique_24h": cap, "quality": quality, "mps": None, "raw": {}})


# ------------------------------------------------------------------ base


class S12Case(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.gw = STATE["gateway"]

	def setUp(self):
		frappe.set_user("Administrator")
		self._wipe()
		self.addCleanup(self._wipe)
		self.addCleanup(patch.stopall)
		self.graph = GraphStub()
		patch.object(bridge, "_default_post", self.graph).start()
		patch("requests.sessions.Session.request", _no_network).start()
		self.ticks: list = []
		patch("frappe.get_request_header", lambda *a, **k: None).start()
		patch("frappe.enqueue", lambda *a, **kw: self.ticks.append((a, kw))).start()
		patch.object(runner, "_sleep", lambda s: None).start()
		patch("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None).start()
		self._prev_request = getattr(frappe.local, "request", None)
		self._prev_ip = getattr(frappe.local, "request_ip", None)
		frappe.local.request = SimpleNamespace(args={"gateway_name": self.gw})
		frappe.local.request_ip = "127.0.0.1"
		if not getattr(frappe.local, "response", None):
			frappe.local.response = frappe._dict()
		self.addCleanup(self._restore_request)
		self.addCleanup(lambda: self.assertEqual(self.graph.violations, [], "allow-list violated"))
		self.addCleanup(lambda: frappe.set_user("Administrator"))

	def _restore_request(self):
		frappe.local.request, frappe.local.request_ip = self._prev_request, self._prev_ip

	def _wipe(self):
		frappe.set_user("Administrator")
		bcs = frappe.get_all(B, {"gateway": self.gw}, pluck="name")
		if bcs:
			frappe.db.delete(R, {"broadcast": ["in", bcs]})
			frappe.db.delete("WhatsApp Broadcast Audience", {"parent": ["in", bcs]})
			frappe.db.delete(B, {"name": ["in", bcs]})
		frappe.db.delete("Gateway Consent", {"gateway": self.gw})
		frappe.db.delete("Gateway Access Entry", {"gateway": self.gw})
		frappe.db.sql("update `tabWhatsApp Templates` set status='APPROVED' where whatsapp_account=%s", ACCOUNT)
		frappe.db.commit()

	# --- API helpers (as the Gateway-write user)
	def mk(self, template=None, **kw) -> str:
		with as_user(WRITER):
			out = bapi.create_broadcast(
				gateway=self.gw, template=template or STATE["util"], title=self._testMethodName[:100],
				language_code="en", body_params=json.dumps(["Friend"]), consent_source="test-run", **kw,
			)  # fmt: skip
		self.assertTrue(out.get("success"), out)
		return out["broadcast"]

	def add(self, b, numbers) -> dict:
		with as_user(WRITER):
			out = bapi.add_broadcast_recipients(broadcast=b, recipients=json.dumps(list(numbers)))
		self.assertTrue(out.get("success"), out)
		return out

	def attest(self, b):
		with as_user(WRITER):
			out = bapi.attest_broadcast_consent(broadcast=b, consent_source="test-run")
		self.assertTrue(out.get("success"), out)

	def start(self, b, count=None) -> dict:
		with as_user(WRITER), meta():
			return bapi.start_broadcast(broadcast=b, confirm_count=count)

	def api(self, fn, **kw) -> dict:
		with as_user(WRITER):
			return fn(**kw)

	def tick(self, b) -> dict:
		frappe.set_user("Administrator")
		return runner.tick(b)

	def tick_until_done(self, b, limit=10) -> dict:
		out = {}
		for _ in range(limit):
			out = self.tick(b)
			if out.get("result") in ("completed", "paused", "idle", "stopped") or str(out.get("result")).startswith("not_running"):
				break
		return out

	def ready(self, count, template=None, base=0) -> str:
		b = self.mk(template)
		self.add(b, [num(base + i) for i in range(count)])
		self.attest(b)
		return b

	def running(self, count, template=None, base=0) -> str:
		b = self.ready(count, template, base)
		out = self.start(b, count)
		self.assertTrue(out.get("success"), out)
		return b

	def rows(self, b, **flt):
		return frappe.get_all(R, {"broadcast": b, **flt}, ["name", "recipient", "status", "skip_reason", "wamid", "attempts", "next_attempt_at", "error_code", "error_message", "failed_at", "message_status"], order_by="recipient asc")

	def by_recipient(self, b) -> dict:
		return {r["recipient"]: r for r in self.rows(b)}

	def val(self, b, field):
		return frappe.db.get_value(B, b, field)

	# --- signed webhook replay (real handler, real HMAC)
	def webhook(self, payload: dict, secret: str = APP_SECRET) -> dict | None:
		raw = json.dumps(payload).encode()
		sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
		request = GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query={}, method="POST")
		frappe.local.response.http_status_code = 200
		with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
			return gateway_webhook.handle_gateway_webhook()

	def status_cb(self, wamid, status, opaque=None, to="447700900000", errors=None, ts=1792000100) -> dict | None:
		st = {"id": wamid, "status": status, "timestamp": str(ts), "recipient_id": to}
		if opaque:
			st["biz_opaque_callback_data"] = opaque
		if errors:
			st["errors"] = errors
		return self.webhook(_envelope({"statuses": [st]}))

	def replay_fixture(self, name, *, wamid=None, opaque=None, to=None) -> dict | None:
		"""Replay a shipped fixture re-pointed at a test row and this gateway's phone number id."""
		payload = json.loads((FIXTURES / name).read_text())
		value = payload["entry"][0]["changes"][0]["value"]
		value["metadata"]["phone_number_id"] = PHONE_ID
		st = value["statuses"][0]
		st["id"] = wamid or st.get("id")
		if opaque:
			st["biz_opaque_callback_data"] = opaque
		if to:
			st["recipient_id"] = to
		return self.webhook(payload)


def _envelope(value: dict, field: str = "messages") -> dict:
	value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": PHONE_ID}, **value}
	return {"object": "whatsapp_business_account", "entry": [{"id": "s1s12-waba", "changes": [{"field": field, "value": value}]}]}


# ------------------------------------------------------------------ S1-S12


class TestBroadcastS1S12(S12Case):
	def setUp(self):
		if not bridge.is_available():
			self.skipTest("frappe_whatsapp is not installed on this site")
		super().setUp()

	def test_S01_happy_path_small_list(self):
		"""S1. Happy path, small list. 3 allow-listed recipients, approved utility template, consent attested.
		Create draft, add 3 recipients, attest consent, preview, start with confirm_count=3, wait for Completed.
		Expect: 3 rows reach sent, then delivered and read as the handsets report. Counters match the rows.
		finished_at is set."""
		b = self.ready(3)
		with as_user(WRITER), meta():
			pv = bapi.preview_broadcast(broadcast=b)
		self.assertTrue(pv["success"], pv)
		self.assertEqual(pv["limits"]["blocking"], [])
		out = self.start(b, 3)
		self.assertTrue(out.get("success"), out)
		self.assertEqual(self.tick_until_done(b)["result"], "completed")
		self.assertEqual(sorted(self.graph.recipients), [num(0), num(1), num(2)])
		self.assertEqual(self.val(b, "status"), "Completed")
		self.assertTrue(self.val(b, "finished_at"))
		rows = self.rows(b)
		self.assertEqual([r["status"] for r in rows], ["sent"] * 3)
		self.assertTrue(all(r["wamid"] for r in rows))
		# the handsets report delivered (all three) then read (two), as signed webhooks
		for r in rows:
			self.status_cb(r["wamid"], "delivered", to=r["recipient"])
		for r in rows[:2]:
			self.status_cb(r["wamid"], "read", to=r["recipient"])
		self.assertEqual([r["status"] for r in self.rows(b)], ["read", "read", "delivered"])
		doc = frappe.get_doc(B, b)
		doc.recount()
		counts = {r["status"]: 0 for r in self.rows(b)}
		for r in self.rows(b):
			counts[r["status"]] += 1
		self.assertEqual(counts, {"read": 2, "delivered": 1})
		self.assertEqual((int(self.val(b, "read_count") or 0), int(self.val(b, "delivered_count") or 0)), (2, 1))
		# allow-list guard (site config wa_outbound_allowlist): a recipient outside it is never posted
		b2 = self.ready(2, base=20)
		calls = len(self.graph.calls)
		with patch.dict(frappe.conf, {"wa_outbound_allowlist": [num(20)]}):
			self.start(b2, 2)
			self.tick_until_done(b2)
		self.assertEqual(self.graph.recipients[calls:], [num(20)])
		self.assertEqual(self.by_recipient(b2)[num(21)]["skip_reason"], "recipient_not_allowlisted")
		self.skipTest("OWNER-LIVE: real handset delivered/read receipts from Meta for 3 owner numbers (checklist S1)")

	def test_S02_intake_filters_and_start_guard(self):
		"""S2. Intake filters and start guard. One allow-listed number with a STOP recorded, one duplicate, one invalid
		number. Expect: the STOP row is stored skipped with reason opted_out; the duplicate is reported in skipped with
		reason duplicate and not stored; the invalid number is reported in invalid and not stored. Wrong confirm_count
		returns confirm_mismatch. Start before attestation returns consent_not_attested. Adding recipients after
		attestation clears the attestation; adding to a non-Draft broadcast returns not_draft; start_broadcast on a
		Paused broadcast is refused. Marketing: 1 + 11 digits is skipped us_plus_one_marketing."""
		gw_doc = frappe.get_doc("Gateway", self.gw)
		gateway_service._record_opt_out(gw_doc, num(1))
		b = self.mk()
		out = self.add(b, [num(0), num(1), num(0), "12"])
		self.assertEqual(out["added"], 2, out)  # the STOP row is stored (skipped) and counted as added
		self.assertIn((num(0), "duplicate"), [(s["recipient"], s["reason"]) for s in out["skipped"]], out)
		self.assertEqual(out["invalid_total"], 1, out)
		rows = self.by_recipient(b)
		self.assertEqual((rows[num(1)]["status"], rows[num(1)]["skip_reason"]), ("skipped", "opted_out"))
		self.assertEqual(rows[num(0)]["status"], "queued")
		self.assertNotIn("12", rows)
		with as_user(WRITER), meta():
			self.assertEqual(bapi.start_broadcast(broadcast=b, confirm_count=1)["error"], "consent_not_attested")
		self.attest(b)
		self.assertEqual(self.val(b, "consent_attested"), 1)
		self.add(b, [num(2)])
		self.assertEqual(self.val(b, "consent_attested"), 0, "adding recipients must clear the attestation")
		self.attest(b)
		with as_user(WRITER), meta():
			self.assertEqual(bapi.start_broadcast(broadcast=b, confirm_count=99)["error"], "confirm_mismatch")
		self.assertTrue(self.start(b, 2).get("success"))
		with as_user(WRITER):
			out = bapi.add_broadcast_recipients(broadcast=b, recipients=json.dumps([num(3)]))
		self.assertEqual(out.get("error"), "not_draft", out)
		self.api(bapi.pause_broadcast, broadcast=b)
		with as_user(WRITER), meta():
			out = bapi.start_broadcast(broadcast=b, confirm_count=2)
		self.assertFalse(out.get("success"), "start on a Paused broadcast must be refused (use resume)")
		# marketing: a US +1 number is skipped
		mb = self.mk(STATE["mkt"])
		self.add(mb, ["15551230001", num(5)])
		self.assertEqual(self.by_recipient(mb)["15551230001"]["skip_reason"], "us_plus_one_marketing")

	def test_S03_template_not_approved(self):
		"""S3. Template not approved. Draft and recipients created while the template is APPROVED; then the template
		changes to a non-approved status. Run preview, then try to start. Expect: preview blocking contains
		template_not_approved:<STATUS>; start is refused with 'Broadcast blocked: ...'. No row is sent."""
		b = self.ready(2)
		frappe.db.set_value("WhatsApp Templates", STATE["util"], "status", "PAUSED")
		frappe.db.commit()
		with as_user(WRITER), meta():
			pv = bapi.preview_broadcast(broadcast=b)
		self.assertIn("template_not_approved:PAUSED", [str(x.get("code") if isinstance(x, dict) else x) for x in pv["limits"]["blocking"]], pv["limits"])
		out = self.start(b, 2)
		self.assertFalse(out.get("success"), out)
		self.assertIn("Broadcast blocked", str(out.get("message")), out)
		self.assertEqual((self.graph.calls, self.val(b, "status")), ([], "Draft"))

	def test_S04_held_message(self):
		"""S4. Held message. Meta may hold messages for quality assessment; rows show message_status =
		held_for_quality_assessment. When at least 10 of the last 50 sent rows exist and more than 30% are held, the
		runner drops to a quarter of the rate. Webhook replay: broadcast_status_held.json is a `sent` status; against
		a queued/deferred/sending row it moves it to `sent` and no further; against an already sent row it changes
		nothing."""
		self.graph.message_status = runner.HELD_STATUS
		b = self.running(12)
		self.tick_until_done(b)
		rows = self.rows(b)
		self.assertEqual({r["message_status"] for r in rows}, {runner.HELD_STATUS})
		ratio, sample = runner._held_ratio(b)
		self.assertGreaterEqual(sample, 10)
		self.assertTrue(runner._is_throttled(ratio, sample), (ratio, sample))
		# webhook replay of the held fixture
		self.graph.message_status = "accepted"
		b2 = self.ready(1, base=40)
		row = self.rows(b2)[0]
		self.assertEqual(row["status"], "queued")
		self.replay_fixture("broadcast_status_held.json", wamid="wamid.S1S12.held", opaque=row["name"])
		self.assertEqual(self.rows(b2)[0]["status"], "sent")
		self.status_cb("wamid.S1S12.held", "delivered", opaque=row["name"])
		self.replay_fixture("broadcast_status_held.json", wamid="wamid.S1S12.held", opaque=row["name"])
		self.assertEqual(self.rows(b2)[0]["status"], "delivered", "a replayed sent must not move a delivered row back")
		self.skipTest("OWNER-LIVE: Meta actually holding a new/paused template's messages (checklist S4)")

	def test_S05_failed_send_permanent_error(self):
		"""S5. Failed send, permanent error. One recipient with a number not on WhatsApp. Expect: row becomes failed
		with error_code, error_message and failed_at. No retry."""
		self.graph.responder = lambda n, to: graph_error(131026, message="Message undeliverable") if to == num(1) else None
		b = self.running(3)
		self.tick_until_done(b)
		r = self.by_recipient(b)[num(1)]
		self.assertEqual(r["status"], "failed", r)
		self.assertEqual(r["error_code"], 131026)
		self.assertTrue(r["error_message"] and r["failed_at"])
		self.assertEqual(r["attempts"], 1)
		self.assertEqual(self.graph.recipients.count(num(1)), 1, "no retry")
		self.assertEqual(self.val(b, "status"), "Completed")
		self.skipTest("OWNER-LIVE: Meta's real answer for a number not on WhatsApp (checklist S5)")

	def test_S06_pause_signals(self):
		"""S6. Pause signals. A running broadcast with queued rows and a signed replay of
		broadcast_status_failed_135000.json for an in-flight row. Expect: the row becomes failed with code 135000 and
		the broadcast moves to Paused with pause_reason 'WhatsApp error 135000 (messages dropped by pacing)'. Queued
		rows stay queued. No new sends until resume. Also: a message_template_status_update that pauses the template
		pauses a Running broadcast with reason template:paused. A bad signature is rejected."""
		b = self.running(4)
		first = self.rows(b)[0]
		self.assertEqual(bsend.send_one(first["name"]), "sent")
		frappe.db.commit()
		wamid = self.rows(b)[0]["wamid"]
		# bad signature first: rejected, nothing changes
		bad = self.webhook(_envelope({"statuses": [{"id": wamid, "status": "failed", "errors": [{"code": 135000}]}]}), secret="wrong-secret")
		self.assertFalse(bad["success"], bad)
		self.assertEqual(frappe.local.response.http_status_code, 401)
		self.assertEqual(self.rows(b)[0]["status"], "sent")
		self.replay_fixture("broadcast_status_failed_135000.json", wamid=wamid, opaque=first["name"])
		row = self.rows(b)[0]
		self.assertEqual((row["status"], row["error_code"]), ("failed", 135000))
		self.assertEqual(self.val(b, "status"), "Paused")
		self.assertEqual(self.val(b, "pause_reason"), "WhatsApp error 135000 (messages dropped by pacing)")
		self.assertEqual([r["status"] for r in self.rows(b)].count("queued"), 3)
		calls = len(self.graph.calls)
		self.tick(b)
		self.assertEqual(len(self.graph.calls), calls, "no new sends while paused")
		# template pause webhook
		b2 = self.running(2, base=30)
		self.webhook(_envelope({"event": "PAUSED", "message_template_id": 1, "message_template_name": "s1s12_util", "message_template_language": "en"}, "message_template_status_update"))
		self.assertEqual(self.val(b2, "status"), "Paused")
		self.assertEqual(self.val(b2, "pause_reason"), "template:paused")

	def test_S07_kill_switch(self):
		"""S7. Kill switch. A running broadcast with queued rows; call pause_all_broadcasts(gateway). Expect: the
		running broadcast pauses with reason kill_switch. No POST to /messages for queued rows after the pause."""
		b = self.running(5)
		self.assertEqual(bsend.send_one(self.rows(b)[0]["name"]), "sent")
		frappe.db.commit()
		with as_user(ADMIN):
			out = bapi.pause_all_broadcasts(gateway=self.gw)
		self.assertTrue(out["success"], out)
		self.assertEqual(out["paused"], [b])
		self.assertEqual((self.val(b, "status"), self.val(b, "pause_reason")), ("Paused", "kill_switch"))
		calls = len(self.graph.calls)
		self.tick(b)
		for r in self.rows(b, status="queued"):
			self.assertEqual(bsend.send_one(r["name"]), "lost_claim")
		self.assertEqual(len(self.graph.calls), calls)
		self.assertEqual(len(self.rows(b, status="queued")), 4)

	def test_S08_worker_restart_and_claim_safety(self):
		"""S8. Worker restart and claim safety. A running broadcast with at least 10 queued rows. After a worker
		restart the */5 cron (resume_stale) revives a Running broadcast that has no live tick. Expect: every row is sent
		once, no wamid repeats. A row left in sending for more than 10 minutes becomes unknown and is not resent."""
		b = self.running(12)
		rows = self.rows(b)
		for r in rows[:4]:
			self.assertEqual(bsend.send_one(r["name"]), "sent")
		self.assertEqual(bsend.send_one(rows[0]["name"]), "lost_claim", "a second claim must not re-post")
		# the worker died holding row 4 in `sending` for over 10 minutes
		stuck = rows[4]["name"]
		old = add_to_date(now_datetime(), minutes=-30)
		frappe.db.sql(f"update `tab{R}` set status='sending', attempts=1, modified=%s where name=%s", (old, stuck))
		frappe.db.commit()
		out = stale.resume_stale()
		self.assertEqual(out["stale_to_unknown"], 1, out)
		self.assertIn(b, out["revived"], out)
		self.assertEqual(frappe.db.get_value(R, stuck, "status"), "unknown")
		self.tick_until_done(b)
		self.assertEqual(self.val(b, "status"), "Completed")
		sent_to = self.graph.recipients
		self.assertEqual(len(sent_to), len(set(sent_to)), "no recipient may receive two messages")
		self.assertEqual(len(sent_to), 11)
		self.assertNotIn(rows[4]["recipient"], sent_to, "an unknown row is never resent")
		wamids = [r["wamid"] for r in self.rows(b) if r["wamid"]]
		self.assertEqual(len(wamids), len(set(wamids)))
		self.skipTest("OWNER-LIVE: a real worker/bench restart mid-run with the Meta message log (checklist S8)")

	def test_S09_unknown_row_handling(self):
		"""S9. Unknown row handling. An ambiguous network error after the request. Expect: the row is unknown.
		Recovery does not resend it. A later sent, delivered or read webhook for it moves it forward (sent resolves
		unknown)."""

		def timeout(n, to):
			raise TimeoutError("read timed out")

		self.graph.responder = lambda n, to: timeout(n, to) if to == num(0) else None
		b = self.running(2)
		self.tick_until_done(b)
		row = self.by_recipient(b)[num(0)]
		self.assertEqual(row["status"], "unknown", row)
		self.assertEqual(self.graph.recipients.count(num(0)), 1)
		stale.resume_stale()
		self.tick(b)
		self.assertEqual(self.graph.recipients.count(num(0)), 1, "recovery must not resend an unknown row")
		self.status_cb("wamid.S1S12.unk", "sent", opaque=row["name"])
		self.assertEqual(frappe.db.get_value(R, row["name"], "status"), "sent")
		self.status_cb("wamid.S1S12.unk", "delivered")
		self.assertEqual(frappe.db.get_value(R, row["name"], "status"), "delivered")
		self.status_cb("wamid.S1S12.unk", "read")
		self.assertEqual(frappe.db.get_value(R, row["name"], "status"), "read")
		self.status_cb("wamid.S1S12.unk", "delivered")  # never backwards
		self.assertEqual(frappe.db.get_value(R, row["name"], "status"), "read")
		self.assertEqual(self.graph.recipients.count(num(0)), 1)

	def test_S10_cancel(self):
		"""S10. Cancel. A paused broadcast with queued rows. Expect: cancel sets Cancelled and moves queued and
		deferred rows to skipped with reason cancelled. Rows already sent are unchanged."""
		b = self.running(5)
		for r in self.rows(b)[:2]:
			self.assertEqual(bsend.send_one(r["name"]), "sent")
		frappe.db.set_value(R, self.rows(b)[2]["name"], {"status": "deferred", "next_attempt_at": add_to_date(now_datetime(), minutes=5)})
		frappe.db.commit()
		self.api(bapi.pause_broadcast, broadcast=b)
		self.assertEqual(self.val(b, "status"), "Paused")
		out = self.api(bapi.cancel_broadcast, broadcast=b)
		self.assertEqual(out["status"], "Cancelled", out)
		rows = self.rows(b)
		self.assertEqual([r["status"] for r in rows], ["sent", "sent", "skipped", "skipped", "skipped"])
		self.assertEqual({r["skip_reason"] for r in rows[2:]}, {"cancelled"})
		calls = len(self.graph.calls)
		self.tick(b)
		self.assertEqual(len(self.graph.calls), calls)

	def test_S11_retry_cap_and_131049_terminal_skip(self):
		"""S11. Retry cap and 131049 terminal skip. A forced retryable error (stubbed 130429) on one row. Expect: the
		row is deferred with growing delays (about 2, 4, 8, 16 s) and is failed after the fifth POST attempt
		(attempts = 5). A stubbed 131049 (send response) gives skipped with skip_reason per_user_marketing_limit and
		error_code 131049; it is never claimed again and the broadcast can complete."""
		self.graph.responder = lambda n, to: graph_error(130429, 429, "rate limit") if to == num(0) else graph_error(131049) if to == num(1) else None
		b = self.running(2)
		retry, limited = self.rows(b)[0]["name"], self.rows(b)[1]["name"]
		delays = []
		for attempt in range(1, 6):
			outcome = bsend.send_one(retry)
			row = frappe.db.get_value(R, retry, ["status", "attempts", "next_attempt_at"], as_dict=True)
			self.assertEqual(row["attempts"], attempt)
			if attempt < 5:
				self.assertEqual((outcome, row["status"]), ("deferred", "deferred"))
				delays.append((row["next_attempt_at"] - now_datetime()).total_seconds())
				frappe.db.set_value(R, retry, "next_attempt_at", None)  # let the next attempt be due now
				frappe.db.commit()
			else:
				self.assertEqual((outcome, row["status"]), ("failed", "failed"))
		for got, want in zip(delays, (2, 4, 8, 16), strict=True):
			self.assertAlmostEqual(got, want, delta=1.5)
		self.assertEqual(self.graph.recipients.count(num(0)), 5)
		self.assertEqual(bsend.send_one(retry), "lost_claim")
		self.assertEqual(bsend.send_one(limited), "skipped")
		row = frappe.db.get_value(R, limited, ["status", "skip_reason", "error_code"], as_dict=True)
		self.assertEqual((row["status"], row["skip_reason"], row["error_code"]), ("skipped", "per_user_marketing_limit", 131049))
		self.assertEqual(bsend.send_one(limited), "lost_claim")
		self.assertEqual(self.tick(b)["result"], "completed")
		# the webhook variant (131049 delivered asynchronously) is terminal too
		self.graph.responder = None
		b2 = self.running(1, base=50)
		r2 = self.rows(b2)[0]
		self.assertEqual(bsend.send_one(r2["name"]), "sent")
		frappe.db.commit()
		self.replay_fixture("broadcast_status_failed_131049.json", wamid=self.rows(b2)[0]["wamid"], opaque=r2["name"])
		row = frappe.db.get_value(R, r2["name"], ["status", "skip_reason", "error_code"], as_dict=True)
		self.assertEqual((row["status"], row["skip_reason"], row["error_code"]), ("skipped", "per_user_marketing_limit", 131049))

	def test_S12_marketing_stop(self):
		"""S12. Marketing stop. A Paused broadcast with a contact queued, and a second Draft broadcast with the same
		contact queued. Replay a user_preferences marketing-stop event for the contact. Expect: the contact's queued
		and deferred rows in Queued, Running or Paused broadcasts become skipped with reason opted_out. A row in a
		Draft broadcast is not changed by the event; it is skipped at send time instead (marketing_opted_out for a
		MARKETING template)."""
		contact = num(7)
		paused = self.running(2, STATE["mkt"], base=7)  # num(7), num(8)
		self.api(bapi.pause_broadcast, broadcast=paused)
		self.assertEqual(self.val(paused, "status"), "Paused")
		draft = self.ready(2, STATE["mkt"], base=7)
		stop = _envelope(
			{"contacts": [{"wa_id": contact, "profile": {"name": "Test"}}],
			 "user_preferences": [{"wa_id": contact, "detail": "User requested to stop marketing messages", "category": "marketing_messages", "value": "stop", "timestamp": 1731700000}]},
			"user_preferences",
		)
		self.webhook(stop)
		row = self.by_recipient(paused)[contact]
		self.assertEqual((row["status"], row["skip_reason"]), ("skipped", "opted_out"))
		self.assertEqual(self.by_recipient(paused)[num(8)]["status"], "queued", "other contacts are untouched")
		self.assertEqual(self.by_recipient(draft)[contact]["status"], "queued", "a Draft row is not changed by the event")
		self.assertEqual(self.start(draft, 2).get("success"), True)
		self.tick_until_done(draft)
		row = self.by_recipient(draft)[contact]
		self.assertEqual((row["status"], row["skip_reason"]), ("skipped", "marketing_opted_out"))
		self.assertNotIn(contact, self.graph.recipients)
		self.assertIn(num(8), self.graph.recipients)
