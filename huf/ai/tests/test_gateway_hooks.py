import sys
import types
from types import SimpleNamespace

import pytest

from huf.ai.gateways import hooks


@pytest.fixture(autouse=True)
def _clean():
	hooks.clear()
	yield
	hooks.clear()


def gw(provider="Slack"):
	return SimpleNamespace(provider=provider)


def test_priority_order_and_call_all():
	hooks.register("h", lambda g: "b", priority=200)
	hooks.register("h", lambda g: "a", priority=10)
	hooks.register("h", lambda g: "c", priority=200)
	assert hooks.call_all("h", gw()) == ["a", "b", "c"]


def test_provider_filter_case_insensitive():
	hooks.register("h", lambda g: "slack", provider="SLACK")
	hooks.register("h", lambda g: "any")
	assert hooks.call_all("h", gw("slack")) == ["slack", "any"]
	assert hooks.call_all("h", gw("Discord")) == ["any"]


def test_call_first_skips_none():
	hooks.register("h", lambda g: None, priority=1)
	hooks.register("h", lambda g: "x", priority=2)
	hooks.register("h", lambda g: "y", priority=3)
	assert hooks.call_first("h", gw()) == "x"
	assert hooks.call_first("missing", gw()) is None


def test_call_chain_threads_value():
	hooks.register("p", lambda g, e, t: t + "1", priority=1)
	hooks.register("p", lambda g, e, t: None, priority=2)
	hooks.register("p", lambda g, e, t: t + "2", priority=3)
	assert hooks.call_chain("p", "t", gw(), "ev") == "t12"


def test_denied_propagates():
	def deny(g):
		raise hooks.GatewayHookDenied("nope")

	hooks.register("h", deny)
	with pytest.raises(hooks.GatewayHookDenied) as ei:
		hooks.call_all("h", gw())
	assert ei.value.reason == "nope"


def test_exception_isolated_and_logged(monkeypatch):
	logged = []
	monkeypatch.setattr(hooks.frappe, "log_error", lambda *a, **k: logged.append(a), raising=False)
	monkeypatch.setattr(hooks.frappe, "get_traceback", lambda: "tb", raising=False)

	def boom(g):
		raise RuntimeError("x")

	hooks.register("h", boom, priority=1)
	hooks.register("h", lambda g: "ok", priority=2)
	assert hooks.call_all("h", gw()) == ["ok"]
	assert len(logged) == 1


def test_clear():
	hooks.register("h", lambda g: 1)
	hooks.clear()
	assert hooks.call_all("h", gw()) == []


def test_register_all_idempotent(monkeypatch):
	mod = types.ModuleType("fake_w0_mod")
	mod.count = 0
	sys.modules["fake_w0_mod"] = mod
	from huf.ai.gateways import _registered

	monkeypatch.setattr(_registered, "MODULES", ("fake_w0_mod",))
	calls = []
	import importlib

	real = importlib.import_module
	monkeypatch.setattr(hooks.importlib, "import_module", lambda n: calls.append(n) or real(n))
	hooks.register_all()
	hooks.register_all()
	assert calls == ["fake_w0_mod"]


def test_event_rejected_hook_dispatches():
	hooks.clear()
	seen = []
	hooks.register(hooks.ON_EVENT_REJECTED, lambda gw, ev, status, reason: seen.append((status, reason)))
	hooks.call_all(hooks.ON_EVENT_REJECTED, object(), object(), "Rejected", "why")
	assert seen == [("Rejected", "why")]
