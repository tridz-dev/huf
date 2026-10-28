# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-G2: scripted end-to-end scenarios for broadcast limits + audiences against a REAL bench database.

Everything goes through the real whitelisted API functions as real users (a Gateway-write user, a read-only user
and a System Manager). The only things replaced are the boundaries to the outside world:

* the HTTP post of the WhatsApp bridge (``bridge._default_post``): a stub that hard-fails (``AllowListViolation``,
  a BaseException so the sender cannot swallow it) when a recipient is outside the fictional allow-list
  (``44 7700 900xxx``, the range Ofcom reserves for drama), and ``requests`` is blocked outright;
* the Meta tier/quality read (``limits.get_messaging_limit``), so RED quality and small budgets can be staged;
* the queue (``frappe.enqueue``): ticks are run by the test itself.

Meta is never contacted: the WhatsApp Account points at an unroutable host with a fake token.
Evidence (scenario, expected, observed) is appended to ``<site>/g2_evidence.json``.
"""

from __future__ import annotations

import json
import re
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import account_events
from huf.ai.whatsapp.broadcast import api as bapi, api_limits, limits as blimits, policy, runner
from huf.ai.whatsapp.broadcast.audiences import api as aapi, membership as aud, wiring

PREFIX = "G2E2E"
ACCOUNT = f"{PREFIX} Account"
FAKE_URL = "http://g2-fake-graph.invalid"
FAKE_TOKEN = "FAKE-TOKEN-NOT-A-META-TOKEN"
PHONE_ID = "g2e2e-fake-phone-id"
ALLOWED = re.compile(r"^447700900\d{3}$")  # the only recipients any stub will accept
WRITER, READER, ADMIN = (f"g2e2e-{r}@example.com" for r in ("writer", "reader", "admin"))
B, R = "WhatsApp Broadcast", "WhatsApp Broadcast Recipient"
EVIDENCE: list[dict] = []
STATE: dict = {}


class AllowListViolation(BaseException):
	"""Raised by the stubs; BaseException so no ``except Exception`` in product code can hide it."""


def num(i: int) -> str:
	return f"447700900{i:03d}"


# ------------------------------------------------------------------ fixtures


def _purge() -> None:
	"""Remove everything this module creates (also leftovers of an aborted earlier run)."""
	gws = frappe.get_all("Gateway", {"gateway_name": f"{PREFIX} Gateway"}, pluck="name")
	for gw in gws:
		bcs = frappe.get_all(B, {"gateway": gw}, pluck="name")
		if bcs:
			frappe.db.delete(R, {"broadcast": ["in", bcs]})
			frappe.db.delete("WhatsApp Broadcast Audience", {"parent": ["in", bcs]})
			frappe.db.delete("Comment", {"reference_doctype": B, "reference_name": ["in", bcs]})
			frappe.db.delete(B, {"name": ["in", bcs]})
		auds = frappe.get_all("WhatsApp Audience", {"gateway": gw}, pluck="name")
		if auds:
			frappe.db.delete("WhatsApp Audience Member", {"audience": ["in", auds]})
			frappe.db.delete("WhatsApp Audience", {"name": ["in", auds]})
		frappe.db.delete("Gateway Consent", {"gateway": gw})
		frappe.db.delete("Gateway Access Entry", {"gateway": gw})
		frappe.db.delete("DocShare", {"share_doctype": "Gateway", "share_name": gw})
		frappe.db.delete("Gateway", {"name": gw})
	frappe.db.delete("WhatsApp Templates", {"whatsapp_account": ACCOUNT})
	frappe.db.delete("WhatsApp Message", {"whatsapp_account": ACCOUNT})
	frappe.db.delete("WhatsApp Account", {"name": ACCOUNT})
	if STATE.get("integration"):
		frappe.db.delete("Integration Settings", {"name": STATE["integration"]})
	for user in (WRITER, READER, ADMIN):
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
	_purge()
	frappe.get_doc(
		{
			"doctype": "WhatsApp Account", "account_name": ACCOUNT, "status": "Active", "url": FAKE_URL,
			"version": "v21.0", "phone_id": PHONE_ID, "business_id": "g2-biz", "app_id": "g2-app",
			"token": FAKE_TOKEN, "webhook_verify_token": "g2e2e-verify", "is_default_outgoing": 0,
		}
	).insert(ignore_permissions=True)  # fmt: skip
	_user(ADMIN, ("System Manager",))
	if not frappe.db.exists("Role", "Huf Gateway User"):
		frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
	_user(WRITER, ("Huf Gateway User",))  # Gateway write comes only from a share on this Gateway
	_user(READER)
	integration = frappe.get_doc(
		{
			"doctype": "Integration Settings", "service": "whatsapp",
			"credentials": [
				{"key": "phone_number_id", "value": PHONE_ID}, {"key": "access_token", "value": FAKE_TOKEN},
				{"key": "webhook_verify_token", "value": "g2e2e-verify"}, {"key": "app_secret", "value": "g2e2e-secret"},
			],
		}
	).insert(ignore_permissions=True)  # fake values only
	STATE["integration"] = integration.name
	gw = frappe.get_doc(
		{"doctype": "Gateway", "gateway_name": f"{PREFIX} Gateway", "provider": "WhatsApp", "is_enabled": 1, "integration_settings": integration.name, "whatsapp_account": ACCOUNT, "execution_user": WRITER}
	).insert(ignore_permissions=True)  # fmt: skip
	STATE["gateway"] = gw.name
	STATE["util"], STATE["mkt"] = _template("g2e2e_util", "UTILITY"), _template("g2e2e_mkt", "MARKETING")
	frappe.share.add("Gateway", gw.name, WRITER, read=1, write=1, share=0, notify=0, flags={"ignore_share_permission": True})
	frappe.share.add("Gateway", gw.name, READER, read=1, write=0, share=0, notify=0, flags={"ignore_share_permission": True})
	frappe.db.commit()


def tearDownModule() -> None:
	frappe.set_user("Administrator")
	policy.set_values({lim.key: None for lim in policy.LIMITS if lim.editable})
	_purge()
	frappe.db.commit()
	path = frappe.get_site_path("g2_evidence.json")
	with open(path, "w") as fh:
		json.dump(EVIDENCE, fh, indent=1, default=str)


# ------------------------------------------------------------------ stubs


class _Resp:
	status_code = 200
	text = "{}"

	def __init__(self, n: int, to: str):
		self._body = {"messages": [{"id": f"wamid.G2E2E.{n}.{to}", "message_status": "accepted"}]}

	def json(self):
		return self._body


class GraphStub:
	"""Replaces ``bridge._default_post``. Records every would-be Graph call; refuses non-allow-listed recipients."""

	def __init__(self):
		self.calls: list[dict] = []
		self.violations: list[str] = []
		self.on_post = None

	def __call__(self, url, json=None, headers=None, timeout=None, **kw):
		if not str(url).startswith(FAKE_URL) or (headers or {}).get("Authorization") != f"Bearer {FAKE_TOKEN}":
			self.violations.append(f"unexpected target {url}")
			raise AllowListViolation(f"unexpected target {url}")
		to = str((json or {}).get("to"))
		if not ALLOWED.match(to):
			self.violations.append(to)
			raise AllowListViolation(f"recipient {to} is not in the allow-list")
		self.calls.append({"to": to, "payload": json})
		if self.on_post:
			self.on_post(len(self.calls), to)
		return _Resp(len(self.calls), to)

	@property
	def recipients(self) -> list[str]:
		return [c["to"] for c in self.calls]


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


def meta(quality: str | None = "GREEN", cap: int | None = 250, mps: int | None = None):
	"""Stage what Meta would report for tier/quality (the Meta read is the only thing replaced)."""
	tier = "TIER_250" if cap == 250 else ("TIER_UNLIMITED" if cap is None else "TIER_TEST")
	return patch.object(
		blimits, "get_messaging_limit",
		return_value={"tier": tier, "max_unique_24h": cap, "quality": quality, "mps": mps, "raw": {}},
	)  # fmt: skip


# ------------------------------------------------------------------ base


class G2Case(unittest.TestCase):
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
		self.ticks = []
		patch("frappe.get_request_header", lambda *a, **k: None).start()  # no HTTP request in-process; API-key test overrides
		patch("frappe.enqueue", lambda *a, **kw: self.ticks.append((a, kw))).start()
		self.addCleanup(lambda: self.assertEqual(self.graph.violations, [], "allow-list violated"))
		self.addCleanup(lambda: policy.set_values({lim.key: None for lim in policy.LIMITS if lim.editable}))
		self.addCleanup(lambda: frappe.set_user("Administrator"))

	def _wipe(self):
		"""Clean slate per test: no broadcast history, so the 24h budget and one-running rules start empty."""
		frappe.set_user("Administrator")
		bcs = frappe.get_all(B, {"gateway": self.gw}, pluck="name")
		if bcs:
			frappe.db.delete(R, {"broadcast": ["in", bcs]})
			frappe.db.delete("WhatsApp Broadcast Audience", {"parent": ["in", bcs]})
			frappe.db.delete(B, {"name": ["in", bcs]})
		frappe.db.commit()

	# --- evidence
	def ev(self, scenario: str, expected, observed):
		EVIDENCE.append({"scenario": scenario, "test": self.id().split(".")[-1], "expected": expected, "observed": observed})

	# --- API helpers (all as real users)
	def mk(self, template=None, user=WRITER, body=("Friend",), **kw) -> str:
		with as_user(user):
			out = bapi.create_broadcast(
				gateway=self.gw, template=template or "g2e2e_util", title=f"{self._testMethodName}"[:100],
				language_code="en", body_params=json.dumps(list(body)) if body is not None else None,
				consent_source="g2 scripted list", **kw,
			)  # fmt: skip
		self.assertTrue(out.get("success"), out)
		return out["broadcast"]

	def add(self, b, numbers, user=WRITER) -> dict:
		with as_user(user):
			out = bapi.add_broadcast_recipients(broadcast=b, recipients=json.dumps(list(numbers)))
		self.assertTrue(out.get("success"), out)
		return out

	def attest(self, b, user=WRITER):
		with as_user(user):
			out = bapi.attest_broadcast_consent(broadcast=b, consent_source="g2 scripted list")
		self.assertTrue(out.get("success"), out)

	def preview(self, b, user=WRITER) -> dict:
		with as_user(user):
			return bapi.preview_broadcast(broadcast=b)

	def start(self, b, count=None, override=None, user=WRITER) -> dict:
		with as_user(user):
			return bapi.start_broadcast(broadcast=b, confirm_count=count, override_warnings=json.dumps(override) if override is not None else None)

	def tick(self, b) -> dict:
		frappe.set_user("Administrator")
		return runner.tick(b)

	def settings(self, **values) -> dict:
		with as_user(ADMIN):
			out = api_limits.update_broadcast_limits(values=json.dumps(values))
		self.assertTrue(out.get("success"), out)
		return {r["key"]: r for r in out["limits"]}

	def limits(self, broadcast=None, user=ADMIN) -> dict:
		with as_user(user), meta("GREEN", 250):
			out = api_limits.get_broadcast_limits(broadcast=broadcast)
		self.assertTrue(out.get("success"), out)
		return {r["key"]: r for r in out["limits"]}

	def rows(self, b, **flt):
		return frappe.get_all(R, {"broadcast": b, **flt}, ["recipient", "status", "skip_reason", "next_attempt_at", "audience", "params", "consent_source"], order_by="recipient asc")

	def status(self, b, field="status"):
		return frappe.db.get_value(B, b, field)

	def ready(self, count, template=None, base=0, **kw) -> str:
		"""A Draft broadcast with ``count`` queued recipients and consent attested."""
		b = self.mk(template, **kw)
		self.add(b, [num(base + i) for i in range(count)])
		self.attest(b)
		return b


# ------------------------------------------------------------------ 1. settings


class TestScenario1Settings(G2Case):
	def test_settings_change_value_source_and_behaviour_then_reset(self):
		before = self.limits()
		self.assertEqual(
			[(before[k]["effective"], before[k]["source"]) for k in ("max_recipients_default", "min_phone_digits", "held_ratio_limit")],
			[(1000, "default"), (8, "default"), (0.3, "default")],
		)
		# behaviour at defaults
		b0 = self.mk()
		out = self.add(b0, [num(101), num(102), num(103), num(104)])
		self.assertEqual((out["added"], out["invalid_total"]), (4, 0))

		after = self.settings(max_recipients_default=2, min_phone_digits=13, held_ratio_limit=0.9)
		for key, want in (("max_recipients_default", 2), ("min_phone_digits", 13), ("held_ratio_limit", 0.9)):
			self.assertEqual((after[key]["effective"], after[key]["source"], after[key]["value"]), (want, "settings", want), key)
		self.assertEqual(self.limits()["max_recipients_default"]["source"], "settings")

		# min_phone_digits=13: the 12-digit numbers are refused as invalid
		b1 = self.mk()
		out = self.add(b1, [num(111), num(112)])
		self.assertEqual((out["added"], out["invalid_total"]), (0, 2))
		self.settings(min_phone_digits=None)
		# a per-broadcast cap beats the setting, and the limits read says so
		b3 = self.mk(max_recipients=3)
		out = self.add(b3, [num(131), num(132), num(133), num(134)])
		self.assertEqual(out["added"], 3)
		row = self.limits(broadcast=b3)["max_recipients_default"]
		self.assertEqual((row["effective"], row["source"]), (3, "broadcast"))

		# held ratio: 8 of the last 20 sends were held by Meta = 0.40
		held_b = self.mk()
		for i in range(20):
			self._row(held_b, num(140 + i), i < 8)
		ratio, sample = runner._held_ratio(held_b)
		self.assertEqual((round(ratio, 2), sample), (0.4, 20))
		self.assertFalse(runner._is_throttled(ratio, sample))  # limit is 0.9 now
		self.settings(held_ratio_limit=0.3)
		self.assertTrue(runner._is_throttled(ratio, sample))
		self.settings(held_ratio_limit=0.5)
		self.assertFalse(runner._is_throttled(ratio, sample))

		# reset all three to default
		reset = self.settings(max_recipients_default=None, min_phone_digits=None, held_ratio_limit=None)
		self.assertEqual(
			[(reset[k]["effective"], reset[k]["source"], reset[k]["value"]) for k in ("max_recipients_default", "min_phone_digits", "held_ratio_limit")],
			[(1000, "default", None), (8, "default", None), (0.3, "default", None)],
		)
		b4 = self.mk()
		self.assertEqual(self.add(b4, [num(151), num(152), num(153)])["added"], 3)
		self.assertTrue(runner._is_throttled(ratio, sample))
		self.ev("1 settings", "3 limits change value+source, behaviour follows (refuse/accept/throttle), reset restores defaults",
			"max_recipients_default value/source 1000->2 (behaviour: see next test), min_phone_digits 8->13 (2 offered, 0 added, 2 invalid), held_ratio 0.3->0.9->0.5 throttle False/True/False, per-broadcast cap source=broadcast, reset -> default")  # fmt: skip

	def _row(self, b, recipient, held):
		d = frappe.get_doc({"doctype": R, "broadcast": b, "recipient": recipient, "status": "sent", "sent_at": now_datetime(),
			"message_status": runner.HELD_STATUS if held else "accepted"})  # fmt: skip
		prev, frappe.flags.in_broadcast_api = frappe.flags.get("in_broadcast_api"), True
		try:
			d.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		finally:
			frappe.flags.in_broadcast_api = prev

	def test_max_recipients_default_setting_applies_to_a_new_broadcast(self):
		self.settings(max_recipients_default=2)
		b = self.mk()
		stored = frappe.db.get_value(B, b, "max_recipients")
		out = self.add(b, [num(121), num(122), num(123), num(124)])
		self.ev("1 settings F1", "max_recipients_default=2 -> a new broadcast without its own cap accepts 2 of 4",
			f"broadcast.max_recipients={stored} (doctype default 1000 snapshot), added={out['added']}, limits source={self.limits(broadcast=b)['max_recipients_default']['source']}")  # fmt: skip
		self.assertEqual(out["added"], 2)

	def test_invalid_value_rejected_and_nothing_stored(self):
		with as_user(ADMIN):
			out = api_limits.update_broadcast_limits(values=json.dumps({"min_phone_digits": 99, "max_batch": 300}))
		self.assertEqual(out.get("error"), "invalid_limit", out)
		rows = self.limits()
		self.assertEqual((rows["min_phone_digits"]["source"], rows["max_batch"]["source"]), ("default", "default"))
		self.ev("1 settings validation", "min_phone_digits=99 refused, nothing stored (even the valid max_batch)", out)

	def test_non_admin_refused_read_only_can_read(self):
		with as_user(WRITER), self.assertRaises(frappe.PermissionError):
			api_limits.update_broadcast_limits(values=json.dumps({"max_batch": 100}))
		with as_user(READER), self.assertRaises(frappe.PermissionError):
			api_limits.update_broadcast_limits(values=json.dumps({"max_batch": 100}))
		self.assertEqual(self.limits()["max_batch"]["source"], "default")
		b = self.mk()
		rows = self.limits(broadcast=b, user=READER)  # read-only user with Gateway read can read a broadcast's limits
		self.assertEqual(rows["max_batch"]["effective"], 200)
		self.ev("1 settings authority", "Gateway-write (non-admin) and read-only users cannot change limits; reader can read", "PermissionError x2, read ok")


# ------------------------------------------------------------------ 2. warnings


class TestScenario2Warnings(G2Case):
	def codes(self, issues):
		return sorted(i["code"] for i in issues)

	def test_red_and_over_budget_warn_but_do_not_block(self):
		b = self.ready(8, base=200)
		with meta("RED", 5):
			out = self.preview(b)
		self.assertTrue(out["success"], out)
		self.assertEqual(out["limits"]["blocking"], [])
		self.assertEqual(self.codes(out["limits"]["warnings"]), ["over_budget", "quality_red"])
		self.assertEqual(out["limits"]["remaining_24h"], 5)
		self.assertEqual(self.graph.calls, [])
		self.ev("2 warnings", "RED + over budget: blocking [], warnings {quality_red, over_budget}, remaining_24h 5", self.codes(out["limits"]["warnings"]))

	def test_start_needs_exact_warning_codes(self):
		b = self.ready(8, base=210)
		with meta("RED", 5):
			refused = self.start(b, count=8)
			self.assertEqual(refused.get("error"), "warnings_changed", refused)
			self.assertEqual(sorted(w["code"] for w in refused["warnings"]), ["over_budget", "quality_red"])
			self.assertEqual(self.status(b), "Draft")
			for partial in (["quality_red"], ["over_budget"], ["quality_red", "over_budget", "tier_unknown"], ["bogus"]):
				self.assertEqual(self.start(b, count=8, override=partial).get("error"), "warnings_changed", partial)
			self.assertEqual(self.status(b), "Draft")
			ok = self.start(b, count=8, override=["over_budget", "quality_red"])
		self.assertTrue(ok.get("success"), ok)
		self.assertEqual(self.status(b), "Running")
		self.assertEqual(ok["deferred_over_budget"], 3)
		self.ev("2 warnings", "no override / partial / superset / bogus -> warnings_changed (Draft); exact codes -> Running", "as expected; deferred_over_budget=3")

	def test_warning_set_changed_between_preview_and_start_is_rejected(self):
		b = self.ready(8, base=220)
		with meta("RED", 5):
			seen = self.codes(self.preview(b)["limits"]["warnings"])
		self.assertEqual(seen, ["over_budget", "quality_red"])
		with meta("GREEN", 5):  # quality recovered after the operator looked at the preview
			out = self.start(b, count=8, override=seen)
		self.assertEqual(out.get("error"), "warnings_changed", out)
		self.assertEqual(self.codes(out["warnings"]), ["over_budget"])
		self.assertEqual(self.status(b), "Draft")
		with meta("RED", 250):  # budget grew: over_budget disappeared, quality still RED
			out = self.start(b, count=8, override=seen)
		self.assertEqual(out.get("error"), "warnings_changed", out)
		self.assertEqual(self.codes(out["warnings"]), ["quality_red"])
		self.ev("2 warnings", "acknowledged set != current set at start -> warnings_changed with the new list", "GREEN: [over_budget]; budget 250: [quality_red]; both Draft")

	def test_api_key_caller_needs_override_but_no_typed_count(self):
		b = self.ready(8, base=230)
		with meta("RED", 250), patch.object(frappe, "get_request_header", return_value="token key:secret"):
			self.assertTrue(bapi._is_api_key_caller())
			no_override = self.start(b)  # no typed count: allowed for API keys; warnings still must be named
			self.assertEqual(no_override.get("error"), "warnings_changed", no_override)
			ok = self.start(b, override=["quality_red"])
		self.assertTrue(ok.get("success"), ok)
		self.assertEqual(self.status(b), "Running")
		b2 = self.ready(3, base=240)
		with meta("GREEN", 250):  # control: a browser session without the count is refused
			self.assertEqual(self.start(b2).get("error"), "confirm_mismatch")
		self.ev("2 warnings api-key", "API key: no typed count needed, but override_warnings still required; browser w/o count -> confirm_mismatch", "as expected")

	def test_typed_count_off_session_caller_without_count(self):
		self.settings(require_typed_count=False)
		self.assertEqual(self.limits()["require_typed_count"]["effective"], False)
		b = self.ready(3, base=250)
		with meta("GREEN", 250):
			out = self.preview(b)
			self.assertFalse(out["confirm_required"])
			ok = self.start(b, override=[])
		self.assertTrue(ok.get("success"), ok)
		self.assertEqual(self.status(b), "Running")
		self.ev("2 warnings typed-count off", "require_typed_count off: preview.confirm_required False, start without count -> Running", "as expected")


# ------------------------------------------------------------------ 3. over-budget deferral


class TestScenario3OverBudget(G2Case):
	def test_only_remaining_budget_is_sent_rest_waits_without_busy_loop(self):
		b = self.ready(8, base=300)
		with meta("GREEN", 5):
			start = self.start(b, count=8, override=["over_budget"])
			self.assertTrue(start.get("success"), start)
			self.assertEqual(start["deferred_over_budget"], 3)
			t0 = time.monotonic()
			first = self.tick(b)
			second = self.tick(b)
			elapsed = time.monotonic() - t0
		self.assertEqual(len(self.graph.calls), 5)
		self.assertEqual(first["result"], "idle", first)  # not "continued": no self re-enqueue while only future rows remain
		self.assertEqual(first["sent"], 5)
		self.assertEqual((second["result"], second["sent"]), ("idle", 0))
		self.assertEqual(len(self.graph.calls), 5)  # the second tick sent nothing more
		queued = self.rows(b, status="queued")
		self.assertEqual(len(queued), 3)
		horizon = add_to_date(now_datetime(), hours=23)
		self.assertTrue(all(r["next_attempt_at"] and r["next_attempt_at"] > horizon for r in queued), queued)
		self.assertEqual(self.status(b), "Running")  # waits for the next window; not completed, not failed
		continuations = [t for t in self.ticks if t[1].get("job_id", "").count("::") > 2]
		self.assertEqual(continuations, [])
		self.assertLess(elapsed, 30)
		self.ev("3 over budget", "5 of 8 sent (budget 5); 3 stay queued with next_attempt_at ~ +24h; tick -> idle, no continuation job",
			f"sent=5 queued=3 next_attempt_at={queued[0]['next_attempt_at']} tick1={first['result']} tick2={second['result']} elapsed={elapsed:.2f}s")  # fmt: skip


# ------------------------------------------------------------------ 4. audiences


def csv(numbers, first="Ann", tags=("vip", "std")):
	lines = ["phone,name,tags,first"]
	lines += [f"{n},Name {n[-3:]},{tags[i % 2]},{first}{i}" for i, n in enumerate(numbers)]
	return "\n".join(lines)


MAPPING = {"phone": "phone", "name": "name", "tags": "tags", "params": ["first"]}


class TestScenario4Audiences(G2Case):
	def make(self, title, purposes=("marketing", "utility")) -> str:
		with as_user(WRITER):
			out = aapi.create_audience(
				gateway=self.gw, title=f"{PREFIX} {title}", consent_source="g2 signup form", consent_basis="opt-in form",
				consent_purposes=list(purposes), consent_attested=True,
			)  # fmt: skip
		self.assertTrue(out.get("success"), out)
		return out["audience"]["name"]

	def fill(self, audience, text, user=WRITER) -> dict:
		with as_user(user):
			out = aapi.import_members(audience=audience, csv_text=text, mapping=json.dumps(MAPPING))
		self.assertTrue(out.get("success"), out)
		return out

	def wire(self, b, picks, user=WRITER):
		with as_user(user):
			return wiring.set_broadcast_audiences(broadcast=b, selection=json.dumps(picks))

	def lists(self):
		a, bb, c, ex = (self.make(t) for t in ("A", "B", "C", "EXCLUDE"))
		n = {i: num(400 + i) for i in range(1, 9)}
		out = self.fill(a, csv([n[1], n[2], n[3], n[4], "12345"]))  # one invalid number
		self.assertEqual((out["added"], out["invalid_total"]), (4, 1))
		self.fill(bb, csv([n[3], n[4], n[5], n[6]], first="Bob"))
		self.fill(c, csv([n[6], n[7]], first="Cy"))
		self.fill(ex, csv([n[2], n[7]]))
		# N5 sent STOP for marketing: recorded the way Meta's user_preferences webhook records it (gateway_consent)
		account_events.record_user_preferences(self.gw, [{"category": account_events.MARKETING, "value": "stop", "wa_id": n[5]}])
		frappe.db.commit()
		return a, bb, c, ex, n

	def test_overlap_exclude_suppression_params_consent_and_snapshot(self):
		a, bb, c, ex, n = self.lists()
		b = self.mk("g2e2e_mkt")
		picks = [{"audience": a}, {"audience": bb}, {"audience": c}, {"audience": ex, "exclude": True}]
		with as_user(WRITER):
			pre = aapi.preview_audience_selection(broadcast=b, selection=json.dumps(picks))
		out = self.wire(b, picks)
		self.assertTrue(out.get("success"), out)
		want = {"total": 10, "dupes": 3, "excluded": 2, "suppressed": 1, "blocked_by_purpose": 0, "final": 4}
		self.assertEqual({k: out["counts"][k] for k in want}, want)
		self.assertEqual(pre["counts"], out["counts"])  # the preview promised the same numbers
		rows = {r["recipient"]: r for r in self.rows(b)}
		self.assertEqual(sorted(r for r, x in rows.items() if x["status"] == "queued"), [n[1], n[3], n[4], n[6]])
		self.assertEqual((rows[n[5]]["status"], rows[n[5]]["skip_reason"]), ("skipped", "marketing_opted_out"))
		self.assertNotIn(n[2], rows)
		self.assertNotIn(n[7], rows)
		# first list wins the audience and the template variables (A has N3/N4 with Ann2/Ann3; B has them as Bob0/Bob1)
		self.assertEqual((rows[n[3]]["audience"], rows[n[4]]["audience"], rows[n[6]]["audience"]), (a, a, bb))
		self.assertEqual(json.loads(rows[n[3]]["params"]), {"body": ["Ann2"]})
		self.assertEqual(json.loads(rows[n[4]]["params"]), {"body": ["Ann3"]})
		self.assertEqual(json.loads(rows[n[6]]["params"]), {"body": ["Bob3"]})
		# consent cover: every sendable row comes from an attested list -> broadcast is attested without a box
		self.assertTrue(out["consent"]["satisfied"])
		self.assertEqual(self.status(b, "consent_attested"), 1)
		self.assertTrue(str(self.status(b, "consent_source")).startswith("Audiences:"))
		# snapshot frozen: edit list A afterwards (add N8, remove N1)
		with as_user(WRITER):
			self.assertTrue(aapi.import_members(audience=a, csv_text=csv([num(408)]), mapping=json.dumps(MAPPING))["success"])
			self.assertTrue(aapi.remove_members(audience=a, recipients=json.dumps([n[1]]))["success"])
		frozen = sorted(r["recipient"] for r in self.rows(b, status="queued"))
		self.assertEqual(frozen, [n[1], n[3], n[4], n[6]])
		# and it really sends: each recipient gets ITS row's template variable in the Graph payload
		with meta("GREEN", 250):
			pv = self.preview(b)
			self.assertEqual(pv["limits"]["blocking"], [], pv["limits"]["blocking"])
			self.assertEqual(pv["limits"]["warnings"], [])
			ok = self.start(b, count=4, override=[])
			self.assertTrue(ok.get("success"), ok)
			res = self.tick(b)
		self.assertEqual(res["result"], "completed", res)
		sent = {c["to"]: c["payload"]["template"]["components"][0]["parameters"][0]["text"] for c in self.graph.calls}
		self.assertEqual(sent, {n[1]: "Ann0", n[3]: "Ann2", n[4]: "Ann3", n[6]: "Bob3"})
		self.ev("4 audiences", "A,B,C minus EXCLUDE: total10 dupes3 excluded2 suppressed1 final4; STOP'd N5 skipped; first-list params; auto-attest; snapshot frozen; payload carries row vars",
			f"counts={out['counts']} sent={sent}")  # fmt: skip

	def test_tag_filter(self):
		a, *_ = self.lists()
		b = self.mk("g2e2e_mkt")
		out = self.wire(b, [{"audience": a, "tags": ["vip"], "tag_filter_mode": "all"}])
		self.assertTrue(out.get("success"), out)
		self.assertEqual(sorted(r["recipient"] for r in self.rows(b)), [num(401), num(403)])  # idx 0,2 are vip
		self.ev("4 audiences tag filter", "tag vip on list A -> N1,N3 only", [r["recipient"] for r in self.rows(b)])

	def test_marketing_template_vs_list_without_marketing_purpose(self):
		ok_list = self.make("MKT-OK")
		util_only = self.make("UTIL-ONLY", purposes=("utility",))
		self.fill(ok_list, csv([num(450), num(451)]))
		self.fill(util_only, csv([num(452), num(453)]))
		# (a) marketing template: wiring blocks the utility-only list and adds none of its rows
		b = self.mk("g2e2e_mkt")
		out = self.wire(b, [{"audience": ok_list}, {"audience": util_only}])
		self.assertEqual([x["code"] for x in out["blocked"]], ["audience_purpose_mismatch"])
		self.assertEqual(sorted(r["recipient"] for r in self.rows(b)), [num(450), num(451)])
		with meta("GREEN", 250):
			codes = [x["code"] for x in self.preview(b)["limits"]["blocking"]]
		self.assertEqual(codes, ["audience_purpose_mismatch"])  # still picked, so the preview blocks
		# (b) utility template: both lists are fine, preview clean; then Meta recategorizes the template
		b2 = self.mk("g2e2e_util")
		out = self.wire(b2, [{"audience": ok_list}, {"audience": util_only}])
		self.assertEqual(out["blocked"], [])
		with meta("GREEN", 250):
			self.assertEqual(self.preview(b2)["limits"]["blocking"], [])
			frappe.db.set_value("WhatsApp Templates", STATE["util"], "category", "MARKETING")
			self.addCleanup(lambda: (frappe.db.set_value("WhatsApp Templates", STATE["util"], "category", "UTILITY"), frappe.db.commit()))
			pv = self.preview(b2)
			self.assertEqual([x["code"] for x in pv["limits"]["blocking"]], ["audience_purpose_mismatch"])
			refused = self.start(b2, count=4, override=[])
			self.assertEqual(refused.get("error"), "audience_purpose_mismatch", refused)
			self.assertEqual(self.status(b2), "Draft")
		self.assertEqual(self.graph.calls, [])
		self.ev("4 audiences purpose", "marketing template vs utility-only list: blocked at wiring + preview; flip utility->marketing after a clean preview: preview AND start refuse",
			f"wiring blocked={[x['code'] for x in out['blocked']] or 'none (utility)'}; after flip preview={[x['code'] for x in pv['limits']['blocking']]} start={refused.get('error')}")  # fmt: skip

	def test_read_only_user_sees_masked_numbers(self):
		a = self.make("MASK")
		self.fill(a, csv([num(460), num(461)]))
		with as_user(READER):
			out = aapi.list_members(audience=a)
		self.assertTrue(out["masked"])
		self.assertEqual([m["recipient"] for m in out["members"]], ["********" + num(460)[-4:], "********" + num(461)[-4:]])
		with as_user(WRITER):
			full = aapi.list_members(audience=a)
		self.assertFalse(full["masked"])
		self.assertEqual([m["recipient"] for m in full["members"]], [num(460), num(461)])
		self.ev("4 audiences masking", "read-only user sees last 4 digits only, writer sees full", [m["recipient"] for m in out["members"]])


# ------------------------------------------------------------------ 5/6. opt-out mid-run, kill switch


class TestScenario5OptOut(G2Case):
	def test_stop_keyword_mid_run_skips_a_queued_recipient(self):
		b = self.ready(6, base=500)
		victim = num(504)
		gateway_doc = frappe.get_doc("Gateway", self.gw)

		def stop_arrives(n, to):
			if n == 2:
				gateway_doc.reload()
				gateway_service._record_opt_out(gateway_doc, victim)  # the STOP keyword handler, as the webhook would

		self.graph.on_post = stop_arrives
		with meta("GREEN", 250):
			self.assertTrue(self.start(b, count=6, override=[]).get("success"))
			res = self.tick(b)
		self.assertEqual(res["result"], "completed", res)
		self.assertNotIn(victim, self.graph.recipients)
		self.assertEqual(len(self.graph.calls), 5)
		row = self.rows(b, recipient=victim)[0]
		self.assertEqual((row["status"], row["skip_reason"]), ("skipped", "opted_out"))
		self.ev("5 opt-out", "STOP for queued N4 arrives during the run -> skipped(opted_out), never posted; other 5 sent", f"posted={len(self.graph.calls)} victim={row['status']}/{row['skip_reason']}")  # fmt: skip

	def test_marketing_stop_preference_mid_run_skips(self):
		b = self.ready(5, template="g2e2e_mkt", base=520)
		victim = num(523)

		def marketing_stop(n, to):
			if n == 1:
				account_events.record_user_preferences(self.gw, [{"category": account_events.MARKETING, "value": "stop", "wa_id": victim}])

		self.graph.on_post = marketing_stop
		with meta("GREEN", 250):
			self.assertTrue(self.start(b, count=5, override=[]).get("success"))
			res = self.tick(b)
		self.assertEqual(res["result"], "completed", res)
		self.assertNotIn(victim, self.graph.recipients)
		self.assertEqual(len(self.graph.calls), 4)
		row = self.rows(b, recipient=victim)[0]
		self.assertEqual(row["status"], "skipped")
		self.ev("5 opt-out marketing", "marketing stop (131050-style preference) mid-run -> skipped, never posted", f"{row['status']}/{row['skip_reason']}")


class TestScenario6KillSwitch(G2Case):
	def test_pause_all_stops_the_run_and_resume_finishes_it(self):
		b = self.ready(12, base=600)

		def kill(n, to):
			if n == 3:
				with as_user(WRITER):
					out = bapi.pause_all_broadcasts(gateway=self.gw)
				assert out["success"] and out["paused"] == [b], out

		self.graph.on_post = kill
		with meta("GREEN", 250):
			self.assertTrue(self.start(b, count=12, override=[]).get("success"))
			res = self.tick(b)
			self.assertEqual((res["result"], res["reason"]), ("paused", "kill_switch"), res)
			self.assertEqual(len(self.graph.calls), 3)
			self.assertEqual((self.status(b), self.status(b, "pause_reason")), ("Paused", "kill_switch"))
			self.assertEqual(len(self.rows(b, status="queued")), 9)
			again = self.tick(b)
			self.assertEqual(again["result"], "not_running:Paused")
			self.assertEqual(len(self.graph.calls), 3)  # nothing sent while paused
			self.graph.on_post = None
			with as_user(WRITER):
				resumed = bapi.resume_broadcast(broadcast=b)
			self.assertTrue(resumed.get("success"), resumed)
			done = self.tick(b)
		self.assertEqual(done["result"], "completed", done)
		self.assertEqual(len(self.graph.calls), 12)
		self.assertEqual(sorted(self.graph.recipients), [num(600 + i) for i in range(12)])  # nobody twice, nobody lost
		self.ev("6 kill switch", "pause_all after the 3rd post: 3 sent, Paused/kill_switch, 9 queued, paused ticks send 0; resume completes with 12 unique posts",
			"as expected")  # fmt: skip
