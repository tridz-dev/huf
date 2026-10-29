"""unittest-side stand-ins for the pytest conveniences the gateway tests used.

``bench run-tests`` is unittest-only, so these tests must not import pytest.
``SupportCase`` gives each test a ``monkeypatch`` (auto-undone), a ``caplog`` and
``use(fixture_fn)`` which runs a fixture function once per test (generator
fixtures are finalised on cleanup).
"""

import contextlib
import importlib
import inspect
import logging
import unittest

_MISSING = object()


def _resolve(dotted):
	parts = dotted.split(".")
	for i in range(len(parts) - 1, 0, -1):
		try:
			obj = importlib.import_module(".".join(parts[:i]))
		except ImportError:
			continue
		for p in parts[i:-1]:
			obj = getattr(obj, p)
		return obj, parts[-1]
	raise ImportError(dotted)


class MonkeyPatch:
	def __init__(self):
		self._undo = []

	def setattr(self, target, name, value=_MISSING, raising=True):
		if value is _MISSING:
			value = name
			target, name = _resolve(target)
		old = getattr(target, name, _MISSING)
		if old is _MISSING and raising:
			raise AttributeError(f"{target!r} has no attribute {name!r}")
		if inspect.isclass(target):
			old = target.__dict__.get(name, old)
		self._undo.append(("attr", target, name, old))
		setattr(target, name, value)

	def delattr(self, target, name=_MISSING, raising=True):
		if name is _MISSING:
			target, name = _resolve(target)
		if not hasattr(target, name):
			if raising:
				raise AttributeError(name)
			return
		self._undo.append(("attr", target, name, getattr(target, name)))
		delattr(target, name)

	def setitem(self, dic, name, value):
		self._undo.append(("item", dic, name, dic.get(name, _MISSING)))
		dic[name] = value

	def delitem(self, dic, name, raising=True):
		if name not in dic:
			if raising:
				raise KeyError(name)
			return
		self._undo.append(("item", dic, name, dic[name]))
		del dic[name]

	def undo(self):
		for kind, obj, name, old in reversed(self._undo):
			if kind == "attr":
				if old is _MISSING:
					with contextlib.suppress(AttributeError):
						delattr(obj, name)
				else:
					setattr(obj, name, old)
			elif old is _MISSING:
				obj.pop(name, None)
			else:
				obj[name] = old
		self._undo = []

	@contextlib.contextmanager
	def context(self):
		m = MonkeyPatch()
		try:
			yield m
		finally:
			m.undo()


class _ListHandler(logging.Handler):
	def __init__(self):
		super().__init__(logging.NOTSET)
		self.records = []

	def emit(self, record):
		self.records.append(record)


class CapLog:
	def __init__(self):
		self.handler = _ListHandler()
		self.handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(message)s"))
		self._root = logging.getLogger()
		self._old_level = self._root.level
		self._root.addHandler(self.handler)

	@property
	def records(self):
		return self.handler.records

	@property
	def text(self):
		return "\n".join(self.handler.format(r) for r in self.records)

	def set_level(self, level, logger=None):
		if isinstance(level, str):
			level = logging.getLevelName(level.upper())
		logging.getLogger(logger).setLevel(level)

	def close(self):
		self._root.removeHandler(self.handler)
		self._root.setLevel(self._old_level)


class SupportCase(unittest.TestCase):
	def _callSetUp(self):
		import sys

		for fx in getattr(sys.modules[type(self).__module__], "_AUTOUSE", ()):
			self.use(fx)
		super()._callSetUp()

	@property
	def monkeypatch(self):
		return self._fx_cache_get("monkeypatch", self._make_monkeypatch)

	@property
	def caplog(self):
		return self._fx_cache_get("caplog", self._make_caplog)

	def _fin(self, fn):
		if "_fx_fins" not in self.__dict__:
			self._fx_fins = []
			self.addCleanup(self.reset_fixtures)
		self._fx_fins.append(fn)

	def reset_fixtures(self):
		"""Finalise and forget every fixture so far (pytest builds them fresh per parametrized case)."""
		fins = self.__dict__.get("_fx_fins", [])
		while fins:
			fins.pop()()
		self.__dict__.get("_fx_cache", {}).clear()

	def _make_monkeypatch(self):
		m = MonkeyPatch()
		self._fin(m.undo)
		return m

	def _make_caplog(self):
		c = CapLog()
		self._fin(c.close)
		return c

	def _fx_cache_get(self, key, make):
		cache = self.__dict__.setdefault("_fx_cache", {})
		if key not in cache:
			cache[key] = make()
		return cache[key]

	def use(self, fixture_fn):
		"""Run a fixture function (taking the test case) once per test."""

		def make():
			res = fixture_fn(self)
			if inspect.isgenerator(res):
				gen = res
				val = next(gen)

				def fin():
					for _ in gen:
						pass

				self._fin(fin)
				return val
			return res

		return self._fx_cache_get(fixture_fn, make)
