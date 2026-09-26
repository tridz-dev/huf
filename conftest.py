"""Repo-root pytest conftest.

Sandbox/CI environments that run these tests outside a full Frappe bench have
no `frappe`, `litellm`, or `agents` (openai-agents SDK) packages installed at
all. `huf/ai/tests/conftest.py` already stubs `frappe` for exactly this case,
but that stub runs too late for any test module that imports
`huf.ai.agent_integration` or `huf.ai.run`: pytest resolves that inner
conftest's own dotted module name (`huf.ai.tests.conftest`) by first importing
the `huf` package, and `huf/__init__.py` does `import frappe` unconditionally
at the top — before the inner conftest's stubbing code ever runs.

This root conftest (outside the `huf` package, so pytest imports it as a bare
`conftest` module with no package machinery) runs first, before any other
conftest or test module in this tree. If a real `frappe` is already
installed (e.g. inside an actual Frappe bench's Python environment), this is
a complete no-op. Only in the "run these unit tests standalone" case does it
install stubs, by executing the bootstrap module used by
`huf/ai/tests/subscription/test_executor_passthrough.py` (and any other
subscription test that needs `agent_integration.py`/`run.py`) directly by
file path, so loading it never itself triggers importing `huf`.
"""

from __future__ import annotations

import importlib.util
import os

try:
	import frappe  # noqa: F401

	_HAS_REAL_FRAPPE = True
except ImportError:
	_HAS_REAL_FRAPPE = False

if not _HAS_REAL_FRAPPE:
	_bootstrap_path = os.path.join(
		os.path.dirname(__file__),
		"huf",
		"ai",
		"tests",
		"subscription",
		"_stub_bootstrap.py",
	)
	if os.path.exists(_bootstrap_path):
		_spec = importlib.util.spec_from_file_location("_huf_test_stub_bootstrap", _bootstrap_path)
		_module = importlib.util.module_from_spec(_spec)
		_spec.loader.exec_module(_module)
