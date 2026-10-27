import importlib
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import frappe  # noqa: E402
import pytest  # noqa: E402

_STUBS = ("frappe.rate_limiter", "cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
		"cryptography.hazmat.primitives.ciphers", "cryptography.hazmat.primitives.padding",
		"cryptography.hazmat.backends")
_added = []
for _name in _STUBS:
	if _name in sys.modules:
		continue
	try:
		importlib.import_module(_name)
		continue
	except Exception:
		pass
	_m = types.ModuleType(_name)
	_m.__path__ = []
	_m.rate_limit = lambda *a, **k: (lambda f: f)
	_m.__getattr__ = lambda attr: MagicMock(name=attr)
	sys.modules[_name] = _m
	_added.append(_name)

_had_gs = "huf.ai.gateway_service" in sys.modules
_had_health = "huf.ai.gateways.health" in sys.modules
_orig_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda fn: fn)
try:
	gs = importlib.import_module("huf.ai.gateway_service")
	health = importlib.import_module("huf.ai.gateways.health")
finally:
	frappe.whitelist = _orig_whitelist
	for _name in _added:
		sys.modules.pop(_name, None)
	if not _had_gs:
		sys.modules.pop("huf.ai.gateway_service", None)
	if not _had_health:
		sys.modules.pop("huf.ai.gateways.health", None)

from huf.ai.gateways import hooks  # noqa: E402

NOW = datetime(2026, 10, 27, 12, 0, 0)


class D(dict):
	__getattr__ = dict.get


class PermErr(Exception):
	pass


class MissingErr(Exception):
	pass


def _throw(msg, exc=Exception):
	raise exc(msg)


@pytest.fixture(autouse=True)
def env(monkeypatch):
	hooks.clear()
	health.register_hooks()
	monkeypatch.setattr(health, "_now", lambda: NOW)
	db = MagicMock(name="db")
	cache = MagicMock(name="cache")
	cache.get_value.return_value = None
	monkeypatch.setattr(frappe, "db", db, raising=False)
	monkeypatch.setattr(health, "_cache", lambda: cache)
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "PermissionError", PermErr, raising=False)
	monkeypatch.setattr(frappe, "DoesNotExistError", MissingErr, raising=False)
	monkeypatch.setattr(frappe, "ValidationError", ValueError, raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda *a, **k: ["System Manager"], raising=False)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True, raising=False)
	monkeypatch.setattr(health, "_", lambda s: s)
	monkeypatch.setattr(sys.modules["huf.ai"], "gateway_service", gs, raising=False)
	yield SimpleNamespace(db=db, cache=cache)
	hooks.clear()


GW = SimpleNamespace(name="slack-main", provider="Slack")
EV = SimpleNamespace(name="GEV-1")


def written(env_):
	return [c.args for c in env_.db.set_value.call_args_list]


# ------------------------------------------------------------------ hooks
def test_hooks_registered_for_all_providers(env):
	for hook in (hooks.ON_EVENT_RECEIVED, hooks.ON_RUN_FAILURE, hooks.ON_EVENT_REJECTED, hooks.ON_RUN_SUCCESS):
		assert hooks._matching(hook, (SimpleNamespace(provider="Telegram"),))


def test_event_received_sets_last_event_at(env):
	hooks.call_all(hooks.ON_EVENT_RECEIVED, GW, EV)
	env.db.set_value.assert_called_once_with("Gateway", "slack-main", "last_event_at", NOW, update_modified=False)


def test_event_received_throttled(env):
	env.cache.get_value.return_value = 1
	hooks.call_all(hooks.ON_EVENT_RECEIVED, GW, EV)
	env.db.set_value.assert_not_called()


def test_event_received_sets_throttle_key(env):
	hooks.call_all(hooks.ON_EVENT_RECEIVED, GW, EV)
	assert env.cache.set_value.call_args.kwargs["expires_in_sec"] == health.LAST_EVENT_THROTTLE_SECONDS


def test_event_received_never_raises(env):
	env.db.set_value.side_effect = RuntimeError("db down")
	health._on_event_received(GW, EV)


def test_run_failure_writes_last_error(env):
	hooks.call_all(hooks.ON_RUN_FAILURE, GW, EV, "agent", "boom")
	args = written(env)[0]
	assert args[:3] == ("Gateway", "slack-main", "last_error")
	assert args[3] == "2026-10-27 12:00:00 | run failed | GEV-1 | boom"


def test_error_truncated(env):
	health._on_run_failure(GW, EV, "agent", "x" * 5000)
	assert len(written(env)[0][3]) <= health.LAST_ERROR_MAX_CHARS


def test_error_redacted(env):
	health._on_run_failure(GW, EV, "agent", "bad xoxb-1234-abcd-efgh and Bearer abcdef123456 token=hunter22")
	msg = written(env)[0][3]
	assert "xoxb-1234" not in msg and "abcdef123456" not in msg and "hunter22" not in msg
	assert "[redacted]" in msg


def test_rejected_writes_with_status_and_reason(env):
	hooks.call_all(hooks.ON_EVENT_REJECTED, GW, EV, "Unrouted", "No enabled route matches this message")
	assert written(env)[0][3] == "2026-10-27 12:00:00 | unrouted | GEV-1 | No enabled route matches this message"


def test_rejected_empty_reason(env):
	health._on_event_rejected(GW, EV, "Rejected", "")
	assert "No reason recorded" in written(env)[0][3]


def test_success_clears_earlier_run_failure(env):
	env.db.get_value.return_value = "2026-10-27 11:00:00 | run failed | GEV-0 | boom"
	hooks.call_all(hooks.ON_RUN_SUCCESS, GW, EV, "agent", "ok")
	env.db.set_value.assert_called_once_with("Gateway", "slack-main", "last_error", None, update_modified=False)


def test_success_keeps_rejection_error(env):
	env.db.get_value.return_value = "2026-10-27 11:00:00 | rejected | GEV-0 | nope"
	health._on_run_success(GW, EV, "flow", "ok")
	env.db.set_value.assert_not_called()


def test_success_keeps_future_failure(env):
	env.db.get_value.return_value = "2026-10-27 13:00:00 | run failed | GEV-0 | boom"
	health._on_run_success(GW, EV, "agent", "ok")
	env.db.set_value.assert_not_called()


def test_success_with_no_error_or_garbage(env):
	env.db.get_value.return_value = None
	health._on_run_success(GW, EV, "agent", "ok")
	env.db.get_value.return_value = "garbage"
	health._on_run_success(GW, EV, "agent", "ok")
	env.db.set_value.assert_not_called()


# ----------------------------------------------------------------- health
def _get_all_factory(events=None, runs=None):
	def get_all(doctype, **kw):
		if doctype == "Agent Run":
			return runs or []
		if kw.get("group_by"):
			since = kw["filters"]["received_at"][1]
			return [{"status": "Succeeded", "count": 3 if since == NOW - timedelta(hours=24) else 9},
				{"status": "Failed", "count": 1}]
		if "agent_run" in kw["fields"] and "name" not in kw["fields"]:
			return [{"agent_run": "AR-1", "flow_run": None}, {"agent_run": "AR-2", "flow_run": "FR-1"}]
		return events or []
	return get_all


def _setup_health(monkeypatch, env, events=None, runs=None):
	env.db.get_value.return_value = {"is_enabled": 1, "last_event_at": NOW, "last_error": "x token=abcdef123", "provider": "Slack"}
	monkeypatch.setattr(frappe, "get_all", _get_all_factory(events, runs), raising=False)


def test_health_permission_denied(monkeypatch, env):
	monkeypatch.setattr(frappe, "get_roles", lambda *a, **k: ["Guest"])
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: False)
	with pytest.raises(PermErr):
		health.get_gateway_health("slack-main")


def test_health_write_permission_allows(monkeypatch, env):
	monkeypatch.setattr(frappe, "get_roles", lambda *a, **k: ["Employee"])
	_setup_health(monkeypatch, env)
	assert health.get_gateway_health("slack-main")["gateway"] == "slack-main"


def test_health_unknown_gateway(monkeypatch, env):
	env.db.get_value.return_value = None
	with pytest.raises(MissingErr):
		health.get_gateway_health("nope")


def test_health_counts_status_and_redaction(monkeypatch, env):
	_setup_health(monkeypatch, env)
	out = health.get_gateway_health("slack-main")
	assert out["counts"]["24h"]["Succeeded"] == 3 and out["counts"]["7d"]["Succeeded"] == 9
	assert out["counts"]["7d"]["total"] == 10 and out["counts"]["24h"]["Queued"] == 0
	assert out["status"]["enabled"] is True and "abcdef123" not in out["status"]["last_error"]


def test_health_recent_events_shape_and_trim(monkeypatch, env):
	ev = [{"name": "GEV-1", "status": "Failed", "received_at": NOW, "sender_id": "U1", "conversation_id": "C1",
		"error_message": "e" * 1000 + " xoxb-123456", "agent_run": "AR-1", "flow_run": None,
		"target_type": "Agent", "target_agent": "bot", "target_flow": None}]
	_setup_health(monkeypatch, env, events=ev)
	row = health.get_gateway_health("slack-main")["recent_events"][0]
	assert row["target"] == "bot" and row["sender"] == "U1" and row["conversation"] == "C1"
	assert len(row["error_message"]) <= health.EVENT_ERROR_MAX_CHARS and "xoxb" not in row["error_message"]


def test_health_usage_aggregates_without_double_count(monkeypatch, env):
	runs = [{"name": "AR-1", "cost": 0.5, "total_tokens": 100, "input_tokens": 60, "output_tokens": 40},
		{"name": "AR-2", "cost": 0.25, "total_tokens": 50, "input_tokens": 30, "output_tokens": 20}]
	_setup_health(monkeypatch, env, runs=runs)
	usage = health.get_gateway_health("slack-main")["usage_7d"]
	assert usage["runs"] == 2 and usage["cost"] == 0.75 and usage["total_tokens"] == 150


def test_health_no_n_plus_one(monkeypatch, env):
	_setup_health(monkeypatch, env)
	calls = []
	base = frappe.get_all
	monkeypatch.setattr(frappe, "get_all", lambda dt, **kw: (calls.append(dt), base(dt, **kw))[1])
	health.get_gateway_health("slack-main")
	assert len(calls) <= 7


# --------------------------------------------------------------- diagnose
def _gateway(**kw):
	base = dict(name="slack-main", provider="Slack", is_enabled=1, execution_user="svc@x.com",
		integration_settings="IS-1", direct_policy="Allow list", room_policy="Allow list",
		room_sender_policy="Allow list", mention_required=0, default_target_type="Agent",
		default_agent="bot", default_flow=None)
	base.update(kw)
	return D(base)


def _setup_diag(monkeypatch, gateway=None, entries=(), bindings=(), event_over=None):
	event = SimpleNamespace(name="GEV-1", gateway="slack-main", sender_id="U1", conversation_id="D1",
		thread_id="", message_text="hi", status="Rejected", error_message="Sender is not approved",
		db_set=MagicMock(), insert=MagicMock(), save=MagicMock())
	for k, v in (event_over or {}).items():
		setattr(event, k, v)
	gw = gateway or _gateway()
	seen = []

	def get_doc(dt, name=None, *a, **k):
		seen.append((dt, name))
		return event if dt == "Gateway Event" else gw

	def get_all(dt, **kw):
		seen.append(("get_all", dt))
		return list(entries) if dt == "Gateway Access Entry" else list(bindings)

	monkeypatch.setattr(frappe, "get_doc", get_doc, raising=False)
	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	monkeypatch.setattr(gs, "_create_pairing_request", MagicMock(side_effect=AssertionError("side effect")))
	return event, seen


def _by(results):
	return {r["check"]: r for r in results}


def test_diagnose_permission_denied(monkeypatch, env):
	_setup_diag(monkeypatch)
	monkeypatch.setattr(frappe, "get_roles", lambda *a, **k: [])
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: False)
	with pytest.raises(PermErr):
		health.diagnose_event("GEV-1")


def test_diagnose_all_ok(monkeypatch, env):
	_setup_diag(monkeypatch, entries=["AE-1"], event_over={"status": "Succeeded", "error_message": ""})
	results = health.diagnose_event("GEV-1")
	assert [r["check"] for r in results][:2] == ["Gateway is turned on", "Run-as user is set"]
	assert all(r["ok"] for r in results) and all(r["how_to_fix"] == "" for r in results)


def test_diagnose_disabled(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(is_enabled=0))
	r = _by(health.diagnose_event("GEV-1"))
	assert not r["Gateway is turned on"]["ok"] and r["Gateway is turned on"]["how_to_fix"]
	assert not r["A route matches this message"]["ok"]


def test_diagnose_no_run_as_user(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(execution_user=None))
	assert not _by(health.diagnose_event("GEV-1"))["Run-as user is set"]["ok"]


def test_diagnose_no_credentials(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(integration_settings=None))
	assert not _by(health.diagnose_event("GEV-1"))["Credentials are connected"]["ok"]


def test_diagnose_direct_not_approved_and_pairing_no_request(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(direct_policy="Pairing"))
	r = _by(health.diagnose_event("GEV-1"))["Sender or channel is allowed"]
	assert not r["ok"] and "approved" in r["plain_language_explanation"]


def test_diagnose_room_not_approved(monkeypatch, env):
	_setup_diag(monkeypatch, event_over={"conversation_id": "C9"})
	r = _by(health.diagnose_event("GEV-1"))["Sender or channel is allowed"]
	assert not r["ok"] and "channel" in r["plain_language_explanation"]


def test_diagnose_room_mention_required(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(mention_required=1, room_policy="Open", room_sender_policy="Open"),
		event_over={"conversation_id": "C9"})
	r = _by(health.diagnose_event("GEV-1"))["Sender or channel is allowed"]
	assert not r["ok"] and "mention" in r["plain_language_explanation"]


def test_diagnose_room_open_ok(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(room_policy="Open", room_sender_policy="Open"),
		event_over={"conversation_id": "C9"})
	assert _by(health.diagnose_event("GEV-1"))["Sender or channel is allowed"]["ok"]


def test_diagnose_no_route_no_default(monkeypatch, env):
	_setup_diag(monkeypatch, gateway=_gateway(default_target_type=None, default_agent=None), entries=["AE"])
	r = _by(health.diagnose_event("GEV-1"))
	assert not r["A route matches this message"]["ok"] and not r["A default agent or flow is set"]["ok"]


def test_diagnose_binding_match(monkeypatch, env):
	b = D(name="B1", priority=1, match_type="Any conversation", match_value=None, target_type="Agent",
		agent="other", flow=None)
	_setup_diag(monkeypatch, gateway=_gateway(default_target_type=None, default_agent=None), entries=["AE"], bindings=[b])
	r = _by(health.diagnose_event("GEV-1"))
	assert r["A route matches this message"]["ok"] and r["A default agent or flow is set"]["ok"]


def test_diagnose_has_no_side_effects(monkeypatch, env):
	event, seen = _setup_diag(monkeypatch, gateway=_gateway(direct_policy="Pairing"))
	health.diagnose_event("GEV-1")
	env.db.set_value.assert_not_called()
	env.db.sql.assert_not_called()
	event.db_set.assert_not_called()
	event.insert.assert_not_called()
	event.save.assert_not_called()
	assert all(not isinstance(dt, dict) for dt, _n in seen)
	gs._create_pairing_request.assert_not_called()


def test_diagnose_output_has_no_secrets(monkeypatch, env):
	_setup_diag(monkeypatch, event_over={"error_message": "failed token=supersecret99 xoxb-111-222-333"})
	text = repr(health.diagnose_event("GEV-1"))
	assert "supersecret99" not in text and "xoxb-111" not in text


def test_user_visible_rejection_not_stored_as_admin_error(monkeypatch):
	import importlib

	health = importlib.import_module("huf.ai.gateways.health")
	hooks_mod = importlib.import_module("huf.ai.gateways.hooks")
	seen = {}
	monkeypatch.setattr(health, "_write_error", lambda gw, tag, ev, reason: seen.update(tag=tag, reason=reason))
	health._on_event_rejected(object(), object(), "Rejected", hooks_mod.USER_VISIBLE_PREFIX + "Open https://x/link?token=SECRET")
	assert "SECRET" not in seen["reason"] and seen["reason"] == health.USER_NOTICE_SUMMARY
