import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateways import hooks, reliability  # noqa: E402
from huf.ai.gateways.slack.api import SlackApiError  # noqa: E402


gateway_webhook = None
gateway_service = None


def _fx_heavy_modules(self):
	"""Import gateway_webhook/gateway_service under temporary stubs; restore sys.modules after."""
	import importlib
	import types

	global gateway_webhook, gateway_service

	@__import__("dataclasses").dataclass
	class GatewayReply:
		conversation_id: str
		text: str
		thread_id: str | None = None
		reply_to_provider_message_id: str | None = None

	def mod(name, **attrs):
		m = types.ModuleType(name)
		m.__dict__.update(attrs)
		return m

	class _Pkg(types.ModuleType):
		def __getattr__(self, name):  # upstream imports provider_hooks etc. from this package
			if name.startswith("__"):
				raise AttributeError(name)
			return __import__("unittest.mock").mock.MagicMock()

	pkg = _Pkg("huf.ai.gateway_adapters")
	pkg.__path__ = []
	pkg.provider_hooks = types.SimpleNamespace(get=lambda *a, **k: None)  # no provider-specific reply target
	stubs = {
		"frappe.rate_limiter": mod("frappe.rate_limiter", rate_limit=lambda **k: (lambda f: f)),
		"huf.ai.gateway_adapters": pkg,
		"huf.ai.gateway_adapters.provider_ids": mod("p", provider_to_service_id=lambda x: x),
		"huf.ai.gateway_adapters.registered": mod("r", get_adapter_class=lambda *a, **k: None),
		"huf.ai.gateway_adapters.types": mod("t", GatewayReply=GatewayReply),
	}
	owned = ("huf.ai.gateway_webhook", "huf.ai.gateway_service")
	saved = {k: sys.modules.get(k) for k in (*stubs, *owned)}
	sys.modules.update(stubs)
	for k in owned:
		sys.modules.pop(k, None)
	try:
		gateway_webhook = importlib.import_module("huf.ai.gateway_webhook")
		try:
			gateway_service = importlib.import_module("huf.ai.gateway_service")
		except Exception:
			gateway_service = None
		yield
	finally:
		for k, old in saved.items():
			if old is None:
				sys.modules.pop(k, None)
			else:
				sys.modules[k] = old
		gateway_webhook = gateway_service = None


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v


def _fx_env(self):
	monkeypatch = self.monkeypatch
	cache = FakeCache()
	monkeypatch.setattr(reliability.frappe, "cache", lambda: cache, raising=False)
	sent = []
	public = []
	gw = gateway_webhook
	monkeypatch.setattr(gw, "send_gateway_reply", lambda g, e, t, **k: public.append(t))

	class FakeApi:
		def post_ephemeral(self, channel, user, text=None, blocks=None, thread_ts=None):
			sent.append((channel, thread_ts, text))

	import importlib

	ctx = importlib.import_module("huf.ai.gateways.slack.context")
	monkeypatch.setattr(ctx, "get_slack_api", lambda g, **k: FakeApi())
	return SimpleNamespace(cache=cache, sent=sent, public=public)


def ev(name="GE-1", **kw):
	d = dict(name=name, conversation_id="C1", thread_id="111.1", provider_event_id="C1:222.3",
		sender_id="U1")
	d.update(kw)
	return SimpleNamespace(**d)


GW = SimpleNamespace(provider="Slack")










# ---- S8: Slack notices are private (never the channel/thread) ----
def _api_fixture(monkeypatch, eph_fails=False, dm_fails=False):
	import importlib

	calls = SimpleNamespace(eph=[], dm=[], opened=[])

	class Api:
		def post_ephemeral(self, channel, user, text=None, blocks=None, thread_ts=None):
			if eph_fails:
				raise RuntimeError("cant_post")
			calls.eph.append((channel, user, thread_ts, text))

		def conversations_open(self, users):
			calls.opened.append(users)
			if dm_fails:
				raise RuntimeError("no im:write")
			return "D9"

		def post_message(self, channel, text=None, blocks=None, thread_ts=None, unfurl=False):
			calls.dm.append((channel, text))

	ctx = importlib.import_module("huf.ai.gateways.slack.context")
	monkeypatch.setattr(ctx, "get_slack_api", lambda g, **k: Api())
	return calls
























# ---- ack reaction ----
def _fx_api(self):
	monkeypatch = self.monkeypatch
	a = MagicMock()
	import huf.ai.gateways.slack.context as sc

	monkeypatch.setattr(sc, "get_slack_api", lambda gateway, **k: a)
	return a














# ---- outbound retry ----
class Adapter:
	def __init__(self, *outcomes):
		self.outcomes = list(outcomes)
		self.calls = 0

	def send_reply(self, reply):
		self.calls += 1
		o = self.outcomes.pop(0)
		if isinstance(o, BaseException):
			raise o
		return o


def _fx_send(self):
	monkeypatch = self.monkeypatch
	def run(adapter, **kw):
		monkeypatch.setattr(gateway_webhook, "get_gateway_adapter", lambda g, *a, **k: adapter)
		sleeps = []
		e = SimpleNamespace(conversation_id="C1", thread_id="")
		try:
			r = gateway_webhook.send_gateway_reply(GW, e, "hi", sleep=sleeps.append, **kw)
		except Exception as exc:
			return exc, sleeps
		return r, sleeps

	return run


class TestModule(SupportCase):
	def setUp(self):
		super().setUp()
		self.use(_fx_heavy_modules)
	# ---- failure notice ----
	def test_failure_notice_has_ref_and_no_error_text(self):
		env = self.use(_fx_env)
		reliability.on_run_failure(GW, ev(), "agent", RuntimeError("secret traceback xoxb-1"))
		assert len(env.sent) == 1
		conv, thread, text = env.sent[0]
		assert (conv, thread) == ("C1", "111.1")
		assert "GE-1" in text and "secret" not in text and "xoxb" not in text

	def test_failure_notice_flow_kind(self):
		env = self.use(_fx_env)
		reliability.on_run_failure(GW, ev("GE-F"), "flow", ValueError("x"))
		assert len(env.sent) == 1

	def test_failure_notice_at_most_once(self):
		env = self.use(_fx_env)
		for _ in range(3):
			reliability.on_run_failure(GW, ev(), "agent", RuntimeError("x"))
		assert len(env.sent) == 1

	def test_failure_notice_never_raises_on_send_error(self):
		monkeypatch = self.monkeypatch
		env = self.use(_fx_env)
		import importlib

		ctx = importlib.import_module("huf.ai.gateways.slack.context")
		monkeypatch.setattr(ctx, "get_slack_api", MagicMock(side_effect=RuntimeError("boom")))
		reliability.on_run_failure(GW, ev(), "agent", RuntimeError("x"))

	def test_slack_notice_is_ephemeral_to_sender_in_thread(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		calls = _api_fixture(monkeypatch)
		reliability.on_event_rejected(GW, ev(), "Rejected", hooks.USER_VISIBLE_PREFIX + "link: https://x/y")
		assert calls.eph == [("C1", "U1", "111.1", "link: https://x/y")]
		assert calls.dm == [] and env.public == []

	def test_slack_notice_falls_back_to_dm(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		calls = _api_fixture(monkeypatch, eph_fails=True)
		reliability.on_event_rejected(GW, ev(), "Rejected", hooks.USER_VISIBLE_PREFIX + "secret link")
		assert calls.opened == [["U1"]] and calls.dm == [("D9", "secret link")]
		assert env.public == []

	def test_slack_notice_nothing_public_when_both_fail(self):
		env = self.use(_fx_env)
		monkeypatch = self.monkeypatch
		_api_fixture(monkeypatch, eph_fails=True, dm_fails=True)
		reliability.on_event_rejected(GW, ev(), "Rejected", hooks.USER_VISIBLE_PREFIX + "secret link")
		assert env.public == []

	def test_non_slack_provider_keeps_reply_path(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(
			SimpleNamespace(provider="Telegram"), ev(), "Rejected", hooks.USER_VISIBLE_PREFIX + "hello"
		)
		assert env.public == ["hello"] and env.sent == []

	def test_failure_notice_never_raises_on_cache_error(self):
		monkeypatch = self.monkeypatch
		env = self.use(_fx_env)
		monkeypatch.setattr(reliability.frappe, "cache", MagicMock(side_effect=RuntimeError("redis")))
		reliability.on_run_failure(GW, ev(), "agent", RuntimeError("x"))
		assert env.sent == []

	def test_no_notice_without_conversation(self):
		env = self.use(_fx_env)
		reliability.on_run_failure(GW, ev(conversation_id=""), "agent", RuntimeError("x"))
		assert env.sent == []

	# ---- rejection ----
	def test_rejected_user_visible_reason_sent_without_prefix(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(), "Rejected", hooks.USER_VISIBLE_PREFIX + "Please use a thread.")
		assert env.sent[0][2] == "Please use a thread."

	def test_rejected_internal_reason_hidden(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(), "Rejected", "sender not in allow-list")
		reliability.on_event_rejected(GW, ev("GE-2"), "Rejected", "pairing required")
		assert env.sent == []

	def test_unrouted_friendly_with_ref(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(), "Unrouted", "no route for channel")
		text = env.sent[0][2]
		assert "GE-1" in text and "no route" not in text and "not set up" in text

	def test_rejected_notice_once(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(), "Unrouted", "r")
		reliability.on_event_rejected(GW, ev(), "Unrouted", "r")
		assert len(env.sent) == 1

	def test_rejected_empty_visible_reason_ignored(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(), "Rejected", hooks.USER_VISIBLE_PREFIX)
		assert env.sent == []

	def test_reaction_added_on_start(self):
		api = self.use(_fx_api)
		reliability.slack_on_run_start(GW, ev(), "agent")
		api.add_reaction.assert_called_once_with("C1", "222.3", "hourglass_flowing_sand")

	def test_reaction_removed_on_success_and_failure(self):
		api = self.use(_fx_api)
		reliability.slack_on_run_end(GW, ev(), "agent", "resp")
		reliability.slack_on_run_end(GW, ev(), "agent", RuntimeError())
		assert api.remove_reaction.call_count == 2

	def test_reaction_parse_fallback(self):
		for bad in ["", "nocolon", "C1:", ":1.2", "C1:abc", None]:
			with self.subTest(bad=bad):
				self.reset_fixtures()
				api = self.use(_fx_api)
				reliability.slack_on_run_start(GW, ev(provider_event_id=bad), "agent")
				api.add_reaction.assert_not_called()

	def test_reaction_errors_swallowed(self):
		api = self.use(_fx_api)
		api.add_reaction.side_effect = SlackApiError("reactions.add", "missing_scope", 200)
		reliability.slack_on_run_start(GW, ev(), "agent")
		api.remove_reaction.side_effect = SlackApiError("reactions.remove", "no_reaction", 200)
		reliability.slack_on_run_end(GW, ev(), "agent")

	def test_reaction_no_token_swallowed(self):
		monkeypatch = self.monkeypatch
		import huf.ai.gateways.slack.context as sc

		monkeypatch.setattr(sc, "get_slack_api", MagicMock(side_effect=ValueError("no token")))
		reliability.slack_on_run_start(GW, ev(), "agent")

	def test_hook_registration(self):
		hooks.clear()
		import importlib

		importlib.reload(reliability)
		slack = hooks._matching(hooks.ON_RUN_START, (GW,))
		other = hooks._matching(hooks.ON_RUN_START, (SimpleNamespace(provider="Telegram"),))
		assert reliability.slack_on_run_start in slack and reliability.slack_on_run_start not in other
		tg = SimpleNamespace(provider="Telegram")
		assert reliability.on_run_failure in hooks._matching(hooks.ON_RUN_FAILURE, (tg,))
		assert reliability.on_event_rejected in hooks._matching(hooks.ON_EVENT_REJECTED, (GW,))
		hooks.clear()

	def test_retry_then_success_exponential(self):
		send = self.use(_fx_send)
		ad = Adapter(SlackApiError("m", "http_503", 503), SlackApiError("m", "http_502", 502), "RCPT")
		r, sleeps = send(ad)
		assert r == "RCPT" and ad.calls == 3 and sleeps == [1.0, 2.0]

	def test_max_three_attempts(self):
		send = self.use(_fx_send)
		ad = Adapter(*[SlackApiError("m", "http_500", 500) for _ in range(5)])
		r, sleeps = send(ad)
		assert isinstance(r, SlackApiError) and ad.calls == 3 and len(sleeps) == 2

	def test_permanent_not_retried(self):
		for code in ["invalid_auth", "channel_not_found", "not_in_channel", "is_archived"]:
			with self.subTest(code=code):
				self.reset_fixtures()
				send = self.use(_fx_send)
				ad = Adapter(ValueError(f"Slack chat.postMessage failed: {code}"), "X")
				r, sleeps = send(ad)
				assert isinstance(r, ValueError) and ad.calls == 1 and sleeps == []

	def test_adapter_valueerror_ratelimited_retried(self):
		send = self.use(_fx_send)
		ad = Adapter(ValueError("Slack chat.postMessage failed: ratelimited"), "OK")
		r, _ = send(ad)
		assert r == "OK" and ad.calls == 2

	def test_timeout_retried(self):
		send = self.use(_fx_send)
		ad = Adapter(TimeoutError(), "OK")
		r, _ = send(ad)
		assert r == "OK"

	def test_retry_after_honoured(self):
		send = self.use(_fx_send)
		err = SlackApiError("m", "ratelimited", 429)
		err.retry_after = 7
		r, sleeps = send(Adapter(err, "OK"))
		assert sleeps == [7.0]

	def test_retry_after_capped(self):
		send = self.use(_fx_send)
		err = SlackApiError("m", "ratelimited", 429)
		err.retry_after = 9999
		_, sleeps = send(Adapter(err, "OK"))
		assert sleeps == [gateway_webhook.SEND_MAX_DELAY]

	def test_http_error_response_status(self):
		send = self.use(_fx_send)
		class HTTPError(Exception):
			response = SimpleNamespace(status_code=503, headers={"Retry-After": "3"})

		r, sleeps = send(Adapter(HTTPError(), "OK"))
		assert r == "OK" and sleeps == [3.0]
		class Bad(Exception):
			response = SimpleNamespace(status_code=404, headers={})

		ad = Adapter(Bad(), "OK")
		r, _ = send(ad)
		assert isinstance(r, Bad) and ad.calls == 1

	def test_no_resend_after_success(self):
		send = self.use(_fx_send)
		ad = Adapter("RCPT", "SECOND")
		r, sleeps = send(ad)
		assert r == "RCPT" and ad.calls == 1 and sleeps == []

	def test_adapter_lookup_error_not_retried(self):
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(gateway_webhook, "get_gateway_adapter", MagicMock(side_effect=RuntimeError("none")))
		with self.assertRaises(RuntimeError):
			gateway_webhook.send_gateway_reply(GW, SimpleNamespace(conversation_id="c", thread_id=""), "x")

	# ---- run idempotency ----
	def test_redelivered_event_not_queued_is_noop(self):
		monkeypatch = self.monkeypatch
		if gateway_service is None:
			self.skipTest("gateway_service not importable in stub env")

		for status in ("Running", "Succeeded", "Failed", "Rejected"):
			doc = SimpleNamespace(name="GE-9", status=status)
			get_doc = MagicMock(return_value=doc)
			monkeypatch.setattr(gateway_service.frappe, "get_doc", get_doc)
			assert gateway_service.process_gateway_event("GE-9") == {"event_name": "GE-9", "status": status}
			get_doc.assert_called_once_with("Gateway Event", "GE-9")

	def test_run_idempotency_key_format_documented(self):
		import inspect

		if gateway_service is None:
			self.skipTest("gateway_service not importable in stub env")

		src = inspect.getsource(gateway_service)
		assert 'client_idempotency_key=f"gateway-event:{event.name}"' in src

	def test_unapproved_room_gets_one_private_hint_per_channel(self):
		env = self.use(_fx_env)
		reason = reliability.ROOM_NOT_APPROVED_REASON
		reliability.on_event_rejected(GW, ev("GE-1"), "Rejected", reason)
		reliability.on_event_rejected(GW, ev("GE-2"), "Rejected", reason)
		assert len(env.sent) == 1 and "admin" in env.sent[0][2].lower()

	def test_unapproved_direct_message_stays_silent(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(conversation_id="D1"), "Rejected", reliability.ROOM_NOT_APPROVED_REASON)
		assert env.sent == []

	def test_notice_thread_rules(self):
		assert reliability._notice_thread("D1", "1.1", "1.1") is None
		assert reliability._notice_thread("C1", "1.1", "1.1") is None  # top-level message: own ts is not a real thread
		assert reliability._notice_thread("C1", "1.1", "2.2") == "1.1"  # reply inside a real thread

	def test_unapproved_room_hint_is_posted_top_level_for_top_level_message(self):
		env = self.use(_fx_env)
		reliability.on_event_rejected(GW, ev(thread_id="222.3", provider_event_id="C1:222.3"), "Rejected",
			reliability.ROOM_NOT_APPROVED_REASON)
		assert env.sent and env.sent[0][1] in (None, "")

	def test_replayed_event_runs_pre_ingest_filters_and_is_rejected(self):
		"""Reaper / dead-letter replay (filters_checked=False) must not bypass the tenant filter."""
		monkeypatch = self.monkeypatch
		if gateway_service is None:
			self.skipTest("gateway_service not importable in stub env")
		rejected = []
		gw = SimpleNamespace(name="gw1", provider="Microsoft Teams", is_enabled=1)
		monkeypatch.setattr(gateway_service.frappe, "get_doc", lambda *a, **k: gw, raising=False)
		monkeypatch.setattr(gateway_service.frappe, "flags", SimpleNamespace(gateway_filter_reason=None), raising=False)
		monkeypatch.setattr(hooks, "register_all", lambda: None)
		monkeypatch.setattr(hooks, "call_filters", lambda hook, g, ctx: False)
		monkeypatch.setattr(gateway_service, "_reject_gateway_event", lambda g, e, s, r: rejected.append((s, r)))
		event = SimpleNamespace(name="GE-9", raw_payload='{"channelData": {"tenant": {"id": "x"}}}')
		out = gateway_service._continue_ingest(event, "gw1", "pid", {"kind": "message"}, True)
		assert out["status"] == "Rejected" and rejected == [("Rejected", "Dropped by an ingest filter")]
