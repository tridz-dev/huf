"""Teams two-way link confirmation, end to end through the real modules.

confirm_teams_link -> send_confirmation -> (captured outbox card) -> card click through
teams_actions.pre_ingest_card_action -> Pending flips to Linked only for the same principal.
Only persistence (an in-memory db), the outbox enqueue and the cache are faked.
"""

import ast
import copy
import importlib
import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import hooks  # noqa: E402
from huf.ai.gateways.teams.messaging import cards  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"
TENANT = "00000000-0000-0000-0000-00000000aaaa"
AAD = "00000000-0000-0000-0000-0000000000u1"
AAD2 = "00000000-0000-0000-0000-0000000000u2"
CONV = "a:1personalchat"
SVC = "https://smba.trafficmanager.net/amer/"
NOW = datetime(2026, 1, 1, 12, 0, 0)
GW = SimpleNamespace(name="gw1", provider="Microsoft Teams")


class Row(dict):
	__getattr__ = dict.get


class Perm(Exception):
	pass


class Cache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def delete_value(self, k):
		self.d.pop(k, None)


class World:
	def __init__(self):
		self.links, self.sessions, self.outbox = {}, {}, []
		self.lock = threading.Lock()
		self.cursor = SimpleNamespace(rowcount=0)
		self.cache = Cache()
		self.user = "alice@x.com"
		self.local = SimpleNamespace(conf={"encryption_key": "k"}, gateway_response_override=None)
		self.personal_ref = {
			"name": "REF1", "conversation_id": CONV, "service_url": SVC, "tenant_id": TENANT,
		}
		self.n = 0

	# --- db
	def _match(self, row, filters):
		return all(row.get(k) == v for k, v in filters.items())

	def get_value(self, dt, filters, fields=None, as_dict=False):
		if dt == "User":
			return {"enabled": 1, "full_name": "Alice A"}.get(fields if isinstance(fields, str) else "enabled")
		table = self.links if dt == "Gateway Identity Link" else self.sessions
		if isinstance(filters, str):
			row = table.get(filters)
		else:
			row = next((r for r in table.values() if self._match(r, filters)), None)
		if row is None:
			return None
		if isinstance(fields, str):
			return row.get(fields)
		return Row({k: row.get(k) for k in fields})

	def set_value(self, dt, name, field, value=None, update_modified=None):
		table = self.links if dt == "Gateway Identity Link" else self.sessions
		table[name].update(field if isinstance(field, dict) else {field: value})

	def get_all(self, dt, filters=None, pluck=None, **k):
		return [r["name"] for r in self.links.values() if self._match(r, filters or {})]

	def sql(self, query, params=()):
		n = 0
		with self.lock:
			if "SET state='Decided'" in query:
				actor, name, now = params
				r = self.sessions.get(name)
				if r and r["state"] == "Open" and r["expires_at"] > now:
					r["state"], r["decided_by"], n = "Decided", actor, 1
			elif "SET state='Expired'" in query:
				r = self.sessions.get(params[0])
				if r and r["state"] == "Open":
					r["state"], n = "Expired", 1
		self.cursor = SimpleNamespace(rowcount=n)

	@property
	def _cursor(self):
		return self.cursor

	def get_doc(self, values):
		w = self

		class D:
			name = None

			def insert(self, ignore_permissions=False):
				w.n += 1
				if values["doctype"] == "Gateway Identity Link":
					self.name = f"L{w.n}"
					w.links[self.name] = {"name": self.name, **values}
				else:
					self.name = f"S{w.n}"
					w.sessions[self.name] = {"name": self.name, **values}
				return self

		return D()


class _Throw(Exception):
	pass


@pytest.fixture
def w(monkeypatch):
	import frappe as real_frappe

	for name in ("actions", "identity_confirm"):
		sys.modules.pop(f"huf.ai.gateways.teams.{name}", None)
		pkg = sys.modules.get("huf.ai.gateways.teams")
		if pkg is not None and hasattr(pkg, name):
			delattr(pkg, name)
	hooks.clear()
	ta = importlib.import_module("huf.ai.gateways.teams.actions")
	tic = importlib.import_module("huf.ai.gateways.teams.identity_confirm")
	ti = importlib.import_module("huf.ai.gateways.teams.identity")
	world = World()
	world.ta, world.tic, world.ti = ta, tic, ti
	counter = iter(range(1000))
	fake = SimpleNamespace(
		db=world, local=world.local, cache=lambda: world.cache,
		get_doc=world.get_doc, get_all=world.get_all,
		session=SimpleNamespace(user="alice@x.com"),
		generate_hash=lambda length=10: f"nonce{next(counter)}",
		get_roles=lambda: [], log_error=lambda *a, **k: None, get_traceback=lambda: "tb",
		PermissionError=Perm, ValidationError=_Throw,
		utils=SimpleNamespace(
			now=lambda: NOW, now_datetime=lambda: NOW, get_url=lambda: "https://huf.test",
			add_to_date=lambda d, seconds=0: d + timedelta(seconds=seconds),
			get_datetime=lambda v: v,
		),
	)

	def throw(msg, exc=None):
		raise (exc or _Throw)(msg)

	fake.throw = throw
	for mod in (ta, tic, ti):
		monkeypatch.setattr(mod, "frappe", fake)
	monkeypatch.setattr(ti, "_", lambda s: s)
	monkeypatch.setattr(ti, "_cache", lambda: world.cache)
	monkeypatch.setattr(ta, "_tenant_ok", lambda gw, t: t == TENANT)
	monkeypatch.setattr(tic.teams_refs, "get_personal_reference", lambda g, t, a: world.personal_ref)
	monkeypatch.setattr(tic.teams_outbox, "enqueue", lambda *a, **k: world.outbox.append(a) or "OUT")
	world.fake = fake
	yield world
	hooks.clear()


def start_link(w, aad=AAD, user="alice@x.com"):
	w.fake.session.user = user
	tok = w.ti.create_link_token("gw1", TENANT, aad, "Eve The CEO")
	return w.ti.confirm_teams_link(tok)


def click(w, verb=cards.VERB_APPROVE, aad=AAD, tenant=TENANT, conv=CONV, session=None):
	act = copy.deepcopy(json.loads((FIXTURES / "invoke_card_action.json").read_text()))
	act["from"]["aadObjectId"] = aad
	act["conversation"]["tenantId"] = tenant
	act["channelData"]["tenant"]["id"] = tenant
	act["conversation"]["id"] = conv
	act["value"]["action"]["verb"] = verb
	act["value"]["action"]["data"] = {"session": session or next(iter(w.sessions))}
	act["huf_kind"] = "card_action"
	w.local.gateway_response_override = None
	assert w.ta.pre_ingest_card_action(GW, {"raw_payload": act}) is False
	return json.loads(w.local.gateway_response_override["body"])


def link_state(w):
	return next(iter(w.links.values()))["state"]


def test_confirm_creates_pending_and_queues_card_to_personal_chat(w):
	assert start_link(w) == {"linked": False, "pending": True, "user": "alice@x.com"}
	assert link_state(w) == "Pending"
	assert w.ti.resolve_user("gw1", TENANT, AAD) is None
	gateway, snapshot, kind, payload, key = w.outbox[0]
	assert gateway == "gw1" and kind == "card"
	assert snapshot["conversation_id"] == CONV and snapshot["tenant_id"] == TENANT
	card_json = json.dumps(payload["activity"])
	assert "Did you just connect your Teams account to Huf user Alice A?" in card_json
	assert "If not, ignore this." in card_json and "Yes" in card_json
	session = next(iter(w.sessions.values()))
	assert session["kind"] == "idlink" and session["tenant_id"] == TENANT
	assert json.loads(session["payload"]) == {"link": next(iter(w.links))}
	assert payload["action_session"] == session["name"]
	assert "Eve The CEO" not in card_json  # attacker-chosen label is never in the card


def test_same_principal_yes_links(w):
	start_link(w)
	body = click(w)
	assert "now connected" in json.dumps(body)
	assert link_state(w) == "Linked"
	assert w.ti.resolve_user("gw1", TENANT, AAD) == "alice@x.com"


def test_other_principal_refused_and_nothing_changes(w):
	start_link(w)
	body = click(w, aad=AAD2)
	assert "no longer valid" in json.dumps(body)
	assert link_state(w) == "Pending" and next(iter(w.sessions.values()))["state"] == "Open"
	assert w.ti.resolve_user("gw1", TENANT, AAD) is None


def test_other_tenant_same_aad_refused(w):
	start_link(w)
	click(w, tenant="00000000-0000-0000-0000-00000000ffff")
	assert link_state(w) == "Pending"


def test_no_revokes(w):
	start_link(w)
	body = click(w, verb=cards.VERB_REJECT)
	assert "nothing was connected" in json.dumps(body)
	assert link_state(w) == "Revoked" and w.ti.resolve_user("gw1", TENANT, AAD) is None


def test_second_click_cannot_flip_after_decision(w):
	start_link(w)
	click(w, verb=cards.VERB_REJECT)
	click(w, verb=cards.VERB_APPROVE)
	assert link_state(w) == "Revoked"


def test_no_personal_reference_revokes_pending(w, monkeypatch):
	monkeypatch.setattr(w.tic.teams_refs, "get_personal_reference", lambda g, t, a: None)
	with pytest.raises(Exception):
		start_link(w)
	assert link_state(w) == "Revoked" and w.outbox == []
	assert w.ti.resolve_user("gw1", TENANT, AAD) is None


def test_outbox_failure_revokes_pending(w, monkeypatch):
	def boom(*a, **k):
		raise RuntimeError("db down")

	monkeypatch.setattr(w.tic.teams_outbox, "enqueue", boom)
	with pytest.raises(Exception):
		start_link(w)
	assert link_state(w) == "Revoked"


def test_new_attempt_supersedes_older_pending(w):
	start_link(w)
	w.local.conf = {"encryption_key": "k"}
	start_link(w)
	states = sorted(r["state"] for r in w.links.values())
	assert states == ["Pending", "Revoked"]


def test_handler_registered_explicitly_and_only_for_idlink(w):
	assert w.ta._KIND_HANDLERS.get("idlink") is w.tic.handle_click
	src = Path("huf/ai/gateways/teams/identity_confirm.py").read_text()
	tree = ast.parse(src)
	calls = [n for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
	assert any(getattr(c.value.func, "id", "") == "register" for c in calls)  # register() at import
