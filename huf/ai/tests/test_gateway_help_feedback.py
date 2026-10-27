"""Tests for the Slack help command and feedback buttons (huf.ai.gateways.help_feedback)."""

import json
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

from huf.ai.gateways import hooks as gw_hooks  # noqa: E402
import types  # noqa: E402

_saved_handlers = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}


def _load_isolated():
	"""Import slack_interactivity + help_feedback with stubbed heavy deps, then remove
	everything added to sys.modules and undo hook/action registrations (no leaked stubs)."""
	names = ("huf.ai.gateways.slack_interactivity", "huf.ai.gateways.help_feedback")
	touched = {n: sys.modules.pop(n, None) for n in names}
	stubs = {}
	if "frappe.rate_limiter" not in sys.modules:
		rl = types.ModuleType("frappe.rate_limiter")
		rl.rate_limit = lambda *a, **k: (lambda fn: fn)
		stubs["frappe.rate_limiter"] = rl
	if "huf.ai.gateway_service" not in sys.modules:
		gs = types.ModuleType("huf.ai.gateway_service")
		gs.ingest_gateway_event = MagicMock()
		stubs["huf.ai.gateway_service"] = gs
	sys.modules.update(stubs)
	orig = frappe.whitelist
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	try:
		from huf.ai.gateways import help_feedback as mod
		from huf.ai.gateways import slack_interactivity as ia_mod
	finally:
		frappe.whitelist = orig
		for n in stubs:
			sys.modules.pop(n, None)
		for n, old in touched.items():
			sys.modules.pop(n, None)
			if old is not None:
				sys.modules[n] = old
	return mod, ia_mod


hf, ia = _load_isolated()
REGISTERED = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
REGISTERED_ACTION = ia._HANDLERS.get("feedback:")
gw_hooks._HANDLERS.clear()
gw_hooks._HANDLERS.update(_saved_handlers)

ROOT = pathlib.Path(__file__).resolve().parents[2]


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v


class FakeDb:
	def __init__(self):
		self.values = {}
		self.set_calls = []
		self.bindings = []

	def get_value(self, dt, filt=None, fields=None, as_dict=False, **kw):
		key = filt if isinstance(filt, str) else None
		if dt == "Agent":
			row = self.values.get(("Agent", key))
			return SimpleNamespace(**row) if row and as_dict is False else (frappe._dict(row) if row else None)
		if dt == "Flow Definition":
			row = self.values.get(("Flow", key))
			return frappe._dict(row) if row else None
		return self.values.get((dt, fields))

	def set_value(self, *a, **k):
		self.set_calls.append(a)


@pytest.fixture
def env(monkeypatch):
	db = FakeDb()
	cache = FakeCache()
	api = MagicMock()
	api.post_message.return_value = {"ts": "9.9"}
	monkeypatch.setattr(frappe, "db", db, raising=False)
	monkeypatch.setattr(frappe, "cache", lambda: cache, raising=False)
	monkeypatch.setattr(frappe, "_dict", lambda d=None: SimpleNamespace(get=lambda k, dflt=None: (d or {}).get(k, dflt), **(d or {})), raising=False)
	monkeypatch.setattr(frappe, "get_all", lambda *a, **k: list(db.bindings), raising=False)
	monkeypatch.setattr(frappe, "log_error", MagicMock(), raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "tb", raising=False)
	monkeypatch.setattr(frappe, "session", SimpleNamespace(user="Administrator"), raising=False)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True, raising=False)
	monkeypatch.setattr("huf.ai.gateways.slack_context.get_slack_api", lambda g, **k: api)
	db.api = api
	db.cache = cache
	return db


def agent(db, name, desc="", disabled=0):
	db.values[("Agent", name)] = {"agent_name": name, "disabled": disabled, "description": desc}


def gw(**kw):
	d = dict(name="GW-1", provider="slack", is_enabled=1, default_target_type="Agent", default_agent="Sales",
		default_flow=None, show_feedback_buttons=0)
	d.update(kw)
	return SimpleNamespace(**d)


def ctx(text="help", **kw):
	d = {"sender_id": "U1", "conversation_id": "D1", "thread_id": "1.1", "message_text": text,
		"is_room": False, "mentioned": False}
	d.update(kw)
	return d


# ---- help triggers
@pytest.mark.parametrize("text", ["help", "HELP", "/help", "?", "What can you do", "  help  ", "what can you do?", "<@UBOT> help"])
def test_help_variants(text):
	assert hf.is_help_text(text)


@pytest.mark.parametrize("text", ["", "helpful", "help me with invoices", "what can you do for invoices", "??", "can you help"])
def test_non_help(text):
	assert not hf.is_help_text(text)


def test_help_answers_and_drops(env):
	agent(env, "Sales", "Answers sales questions")
	assert hf.pre_ingest_filter(gw(), ctx()) is False
	args = env.api.post_message.call_args
	assert args.args[0] == "D1" and args.kwargs["thread_ts"] == "1.1"
	assert "Sales" in args.kwargs["text"] and "Answers sales questions" in args.kwargs["text"]
	assert "mention me" in args.kwargs["text"] and "link" in args.kwargs["text"]


def test_non_help_passes_through(env):
	assert hf.pre_ingest_filter(gw(), ctx("how are sales")) is True
	env.api.post_message.assert_not_called()


def test_works_when_unlinked_and_starts_no_run(env, monkeypatch):
	agent(env, "Sales")
	monkeypatch.setattr(hf, "_linked_user", lambda g, s: None)
	started = MagicMock()
	monkeypatch.setitem(sys.modules, "huf.ai.agent.integration", SimpleNamespace(run_agent_sync=started))
	assert hf.pre_ingest_filter(gw(), ctx()) is False
	started.assert_not_called()
	assert "Sales" in env.api.post_message.call_args.kwargs["text"]


def test_room_without_mention_ignored(env):
	assert hf.pre_ingest_filter(gw(), ctx(is_room=True, mentioned=False)) is True
	env.api.post_message.assert_not_called()


def test_room_with_mention_answers(env):
	agent(env, "Sales")
	assert hf.pre_ingest_filter(gw(), ctx(is_room=True, mentioned=True, conversation_id="C1")) is False


def test_disabled_gateway_passes(env):
	assert hf.pre_ingest_filter(gw(is_enabled=0), ctx()) is True


def test_duplicate_mention_event_answered_once(env):
	agent(env, "Sales")
	hf.pre_ingest_filter(gw(), ctx())
	assert hf.pre_ingest_filter(gw(), ctx()) is False
	assert env.api.post_message.call_count == 1


def test_no_token_passes_through(env, monkeypatch):
	def boom(g, **k):
		raise ValueError("no token")

	monkeypatch.setattr("huf.ai.gateways.slack_context.get_slack_api", boom)
	assert hf.pre_ingest_filter(gw(), ctx()) is True


def test_post_failure_still_drops(env):
	agent(env, "Sales")
	env.api.post_message.side_effect = RuntimeError("x")
	assert hf.pre_ingest_filter(gw(), ctx()) is False


def test_disabled_targets_not_listed(env):
	agent(env, "Sales")
	agent(env, "Old", disabled=1)
	env.bindings = [{"target_type": "Agent", "agent": "Old", "flow": None, "description": "x"}]
	names = [n for n, _d in hf.reachable_targets(gw())]
	assert names == ["Sales"]


def test_cap_and_dedupe(env):
	env.bindings = []
	for i in range(12):
		agent(env, f"A{i}")
		env.bindings.append({"target_type": "Agent", "agent": f"A{i}", "flow": None, "description": ""})
	env.bindings.append(env.bindings[0])
	text = hf.build_help(gw(default_agent=None, default_target_type=None)).fallback
	assert text.count("•") == hf.MAX_TARGETS and "4 more" in text


def test_binding_description_preferred_and_flow(env):
	agent(env, "Sales", "agent desc")
	env.values[("Flow", "F1")] = {"flow_name": "Expense flow", "status": "Published"}
	env.bindings = [
		{"target_type": "Agent", "agent": "Sales", "flow": None, "description": "binding desc"},
		{"target_type": "Flow", "agent": None, "flow": "F1", "description": ""},
	]
	text = hf.build_help(gw()).fallback
	assert "binding desc" in text and "agent desc" not in text and "Expense flow" in text


def test_permission_filter_for_linked_user(env, monkeypatch):
	agent(env, "Sales")
	monkeypatch.setattr(frappe, "has_permission", lambda dt, p, name, user=None: False)
	assert hf.reachable_targets(gw(), "bob@x.com") == []
	assert "Nothing is set up" in hf.build_help(gw(), "bob@x.com").fallback


def test_no_secrets_or_ids(env):
	agent(env, "Sales")
	text = hf.build_help(gw(integration_settings="IS-1", execution_user="svc@x.com")).fallback
	for bad in ("GW-1", "IS-1", "svc@x.com", "http", "token"):
		assert bad not in text


def test_feedback_hint_only_when_enabled(env):
	agent(env, "Sales")
	assert "Feedback" not in hf.build_help(gw()).fallback
	assert "Feedback" in hf.build_help(gw(show_feedback_buttons=1)).fallback


# ---- feedback prompt
def ev():
	return SimpleNamespace(name="EV-1", agent_run="RUN-1", conversation_id="C1", thread_id="1.1", sender_id="U1")


def test_flag_off_posts_nothing(env, monkeypatch):
	create = MagicMock()
	monkeypatch.setattr(ia, "create_action_session", create)
	hf.on_run_success(gw(), ev(), "agent", "ok")
	create.assert_not_called()
	env.api.post_message.assert_not_called()


def test_flag_on_posts_one_followup(env, monkeypatch):
	create = MagicMock(return_value="SESS-1")
	monkeypatch.setattr(ia, "create_action_session", create)
	hf.on_run_success(gw(show_feedback_buttons=1), ev(), "agent", "ok")
	assert create.call_args.args[1] == "feedback:"
	assert create.call_args.args[2] == {"agent_run": "RUN-1", "gateway_event": "EV-1"}
	assert create.call_args.kwargs["intended_slack_user"] == "U1"
	env.api.post_message.assert_called_once()
	kw = env.api.post_message.call_args.kwargs
	assert kw["thread_ts"] == "1.1"
	ids = [e["action_id"] for e in kw["blocks"][1]["elements"]]
	assert len(ids) == 2 and all("SESS-1" in i for i in ids)


def test_flow_kind_skipped(env, monkeypatch):
	monkeypatch.setattr(ia, "create_action_session", MagicMock())
	hf.on_run_success(gw(show_feedback_buttons=1), ev(), "flow", None)
	env.api.post_message.assert_not_called()


def test_prompt_failure_never_raises(env, monkeypatch):
	monkeypatch.setattr(ia, "create_action_session", MagicMock(side_effect=RuntimeError("db")))
	hf.on_run_success(gw(show_feedback_buttons=1), ev(), "agent", "ok")


# ---- click handler
def click(choice="up", clicker="U1"):
	return {"agent_run": "RUN-1", "gateway_event": "EV-1"} and (
		{"payload": {"agent_run": "RUN-1", "gateway_event": "EV-1"}, "choice": choice},
		{"user": {"id": clicker}},
	)


@pytest.fixture
def click_env(env, monkeypatch):
	def gv(dt, filt=None, fields=None, as_dict=False, **kw):
		return {"Gateway Event": "U1", "Agent Run": "Sales"}.get(dt) if dt != "Agent Message" else "MSG-1"

	env.get_value = gv
	monkeypatch.setattr(env, "get_value", gv)
	inserted = []
	users = []
	monkeypatch.setattr(frappe, "get_doc", lambda v: SimpleNamespace(insert=lambda: inserted.append(v)), raising=False)
	monkeypatch.setattr(frappe, "set_user", lambda u: users.append(u), raising=False)
	env.inserted, env.users = inserted, users
	return env


def test_asker_click_writes_feedback(click_env):
	s, p = click("up")
	out = hf.handle_feedback(gw(), s, "alice@x.com", p)
	assert out["text"] == hf.MSG_THANKS
	assert click_env.inserted == [{"doctype": "Agent Run Feedback", "feedback": "Thumbs Up",
		"agent": "Sales", "agent_message": "MSG-1"}]
	assert click_env.users == ["alice@x.com", "Administrator"]


def test_down_maps_to_thumbs_down(click_env):
	s, p = click("down")
	hf.handle_feedback(gw(), s, "alice@x.com", p)
	assert click_env.inserted[0]["feedback"] == "Thumbs Down"


def test_other_user_rejected(click_env):
	s, p = click("up", clicker="U2")
	assert hf.handle_feedback(gw(), s, "bob@x.com", p)["text"] == hf.MSG_NOT_ASKER
	assert click_env.inserted == []


def test_missing_permission_handled(click_env, monkeypatch):
	def deny(v):
		def ins():
			raise frappe.PermissionError("no")

		return SimpleNamespace(insert=ins)

	monkeypatch.setattr(frappe, "get_doc", deny, raising=False)
	monkeypatch.setattr(frappe, "PermissionError", PermissionError, raising=False)
	s, p = click("up")
	assert hf.handle_feedback(gw(), s, "alice@x.com", p)["text"] == hf.MSG_SAVE_FAILED
	assert click_env.users[-1] == "Administrator"


def test_unknown_choice_or_missing_doctype(click_env, monkeypatch):
	s, p = click("sideways")
	assert hf.handle_feedback(gw(), s, "a@x.com", p)["text"] == ia.MSG_UNKNOWN
	monkeypatch.setattr(frappe, "get_doc", MagicMock(side_effect=ImportError("DocType missing")), raising=False)
	s, p = click("up")
	assert hf.handle_feedback(gw(), s, "a@x.com", p)["text"] == hf.MSG_SAVE_FAILED


def test_registrations_at_import():
	assert REGISTERED_ACTION is hf.handle_feedback
	assert any(f is hf.pre_ingest_filter for _p, _s, prov, f in REGISTERED[gw_hooks.PRE_INGEST_FILTER] if prov == "slack")
	assert any(f is hf.on_run_success for _p, _s, prov, f in REGISTERED[gw_hooks.ON_RUN_SUCCESS] if prov == "slack")


def test_gateway_json_field_order():
	d = json.loads((ROOT / "huf/doctype/gateway/gateway.json").read_text())
	f = [x for x in d["fields"] if x["fieldname"] == "show_feedback_buttons"]
	assert len(f) == 1 and f[0]["fieldtype"] == "Check" and f[0]["default"] == "0"
	assert f[0]["label"] == "Ask for feedback after answers"
	assert d["field_order"].count("show_feedback_buttons") == 1
	assert set(d["field_order"]) == {x["fieldname"] for x in d["fields"]}


# ---- reactions as feedback ---------------------------------------------
def test_reaction_choice_mapping():
	assert hf._reaction_choice("+1") == "up" and hf._reaction_choice("thumbsup") == "up"
	assert hf._reaction_choice("+1::skin-tone-3") == "up"
	assert hf._reaction_choice("-1") == "down" and hf._reaction_choice("thumbsdown") == "down"
	assert hf._reaction_choice("tada") is None and hf._reaction_choice(None) is None


def _reaction_payload(**over):
	event = {"type": "reaction_added", "user": "U1", "reaction": "+1", "item_user": "UBOT",
		"item": {"type": "message", "channel": "C1", "ts": "1.2"}}
	event.update(over)
	return {"team_id": "T1", "authorizations": [{"user_id": "UBOT"}], "event": event}


@pytest.fixture
def rx(monkeypatch):
	state = SimpleNamespace(saved=[], cache={}, links=[{"user": "ann@x.com"}], runs=[{"agent_run": "RUN1"}], told=[])

	def get_all(doctype, **kw):
		return state.links if doctype == "Gateway Identity Link" else state.runs

	class Cache:
		def get_value(self, k):
			return state.cache.get(k)

		def set_value(self, k, v, expires_in_sec=None):
			state.cache[k] = v

	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	monkeypatch.setattr(frappe, "cache", lambda: Cache(), raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda values: SimpleNamespace(insert=lambda: state.saved.append(values)), raising=False)
	monkeypatch.setattr(frappe, "set_user", lambda u: None, raising=False)
	monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: "agent-1", raising=False)
	monkeypatch.setattr(hf, "_message_for_run", lambda run: "MSG1")
	import importlib

	ctx = importlib.import_module("huf.ai.gateways.slack_context")
	monkeypatch.setattr(ctx, "get_slack_api", lambda g, **k: SimpleNamespace(post_ephemeral=lambda *a, **kw: state.told.append(kw.get("text"))))
	return state


GWX = SimpleNamespace(name="gw1")


def test_thumbs_up_on_bot_message_saves_feedback_once(rx):
	assert hf.handle_reaction(GWX, _reaction_payload()) is True
	assert rx.saved == [{"doctype": "Agent Run Feedback", "feedback": "Thumbs Up", "agent": "agent-1", "agent_message": "MSG1"}]
	assert rx.told == [hf.MSG_THANKS]
	assert hf.handle_reaction(GWX, _reaction_payload()) is False  # same reaction twice is ignored
	assert len(rx.saved) == 1


def test_reaction_ignored_for_other_cases(rx):
	assert hf.handle_reaction(GWX, _reaction_payload(reaction="tada")) is False
	assert hf.handle_reaction(GWX, _reaction_payload(item_user="UOTHER")) is False  # not the bot's message
	rx.links = []
	assert hf.handle_reaction(GWX, _reaction_payload()) is False  # reactor not linked
	assert rx.saved == []
