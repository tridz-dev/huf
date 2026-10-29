"""Tests for private-by-default Slack replies (huf.ai.gateways.slack.privacy)."""

import json
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateways import hooks as gw_hooks  # noqa: E402

_saved = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
try:
	from huf.ai.gateways.slack import privacy  # noqa: E402
finally:
	gw_hooks._HANDLERS.clear()
	gw_hooks._HANDLERS.update(_saved)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRET = "xoxb-SECRET-TOKEN"
ANSWER = "Your salary is 123456"


class FakeCache:
	def __init__(self):
		self.d = {}
		self.ttl = {}

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v
		self.ttl[k] = expires_in_sec

	def get_value(self, k):
		return self.d.get(k)

	def delete_value(self, k):
		self.d.pop(k, None)


class FakeApi:
	def __init__(self, dm="D99", open_error=None, post_error=None):
		self.dm, self.open_error, self.post_error = dm, open_error, post_error
		self.posts, self.ephemerals, self.opens = [], [], []

	def conversations_open(self, users):
		self.opens.append(users)
		if self.open_error:
			raise self.open_error
		return self.dm

	def post_message(self, channel, text=None, blocks=None, thread_ts=None, unfurl=False):
		if self.post_error:
			raise self.post_error
		self.posts.append((channel, text, thread_ts))
		return {}

	def post_ephemeral(self, channel, user, text=None, blocks=None, thread_ts=None):
		self.ephemerals.append((channel, user, text, thread_ts))
		return {}


def _fx_env(self):
	monkeypatch = self.monkeypatch
	cache = FakeCache()
	api = FakeApi()
	monkeypatch.setattr(privacy, "_cache", lambda: cache)
	monkeypatch.setattr(privacy, "get_slack_api", lambda gateway, **k: api)
	return SimpleNamespace(cache=cache, api=api)


def gw(policy=privacy.ALWAYS_PRIVATE):
	return SimpleNamespace(name="GW", provider="slack", private_reply_policy=policy)


def ev(conv="C1", ctype=None, sender="U1", thread="111.2", name="EV-1", run=None):
	inner = {"channel": conv}
	if ctype:
		inner["channel_type"] = ctype
	return SimpleNamespace(
		name=name, sender_id=sender, conversation_id=conv, thread_id=thread, agent_run=run,
		raw_payload={"event": inner},
	)


class TestModule(SupportCase):
	def setUp(self):
		super().setUp()
		self.use(_fx_env)
	# ---- policies -------------------------------------------------------------------
	def test_reply_where_asked_no_change(self):
		env = self.use(_fx_env)
		e = ev()
		assert privacy.resolve_reply_target(gw(privacy.REPLY_WHERE_ASKED), e, ANSWER) is None
		assert env.api.opens == [] and env.api.posts == [] and e.thread_id == "111.2"

	def test_missing_policy_defaults_no_change(self):
		env = self.use(_fx_env)
		g = SimpleNamespace(name="GW", provider="slack")
		assert privacy.resolve_reply_target(g, ev(), ANSWER) is None

	def test_always_private_in_room_redirects(self):
		env = self.use(_fx_env)
		e = ev()
		assert privacy.resolve_reply_target(gw(), e, ANSWER) == "D99"
		assert env.api.opens == [["U1"]]

	def test_sensitive_policy_unmarked_no_change(self):
		env = self.use(_fx_env)
		assert privacy.resolve_reply_target(gw(privacy.PRIVATE_WHEN_SENSITIVE), ev(), ANSWER) is None
		assert env.api.opens == []

	def test_sensitive_policy_marked_redirects(self):
		env = self.use(_fx_env)
		e = ev()
		privacy.mark_sensitive("EV-1", "pii")
		assert privacy.resolve_reply_target(gw(privacy.PRIVATE_WHEN_SENSITIVE), e, ANSWER) == "D99"

	def test_sensitive_marked_via_agent_run(self):
		env = self.use(_fx_env)
		e = ev(run="RUN-7")
		privacy.mark_sensitive("RUN-7")
		assert privacy.resolve_reply_target(gw(privacy.PRIVATE_WHEN_SENSITIVE), e, ANSWER) == "D99"

	# ---- room vs DM ---------------------------------------------------------------------
	def test_is_room(self):
		for conv, ctype, room in [
	("C1", "channel", True), ("G1", "group", True), ("G2", "mpim", True), ("D1", "im", False),
	("C1", None, True), ("G1", None, True), ("D1", None, False),
]:
			with self.subTest(conv=conv, ctype=ctype, room=room):
				self.reset_fixtures()
				assert privacy.is_room(ev(conv=conv, ctype=ctype)) is room

	def test_is_room_payload_as_json_string(self):
		e = ev()
		e.raw_payload = json.dumps({"event": {"channel_type": "im"}})
		assert privacy.is_room(e) is False

	def test_dm_never_redirected(self):
		env = self.use(_fx_env)
		e = ev(conv="D1", ctype="im")
		assert privacy.resolve_reply_target(gw(), e, ANSWER) is None
		assert env.api.opens == [] and env.api.posts == [] and e.thread_id == "111.2"

	# ---- ack + thread -----------------------------------------------------------------------
	def test_ack_posted_once_in_thread_and_neutral(self):
		env = self.use(_fx_env)
		privacy.resolve_reply_target(gw(), ev(), ANSWER)
		assert env.api.posts == [("C1", privacy.ACK_TEXT, "111.2")]
		assert ANSWER not in env.api.posts[0][1]

	def test_thread_id_cleared_on_redirect(self):
		env = self.use(_fx_env)
		e = ev()
		privacy.resolve_reply_target(gw(), e, ANSWER)
		assert e.thread_id is None

	def test_ack_failure_does_not_block_dm(self):
		env = self.use(_fx_env)
		env.api.post_error = RuntimeError("boom")
		e = ev()
		assert privacy.resolve_reply_target(gw(), e, ANSWER) == "D99"

	# ---- fail closed ----------------------------------------------------------------------------
	def test_dm_open_error_fails_closed(self):
		env = self.use(_fx_env)
		env.api.open_error = RuntimeError("missing_scope")
		e = ev()
		target = privacy.resolve_reply_target(gw(), e, ANSWER)
		assert target == "U1" and target != "C1"
		assert e.thread_id is None

	def test_dm_open_error_never_posts_answer_in_channel(self):
		env = self.use(_fx_env)
		env.api.open_error = RuntimeError("missing_scope")
		privacy.resolve_reply_target(gw(), ev(), ANSWER)
		assert env.api.posts == [("C1", privacy.FAILED_TEXT, "111.2")]
		assert all(ANSWER not in (p[1] or "") for p in env.api.posts)

	def test_dm_open_returns_none_fails_closed(self):
		env = self.use(_fx_env)
		env.api.dm = None
		assert privacy.resolve_reply_target(gw(), ev(), ANSWER) == "U1"

	def test_no_sender_returns_unusable_target(self):
		env = self.use(_fx_env)
		target = privacy.resolve_reply_target(gw(), ev(sender=""), ANSWER)
		assert target == privacy.UNUSABLE_TARGET and not target.startswith(("C", "G"))
		assert env.api.opens == []

	def test_missing_token_fails_closed(self):
		monkeypatch = self.monkeypatch
		def boom(gateway, **k):
			raise ValueError("Slack gateway has no bot token configured")

		monkeypatch.setattr(privacy, "get_slack_api", boom)
		assert privacy.resolve_reply_target(gw(), ev(), ANSWER) == "U1"

	def test_through_hooks_call_first_never_none_on_failure(self):
		env = self.use(_fx_env)
		env.api.open_error = RuntimeError("x")
		saved = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
		try:
			gw_hooks._HANDLERS.clear()
			gw_hooks.register(gw_hooks.RESOLVE_REPLY_TARGET, privacy.resolve_reply_target, provider="slack")
			assert gw_hooks.call_first(gw_hooks.RESOLVE_REPLY_TARGET, gw(), ev(), ANSWER) == "U1"
		finally:
			gw_hooks._HANDLERS.clear()
			gw_hooks._HANDLERS.update(saved)

	# ---- marking lifecycle -----------------------------------------------------------------------
	def test_mark_lifecycle(self):
		env = self.use(_fx_env)
		e = ev()
		assert privacy.is_marked_sensitive(e) is False
		privacy.mark_sensitive(e, "why")
		assert privacy.is_marked_sensitive(e) is True
		assert env.cache.ttl[privacy._KEY + "EV-1"] == privacy.SENSITIVE_TTL_SECONDS
		privacy.clear_sensitive(e)
		assert privacy.is_marked_sensitive(e) is False

	def test_mark_does_not_leak_between_events(self):
		env = self.use(_fx_env)
		privacy.mark_sensitive("EV-1")
		assert privacy.is_marked_sensitive(ev(name="EV-2")) is False

	# ---- ephemeral / registration / json / secrets --------------------------------------------------
	def test_reply_ephemeral(self):
		env = self.use(_fx_env)
		privacy.reply_ephemeral(gw(), ev(), "only you")
		assert env.api.ephemerals == [("C1", "U1", "only you", "111.2")]

	def test_registered_for_slack_only(self):
		saved = {k: list(v) for k, v in gw_hooks._HANDLERS.items()}
		try:
			gw_hooks._HANDLERS.clear()
			gw_hooks.register(gw_hooks.RESOLVE_REPLY_TARGET, privacy.resolve_reply_target, provider="slack")
			other = SimpleNamespace(provider="discord")
			assert gw_hooks._matching(gw_hooks.RESOLVE_REPLY_TARGET, (other,)) == []
		finally:
			gw_hooks._HANDLERS.clear()
			gw_hooks._HANDLERS.update(saved)

	def test_gateway_json_field(self):
		d = json.loads((ROOT / "huf/doctype/gateway/gateway.json").read_text())
		f = {x["fieldname"]: x for x in d["fields"]}["private_reply_policy"]
		assert f["fieldtype"] == "Select" and f["default"] == "Reply where asked"
		assert f["options"].split("\n") == [privacy.REPLY_WHERE_ASKED, privacy.PRIVATE_WHEN_SENSITIVE, privacy.ALWAYS_PRIVATE]
		assert "private_reply_policy" in d["field_order"] and "unmapped_policy" in d["field_order"]

	def test_no_token_in_outputs(self):
		env = self.use(_fx_env)
		e = ev()
		env.api.open_error = RuntimeError("boom")
		out = [privacy.resolve_reply_target(gw(), e, ANSWER), privacy.ACK_TEXT, privacy.FAILED_TEXT, env.api.posts]
		assert SECRET not in repr(out)
