import sys
import types
from types import SimpleNamespace

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.gateways import hooks


def _fx_clean(self):
	hooks.clear()
	yield
	hooks.clear()


def gw(provider="Slack"):
	return SimpleNamespace(provider=provider)




















# --- call_filters (T16): stop at first False, fail closed on exceptions -------------------------


def _flags(monkeypatch):
	import frappe

	monkeypatch.setattr(frappe, "flags", SimpleNamespace(gateway_filter_reason=None), raising=False)
	return frappe.flags


_AUTOUSE = (_fx_clean,)


class TestModule(SupportCase):
	def test_priority_order_and_call_all(self):
		hooks.register("h", lambda g: "b", priority=200)
		hooks.register("h", lambda g: "a", priority=10)
		hooks.register("h", lambda g: "c", priority=200)
		assert hooks.call_all("h", gw()) == ["a", "b", "c"]

	def test_provider_filter_case_insensitive(self):
		hooks.register("h", lambda g: "slack", provider="SLACK")
		hooks.register("h", lambda g: "any")
		assert hooks.call_all("h", gw("slack")) == ["slack", "any"]
		assert hooks.call_all("h", gw("Discord")) == ["any"]

	def test_call_first_skips_none(self):
		hooks.register("h", lambda g: None, priority=1)
		hooks.register("h", lambda g: "x", priority=2)
		hooks.register("h", lambda g: "y", priority=3)
		assert hooks.call_first("h", gw()) == "x"
		assert hooks.call_first("missing", gw()) is None

	def test_call_chain_threads_value(self):
		hooks.register("p", lambda g, e, t: t + "1", priority=1)
		hooks.register("p", lambda g, e, t: None, priority=2)
		hooks.register("p", lambda g, e, t: t + "2", priority=3)
		assert hooks.call_chain("p", "t", gw(), "ev") == "t12"

	def test_denied_propagates(self):
		def deny(g):
			raise hooks.GatewayHookDenied("nope")

		hooks.register("h", deny)
		with self.assertRaises(hooks.GatewayHookDenied) as ei:
			hooks.call_all("h", gw())
		assert ei.exception.reason == "nope"

	def test_exception_isolated_and_logged(self):
		monkeypatch = self.monkeypatch
		logged = []
		monkeypatch.setattr(hooks.frappe, "log_error", lambda *a, **k: logged.append(a), raising=False)
		monkeypatch.setattr(hooks.frappe, "get_traceback", lambda: "tb", raising=False)

		def boom(g):
			raise RuntimeError("x")

		hooks.register("h", boom, priority=1)
		hooks.register("h", lambda g: "ok", priority=2)
		assert hooks.call_all("h", gw()) == ["ok"]
		assert len(logged) == 1

	def test_clear(self):
		hooks.register("h", lambda g: 1)
		hooks.clear()
		assert hooks.call_all("h", gw()) == []

	def test_register_all_idempotent(self):
		monkeypatch = self.monkeypatch
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

	def test_event_rejected_hook_dispatches(self):
		hooks.clear()
		seen = []
		hooks.register(hooks.ON_EVENT_REJECTED, lambda gw, ev, status, reason: seen.append((status, reason)))
		hooks.call_all(hooks.ON_EVENT_REJECTED, object(), object(), "Rejected", "why")
		assert seen == [("Rejected", "why")]

	def test_call_filters_all_pass_and_none_is_pass(self):
		monkeypatch = self.monkeypatch
		_flags(monkeypatch)
		hooks.register("f", lambda g: True, priority=1)
		hooks.register("f", lambda g: None, priority=2)
		assert hooks.call_filters("f", gw()) is True
		assert hooks.call_filters("missing", gw()) is True

	def test_call_filters_stops_at_first_false_in_priority_order(self):
		monkeypatch = self.monkeypatch
		_flags(monkeypatch)
		seen = []
		hooks.register("f", lambda g: seen.append("c") or True, priority=30)
		hooks.register("f", lambda g: seen.append("a") or True, priority=10)
		hooks.register("f", lambda g: seen.append("b") or False, priority=20)
		assert hooks.call_filters("f", gw()) is False
		assert seen == ["a", "b"]

	def test_call_filters_exception_is_false_with_generic_reason(self):
		monkeypatch = self.monkeypatch
		flags = _flags(monkeypatch)
		seen = []

		def boom(g):
			raise RuntimeError("secret detail")

		hooks.register("f", boom, priority=1)
		hooks.register("f", lambda g: seen.append("later") or True, priority=2)
		assert hooks.call_filters("f", gw()) is False
		assert seen == [] and flags.gateway_filter_reason == "filter_error"

	def test_call_filters_exception_keeps_reason_a_filter_set(self):
		monkeypatch = self.monkeypatch
		flags = _flags(monkeypatch)

		def boom(g):
			flags.gateway_filter_reason = "specific"
			raise RuntimeError("x")

		hooks.register("f", boom)
		assert hooks.call_filters("f", gw()) is False
		assert flags.gateway_filter_reason == "specific"

	def test_call_filters_respects_provider(self):
		monkeypatch = self.monkeypatch
		_flags(monkeypatch)
		hooks.register("f", lambda g: False, provider="teams")
		assert hooks.call_filters("f", gw("Slack")) is True
		assert hooks.call_filters("f", gw("Teams")) is False

	def test_call_filters_denied_propagates(self):
		monkeypatch = self.monkeypatch
		_flags(monkeypatch)

		def deny(g):
			raise hooks.GatewayHookDenied("no")

		hooks.register("f", deny)
		with self.assertRaises(hooks.GatewayHookDenied):
			hooks.call_filters("f", gw())
