"""Repo-root pytest bootstrap for bench-less runs.

``huf/__init__.py`` does ``import frappe`` unconditionally, so pytest cannot even import a test
module under ``huf/`` on a machine without frappe. When (and only when) the real ``frappe`` is not
importable, install an auto-stub so pure-logic tests (e.g. ``huf/ai/graph/tests``) can run with plain
``python -m pytest``. On a bench the real package is importable and this file does nothing.
"""

import importlib.abc
import importlib.machinery
import sys
from unittest.mock import MagicMock

try:
	import frappe  # noqa: F401
except ImportError:

	class _Loader(importlib.abc.Loader):
		def create_module(self, spec):
			module = MagicMock(name=spec.name)
			module.__path__ = []
			module.__spec__ = spec
			module.__name__ = spec.name
			return module

		def exec_module(self, module):
			pass

	class _Finder(importlib.abc.MetaPathFinder):
		def find_spec(self, name, path, target=None):
			if name == "frappe" or name.startswith("frappe."):
				return importlib.machinery.ModuleSpec(name, _Loader(), is_package=True)
			return None

	sys.meta_path.insert(0, _Finder())
