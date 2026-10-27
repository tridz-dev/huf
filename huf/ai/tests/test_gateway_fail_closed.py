"""Fail-closed identity (S8 fix 1) and tool-gate fail-closed (fix 5)."""

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "huf/ai/tests")
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
