"""Fail-closed identity (S8 fix 1) and tool-gate fail-closed (fix 5)."""

import importlib
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import hooks  # noqa: E402

gateway_service = None


@pytest.fixture(scope="module", autouse=True)
def _heavy_modules():
	global gateway_service

	def mod(name, **attrs):
		m = types.ModuleType(name)
		m.__dict__.update(attrs)
		return m

	pkg = mod("huf.ai.gateway_adapters")
	pkg.__path__ = []
	stubs = {
		"frappe.rate_limiter": mod("frappe.rate_limiter", rate_limit=lambda **k: (lambda f: f)),
		"huf.ai.gateway_adapters": pkg,
		"huf.ai.gateway_adapters.provider_ids": mod("p", provider_to_service_id=lambda x: x),
		"huf.ai.gateway_adapters.registered": mod("r", get_adapter_class=lambda *a, **k: None),
		"huf.ai.gateway_adapters.types": mod("t", GatewayReply=object),
	}
	owned = ("huf.ai.gateway_webhook", "huf.ai.gateway_service")
	saved = {k: sys.modules.get(k) for k in (*stubs, *owned)}
	sys.modules.update(stubs)
	for k in owned:
		sys.modules.pop(k, None)
	try:
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
		gateway_service = None


@pytest.fixture(autouse=True)
def _clean():
	hooks.clear()
	yield
	hooks.clear()


def gw(provider="Slack"):
	return SimpleNamespace(provider=provider)


# ---- hooks ----
def test_call_first_strict_converts_exception_to_denied(monkeypatch):
	monkeypatch.setattr(hooks.frappe, "log_error", lambda *a, **k: None, raising=False)
	monkeypatch.setattr(hooks.frappe, "get_traceback", lambda: "tb", raising=False)

	def boom(g, e):
		raise RuntimeError("secret detail")

	hooks.register("h", boom)
	with pytest.raises(hooks.GatewayHookDenied) as ei:
		hooks.call_first("h", gw(), None, strict=True)
	assert ei.value.reason == hooks.STRICT_DENIED_REASON
	assert "secret" not in ei.value.reason
	assert not ei.value.reason.startswith(hooks.USER_VISIBLE_PREFIX)
	# non-strict keeps the old skip behaviour
	assert hooks.call_first("h", gw(), None) is None


def test_has_handler_respects_provider():
	hooks.register("h", lambda g, e: 1, provider="slack")
	assert hooks.has_handler("h", gw("Slack"))
	assert not hooks.has_handler("h", gw("Telegram"))
	assert not hooks.has_handler("nope", gw("Slack"))


def test_register_all_failure_isolated_and_flag_after_loop(monkeypatch):
	from huf.ai.gateways import _registered

	good = types.ModuleType("fake_s8_good")
	sys.modules["fake_s8_good"] = good
	monkeypatch.setattr(hooks.frappe, "log_error", lambda *a, **k: None, raising=False)
	monkeypatch.setattr(hooks.frappe, "get_traceback", lambda: "tb", raising=False)
	monkeypatch.setattr(_registered, "MODULES", ("fake_s8_missing_mod", "fake_s8_good"))
	imported = []
	real = importlib.import_module

	def spy(name, *a, **k):
		imported.append(name)
		return real(name, *a, **k)

	monkeypatch.setattr(importlib, "import_module", spy)
	try:
		hooks.register_all()
	finally:
		sys.modules.pop("fake_s8_good", None)
	assert imported == ["fake_s8_missing_mod", "fake_s8_good"]
	assert hooks.registration_failures() == ["fake_s8_missing_mod"]
	assert hooks._REGISTERED is True


# ---- gateway_service ----
def _run(monkeypatch, provider, handler=None, policy=None):
	if gateway_service is None:
		pytest.skip("gateway_service not importable in stub env")
	event = MagicMock()
	event.name = "GE-1"
	event.status = "Queued"
	event.gateway = "G"
	event.target_type = "Flow"
	gateway = SimpleNamespace(
		name="G", provider=provider, is_enabled=1, execution_user="svc@x", unmapped_policy=policy
	)

	def get_doc(dt, name=None):
		return event if dt == "Gateway Event" else gateway

	monkeypatch.setattr(gateway_service.frappe, "get_doc", get_doc, raising=False)
	monkeypatch.setattr(hooks, "register_all", lambda: None)
	monkeypatch.setattr(hooks.frappe, "log_error", lambda *a, **k: None, raising=False)
	monkeypatch.setattr(hooks.frappe, "get_traceback", lambda: "tb", raising=False)
	seen = {}
	monkeypatch.setattr(gateway_service.frappe, "set_user", lambda u: seen.setdefault("user", u), raising=False)
	if handler:
		hooks.register(hooks.RESOLVE_RUN_USER, handler, provider=provider)
	rejected = []
	hooks.register(hooks.ON_EVENT_REJECTED, lambda g, e, s, r: rejected.append((s, r)))
	# stop right after identity resolution when it succeeds
	monkeypatch.setattr(
		hooks, "call_all",
		(lambda orig: lambda h, *a, **k: (_ for _ in ()).throw(StopIteration) if h == hooks.ON_RUN_START else orig(h, *a, **k))(hooks.call_all),
	)
	try:
		out = gateway_service.process_gateway_event("GE-1")
	except StopIteration:
		out = None
	return out, rejected, seen


def test_slack_without_identity_handler_rejected(monkeypatch):
	out, rejected, seen = _run(monkeypatch, "Slack")
	assert out["status"] == "Rejected"
	assert rejected == [("Rejected", "Identity checking is unavailable")]
	assert "user" not in seen


def test_slack_handler_error_rejected_not_service_user(monkeypatch):
	def boom(g, e):
		raise RuntimeError("auth.test down")

	out, rejected, seen = _run(monkeypatch, "Slack", boom, "Ask to link account")
	assert out["status"] == "Rejected"
	assert rejected[0][1] == "Identity checking is unavailable"
	assert "user" not in seen


def test_slack_service_policy_none_falls_back_when_handler_ran(monkeypatch):
	out, rejected, seen = _run(monkeypatch, "Slack", lambda g, e: None, "Use service user")
	assert rejected == []
	assert seen["user"] == "svc@x"


def test_other_provider_keeps_fallback_without_handler(monkeypatch):
	out, rejected, seen = _run(monkeypatch, "Telegram")
	assert rejected == []
	assert seen["user"] == "svc@x"


# ---- privacy fail-closed target vs. the real adapter's send path (S8 fix 9) ----
def _real_adapter_send(target, posted):
	"""Drive the REAL Slack adapter's send_reply with a fake HTTP layer that behaves like Slack:
	channel ids (C/G/D) and user ids (U/W) are accepted, anything else is channel_not_found."""
	# Load the real adapter package (the module fixture stubs it); restore everything after.
	saved = {k: v for k, v in sys.modules.items() if k.startswith("huf.ai.gateway_adapters")}
	for k in saved:
		sys.modules.pop(k)
	import os

	shim = types.ModuleType("huf.ai.gateway_adapters")  # skip the package __init__ (heavy imports)
	shim.__path__ = [os.path.join(os.path.dirname(__file__), "..", "gateway_adapters")]
	sys.modules["huf.ai.gateway_adapters"] = shim
	try:
		adapter_mod = importlib.import_module("huf.ai.gateway_adapters.slack")
		types_mod = importlib.import_module("huf.ai.gateway_adapters.types")
	finally:
		for k in [k for k in sys.modules if k.startswith("huf.ai.gateway_adapters")]:
			sys.modules.pop(k)
		sys.modules.update(saved)
		pkg = sys.modules.get("huf.ai")
		if pkg is not None and hasattr(pkg, "gateway_adapters"):
			delattr(pkg, "gateway_adapters")

	def http_post(url, *, headers, json_data, timeout):
		posted.append(dict(json_data))
		ok = str(json_data["channel"])[:1] in "CGDUW" and json_data["channel"].isalnum()
		return {"ok": True, "ts": "1.2"} if ok else {"ok": False, "error": "channel_not_found"}

	adapter = adapter_mod.SlackGatewayAdapter({"token": "xoxb-test"}, http_post=http_post)
	reply = types_mod.GatewayReply(conversation_id=target, text="private answer", thread_id=None)
	return adapter.send_reply(reply)


def test_privacy_fail_closed_target_never_reaches_origin_channel(monkeypatch):
	"""Residual risk (documented): a bare ``U...`` id works with chat.postMessage only when the
	app's Messages tab is enabled (the generated manifest enables it). If Slack ever rejected
	it, the adapter raises and the event is marked Failed; it still never posts to the channel."""
	privacy = importlib.import_module("huf.ai.gateways.slack.privacy")
	api = SimpleNamespace(
		conversations_open=MagicMock(side_effect=RuntimeError("missing_scope")),
		post_message=MagicMock(),
	)
	monkeypatch.setattr(privacy, "get_slack_api", lambda g, **k: api)
	for sender, expect_ok in (("U1", True), ("", False)):
		event = SimpleNamespace(conversation_id="C1", thread_id="111.2", sender_id=sender)
		target = privacy.resolve_reply_target(
			SimpleNamespace(provider="Slack", private_reply_policy="Always private"), event, "private answer"
		)
		assert target and target != "C1" and not target.startswith("C")
		posted = []
		if expect_ok:
			assert _real_adapter_send(target, posted).provider_message_id == "1.2"
		else:
			with pytest.raises(ValueError):
				_real_adapter_send(target, posted)
		assert all(p["channel"] != "C1" for p in posted)
		assert event.thread_id is None  # no channel thread is addressed either
