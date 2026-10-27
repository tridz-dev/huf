"""Unit tests for huf/ai/gateways/bindings_api.py (frappe is a MagicMock stub)."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

_original_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda fn: fn)
sys.modules.pop("huf.ai.gateways.bindings_api", None)
try:
	from huf.ai.gateways import bindings_api as ba  # noqa: E402
finally:
	frappe.whitelist = _original_whitelist

from huf.ai.gateways.slack_api import SlackApiError  # noqa: E402

TOKEN = "xoxb-SECRET-TOKEN-999"


class PermErr(Exception):
	pass


class ValErr(Exception):
	pass


class NotFound(Exception):
	pass


def _throw(msg, exc=None, *a, **k):
	raise (exc or Exception)(msg)


class Db:
	def __init__(self, existing=(), gateway_of=None):
		self.existing = set(existing)
		self.gateway_of = gateway_of or {}
		self.sets = []
		self.fail_on = None
		self.rolled_back = False

	def exists(self, doctype, name=None):
		return (doctype, name) in self.existing

	def get_value(self, doctype, name, field):
		return self.gateway_of.get(name)

	def set_value(self, doctype, name, field, value):
		if self.fail_on == name:
			raise RuntimeError("boom")
		self.sets.append((name, value))

	def rollback(self):
		self.rolled_back = True


@pytest.fixture(autouse=True)
def env(monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw)
	monkeypatch.setattr(frappe, "PermissionError", PermErr, raising=False)
	monkeypatch.setattr(frappe, "ValidationError", ValErr, raising=False)
	monkeypatch.setattr(frappe, "DoesNotExistError", NotFound, raising=False)
	monkeypatch.setattr(ba, "_", lambda s: s)
	db = Db(existing={("Gateway", "gw"), ("Agent", "Support"), ("Flow Definition", "Flow1")})
	monkeypatch.setattr(frappe, "db", db, raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: False)
	gw = SimpleNamespace(name="gw", provider="Slack", execution_user=None, integration_settings="IS")
	monkeypatch.setattr(frappe, "get_doc", MagicMock(return_value=gw))
	monkeypatch.setattr(frappe, "get_all", MagicMock(return_value=[]))
	monkeypatch.setattr(frappe, "delete_doc", MagicMock())
	return SimpleNamespace(db=db, gw=gw)


def good(**over):
	b = {"match_type": "Room or channel", "match_value": "C1", "target_type": "Agent", "agent": "Support"}
	b.update(over)
	return b


# ---- permissions ----
def test_denied_without_role_or_write(monkeypatch):
	monkeypatch.setattr(frappe, "get_roles", lambda: ["Guest"])
	with pytest.raises(PermErr):
		ba.save_binding("gw", good())
	with pytest.raises(PermErr):
		ba.list_bindings("gw")


def test_gateway_write_permission_allows(monkeypatch):
	monkeypatch.setattr(frappe, "get_roles", lambda: ["Guest"])
	monkeypatch.setattr(frappe, "has_permission", lambda dt, pt, doc=None: pt == "write" and doc == "gw")
	monkeypatch.setattr(ba, "_ordered_bindings", lambda g: [])
	assert ba.reorder_bindings("gw", []) == []


def test_unknown_gateway(env):
	with pytest.raises(NotFound):
		ba.list_bindings("nope")


def test_delete_checks_permission_on_owning_gateway(env, monkeypatch):
	env.db.gateway_of = {"B1": "gw"}
	monkeypatch.setattr(frappe, "get_roles", lambda: ["Guest"])
	with pytest.raises(PermErr):
		ba.delete_binding("B1")
	frappe.delete_doc.assert_not_called()


def test_delete_ok_and_missing(env):
	env.db.gateway_of = {"B1": "gw"}
	assert ba.delete_binding("B1") == {"deleted": "B1"}
	with pytest.raises(NotFound):
		ba.delete_binding("B2")


# ---- validation ----
def test_any_conversation_rejects_value():
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(match_type="Any conversation"))


def test_any_conversation_ok_without_value():
	out = ba.validate_binding_payload(good(match_type="Any conversation", match_value=""))
	assert out["match_value"] == ""


@pytest.mark.parametrize("mt", ["Direct message", "Room or channel", "Thread", "Sender"])
def test_value_required(mt):
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(match_type=mt, match_value="  "))
	assert ba.validate_binding_payload(good(match_type=mt, match_value=" X1 "))["match_value"] == "X1"


def test_bad_match_type():
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(match_type="Fuzzy"))


def test_target_validation():
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(target_type=""))
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(agent=""))
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(agent="Ghost"))
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(flow="Flow1"))
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(target_type="Flow", agent="", flow="Ghost"))
	out = ba.validate_binding_payload(good(target_type="Flow", agent="", flow="Flow1"))
	assert out["flow"] == "Flow1" and out["agent"] is None


def test_agent_access_for_run_as_user(env, monkeypatch):
	env.gw.execution_user = "bot@x.com"
	mod = SimpleNamespace(check_agent_access=lambda agent, user, for_execution: False)
	monkeypatch.setitem(sys.modules, "huf.ai.agent_access", mod)
	with pytest.raises(ValErr):
		ba.validate_binding_payload(good(), env.gw)
	mod.check_agent_access = lambda agent, user, for_execution: True
	assert ba.validate_binding_payload(good(), env.gw)["agent"] == "Support"


# ---- save ----
def test_create_assigns_next_priority(env, monkeypatch):
	monkeypatch.setattr(frappe, "get_all", MagicMock(return_value=[1, 4]))
	doc = MagicMock()
	doc.get.side_effect = lambda f: {"priority": 5}.get(f)
	monkeypatch.setattr(frappe, "get_doc", MagicMock(side_effect=lambda *a, **k: env.gw if a == ("Gateway", "gw") else doc))
	ba.save_binding("gw", good())
	payload = frappe.get_doc.call_args_list[-1].args[0]
	assert payload["priority"] == 5 and payload["gateway"] == "gw"
	doc.save.assert_called_once()


def test_update_rejects_binding_of_other_gateway(env):
	env.db.gateway_of = {"B9": "other"}
	with pytest.raises(NotFound):
		ba.save_binding("gw", good(name="B9"))


def test_update_applies_values(env, monkeypatch):
	env.db.gateway_of = {"B1": "gw"}
	doc = MagicMock()
	monkeypatch.setattr(frappe, "get_doc", MagicMock(side_effect=lambda *a, **k: env.gw if a == ("Gateway", "gw") else doc))
	ba.save_binding("gw", good(name="B1", is_enabled=0))
	assert doc.update.call_args.args[0]["is_enabled"] == 0
	doc.save.assert_called_once()


# ---- reorder ----
def test_reorder_writes_gapless(env, monkeypatch):
	monkeypatch.setattr(ba, "_ordered_bindings", lambda g: [{"name": "A"}, {"name": "B"}, {"name": "C"}])
	ba.reorder_bindings("gw", '["C", "A", "B"]')
	assert env.db.sets == [("C", 1), ("A", 2), ("B", 3)]


@pytest.mark.parametrize("order", [["A", "A", "B"], ["A", "B"], ["A", "B", "C", "D"], "notalist"])
def test_reorder_rejects_bad_sets_without_writes(env, monkeypatch, order):
	monkeypatch.setattr(ba, "_ordered_bindings", lambda g: [{"name": "A"}, {"name": "B"}, {"name": "C"}])
	with pytest.raises(ValErr):
		ba.reorder_bindings("gw", order)
	assert env.db.sets == []


def test_reorder_rolls_back_on_failure(env, monkeypatch):
	monkeypatch.setattr(ba, "_ordered_bindings", lambda g: [{"name": "A"}, {"name": "B"}])
	env.db.fail_on = "B"
	with pytest.raises(RuntimeError):
		ba.reorder_bindings("gw", ["A", "B"])
	assert env.db.rolled_back


# ---- test_route ----
def test_test_route_read_only_and_filters_context(env, monkeypatch):
	gs = SimpleNamespace(preview_gateway_route=MagicMock(return_value={"status": "Queued"}))
	monkeypatch.setattr("huf.ai.gateway_service", gs, raising=False)
	monkeypatch.setitem(sys.modules, "huf.ai.gateway_service", gs)
	out = ba.test_route("gw", {"conversation_id": " C1 ", "evil": "x"})
	assert out == {"status": "Queued"}
	gs.preview_gateway_route.assert_called_once_with("gw", {"conversation_id": "C1"})
	frappe.get_doc.assert_called_once()  # only the permission-check gateway load
	assert env.db.sets == []


def test_test_route_needs_permission(monkeypatch):
	monkeypatch.setattr(frappe, "get_roles", lambda: [])
	with pytest.raises(PermErr):
		ba.test_route("gw", {})


# ---- pickers ----
class FakeApi:
	def __init__(self, pages, err=None):
		self.pages, self.err, self.calls = pages, err, []

	def _page(self, cursor):
		self.calls.append(cursor)
		if self.err:
			raise self.err
		return self.pages[len(self.calls) - 1]

	def conversations_list(self, types, cursor=None, limit=200):
		return self._page(cursor)

	def users_list(self, cursor=None, limit=200):
		return self._page(cursor)


def use_api(monkeypatch, api):
	import huf.ai.gateways.slack_context as sc

	monkeypatch.setattr(sc, "get_slack_api", lambda gw: api)


def ch(i, **kw):
	return {"id": f"C{i}", "name": f"chan{i}", "is_member": True, **kw}


def test_channel_normalisation(monkeypatch):
	api = FakeApi([{"channels": [ch(1), ch(2, is_private=True, is_member=False), ch(3, is_archived=True)]}])
	use_api(monkeypatch, api)
	out = ba.list_slack_channels("gw")
	assert out["items"] == [
		{"id": "C1", "label": "#chan1", "kind": "public", "is_member": True},
		{"id": "C2", "label": "#chan2", "kind": "private", "is_member": False},
	]
	assert out["next_cursor"] is None and out["error"] is None


def test_channel_query_filter_server_side(monkeypatch):
	use_api(monkeypatch, FakeApi([{"channels": [ch(1), {"id": "C9", "name": "support"}]}]))
	out = ba.list_slack_channels("gw", query="#SUPP")
	assert [i["id"] for i in out["items"]] == ["C9"]


def test_channel_pagination_cursor_returned(monkeypatch):
	pages = [{"channels": [ch(i) for i in range(60)], "response_metadata": {"next_cursor": "NEXT"}}]
	api = FakeApi(pages)
	use_api(monkeypatch, api)
	out = ba.list_slack_channels("gw", cursor="START")
	assert api.calls == ["START"] and len(out["items"]) == 60 and out["next_cursor"] == "NEXT"


def test_page_scan_cap(monkeypatch):
	pages = [{"channels": [], "response_metadata": {"next_cursor": f"c{i}"}} for i in range(10)]
	api = FakeApi(pages)
	use_api(monkeypatch, api)
	out = ba.list_slack_channels("gw", query="zzz")
	assert len(api.calls) == ba.PICKER_MAX_PAGES and out["next_cursor"] == "c4"


def test_users_normalisation_skips_bots_deleted(monkeypatch):
	members = [
		{"id": "U1", "name": "ann", "real_name": "Ann A", "profile": {"display_name": "annie"}},
		{"id": "U2", "name": "bob", "real_name": "Bob"},
		{"id": "U3", "name": "bot", "is_bot": True},
		{"id": "U4", "name": "gone", "deleted": True},
		{"id": "USLACKBOT", "name": "slackbot"},
	]
	use_api(monkeypatch, FakeApi([{"members": members}]))
	out = ba.list_slack_users("gw")
	assert out["items"] == [
		{"id": "U1", "label": "annie", "kind": "user", "is_member": True},
		{"id": "U2", "label": "Bob", "kind": "user", "is_member": True},
	]


def test_missing_scope_message_has_no_token(monkeypatch):
	use_api(monkeypatch, FakeApi([], err=SlackApiError("conversations.list", "missing_scope", 200)))
	out = ba.list_slack_channels("gw")
	assert out["items"] == [] and "channels:read" in out["error"]
	assert TOKEN not in str(out) and "conversations.list" not in out["error"]
	use_api(monkeypatch, FakeApi([], err=SlackApiError("users.list", "missing_scope")))
	assert "users:read" in ba.list_slack_users("gw")["error"]


def test_generic_slack_error_is_plain(monkeypatch):
	use_api(monkeypatch, FakeApi([], err=SlackApiError("users.list", "fatal_error", 500)))
	assert "fatal_error" not in ba.list_slack_users("gw")["error"]


def test_no_token_configured(monkeypatch):
	import huf.ai.gateways.slack_context as sc

	def boom(gw):
		raise ValueError("Slack gateway has no bot token configured")

	monkeypatch.setattr(sc, "get_slack_api", boom)
	out = ba.list_slack_channels("gw")
	assert out["items"] == [] and "bot token" in out["error"]


def test_non_slack_provider_not_supported(env):
	env.gw.provider = "Telegram"
	for fn in (ba.list_slack_channels, ba.list_slack_users):
		out = fn("gw")
		assert out["supported"] is False and out["items"] == [] and "only available" in out["error"]


def test_pickers_need_permission(monkeypatch):
	monkeypatch.setattr(frappe, "get_roles", lambda: [])
	with pytest.raises(PermErr):
		ba.list_slack_users("gw")
