"""Two-way Slack confirmation of self-links (huf.ai.gateways.identity_confirm)."""

from __future__ import annotations

import importlib
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "testing"))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import frappe  # noqa: E402
import pytest  # noqa: E402

TARGETS = ("huf.ai.gateways.slack_interactivity", "huf.ai.gateways.identity_confirm", "huf.ai.gateways.identity")


def _load_isolated():
	touched, stubs, attrs = {}, {}, {}
	if "frappe.rate_limiter" not in sys.modules:
		rl = types.ModuleType("frappe.rate_limiter")
		rl.rate_limit = lambda *a, **k: (lambda fn: fn)
		stubs["frappe.rate_limiter"] = rl
	pkg = sys.modules.get("huf.ai.gateways")
	for name in TARGETS:
		touched[name] = sys.modules.pop(name, None)
		short = name.rsplit(".", 1)[-1]
		if pkg is not None and hasattr(pkg, short):
			attrs[short] = getattr(pkg, short)
			delattr(pkg, short)
	sys.modules.update(stubs)
	orig = frappe.whitelist
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	try:
		ic = importlib.import_module("huf.ai.gateways.identity_confirm")
		si = importlib.import_module("huf.ai.gateways.slack_interactivity")
		ident = importlib.import_module("huf.ai.gateways.identity")
	finally:
		frappe.whitelist = orig
		for name in stubs:
			sys.modules.pop(name, None)
		for name, old in touched.items():
			sys.modules.pop(name, None)
			if old is not None:
				sys.modules[name] = old
		if pkg is not None:
			for short in [n.rsplit(".", 1)[-1] for n in TARGETS]:
				if hasattr(pkg, short):
					delattr(pkg, short)
			for short, old_attr in attrs.items():
				setattr(pkg, short, old_attr)
	return ic, si, ident


ic, si, ident = _load_isolated()


class FakeDb:
	def __init__(self, rows):
		self.rows = rows
		self.sets = []

	def get_value(self, dt, name, fields=None, as_dict=False):
		if dt == "User":
			return "Alice Example"
		row = self.rows.get(name)
		return SimpleNamespace(**row) if row else None

	def set_value(self, dt, name, field, value=None):
		vals = field if isinstance(field, dict) else {field: value}
		self.rows[name].update(vals)
		self.sets.append((name, vals))


@pytest.fixture
def env(monkeypatch):
	rows = {"L1": {"name": "L1", "gateway": "GW", "team_id": "T1", "external_id": "U1",
		"state": "Pending", "user": "alice@x.com"}}
	monkeypatch.setattr(frappe, "db", FakeDb(rows), raising=False)
	monkeypatch.setattr(frappe.utils, "now", lambda: "2026-01-01 00:00:00", raising=False)
	monkeypatch.setattr(ident, "key_lock", lambda *a: "k")
	monkeypatch.setattr(ident, "release_key_lock", lambda k: None)
	monkeypatch.setattr(ident, "_find_link", lambda g, t, e: None)
	monkeypatch.setattr(ident, "_usable", lambda u, s=None: True)
	return rows


GW = SimpleNamespace(name="GW", provider="Slack")


def session(choice="approve", slack="U1", team="T1", link="L1"):
	return {"intended_slack_user": slack, "payload": {"link": link, "team_id": team}, "choice": choice}


def payload(user="U1", team="T1"):
	return {"user": {"id": user}, "team": {"id": team}}


def test_handler_registered_without_actor_requirement():
	assert si.get_action_handler.__name__  # registry present
	assert si._HANDLERS["idlink:"] is ic.handle_click
	assert si._actor_optional("idlink:abc") is True
	assert si._actor_optional("approval:x") is False


def test_send_confirmation_dm_with_buttons(monkeypatch):
	created = {}
	monkeypatch.setattr(si, "create_action_session",
		lambda gw, kind, payload, **kw: created.update(kind=kind, payload=payload, **kw) or "S1")
	dm = []
	monkeypatch.setattr(ic, "_send_dm", lambda gw, ext, text, blocks: dm.append((ext, text, blocks)))
	monkeypatch.setattr(frappe, "db", FakeDb({}), raising=False)
	assert ic.send_confirmation(GW, "L1", "T1", "U1", "alice@x.com") == "S1"
	assert created["kind"] == "idlink:" and created["intended_slack_user"] == "U1"
	assert created["payload"]["link"] == "L1"
	ext, text, blocks = dm[0]
	assert ext == "U1" and "Alice Example" in repr(blocks) and "If not, ignore this." in repr(blocks)
	assert "Yes, link it" in repr(blocks) and "No" in repr(blocks)


def test_yes_by_same_slack_user_links(env):
	out = ic.handle_click(GW, session(), None, payload())
	assert out["text"] == ic.MSG_LINKED
	assert env["L1"]["state"] == "Linked"


def test_no_revokes(env):
	out = ic.handle_click(GW, session("reject"), None, payload())
	assert out["text"] == ic.MSG_REVOKED and env["L1"]["state"] == "Revoked"


def test_different_slack_user_cannot_confirm(env):
	out = ic.handle_click(GW, session(), None, payload(user="U2"))
	assert out["text"] == ic.MSG_INVALID and env["L1"]["state"] == "Pending"


def test_wrong_team_cannot_confirm(env):
	out = ic.handle_click(GW, session(), None, payload(team="T2"))
	assert out["text"] == ic.MSG_INVALID and env["L1"]["state"] == "Pending"


def test_link_for_other_person_not_flipped(env):
	env["L1"]["external_id"] = "U9"
	out = ic.handle_click(GW, session(), None, payload())
	assert out["text"] == ic.MSG_INVALID and env["L1"]["state"] == "Pending"


def test_already_linked_elsewhere_revokes_pending(env, monkeypatch):
	monkeypatch.setattr(ident, "_find_link", lambda g, t, e: SimpleNamespace(name="L0", user="bob@x.com"))
	out = ic.handle_click(GW, session(), None, payload())
	assert out["text"] == ic.MSG_INVALID and env["L1"]["state"] == "Revoked"


def test_non_pending_not_flipped(env):
	env["L1"]["state"] = "Revoked"
	out = ic.handle_click(GW, session(), None, payload())
	assert out["text"] == ic.MSG_INVALID and env["L1"]["state"] == "Revoked"
