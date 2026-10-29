"""Tests for Teams private output classification and per-user conversation key (WP T9)."""

import importlib
import json
import pathlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter  # noqa: E402
from huf.ai.gateway_adapters.types import GatewayReply  # noqa: E402
from huf.ai.gateways import hooks  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"
TENANT = "00000000-0000-0000-0000-00000000aaaa"
AAD = "00000000-0000-0000-0000-0000000000u1"
AAD2 = "00000000-0000-0000-0000-0000000000u2"
CHANNEL = "19:fakechannel@thread.tacv2"
PERSONAL = "a:1personalconv"
SVC = "https://smba.trafficmanager.net/amer/"
SECRET_ANSWER = "TOP-SECRET-ANSWER-4711"


def load(name):
	return json.loads((FIXTURES / f"{name}.json").read_text())


def import_fresh():
	for mod in ("huf.ai.gateways.teams.messaging.privacy",):
		sys.modules.pop(mod, None)
	pkg = sys.modules.get("huf.ai.gateways")
	if pkg is not None and hasattr(pkg, "teams_privacy"):
		delattr(pkg, "teams_privacy")
	return importlib.import_module("huf.ai.gateways.teams.messaging.privacy")


tp = import_fresh()


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def get_value(self, k):
		return self.d.get(k)

	def delete_value(self, k):
		self.d.pop(k, None)


class Env:
	"""Fakes for frappe + collaborators; collects outbox enqueues and API calls."""

	def __init__(self):
		self.cache = FakeCache()
		self.tool_rows = []
		self.tool_error = False
		self.refs = {}  # (tenant, aad) -> personal reference dict
		self.ref_rows = [{"service_url": SVC}]
		self.policy = "Private when records touched"
		self.linked = {AAD: "u@example.com"}
		self.create_result = PERSONAL
		self.create_calls = []
		self.upserts = []
		self.enqueued = []

	def get_all(self, doctype, **kw):
		if doctype == "Agent Tool Call":
			if self.tool_error:
				raise RuntimeError("db down")
			return self.tool_rows
		return self.ref_rows


def _fx_env(self):
	monkeypatch = self.monkeypatch
	e = Env()
	monkeypatch.setattr(tp, "frappe", SimpleNamespace(cache=lambda: e.cache, get_all=e.get_all))
	monkeypatch.setattr(tp.teams_tenant, "get_settings", lambda g: {"private_output_policy": e.policy})
	monkeypatch.setattr(tp.teams_tenant, "get_gateway_credential", lambda g, k: "x")
	monkeypatch.setattr(
		tp.teams_refs, "get_personal_reference", lambda g, t, a: e.refs.get((t, a))
	)
	monkeypatch.setattr(tp.teams_refs, "_find", lambda g, t, c: "refname")
	monkeypatch.setattr(
		tp.teams_refs, "upsert_reference", lambda g, m, installed=True: e.upserts.append(m) or "newref"
	)
	monkeypatch.setattr(tp.teams_identity, "resolve_user", lambda g, t, a: e.linked.get(a))
	monkeypatch.setattr(tp.teams_api, "make_token_provider", lambda creds, gateway_name=None: lambda **k: "tok")

	def create(*a, **kw):
		e.create_calls.append(a)
		if isinstance(e.create_result, Exception):
			raise e.create_result
		return e.create_result

	monkeypatch.setattr(tp.teams_api, "create_personal_conversation", create)

	def enqueue(gateway, snapshot, kind, payload, key):
		e.enqueued.append({"gateway": gateway, "snapshot": snapshot, "kind": kind, "payload": payload, "key": key})
		return "n1"

	monkeypatch.setattr(tp.teams_outbox, "enqueue", enqueue)
	return e


GW = SimpleNamespace(name="gw1", provider="Microsoft Teams")


def ev(fixture="channel_mention", **kw):
	base = dict(
		name="EVT-1",
		raw_payload=load(fixture),
		thread_id="1700000000100",
		agent_run="RUN-1",
		conversation_id=CHANNEL,
	)
	base.update(kw)
	return SimpleNamespace(**base)


def all_text(env):
	return json.dumps(env.enqueued)










































# ---- fail closed ----------------------------------------------------------------------
def _assert_failed_closed(env, e, got):
	assert got == tp.UNUSABLE_TARGET
	assert e.thread_id is None
	assert [n["payload"]["activity"]["text"] for n in env.enqueued] == [tp.UNAVAILABLE_TEXT]
	assert SECRET_ANSWER not in all_text(env)


class TestModule(SupportCase):
	# ---- conversation key -----------------------------------------------------------------
	def test_key_channel_per_user(self):
		a = tp.resolve_conversation_key(GW, ev())
		act = load("channel_mention")
		act["from"]["aadObjectId"] = AAD2
		b = tp.resolve_conversation_key(GW, ev(raw_payload=act))
		assert a == f"teams:{TENANT}:1700000000100:{AAD}"
		assert b == f"teams:{TENANT}:1700000000100:{AAD2}"
		assert a != b

	def test_key_group_chat_per_user(self):
		act = load("group_chat_message")
		k = tp.resolve_conversation_key(GW, ev(raw_payload=act))
		conv = act["conversation"]["id"].split(";messageid=")[0]
		assert k == f"teams:{TENANT}:{conv}:{AAD}"
		act["from"]["aadObjectId"] = AAD2
		assert tp.resolve_conversation_key(GW, ev(raw_payload=act)) != k

	def test_key_personal(self):
		act = load("personal_message")
		k = tp.resolve_conversation_key(GW, ev("personal_message"))
		assert k == f"teams:{TENANT}:{act['conversation']['id']}"

	def test_key_raw_payload_json_string(self):
		e = ev(raw_payload=json.dumps(load("channel_mention")))
		assert tp.resolve_conversation_key(GW, e).endswith(f":{AAD}")

	def test_key_none_when_not_derivable(self):
		assert tp.resolve_conversation_key(GW, ev(raw_payload=None)) is None
		act = load("channel_mention")
		del act["from"]["aadObjectId"]
		assert tp.resolve_conversation_key(GW, ev(raw_payload=act)) is None

	def test_never_raises_on_malformed(self):
		env = self.use(_fx_env)
		for raw in [None, "", "not json", "[]", 5, {"conversation": None}, {"from": 1}]:
			with self.subTest(raw=raw):
				e = ev(raw_payload=raw)
				assert tp.resolve_conversation_key(GW, e) is None
				assert tp.resolve_reply_target(GW, e, "x") in (None, tp.UNUSABLE_TARGET)

	# ---- classification -------------------------------------------------------------------
	def test_touched_by_record_tool(self):
		env = self.use(_fx_env)
		env.tool_rows = [{"tool": "get_list"}]
		assert tp.run_touched_records("RUN-1") is True

	def test_allowlisted_tools_do_not_touch(self):
		env = self.use(_fx_env)
		env.tool_rows = [{"tool": "Calculator"}, {"tool": "search_knowledge"}]
		assert tp.run_touched_records("RUN-1") is False

	def test_mixed_tools_touch(self):
		env = self.use(_fx_env)
		env.tool_rows = [{"tool": "calculator"}, {"tool": "update_document"}]
		assert tp.run_touched_records("RUN-1") is True

	def test_no_tools_no_run_not_touched(self):
		env = self.use(_fx_env)
		assert tp.run_touched_records("RUN-1") is False
		assert tp.run_touched_records(None) is False

	def test_lookup_error_counts_as_touched(self):
		env = self.use(_fx_env)
		env.tool_error = True
		assert tp.run_touched_records("RUN-1") is True

	# ---- policies -------------------------------------------------------------------------
	def test_policy_always_private_redirects(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.refs[(TENANT, AAD)] = {"conversation_id": PERSONAL}
		assert tp.resolve_reply_target(GW, ev(), "hi") == PERSONAL

	def test_policy_records_touched_redirects(self):
		env = self.use(_fx_env)
		env.refs[(TENANT, AAD)] = {"conversation_id": PERSONAL}
		env.tool_rows = [{"tool": "get_document"}]
		assert tp.resolve_reply_target(GW, ev(), "hi") == PERSONAL

	def test_policy_records_not_touched_stays(self):
		env = self.use(_fx_env)
		env.tool_rows = [{"tool": "calculator"}]
		assert tp.resolve_reply_target(GW, ev(), "hi") is None
		assert env.enqueued == []

	def test_policy_channel_stays_even_with_records(self):
		env = self.use(_fx_env)
		env.policy = "Channel"
		env.tool_rows = [{"tool": "get_document"}]
		assert tp.resolve_reply_target(GW, ev(), "hi") is None

	def test_policy_unreadable_is_private(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		def boom(g):
			raise RuntimeError("x")

		monkeypatch.setattr(tp.teams_tenant, "get_settings", boom)
		env.refs[(TENANT, AAD)] = {"conversation_id": PERSONAL}
		assert tp.resolve_reply_target(GW, ev(), "hi") == PERSONAL

	def test_personal_chat_never_redirects(self):
		env = self.use(_fx_env)
		for policy in ["Always private", "Private when records touched", "Channel"]:
			with self.subTest(policy=policy):
				env.policy = policy
				env.tool_rows = [{"tool": "get_document"}]
				e = ev("personal_message", thread_id=None)
				assert tp.resolve_reply_target(GW, e, "hi") is None
				assert env.enqueued == []

	def test_group_chat_is_room(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.refs[(TENANT, AAD)] = {"conversation_id": PERSONAL}
		assert tp.resolve_reply_target(GW, ev("group_chat_message"), "hi") == PERSONAL

	# ---- redirect success -----------------------------------------------------------------
	def test_redirect_success_note_and_thread_cleared(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.refs[(TENANT, AAD)] = {"conversation_id": PERSONAL}
		e = ev()
		assert tp.resolve_reply_target(GW, e, SECRET_ANSWER) == PERSONAL
		assert e.thread_id is None
		assert len(env.enqueued) == 1
		n = env.enqueued[0]
		assert n["payload"]["activity"]["text"] == tp.ACK_TEXT
		assert n["snapshot"]["conversation_id"] == f"{CHANNEL};messageid=1700000000100"
		assert SECRET_ANSWER not in all_text(env)
		assert env.create_calls == []

	def test_creates_personal_conversation_for_linked_user(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		e = ev()
		assert tp.resolve_reply_target(GW, e, "x") == PERSONAL
		assert len(env.create_calls) == 1
		assert env.create_calls[0][:4] == (SVC, TENANT, "28:00000000-0000-0000-0000-0000000000b1", AAD)
		assert len(env.upserts) == 1 and env.upserts[0].conversation_id == PERSONAL
		assert env.upserts[0].conversation_type == "personal"
		assert e.thread_id is None

	def test_fail_closed_unlinked_user(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.linked = {}
		e = ev()
		_assert_failed_closed(env, e, tp.resolve_reply_target(GW, e, SECRET_ANSWER))
		assert env.create_calls == []

	def test_fail_closed_create_returns_nothing(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.create_result = None
		e = ev()
		_assert_failed_closed(env, e, tp.resolve_reply_target(GW, e, SECRET_ANSWER))

	def test_fail_closed_create_raises(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.create_result = RuntimeError("403")
		e = ev()
		_assert_failed_closed(env, e, tp.resolve_reply_target(GW, e, SECRET_ANSWER))

	def test_fail_closed_no_service_url(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.ref_rows = []
		act = load("channel_mention")
		act["serviceUrl"] = ""
		e = ev(raw_payload=act)
		_assert_failed_closed(env, e, tp.resolve_reply_target(GW, e, SECRET_ANSWER))

	def test_fail_closed_even_if_note_enqueue_fails(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		env.policy = "Always private"
		env.linked = {}

		def boom(*a, **k):
			raise RuntimeError("outbox down")

		monkeypatch.setattr(tp.teams_outbox, "enqueue", boom)
		e = ev()
		assert tp.resolve_reply_target(GW, e, "x") == tp.UNUSABLE_TARGET

	def test_real_adapter_send_never_enqueues_answer_for_channel(self):
		env = self.use(_fx_env)
		env.policy = "Always private"
		env.linked = {}
		e = ev()
		target = tp.resolve_reply_target(GW, e, SECRET_ANSWER)
		sent = []
		outbox = SimpleNamespace(enqueue=lambda gw, snap, kind, payload, key: sent.append((snap, payload)) or "n")
		channel_row = {
			"name": "ref1", "conversation_id": CHANNEL, "conversation_type": "channel",
			"service_url": SVC, "tenant_id": TENANT, "gateway": "gw1",
		}  # fmt: skip

		def lookup(conversation_id, gateway, app_id):
			base = conversation_id.split(";messageid=", 1)[0]
			return channel_row if base == CHANNEL else None

		adapter = TeamsGatewayAdapter(
			{"app_id": "app", "app_password": "pw", "tenant_id": TENANT},
			gateway_name="gw1",
			reference_lookup=lookup,
			outbox=outbox,
		)
		with self.assertRaises(ValueError):
			adapter.send_reply(GatewayReply(conversation_id=target, text=SECRET_ANSWER, thread_id=e.thread_id))
		assert sent == []
		assert SECRET_ANSWER not in all_text(env)

	# ---- mark_sensitive -------------------------------------------------------------------
	def test_mark_sensitive_lifecycle(self):
		env = self.use(_fx_env)
		e = ev()
		assert tp.is_marked_sensitive(e) is False
		tp.mark_sensitive(e, "pii")
		assert tp.is_marked_sensitive(e) is True
		tp.clear_sensitive(e)
		assert tp.is_marked_sensitive(e) is False

	def test_mark_sensitive_by_name_and_by_run(self):
		env = self.use(_fx_env)
		tp.mark_sensitive("EVT-1")
		assert tp.is_marked_sensitive(ev()) is True
		tp.clear_sensitive("EVT-1")
		tp.mark_sensitive("RUN-1")
		assert tp.is_marked_sensitive(ev()) is True

	def test_marked_sensitive_redirects_under_channel_policy(self):
		env = self.use(_fx_env)
		env.policy = "Channel"
		env.refs[(TENANT, AAD)] = {"conversation_id": PERSONAL}
		e = ev()
		tp.mark_sensitive(e)
		assert tp.resolve_reply_target(GW, e, "x") == PERSONAL

	def test_mark_sensitive_never_raises(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(tp, "frappe", SimpleNamespace(cache=lambda: (_ for _ in ()).throw(RuntimeError())))
		tp.mark_sensitive("x")
		assert tp.is_marked_sensitive("x") is False

	# ---- registration ---------------------------------------------------------------------
	def test_handlers_registered_for_teams_provider(self):
		hooks.clear()
		try:
			tp.register()
			kinds = {h: [p for _pr, _s, p, f in hooks._HANDLERS[h]] for h in hooks._HANDLERS}
			assert kinds[hooks.RESOLVE_CONVERSATION_KEY] == ["microsoft teams"]
			assert kinds[hooks.RESOLVE_REPLY_TARGET] == ["microsoft teams"]
			assert hooks.call_first(hooks.RESOLVE_CONVERSATION_KEY, GW, ev()).startswith("teams:")
			slack = SimpleNamespace(name="s", provider="Slack")
			assert hooks.call_first(hooks.RESOLVE_CONVERSATION_KEY, slack, ev()) is None
		finally:
			hooks.clear()
