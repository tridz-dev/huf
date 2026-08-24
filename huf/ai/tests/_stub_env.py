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
"""

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


def install():
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
    frappe.utils = frappe_utils

    frappe_tests = _make_module("frappe.tests")

    class UnitTestCase:
        pass

    frappe_tests.UnitTestCase = UnitTestCase
    frappe.tests = frappe_tests

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

    # --- huf / huf.ai / huf.ai.providers packages ------------------------
    # sys.path already has the repo root on it when tests are run from there;
    # these just need to exist as importable packages pointing at the real
    # on-disk source so `import huf.ai.providers.litellm` etc. resolve normally.
    repo_pkg = _make_module("huf")
    if not hasattr(repo_pkg, "__path__"):
        repo_pkg.__path__ = ["huf"]

    ai_pkg = _make_module("huf.ai")
    if not hasattr(ai_pkg, "__path__"):
        ai_pkg.__path__ = ["huf/ai"]

    providers_pkg = _make_module("huf.ai.providers")
    if not hasattr(providers_pkg, "__path__"):
        providers_pkg.__path__ = ["huf/ai/providers"]
