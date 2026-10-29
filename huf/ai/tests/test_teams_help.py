import copy
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

from huf.ai.gateways import hooks  # noqa: E402
from huf.ai.gateways.teams import contract as tc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "teams"
TENANT = "00000000-0000-0000-0000-00000000aaaa"
AAD = "00000000-0000-0000-0000-0000000000u1"
OTHER_AAD = "00000000-0000-0000-0000-0000000000u2"
GW = SimpleNamespace(name="gw1", provider="Microsoft Teams")


def load(name):
	return json.loads((FIXTURES / f"{name}.json").read_text())


def fresh_module():
	"""Import teams_help after clearing stale hooks and package attributes."""
	sys.modules.pop("huf.ai.gateways.teams.messaging.help", None)
	pkg = sys.modules.get("huf.ai.gateways")
	if pkg is not None and hasattr(pkg, "teams_help"):
		delattr(pkg, "teams_help")
	hooks.clear()
	return importlib.import_module("huf.ai.gateways.teams.messaging.help")


class FakeFrappe:
	def __init__(self):
		self.flags = SimpleNamespace(gateway_filter_reason="stale")
		self.runs = []
		self.queries = []
		self.errors = []
		self.db = SimpleNamespace(get_value=lambda dt, name, field: "Ada Lovelace")

	def get_all(self, doctype, filters=None, fields=None, order_by=None, limit=None):
		self.queries.append((doctype, filters, fields, limit))
		rows = [r for r in self.runs if r["requester_user"] == filters["requester_user"]
			and r["gateway"] == filters["gateway"]]
		rows.sort(key=lambda r: r["creation"], reverse=True)
		return [{k: r[k] for k in fields} for r in rows[:limit]]

	def log_error(self, *a, **k):
		self.errors.append(a)

	def get_traceback(self):
		return "tb"


def _fx_env(self):
	monkeypatch = self.monkeypatch
	h = fresh_module()
	fake = FakeFrappe()
	monkeypatch.setattr(h, "frappe", fake)
	state = SimpleNamespace(
		h=h, fake=fake, sent=[], links={(TENANT, AAD): "ada@x.com"}, revoked=[], tokens=[]
	)
	monkeypatch.setattr(
		h.teams_identity, "resolve_user", lambda gw, t, a: state.links.get((t, a))
	)

	def disconnect(gw, t, a):
		if (t, a) in state.links:
			state.revoked.append((gw, t, a))
			del state.links[(t, a)]
			return True
		return False

	monkeypatch.setattr(h.teams_identity, "disconnect_current", disconnect)

	def prompt(gw, t, a, label):
		state.tokens.append((gw, t, a, label))
		return "ONETIME"

	monkeypatch.setattr(h.teams_identity, "_prompt_token", prompt)
	monkeypatch.setattr(h.teams_identity, "link_url", lambda tok: f"https://huf.test/link?token={tok}")
	monkeypatch.setattr(
		h.teams_outbox,
		"enqueue",
		lambda gw, snap, kind, payload, key: state.sent.append((gw, snap, kind, payload, key)) or "n1",
	)
	yield state
	hooks.clear()


def ctx(fixture, text):
	activity = copy.deepcopy(load(fixture))
	activity["text"] = text
	return {"message_text": text, "raw_payload": activity}


def run(env, fixture, text, **kw):
	c = ctx(fixture, text)
	if "activity" in kw:
		c["raw_payload"].update(kw["activity"])
	return env.h.pre_ingest_commands(GW, c), c


def reply_text(env):
	return env.sent[-1][3]["activity"]["text"]


FIX = ["personal_message", "channel_mention", "group_chat_message"]


# --- registration -------------------------------------------------------------------------








# --- parsing ------------------------------------------------------------------------------








# --- help ---------------------------------------------------------------------------------








# --- connect ------------------------------------------------------------------------------








# --- status -------------------------------------------------------------------------------


def seed_runs(env):
	env.fake.runs = [
		{
			"name": f"R{i}",
			"status": "Success",
			"creation": f"2026-01-0{i} 10:00",
			"requester_user": "ada@x.com",
			"gateway": "gw1",
			"prompt": "SECRET BODY",
		}
		for i in range(1, 8)
	] + [
		{"name": "BOB1", "status": "Failed", "creation": "2026-01-09 10:00", "requester_user": "bob@x.com",
		 "gateway": "gw1", "prompt": "BOB BODY"},
		{"name": "OTHERGW", "status": "Failed", "creation": "2026-01-09 11:00", "requester_user": "ada@x.com",
		 "gateway": "gw2", "prompt": "x"},
	]












# --- disconnect ---------------------------------------------------------------------------










# --- reply shape, safety ------------------------------------------------------------------






















# --- T16: connect remembers the personal chat (needed for the confirmation card) -------------


class TestModule(SupportCase):
	def test_hook_registered_for_teams_priority_40(self):
		h = fresh_module()
		entries = [e for e in hooks._HANDLERS[hooks.PRE_INGEST_FILTER] if e[3] is h.pre_ingest_commands]
		assert [(p, prov) for p, _s, prov, _f in entries] == [(40, "microsoft teams")]
		assert tc.HOOK_PRIORITY_COMMANDS == 40
		hooks.clear()

	def test_hook_not_called_for_other_provider(self):
		env = self.use(_fx_env)
		slack = SimpleNamespace(provider="Slack")
		called = hooks.call_all(hooks.PRE_INGEST_FILTER, slack, ctx("personal_message", "help"))
		assert called == []
		assert env.sent == []

	def test_hook_dispatch_through_hooks_module(self):
		env = self.use(_fx_env)
		res = hooks.call_all(hooks.PRE_INGEST_FILTER, GW, ctx("personal_message", "help"))
		assert res == [False] and len(env.sent) == 1

	def test_parse_command_variants(self):
		env = self.use(_fx_env)
		for text, expected in [
		("help", "help"), ("HELP", "help"), ("  Help  ", "help"), ("/help", "help"),
		("/Connect", "connect"), ("status", "status"), ("/STATUS ", "status"),
		("disconnect", "disconnect"), (" / disconnect", "disconnect"),
	]:
			with self.subTest(text=text, expected=expected):
				assert env.h.parse_command(text) == expected

	def test_non_commands_pass_through(self):
		env = self.use(_fx_env)
		for text in ["", "helpme", "help me", "connect now", "what is status", "//help", "statuses", None, 5, "hello"]:
			with self.subTest(text=text):
				c = {"message_text": text, "raw_payload": load("personal_message")}
				assert env.h.pre_ingest_commands(GW, c) is True
				assert env.sent == []

	def test_missing_context_passes_through(self):
		env = self.use(_fx_env)
		assert env.h.pre_ingest_commands(GW, {}) is True
		assert env.h.pre_ingest_commands(GW, None) is True

	def test_help_linked_in_every_chat_type(self):
		env = self.use(_fx_env)
		for fixture in FIX:
			with self.subTest(fixture=fixture):
				res, _ = run(env, fixture, "help")
				assert res is False
				assert "enabled workflows" in reply_text(env)
				assert "disconnect" in reply_text(env)

	def test_help_unlinked_personal_gets_connect_text(self):
		env = self.use(_fx_env)
		env.links.clear()
		run(env, "personal_message", "/help")
		assert "Connect your Huf account" in reply_text(env)
		assert "https://" not in reply_text(env)

	def test_help_unlinked_channel_points_to_personal_chat(self):
		env = self.use(_fx_env)
		env.links.clear()
		run(env, "channel_mention", "help")
		assert "Open a personal chat with me and send connect" in reply_text(env)

	def test_connect_unlinked_personal_gives_link(self):
		env = self.use(_fx_env)
		env.links.clear()
		res, _ = run(env, "personal_message", "connect")
		assert res is False
		assert "https://huf.test/link?token=ONETIME" in reply_text(env)
		assert env.tokens == [("gw1", TENANT, AAD, "Ada Example")]

	def test_connect_in_shared_chat_never_mints_token(self):
		env = self.use(_fx_env)
		for fixture in ["channel_mention", "group_chat_message"]:
			with self.subTest(fixture=fixture):
				env.links.clear()
				run(env, fixture, "connect")
				assert reply_text(env) == "Open a personal chat with me and send connect."
				assert env.tokens == []

	def test_connect_linked_says_so_with_label(self):
		env = self.use(_fx_env)
		run(env, "personal_message", "Connect")
		assert "connected to Huf as Ada Lovelace" in reply_text(env)
		assert env.tokens == []

	def test_status_personal_lists_last_five_own_runs(self):
		env = self.use(_fx_env)
		seed_runs(env)
		res, _ = run(env, "personal_message", "status")
		text = reply_text(env)
		assert res is False
		assert "Ada Lovelace" in text
		assert all(f"R{i}:" in text for i in (3, 4, 5, 6, 7))
		assert "R2:" not in text and "BOB1" not in text and "OTHERGW" not in text

	def test_status_has_no_message_bodies(self):
		env = self.use(_fx_env)
		seed_runs(env)
		run(env, "personal_message", "status")
		assert "SECRET BODY" not in reply_text(env) and "BOB BODY" not in reply_text(env)
		doctype, filters, fields, limit = env.fake.queries[-1]
		assert doctype == "Agent Run" and limit == 5
		assert filters == {"requester_user": "ada@x.com", "gateway": "gw1"}
		assert "prompt" not in fields

	def test_status_no_runs(self):
		env = self.use(_fx_env)
		run(env, "personal_message", "status")
		assert "No recent requests" in reply_text(env)

	def test_status_unlinked_gets_connect_text(self):
		env = self.use(_fx_env)
		env.links.clear()
		run(env, "personal_message", "status")
		assert "Connect your Huf account" in reply_text(env)
		assert env.fake.queries == []

	def test_status_in_shared_chat_does_not_list_runs(self):
		env = self.use(_fx_env)
		for fixture in ["channel_mention", "group_chat_message"]:
			with self.subTest(fixture=fixture):
				seed_runs(env)
				run(env, fixture, "status")
				assert reply_text(env) == "Open a personal chat with me and send status."
				assert env.fake.queries == []

	def test_disconnect_in_every_chat_type(self):
		env = self.use(_fx_env)
		for fixture in FIX:
			with self.subTest(fixture=fixture):
				res, _ = run(env, fixture, "disconnect")
				assert res is False
				assert reply_text(env).startswith("Your Huf account is disconnected from Teams.")
				assert env.revoked == [("gw1", TENANT, AAD)]

	def test_disconnect_revokes_only_that_principal(self):
		env = self.use(_fx_env)
		env.links[(TENANT, OTHER_AAD)] = "bob@x.com"
		run(env, "personal_message", "disconnect")
		assert env.revoked == [("gw1", TENANT, AAD)]
		assert (TENANT, OTHER_AAD) in env.links

	def test_disconnect_when_not_linked(self):
		env = self.use(_fx_env)
		env.links.clear()
		run(env, "personal_message", "disconnect")
		assert "not connected" in reply_text(env)
		assert env.revoked == []

	def test_target_user_never_taken_from_text(self):
		env = self.use(_fx_env)
		env.links[(TENANT, OTHER_AAD)] = "bob@x.com"
		res, _ = run(env, "personal_message", "disconnect bob@x.com")
		assert res is True and env.revoked == []

	def test_reply_goes_to_originating_conversation(self):
		env = self.use(_fx_env)
		_, c = run(env, "channel_mention", "help")
		gw, snap, kind, payload, key = env.sent[-1]
		assert gw == "gw1" and kind == "reply"
		assert snap["conversation_id"] == c["raw_payload"]["conversation"]["id"]
		assert snap["service_url"] == "https://smba.trafficmanager.net/amer"
		assert snap["tenant_id"] == TENANT
		act = payload["activity"]
		assert act["type"] == "message" and act["replyToId"] == c["raw_payload"]["id"]

	def test_hostile_service_url_sends_nothing(self):
		env = self.use(_fx_env)
		for url in [
		"http://smba.trafficmanager.net/amer/",
		"https://evil.example.com/",
		"https://x@smba.trafficmanager.net",
		"",
		"javascript:1",
	]:
			with self.subTest(url=url):
				res, _ = run(env, "personal_message", "help", activity={"serviceUrl": url})
				assert res is False
				assert env.sent == []

	def test_idempotency_key_stable_and_distinct(self):
		env = self.use(_fx_env)
		run(env, "personal_message", "help")
		run(env, "personal_message", "help")
		run(env, "personal_message", "status")
		run(env, "channel_mention", "help")
		keys = [s[4] for s in env.sent]
		assert keys[0] == keys[1]
		assert len({keys[0], keys[2], keys[3]}) == 3
		assert keys[0].startswith("teams_help:")

	def test_command_never_touches_filter_reason(self):
		env = self.use(_fx_env)
		env.fake.flags.gateway_filter_reason = "tenant_not_allowed"
		run(env, "personal_message", "help")
		assert env.fake.flags.gateway_filter_reason == "tenant_not_allowed"

	def test_internal_error_sends_nothing_but_drops(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(env.h.teams_identity, "resolve_user", lambda *a: 1 / 0)
		res, _ = run(env, "personal_message", "help")
		assert res is False and env.sent == [] and env.fake.errors

	def test_outbox_failure_never_raises(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		def boom(*a, **k):
			raise RuntimeError("db down")

		monkeypatch.setattr(env.h.teams_outbox, "enqueue", boom)
		res, _ = run(env, "personal_message", "help")
		assert res is False

	def test_guest_gets_unsupported_and_no_token(self):
		env = self.use(_fx_env)
		env.links.clear()
		act = {"from": {"id": "29:g", "name": "Guest", "aadObjectId": AAD, "userType": "Guest"}}
		run(env, "personal_message", "connect", activity=act)
		assert "not supported" in reply_text(env)
		assert env.tokens == []

	def test_raw_payload_as_json_string(self):
		env = self.use(_fx_env)
		c = ctx("personal_message", "help")
		c["raw_payload"] = json.dumps(c["raw_payload"])
		assert env.h.pre_ingest_commands(GW, c) is False
		assert len(env.sent) == 1

	def test_outbound_payloads_carry_no_secrets(self):
		env = self.use(_fx_env)
		seed_runs(env)
		for text in ("help", "status", "disconnect"):
			run(env, "personal_message", text)
		blob = json.dumps(env.sent)
		for needle in ("Bearer", "client_secret", "encryption_key", "eyJ", "password", "SECRET BODY"):
			assert needle not in blob

	def test_connect_link_is_only_link_material(self):
		env = self.use(_fx_env)
		env.links.clear()
		run(env, "personal_message", "connect")
		blob = json.dumps(env.sent[-1][3])
		assert blob.count("token=") == 1 and AAD not in blob and TENANT not in blob

	def test_connect_in_personal_chat_remembers_reference(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		calls = []
		monkeypatch.setattr(env.h.teams_refs, "upsert_reference", lambda gw, meta, installed=True: calls.append((gw, meta)))
		env.links.clear()
		run(env, "personal_message", "connect")
		assert len(calls) == 1 and calls[0][0] == "gw1" and calls[0][1].conversation_type == "personal"

	def test_connect_in_room_remembers_nothing_and_mints_no_token(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		for fixture in ["channel_mention", "group_chat_message"]:
			with self.subTest(fixture=fixture):
				calls = []
				monkeypatch.setattr(env.h.teams_refs, "upsert_reference", lambda *a, **k: calls.append(a))
				env.links.clear()
				run(env, fixture, "connect")
				assert calls == [] and env.tokens == []
				assert "personal chat" in reply_text(env) and "http" not in reply_text(env)
