"""Shared stub bootstrap for tests that need to import `huf.ai.agent_integration`
or `huf.ai.run` without a live Frappe bench / litellm / openai-agents install.

This sandbox has none of those packages available, and the existing
`huf/ai/tests/conftest.py` (which stubs `frappe`) runs too late for a module
that imports `frappe` at package-`__init__` time (`huf/__init__.py`) - the act
of importing the conftest module itself imports `huf`, before the conftest
body runs. Tests that need `agent_integration.py` import this bootstrap module
FIRST (before anything under the `huf` namespace) to install every stub.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock


class _AutoStubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
	"""Auto-create any `frappe.*` submodule as an empty MagicMock-backed stub.

	`agent_integration.py`'s dependency chain reaches into many `frappe.utils.*`
	/ `frappe.model.*` / etc. submodules this sandbox doesn't have installed.
	Rather than hand-stub each one, this finder intercepts any not-yet-resolved
	`frappe.<...>` import and manufactures a stub module for it on demand, so
	the real `huf.ai.*` source can be imported and exercised unmodified.
	"""

	PREFIXES = ("frappe.", "litellm.", "agents.")

	def find_spec(self, name, path, target=None):
		if name.startswith(self.PREFIXES) and name not in sys.modules:
			return importlib.machinery.ModuleSpec(name, self, is_package=True)
		return None

	def create_module(self, spec):
		mod = types.ModuleType(spec.name)
		mod.__path__ = []  # pretend to be a package so deeper imports keep working
		mod.__getattr__ = lambda attr: MagicMock()  # noqa: ARG005
		return mod

	def exec_module(self, module):
		pass


sys.meta_path.insert(0, _AutoStubFinder())


def _install(name: str, module: types.ModuleType | None = None) -> types.ModuleType:
	if name in sys.modules:
		return sys.modules[name]
	mod = module or MagicMock()
	sys.modules[name] = mod
	return mod


if "frappe" not in sys.modules:
	frappe_mod = types.ModuleType("frappe")
	frappe_mod._is_stub = True

	class _StubException(Exception):
		pass

	for exc_name in (
		"ValidationError",
		"PermissionError",
		"DoesNotExistError",
		"TimestampMismatchError",
	):
		setattr(frappe_mod, exc_name, type(exc_name, (_StubException,), {}))

	frappe_mod.get_doc = MagicMock()
	frappe_mod.get_cached_doc = MagicMock()
	frappe_mod.get_cached_value = MagicMock()
	frappe_mod.get_all = MagicMock(return_value=[])
	frappe_mod.db = MagicMock()
	frappe_mod.cache = MagicMock()
	frappe_mod.session = types.SimpleNamespace(user="test@example.com")
	frappe_mod.flags = types.SimpleNamespace()
	frappe_mod.throw = MagicMock(side_effect=lambda *a, **k: (_ for _ in ()).throw(frappe_mod.ValidationError(*a)))
	frappe_mod.log_error = MagicMock()
	frappe_mod.logger = MagicMock(return_value=MagicMock())
	frappe_mod.publish_realtime = MagicMock()
	frappe_mod.as_json = staticmethod(lambda v: v)
	frappe_mod.parse_json = staticmethod(lambda v: v)
	frappe_mod.has_permission = MagicMock(return_value=True)
	frappe_mod.whitelist = lambda *a, **k: (lambda f: f)
	frappe_mod._ = lambda s: s

	utils_mod = types.ModuleType("frappe.utils")
	utils_mod.__path__ = []  # pretend to be a package so frappe.utils.<x> auto-stubs
	utils_mod.__getattr__ = lambda attr: MagicMock()  # noqa: ARG005
	utils_mod.now_datetime = MagicMock(side_effect=lambda: __import__("datetime").datetime.now())
	utils_mod.add_to_date = MagicMock(return_value="2026-09-26T00:00:00Z")

	background_jobs_mod = types.ModuleType("frappe.utils.background_jobs")
	background_jobs_mod.enqueue = MagicMock()

	rate_limiter_mod = types.ModuleType("frappe.rate_limiter")
	rate_limiter_mod.rate_limit = lambda *a, **k: (lambda f: f)

	frappe_mod.enqueue = MagicMock()
	frappe_mod.utils = utils_mod

	# PEP 562 module __getattr__: any attribute not explicitly stubbed above
	# (e.g. `frappe.client`, `frappe.model_wrapper`, ...) resolves to a fresh
	# MagicMock instead of raising AttributeError, so importing modules deep
	# in agent_integration.py's dependency chain never fails just because this
	# stub didn't anticipate one specific attribute.
	_frappe_dynamic_attrs: dict[str, MagicMock] = {}

	def _frappe_getattr(name):
		if name not in _frappe_dynamic_attrs:
			_frappe_dynamic_attrs[name] = MagicMock()
		return _frappe_dynamic_attrs[name]

	frappe_mod.__getattr__ = _frappe_getattr

	_install("frappe", frappe_mod)
	_install("frappe.utils", utils_mod)
	_install("frappe.utils.background_jobs", background_jobs_mod)
	_install("frappe.rate_limiter", rate_limiter_mod)
	_install("frappe.model")
	_install("frappe.model.document")
	sys.modules["frappe.model.document"].Document = object

litellm_mod = types.ModuleType("litellm")
litellm_mod.__path__ = []
litellm_mod.__getattr__ = lambda attr: MagicMock()  # noqa: ARG005
litellm_mod.token_counter = MagicMock(return_value=0)
_install("litellm", litellm_mod)

agents_mod = types.ModuleType("agents")
agents_mod.__path__ = []
agents_mod.__getattr__ = lambda attr: MagicMock()  # noqa: ARG005
for name in ("OpenAIProvider", "Agent", "Runner", "Tool", "function_tool", "ModelSettings"):
	setattr(agents_mod, name, MagicMock())
_install("agents", agents_mod)

__all__ = []
