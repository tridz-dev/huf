# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Shared sys.modules stubbing for standalone (frappe-less, litellm-less) test runs.

`huf/ai/tests/conftest.py` stubs a bare `frappe` MagicMock, which is enough for
modules that only ever do `import frappe` / `frappe.something(...)`. Several of
the modules under test here also do submodule-style imports —
`from frappe.utils import now`, `from frappe.tests import UnitTestCase`,
`from litellm.utils import trim_messages`, `from litellm import token_counter`,
`from agents.tool_context import ToolContext` — which a bare MagicMock cannot
satisfy (`ModuleNotFoundError: 'frappe' is not a package`). This module installs
proper (empty-but-importable) submodules for exactly those import sites so the
real production code under test — `huf.ai.providers.litellm`,
`huf.ai.context_segments`, `huf.ai.agent_run_analytics`, `huf.ai.cost_calculator`
— can be imported unmodified in this environment, where frappe is not installed
and the `litellm` package resolves to a broken/partial namespace install (see
`/opt/homebrew/lib/python3.14/site-packages/litellm.pth`, unrelated to this repo).

Call `install()` before importing any `huf.ai.*` module. Safe to call multiple
times (idempotent — checks `sys.modules` first).

Every stub here is gated on the corresponding real package being absent. That
gate is not a nicety: these test modules are also collected by `bench run-tests
--app huf`, in a process that has the real frappe, litellm and agents packages
loaded and a live site connected. Stubbing unconditionally used to reach into
the *real* `frappe.utils` and replace `now_datetime`/`now`/`add_to_date` with
MagicMocks for the rest of the process, which aborted the whole run the next
time frappe did date arithmetic against the database (`throttle_user_creation`
-> `get_creation_count`), and swapped the real `frappe.tests.UnitTestCase` for
an empty class, silently de-registering every test that subclassed it.
"""

import importlib.util
import json
import sys
import types
from unittest.mock import MagicMock


def _make_module(name):
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _is_real_package(name):
    """True when `name` resolves to a genuinely installed package.

    A module we (or conftest) put in `sys.modules` ourselves is a MagicMock or
    a bare `types.ModuleType` with no `__file__`; a real installed package has
    one. A package that only resolves as an empty namespace (the broken local
    `litellm` install this module exists to work around) also counts as absent.
    """
    module = sys.modules.get(name)
    if module is not None:
        return not isinstance(module, MagicMock) and getattr(module, "__file__", None) is not None
    try:
        spec = importlib.util.find_spec(name)
    except Exception:
        # find_spec imports parent packages, and a parent may itself blow up in
        # a stubbed environment. Treat anything unresolvable as absent.
        return False
    return spec is not None and spec.origin is not None


def install():
    # Each section is skipped outright when the real package is installed --
    # under `bench run-tests` these stubs would otherwise mutate the live
    # modules for the whole process. See the module docstring.
    if not _is_real_package("frappe"):
        # --- frappe -------------------------------------------------------
        if "frappe" not in sys.modules or not hasattr(sys.modules["frappe"], "__path__"):
            frappe = MagicMock(name="frappe")
            frappe.__path__ = []  # makes `frappe` importable as a package
            sys.modules["frappe"] = frappe
        frappe = sys.modules["frappe"]
        # `frappe.as_json` is used by huf.ai.context_segments to serialize tool
        # calls before token-counting them. A bare MagicMock return value has no
        # real length/content, which silently zeroes out any test relying on the
        # serialized text -- wire it to the real json.dumps so counting behaves
        # like it does in production.
        frappe.as_json = lambda obj, **kwargs: json.dumps(obj)

        frappe_utils = _make_module("frappe.utils")
        frappe_utils.now = MagicMock(return_value="2026-01-01 00:00:00")
        frappe_utils.add_to_date = MagicMock()
        frappe_utils.get_datetime = MagicMock(side_effect=lambda v: v)
        frappe_utils.now_datetime = MagicMock()
        # Identity passthrough is enough for tests that never exercise the
        # aware/naive normalisation itself (agent_run_analytics_api.py imports
        # this at module level, so it must exist for the module to import at
        # all) -- tests that actually need real tz-conversion behaviour talk to
        # a live bench instead, since pytz's tzdata isn't available here.
        frappe_utils.convert_utc_to_system_timezone = MagicMock(side_effect=lambda v: v)
        frappe.utils = frappe_utils

        frappe_tests = _make_module("frappe.tests")

        class UnitTestCase:
            pass

        frappe_tests.UnitTestCase = UnitTestCase
        frappe.tests = frappe_tests

    if not _is_real_package("litellm"):
        # --- litellm --------------------------------------------------------
        # The real `litellm` package (pip-installed, version 1.95.0) is shadowed in
        # this environment by an unrelated broken namespace package at
        # /private/tmp/litellm_work — `import litellm` succeeds but exposes no
        # attributes at all. Stub it fully rather than depending on that install.
        if "litellm" not in sys.modules or not isinstance(sys.modules["litellm"], MagicMock):
            litellm_mock = MagicMock(name="litellm")

            class InternalServerError(Exception):
                pass

            class RateLimitError(Exception):
                pass

            class APIError(Exception):
                pass

            class BadRequestError(Exception):
                pass

            class ContextWindowExceededError(Exception):
                pass

            litellm_mock.InternalServerError = InternalServerError
            litellm_mock.RateLimitError = RateLimitError
            litellm_mock.APIError = APIError
            litellm_mock.BadRequestError = BadRequestError
            litellm_mock.ContextWindowExceededError = ContextWindowExceededError
            litellm_mock.token_counter = MagicMock(return_value=0)
            sys.modules["litellm"] = litellm_mock

        litellm_utils = _make_module("litellm.utils")
        litellm_utils.trim_messages = MagicMock()

    if not _is_real_package("agents"):
        # --- agents (OpenAI Agents SDK) --------------------------------------
        _make_module("agents")
        agents_tool_context = _make_module("agents.tool_context")

        class ToolContext:
            def __init__(self, *args, **kwargs):
                pass

        agents_tool_context.ToolContext = ToolContext

        agents_usage = _make_module("agents.usage")

        class Usage:
            pass

        agents_usage.Usage = Usage

        agents = sys.modules["agents"]

        class FunctionTool:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        agents.FunctionTool = FunctionTool

    # --- huf / huf.ai / huf.ai.providers packages ------------------------
    # sys.path already has the repo root on it when tests are run from there;
    # these just need to exist as importable packages pointing at the real
    # on-disk source so `import huf.ai.providers.litellm` etc. resolve normally.
    #
    # Gated the same way as the sections above. Under a bench, `huf` is a real
    # installed package but its subpackages are often not imported yet, so an
    # ungated `_make_module("huf.ai.providers")` inserts a bare module with a
    # repo-relative `__path__` ahead of the real one, and every later
    # `import huf.ai.providers.litellm` fails with ModuleNotFoundError.
    for name, rel_path in (
        ("huf", "huf"),
        ("huf.ai", "huf/ai"),
        ("huf.ai.providers", "huf/ai/providers"),
    ):
        if _is_real_package(name):
            continue
        pkg = _make_module(name)
        if not hasattr(pkg, "__path__"):
            pkg.__path__ = [rel_path]
