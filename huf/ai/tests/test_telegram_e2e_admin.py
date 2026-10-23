# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""End-to-end Telegram admin cockpit flows (E2E-4).

Runs the real ``telegram_admin`` / ``telegram_miniapp_api`` code over an in-memory fake Frappe layer
(tables, read permissions, workflow). No site, no live Telegram, no LLM: fakes only.
"""

import dataclasses
import json
import threading
import time
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai import telegram_admin as ta
from huf.ai import telegram_miniapp_api as _api
from huf.ai.gateway_adapters import telegram_admin_hooks
from huf.ai.gateway_adapters import telegram_miniapp as miniapp
from huf.ai.gateway_adapters.telegram_inbound import TelegramUpdate
from huf.ai.tests.test_telegram_admin import FakeAdapter


class _HeaderApi:
	"""Mini App endpoints with ``token=`` delivered via the X-Huf-Tg-Token header (the only accepted transport)."""

	def __getattr__(self, name):
		fn = getattr(_api, name)
		if not callable(fn):
			return fn

		def call(*a, token=None, **kw):
			raw = token or ""
			with patch("frappe.get_request_header", lambda h: raw if h == _api.TOKEN_HEADER else None):
				return fn(*a, **kw)

		return call


api = _HeaderApi()

TOKEN = "123456:TEST-not-a-real-token"
GW = "tg-gw"
TG, CHAT = "777", "777"
TG2, CHAT2 = "888", "888"
BOUND = "ops@example.com"
BOUND2 = "ops2@example.com"
ADMIN = "boss@example.com"
NOW_DT = datetime(2026, 10, 23, 9, 0, 0)
ACTION = {"op": "workflow", "dt": "Leave Application", "dn": "LA-1", "transition": "Approve"}

DOCTYPES = {
	"Leave Application": {
		"title_field": "employee_name",
		"workflow": "Leave Approval",
		"submittable": 1,
		"fields": [
			("employee_name", "Data", 1, 0),
			("leave_type", "Data", 1, 0),
			("hr_note", "Small Text", 1, 1),  # permlevel 1: never echoed
		],
	},
	"Salary Slip": {"title_field": "employee_name", "fields": [("employee_name", "Data", 1, 0)]},
	"Workflow Action": {"fields": [("status", "Data", 1, 0)]},
	"Telegram Admin Audit": {"fields": []},
	"Telegram Admin Binding": {"fields": []},
	"Gateway": {"fields": []},
	"User": {"fields": []},
}


class _Row(dict):
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(key) from None


def _matches(row, filters):
	if isinstance(filters, str):
		return row.get("name") == filters
	for key, want in (filters or {}).items():
		have = row.get(key)
		if isinstance(want, tuple):  # ("<op>", value)
			op, val = want
			if op != ">=" or have is None or not have >= val:
				return False
		elif have != want:
			return False
	return True


class FakeMeta:
	def __init__(self, spec):
		self.istable = 0
		self.issingle = 0
		self.title_field = spec.get("title_field")
		self.is_submittable = spec.get("submittable", 0)
		self._workflow = spec.get("workflow")
		self.fields = [
			SimpleNamespace(fieldname=f, label=f.title(), fieldtype=t, in_list_view=lv, permlevel=p, hidden=0)
			for f, t, lv, p in spec.get("fields", [])
		]

	def has_field(self, fieldname):
		return fieldname == self.title_field or any(d.fieldname == fieldname for d in self.fields)

	def get_workflow(self):
		return self._workflow


class FakeFrappe:
	"""In-memory tables + per-user read permissions + a two-step workflow. Patched into ``frappe``."""

	def __init__(self):
		self.tables = {
			"Gateway": [{"name": GW, "provider": "Telegram", "gateway_name": "Huf Ops Bot"}],
			"User": [{"name": u, "enabled": 1} for u in (BOUND, BOUND2, ADMIN)],
			"Telegram Admin Binding": [],
			"Telegram Admin Audit": [],
			"Leave Application": [
				{
					"name": "LA-1",
					"employee_name": "Ana Lee",
					"leave_type": "Annual",
					"hr_note": "x",
					"workflow_state": "Pending Approval",
					"docstatus": 0,
					"modified": NOW_DT,
				},
				{
					"name": "LA-2",
					"employee_name": "Ben Ortiz",
					"leave_type": "Sick",
					"workflow_state": "Pending Approval",
					"docstatus": 0,
					"modified": NOW_DT,
				},
			],
			"Salary Slip": [{"name": "SS-1", "employee_name": "Ana Lee", "docstatus": 0, "modified": NOW_DT}],
			"Workflow Action": [
				{
					"name": "WA-1",
					"reference_doctype": "Leave Application",
					"reference_name": "LA-1",
					"workflow_state": "Pending Approval",
					"status": "Open",
					"creation": NOW_DT,
				},
				{
					"name": "WA-2",
					"reference_doctype": "Leave Application",
					"reference_name": "LA-2",
					"workflow_state": "Pending Approval",
					"status": "Open",
					"creation": NOW_DT,
				},
			],
		}
		self.doctypes = DOCTYPES
		self.perms = {
			(BOUND, "Leave Application"),
			(BOUND, "Workflow Action"),
			(BOUND2, "Leave Application"),
			(BOUND2, "Workflow Action"),
			(ADMIN, "Leave Application"),
			(ADMIN, "Workflow Action"),
			(ADMIN, "Telegram Admin Audit"),
		}
		self.gateway_admin = {ADMIN}
		self.session = SimpleNamespace(user="Guest")
		self.applied = []  # (user, name, transition) actually applied by the workflow engine
		self.apply_error = None  # raised once by the next apply_workflow call
		self.commits = 0

	# session / tables
	def table(self, dt):
		return self.tables.setdefault(dt, [])

	def set_user(self, user):
		self.session.user = user

	def can_read(self, dt):
		return (self.session.user, dt) in self.perms

	def insert(self, dt, data):
		row = _Row(data)
		row.setdefault("name", f"{dt.split()[0][:3].upper()}-{len(self.table(dt)) + 1:04d}")
		row.setdefault("creation", datetime.now())
		row.setdefault("modified", datetime.now())
		self.table(dt).append(row)
		return row

	def find(self, dt, filters):
		return next((r for r in self.table(dt) if _matches(r, filters)), None)

	# frappe.get_* surface
	def get_meta(self, dt):
		if dt not in self.doctypes:
			raise frappe.DoesNotExistError(dt)
		return FakeMeta(self.doctypes[dt])

	def get_doc(self, *args, **kw):
		if isinstance(args[0], dict):
			data = {k: v for k, v in args[0].items() if k != "doctype"}
			return FakeDoc(self, args[0]["doctype"], self.insert(args[0]["doctype"], data))
		dt, name = args
		row = self.find(dt, {"name": name})
		if row is None:
			raise frappe.DoesNotExistError(name)
		return FakeDoc(self, dt, row)

	def _select(self, dt, or_filters, filters, limit):
		rows = [r for r in self.table(dt) if _matches(r, filters or {})]
		if or_filters:
			rows = [r for r in rows if any(self._like(r, c) for c in or_filters)]
		return [_Row(r) for r in rows][: limit or None]

	@staticmethod
	def _like(row, clause):
		_dt, field, _op, pattern = clause
		value = row.get(field)
		return bool(value) and pattern.strip("%").lower() in str(value).lower()

	def get_list(self, dt, fields=None, or_filters=None, filters=None, limit_page_length=None, **kw):
		if not self.can_read(dt):
			raise frappe.PermissionError(f"No read permission on {dt}")
		return self._select(dt, or_filters, filters, limit_page_length)

	def get_all(self, dt, filters=None, fields=None, limit_page_length=None, **kw):
		return self._select(dt, None, filters, limit_page_length)

	def delete_doc(self, dt, name, **kw):
		self.tables[dt] = [r for r in self.table(dt) if r.get("name") != name]

	def cached_value(self, dt, name, field):
		return "workflow_state" if dt == "Workflow" else None

	# workflow engine (frappe.model.workflow)
	def transitions(self, doc):
		if doc.get("workflow_state") == "Pending Approval":
			return [{"action": "Approve"}, {"action": "Reject"}]
		return []

	def apply_workflow(self, doc, action):
		if self.apply_error is not None:
			err, self.apply_error = self.apply_error, None
			raise err
		doc._row["workflow_state"] = {"Approve": "Approved", "Reject": "Rejected"}[action]
		self.applied.append((self.session.user, doc.name, action))
		return doc

	# frappe.db
	def get_value(self, doctype, filters=None, fieldnames=None, as_dict=False, **kw):
		row = self.find(doctype, filters)
		if row is None:
			return None
		if isinstance(fieldnames, str):
			return row.get(fieldnames)
		fields = fieldnames or ["name"]
		return _Row({f: row.get(f) for f in fields}) if as_dict else tuple(row.get(f) for f in fields)

	def exists(self, doctype, filters=None):
		if doctype == "DocType":
			return filters in self.doctypes
		return self.find(doctype, filters) is not None

	def set_value(self, doctype, name, field, value=None, update_modified=True):
		row = self.find(doctype, name)
		if row is None:
			raise frappe.DoesNotExistError(name)
		for key, val in field.items() if isinstance(field, dict) else [(field, value)]:
			row[key] = val

	def count(self, doctype, filters=None):
		return sum(1 for r in self.table(doctype) if _matches(r, filters or {}))

	def commit(self):
		self.commits += 1

	def rollback(self):
		pass


class FakeDoc:
	def __init__(self, store, dt, row):
		self._store, self.doctype, self._row = store, dt, row

	@property
	def name(self):
		return self._row["name"]

	@property
	def docstatus(self):
		return self._row.get("docstatus", 0)

	@property
	def modified(self):
		return self._row.get("modified")

	def get(self, key, default=None):
		return self._row.get(key, default)

	def check_permission(self, ptype="read"):
		if not self._store.can_read(self.doctype):
			raise frappe.PermissionError(f"No {ptype} on {self.doctype}")

	def insert(self, ignore_permissions=False):
		return self


def _upd(text, tg=TG, chat=CHAT):
	command = text[1:].split()[0] if text.startswith("/") else ""
	payload = text.split(None, 1)[1] if command == "start" and " " in text else ""
	return TelegramUpdate(
		kind="message",
		update_id="1",
		raw={},
		chat_id=chat,
		chat_type="private",
		sender_id=tg,
		message_id="10",
		text=text,
		command=command,
		start_payload=payload,
	)


def _press(data, tg=TG, chat=CHAT):
	return TelegramUpdate(
		kind="callback_query",
		update_id="2",
		raw={},
		chat_id=chat,
		chat_type="private",
		sender_id=tg,
		message_id="11",
		callback_query_id="cq1",
		callback_data=data,
	)


class AtomicCache(ta.MemCache):
	"""MemCache plus the Redis surface (make_key / incrby / expire / set NX), every op lock-guarded."""

	def __init__(self):
		super().__init__()
		self._lock = threading.Lock()
		self.counts, self.flags = {}, {}

	def get_value(self, key):
		with self._lock:
			return super().get_value(key)

	def set_value(self, key, value, expires_in_sec=None):
		with self._lock:
			super().set_value(key, value, expires_in_sec)

	def delete_value(self, key):
		with self._lock:
			super().delete_value(key)

	def make_key(self, key):
		return f"site|{key}"

	def incrby(self, key, n):
		with self._lock:
			self.counts[key] = self.counts.get(key, 0) + n
			return self.counts[key]

	def expire(self, key, ttl):
		pass

	def set(self, key, value, nx=False, ex=None):
		with self._lock:
			if nx and key in self.flags:
				return False
			self.flags[key] = value
			return True


class E2EBase(unittest.TestCase):
	def setUp(self):
		self.fx = FakeFrappe()
		self.clock = [time.time()]
		self.cache = ta.MemCache(clock=lambda: self.clock[0])
		from huf.ai.tests.telegram_fakes import isolate_admin_cache, set_local_flags

		set_local_flags(self, in_test=False)
		isolate_admin_cache(self, ta, self.cache)
		self.adapter = FakeAdapter()
		self.gateway = SimpleNamespace(name=GW)
		fx = self.fx
		patches = [
			patch.object(frappe, "db", fx, create=True),
			patch.object(frappe, "session", fx.session, create=True),
			patch.object(frappe, "set_user", fx.set_user, create=True),
			patch.object(frappe, "get_doc", fx.get_doc, create=True),
			patch.object(frappe, "get_meta", fx.get_meta, create=True),
			patch.object(frappe, "get_list", fx.get_list, create=True),
			patch.object(frappe, "get_all", fx.get_all, create=True),
			patch.object(frappe, "delete_doc", fx.delete_doc, create=True),
			patch.object(frappe, "get_cached_value", fx.cached_value, create=True),
			patch.object(frappe, "get_request_header", lambda *a, **k: "", create=True),
			patch.object(frappe.utils, "get_fullname", lambda u: "Ops Person" if u == BOUND else u),
			patch.object(frappe.utils, "now_datetime", datetime.now),
			patch.object(frappe.utils, "add_days", lambda dt, n: dt + timedelta(days=n)),
			patch.object(frappe.utils, "get_url", lambda path="": "https://huf.example" + path),
			patch("huf.permissions.is_gateway_admin", lambda user=None: user in fx.gateway_admin),
			patch("frappe.model.workflow.get_transitions", fx.transitions),
			patch("frappe.model.workflow.apply_workflow", fx.apply_workflow),
			patch.object(ta, "_LOCAL", self.cache),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	# helpers
	def mint(self, user, role):
		prev = self.fx.session.user
		self.fx.session.user = user
		try:
			return ta.create_binding_code(GW, role)["code"]
		finally:
			self.fx.session.user = prev

	def bind(self, user, role, tg=TG, chat=CHAT):
		return ta.handle_message(
			self.gateway, self.adapter, _upd(f"/start {self.mint(user, role)}", tg, chat), cache=self.cache
		)

	def send(self, text, tg=TG, chat=CHAT):
		return ta.handle_message(self.gateway, self.adapter, _upd(text, tg, chat), cache=self.cache)

	def press(self, data, tg=TG, chat=CHAT):
		return ta.handle_callback(self.gateway, self.adapter, _press(data, tg, chat), cache=self.cache)

	def sent(self):
		return [c.args[1] for c in self.adapter.sender.send_text.call_args_list]

	def last_text(self):
		return self.sent()[-1]

	def buttons(self):
		markup = self.adapter.sender.send_text.call_args_list[-1].kwargs.get("markup") or {}
		return [b for row in markup.get("inline_keyboard", []) for b in row if "callback_data" in b]

	def button(self, prefix):
		return next(b["callback_data"] for b in self.buttons() if b["text"].startswith(prefix))

	def audit(self):
		return list(self.fx.table("Telegram Admin Audit"))

	def miniapp_token(self):
		init = miniapp.build_init_data_for_test(
			TOKEN, user={"id": int(TG), "first_name": "Ops"}, auth_date=int(time.time()) - 5
		)
		return ta.miniapp_auth(init, GW, bot_token=TOKEN, cache=self.cache)["token"]


class TestOperatorChatFlow(E2EBase):
	def test_full_operator_flow_bind_to_unbind(self):
		self.assertEqual(self.bind(BOUND, "Operator")["note"], "bound")

		self.send("/me")
		self.assertIn(BOUND, self.last_text())
		self.assertIn("Scope: Operator", self.last_text())

		self.send("/find Leave Application Ana")
		self.assertIn("Leave Application (1)", self.last_text())
		self.assertIn("LA-1", self.last_text())

		for text in ("/find User ops", "/find Telegram Admin Audit x", "/find Telegram Admin Binding"):
			self.send(text)
			self.assertEqual(self.last_text(), "That DocType is not available here.", text)
		self.send("/find Salary Slip Ana")  # allowed doctype, but no read permission for this user
		self.assertEqual(self.last_text(), "You do not have permission for that.")

		self.send("/open Leave Application LA-1")
		self.assertIn("Workflow state: Pending Approval", self.last_text())
		self.assertNotIn("hr_note", self.last_text())  # permlevel > 0 never echoed
		self.assertIn("Ana Lee", self.last_text())
		self.button("Approve")

		self.send("/approvals")
		self.assertIn("Waiting for you (2)", self.last_text())
		self.assertEqual(self.press(self.button("Approve LA-1"))["note"], "proposed")
		self.assertIn("Apply 'Approve' to Leave Application LA-1", self.last_text())
		self.assertEqual(self.press(self.button("Confirm"))["note"], "confirmed")

		self.assertEqual(self.fx.applied, [(BOUND, "LA-1", "Approve")])
		self.assertEqual(
			self.adapter.sender.edit_message_text.call_args.args[2],
			"Done: Leave Application LA-1 is now Approved",
		)
		row = [r for r in self.audit() if r["action"] == "workflow"][-1]
		self.assertEqual((row["frappe_user"], row["reference_name"], row["result"]), (BOUND, "LA-1", "ok"))
		self.assertTrue(row["confirmed_by_nonce"])
		self.assertEqual(json.loads(row["arguments_json"])["transition"], "Approve")

		self.send("/unbind")
		self.assertEqual(self.press(self.button("Confirm"))["note"], "confirmed")
		self.assertEqual(self.audit()[-1]["action"], "unbind")
		self.assertIsNone(ta.get_binding(TG, GW, cache=self.cache))
		count = len(self.sent())
		self.assertIsNone(self.send("/me"))  # unbound: falls through, no cockpit reply
		self.assertEqual(len(self.sent()), count)

	def test_viewer_sees_no_action_buttons(self):
		self.bind(BOUND, "Viewer")
		self.send("/approvals")
		self.assertEqual(self.buttons(), [])
		self.send("/open Leave Application LA-1")
		self.assertEqual(self.buttons(), [])


class TestRevocation(E2EBase):
	def test_chat_unbind_stops_miniapp_token_immediately(self):
		self.bind(BOUND, "Operator")
		token = self.miniapp_token()
		self.assertTrue(api.me(token=token)["ok"])
		self.send("/unbind")
		self.press(self.button("Confirm"))
		res = api.me(token=token)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "unauthorized")
		self.assertFalse(api.act_prepare("Leave Application", "LA-1", "Approve", token=token)["ok"])

	def test_owner_revoke_binding_kills_token(self):
		self.bind(BOUND, "Operator")
		token = self.miniapp_token()
		name = self.fx.table("Telegram Admin Binding")[0]["name"]
		self.fx.session.user = BOUND
		self.assertTrue(ta.revoke_binding(name)["ok"])
		self.assertEqual(api.me(token=token)["error"]["code"], "unauthorized")

	def test_non_owner_cannot_revoke_binding(self):
		self.bind(BOUND, "Operator")
		name = self.fx.table("Telegram Admin Binding")[0]["name"]

		def throw(msg, exc=frappe.ValidationError):
			raise exc(msg)

		self.fx.session.user = BOUND2
		with patch.object(frappe, "throw", throw, create=True):
			with self.assertRaises(frappe.PermissionError):
				ta.revoke_binding(name)
		self.assertEqual(self.fx.find("Telegram Admin Binding", {"name": name})["is_active"], 1)

	def test_admin_binding_downgraded_when_gateway_admin_lost(self):
		self.assertEqual(self.bind(ADMIN, "Admin")["note"], "bound")
		self.send("/audit")
		self.assertNotIn("scope required", self.last_text())
		token = self.miniapp_token()
		self.assertEqual(api.config(token=token)["data"]["role_scope"], "Admin")
		self.assertTrue(api.config(token=token)["data"]["features"]["audit_all"])

		self.fx.gateway_admin.discard(ADMIN)
		self.send("/audit")  # verdict is cached for _ADMIN_RECHECK_TTL: staleness is bounded, not zero
		self.assertNotIn("scope required", self.last_text())
		self.clock[0] += ta._ADMIN_RECHECK_TTL + 1
		self.send("/audit")
		self.assertEqual(self.last_text(), "Admin scope required.")
		for _ in range(3):
			cfg = api.config(token=token)["data"]
			self.assertEqual(cfg["role_scope"], "Operator")
			self.assertFalse(cfg["features"]["audit_all"])
			self.assertTrue(cfg["features"]["act"])
		downgrades = [r for r in self.audit() if r["result"] == "scope_downgraded"]
		self.assertEqual(len(downgrades), 1)
		self.assertEqual(api.audit(token=token)["data"]["scope"], "own")


class TestHardening(E2EBase):
	def test_claim_fallback_is_single_use_under_concurrency(self):
		class Slow(ta.MemCache):  # widen the check-then-set window; no make_key => lock-guarded fallback
			def get_value(self, key):
				value = super().get_value(key)
				time.sleep(0.002)
				return value

		cache, wins = Slow(), []
		barrier = threading.Barrier(8)

		def go():
			barrier.wait()
			wins.append(ta._claim(cache, "nonce-1", 60))

		threads = [threading.Thread(target=go) for _ in range(8)]
		for t in threads:
			t.start()
		for t in threads:
			t.join()
		self.assertEqual(wins.count(True), 1, wins)

	def test_callback_with_missing_chat_type_is_refused(self):
		self.bind(BOUND, "Operator")
		self.send("/unbind")
		data = self.button("Confirm")
		for chat_type in ("", None, "group", "supergroup"):
			upd = dataclasses.replace(_press(data), chat_type=chat_type)
			res = ta.handle_callback(self.gateway, self.adapter, upd, cache=self.cache)
			self.assertEqual(res["note"], "not_private", chat_type)
		self.assertIsNotNone(ta.get_binding(TG, GW, cache=self.cache))

	def test_message_with_missing_chat_type_is_not_handled(self):
		self.bind(BOUND, "Operator")
		upd = dataclasses.replace(_upd("/me"), chat_type="")
		self.assertIsNone(ta.handle_message(self.gateway, self.adapter, upd, cache=self.cache))

	def test_restore_failure_chains_the_body_exception_and_leaves_no_bound_user(self):
		calls = []

		def set_user(user):
			calls.append(user)
			if user == "prev-user":
				raise RuntimeError("restore boom")

		self.fx.session.user = "prev-user"
		with patch.object(frappe, "set_user", set_user):
			with self.assertRaises(ta.AdminError) as ctx:
				with ta.run_as(BOUND):
					raise ValueError("body failed")
		self.assertIsInstance(ctx.exception.__cause__, ValueError)
		self.assertEqual(calls[-1], "Guest")  # last-resort drop: the bound user is not left active
		self.assertNotEqual(calls[-1], BOUND)


class TestMiniAppParity(E2EBase):
	def test_initdata_token_act_matches_chat_cockpit_audit(self):
		self.bind(BOUND, "Operator")
		token = self.miniapp_token()

		approvals = api.approvals(token=token)["data"]["items"]
		self.assertEqual({i["name"] for i in approvals}, {"LA-1", "LA-2"})
		self.assertIn("Approve", approvals[0]["actions"])

		prep = api.act_prepare("Leave Application", "LA-1", "Approve", token=token)
		self.assertTrue(prep["ok"], prep)
		conf = api.act_confirm(prep["data"]["nonce"], token=token)
		self.assertEqual(conf["data"]["result"], "Done: Leave Application LA-1 is now Approved")
		self.assertFalse(api.act_confirm(prep["data"]["nonce"], token=token)["ok"])  # single use

		self.send("/approvals")
		self.press(self.button("Approve LA-2"))
		self.press(self.button("Confirm"))

		rows = [r for r in self.audit() if r["action"] == "workflow"]
		self.assertEqual(len(rows), 2)
		mini, chat = rows
		for key in ("action", "frappe_user", "reference_doctype", "result", "gateway", "telegram_user_id"):
			self.assertEqual(mini[key], chat[key], key)
		self.assertEqual(set(json.loads(mini["arguments_json"])), set(json.loads(chat["arguments_json"])))
		self.assertTrue(mini["confirmed_by_nonce"] and chat["confirmed_by_nonce"])
		self.assertNotEqual(mini["confirmed_by_nonce"], chat["confirmed_by_nonce"])
		self.assertEqual(self.fx.applied, [(BOUND, "LA-1", "Approve"), (BOUND, "LA-2", "Approve")])

		audit = api.audit(token=token)["data"]["items"]
		self.assertEqual({r["reference_name"] for r in audit if r["action"] == "workflow"}, {"LA-1", "LA-2"})

	def test_chat_nonce_cannot_be_confirmed_from_miniapp(self):
		self.bind(BOUND, "Operator")
		token = self.miniapp_token()
		self.send("/approvals")
		chat_nonce = ta.parse_callback_payload(
			self.adapter.verify_callback_data(self.button("Approve LA-1"), CHAT)
		)[1]
		self.assertFalse(api.act_confirm(chat_nonce, token=token)["ok"])
		self.assertEqual(self.fx.applied, [])


class TestNonceReplay(E2EBase):
	def test_cross_user_and_replayed_confirmation_rejected(self):
		self.bind(BOUND, "Operator", tg=TG, chat=CHAT)
		self.bind(BOUND2, "Operator", tg=TG2, chat=CHAT2)
		self.send("/open Leave Application LA-1", tg=TG, chat=CHAT)
		self.assertEqual(self.press(self.button("Approve"), tg=TG, chat=CHAT)["note"], "proposed")
		confirm = self.button("Confirm")

		self.assertEqual(self.press(confirm, tg=TG2, chat=CHAT)["note"], "nonce_rejected")
		self.assertEqual(self.fx.applied, [])
		self.assertEqual(self.press(confirm, tg=TG, chat=CHAT)["note"], "confirmed")
		self.assertEqual(self.fx.applied, [(BOUND, "LA-1", "Approve")])

		self.assertEqual(self.press(confirm, tg=TG, chat=CHAT)["note"], "nonce_rejected")
		self.assertEqual(self.press(confirm, tg=TG2, chat=CHAT)["note"], "nonce_rejected")
		self.assertEqual(len(self.fx.applied), 1)
		self.assertEqual(len([r for r in self.audit() if r["action"] == "workflow"]), 1)

	def test_group_press_does_not_burn_owner_confirmation(self):
		self.bind(BOUND, "Operator")
		self.send("/open Leave Application LA-1")
		self.press(self.button("Approve"))
		confirm = self.button("Confirm")
		group_press = dataclasses.replace(_press(confirm), chat_type="supergroup")
		res = ta.handle_callback(self.gateway, self.adapter, group_press, cache=self.cache)
		self.assertEqual(res["note"], "not_private")
		self.assertEqual(self.press(confirm)["note"], "confirmed")
		self.assertEqual(self.fx.applied, [(BOUND, "LA-1", "Approve")])


class TestNonCockpitTraffic(E2EBase):
	def test_bot_group_business_channel_never_reach_cockpit(self):
		self.bind(BOUND, "Operator")
		base = _upd("/me")
		start_group = _upd("/start BIND-ABCDEFGHJK")
		variants = [
			dataclasses.replace(base, is_bot=True),
			dataclasses.replace(base, chat_type="group"),
			dataclasses.replace(base, chat_type="supergroup"),
			dataclasses.replace(base, chat_type="channel", is_channel=True),
			dataclasses.replace(base, is_channel=True),
			dataclasses.replace(base, business_connection_id="bc-1"),
			dataclasses.replace(base, sender_business_bot="biz-bot"),
			dataclasses.replace(base, kind="channel_post"),
			dataclasses.replace(base, kind="business_message"),
			dataclasses.replace(start_group, chat_type="group"),
		]
		before, bindings_before = len(self.sent()), len(self.fx.table("Telegram Admin Binding"))
		with patch.object(ta, "get_binding", side_effect=AssertionError("binding looked up")):
			for update in variants:
				self.assertIsNone(ta.handle_message(self.gateway, self.adapter, update, cache=self.cache))
				self.assertIsNone(
					telegram_admin_hooks.handle_message(self.gateway, self.adapter, update, None)
				)
		self.assertEqual(len(self.sent()), before)
		self.assertEqual(len(self.fx.table("Telegram Admin Binding")), bindings_before)


class TestRunAsRestore(E2EBase):
	def test_run_as_restores_prior_user_when_body_raises(self):
		self.assertEqual(self.fx.session.user, "Guest")
		for exc in (ValueError("boom"), frappe.PermissionError("nope")):
			with self.assertRaises(type(exc)):
				with ta.run_as(BOUND):
					self.assertEqual(self.fx.session.user, BOUND)
					raise exc
			self.assertEqual(self.fx.session.user, "Guest")

		with self.assertRaises(RuntimeError):
			with ta.run_as(BOUND):
				with ta.run_as(BOUND2):
					raise RuntimeError("inner")
		self.assertEqual(self.fx.session.user, "Guest")

	def test_command_and_workflow_errors_restore_user(self):
		self.bind(BOUND, "Operator")
		with patch.object(ta, "_resolve_doctype", side_effect=RuntimeError("db down")):
			self.send("/find Leave Application x")
		self.assertTrue(self.last_text().startswith("Error:"))
		self.assertEqual(self.fx.session.user, "Guest")

		self.fx.apply_error = RuntimeError("workflow exploded")
		self.send("/approvals")
		self.press(self.button("Approve LA-1"))
		self.press(self.button("Confirm"))
		self.assertEqual(self.fx.session.user, "Guest")
		self.assertTrue(self.adapter.sender.edit_message_text.call_args.args[2].startswith("Failed:"))
		self.assertEqual(self.audit()[-1]["result"], "error")
		self.assertEqual(self.fx.applied, [])


class TestAtomicityUnderThreads(unittest.TestCase):
	THREADS = 64

	def _race(self, fn):
		barrier = threading.Barrier(self.THREADS)
		results, lock = [], threading.Lock()

		def worker():
			barrier.wait()
			try:
				out = fn()
			except Exception as exc:  # noqa: BLE001 - captured for counting
				out = exc
			with lock:
				results.append(out)

		threads = [threading.Thread(target=worker) for _ in range(self.THREADS)]
		for t in threads:
			t.start()
		for t in threads:
			t.join()
		return results

	def test_rate_limit_exact_with_lock_guarded_cache(self):
		cache = ta.MemCache()
		now = time.time()
		res = self._race(lambda: ta.check_rate("u:1", 30, 60, cache=cache, now=now))
		self.assertEqual(sum(1 for r in res if r is True), 30)

	def test_rate_limit_exact_with_atomic_counter(self):
		cache = AtomicCache()
		now = time.time()
		res = self._race(lambda: ta.check_rate("u:2", 30, 60, cache=cache, now=now))
		self.assertEqual(sum(1 for r in res if r is True), 30)

	def test_bind_code_redeemed_exactly_once(self):
		cache = AtomicCache()
		code = ta.mint_bind_code(BOUND, GW, "Viewer", cache=cache)
		res = self._race(lambda: ta.consume_bind_code("BIND-" + code, GW, cache=cache))
		self.assertEqual(sum(1 for r in res if r), 1)

	def test_nonce_consumed_exactly_once(self):
		cache = AtomicCache()
		nonce = ta.issue_nonce(TG, CHAT, ACTION, cache=cache, now=time.time())
		res = self._race(lambda: ta.consume_nonce(nonce, TG, CHAT, cache=cache, now=time.time()))
		self.assertEqual(sum(1 for r in res if isinstance(r, dict)), 1)


if __name__ == "__main__":
	unittest.main()
