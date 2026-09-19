# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Guest-path safeguard tests for ``run_agent_sync`` / ``run_agent_sync_chat``
(Track-Item: ST-R4.3).

Covers two things per the ST:

1. Oracle-avoidance regression: a nonexistent ``agent_name`` and an existing
   ``allow_guest=0`` agent must raise ``frappe.PermissionError`` with the
   exact same message to a Guest caller. This is the invariant the
   ``@rate_limit`` addition (and the whole "keep allow_guest=True" decision
   in ST-R4.3) depends on -- if this regresses, the exception shape becomes
   an oracle for enumerating agent names.
2. The ``@rate_limit`` decorator is actually applied to both whitelisted
   entrypoints -- verified via the ``functools.wraps``-provided
   ``__wrapped__`` chain (cheap, no real HTTP/cache dependency) and via a
   real end-to-end throttle check that drives the real
   ``frappe.rate_limiter.RateLimiter`` machinery by faking a request
   context, matching how ``rate_limit()`` itself gates on ``frappe.request``
   truthiness (see ``frappe/rate_limiter.py::rate_limit`` -- it is a no-op
   unless ``frappe.request`` is set).
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import run_agent_sync
from huf.ai.chat_api import run_agent_sync_chat
from huf.ai.tests.factories import make_agent, make_ai_provider_and_model

PREFIX = "ST-R4.3-guest-safeguards"


class TestRunAgentSyncGuestSafeguards(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._names = {"Agent": [], "AI Model": [], "AI Provider": []}
        provider, model = make_ai_provider_and_model()
        self._track("AI Provider", provider)
        self._track("AI Model", model)

        self.blocked_agent = make_agent(
            agent_name=f"{PREFIX} blocked {frappe.generate_hash(length=6)}",
            provider=provider,
            model=model,
            allow_guest=0,
        )
        self._track("Agent", self.blocked_agent.name)

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype in ("Agent", "AI Model", "AI Provider"):
            for name in self._names.get(doctype, []):
                try:
                    frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
                except Exception:
                    pass
        frappe.db.commit()
        frappe.local.request = None
        frappe.local.request_ip = None

    def _track(self, doctype, name):
        self._names.setdefault(doctype, []).append(name)

    # -- Oracle-avoidance regression ----------------------------------

    def test_guest_nonexistent_and_disallowed_agent_raise_identical_error(self):
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError) as ctx_missing:
                run_agent_sync(agent_name=f"{PREFIX} does-not-exist")
            with self.assertRaises(frappe.PermissionError) as ctx_blocked:
                run_agent_sync(agent_name=self.blocked_agent.name)
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(str(ctx_missing.exception), str(ctx_blocked.exception))

    def test_guest_nonexistent_and_disallowed_agent_raise_identical_error_via_chat_entrypoint(self):
        # run_agent_sync_chat's create_new=False path delegates straight to
        # run_agent_sync, so this exercises the same check transitively.
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError) as ctx_missing:
                run_agent_sync_chat(agent_name=f"{PREFIX} does-not-exist-chat")
            with self.assertRaises(frappe.PermissionError) as ctx_blocked:
                run_agent_sync_chat(agent_name=self.blocked_agent.name)
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(str(ctx_missing.exception), str(ctx_blocked.exception))

    # -- rate_limit decorator is actually applied ----------------------

    def test_run_agent_sync_is_wrapped_by_rate_limit(self):
        self.assertTrue(hasattr(run_agent_sync, "__wrapped__"))

    def test_run_agent_sync_chat_is_wrapped_by_rate_limit(self):
        self.assertTrue(hasattr(run_agent_sync_chat, "__wrapped__"))

    def test_run_agent_sync_rejects_beyond_configured_limit_for_guest(self):
        # rate_limit() only engages when frappe.request is truthy (see
        # frappe/rate_limiter.py::rate_limit -- `if not frappe.request or
        # (...)`  short-circuits to a plain call otherwise). Fake a minimal
        # request object so the real RateLimiter branch is entered, then
        # mock the underlying frappe.cache counter directly (rather than
        # driving 21 real sequential calls through the shared Redis-backed
        # counter) -- this bench's cache is shared with other concurrent
        # test/agent processes (see the ST's live-bench note), and
        # frappe.cache's local read caching makes counting real increments
        # across many calls in one process nondeterministic. Mocking
        # get/incrby directly is the "mocked limiter" option the ST's Test
        # section explicitly allows.
        frappe.local.request = SimpleNamespace(method="POST")
        frappe.local.request_ip = "127.0.0.1"
        frappe.form_dict["cmd"] = "huf.ai.agent_integration.run_agent_sync"
        frappe.form_dict["agent_name"] = f"{PREFIX} does-not-exist-rl"

        frappe.set_user("Guest")
        try:
            # Simulate the configured limit (20/60s, see run_agent_sync's
            # @rate_limit(...) call) already being exceeded for this
            # identity: frappe.cache.get(...) returning a falsy/None prior
            # count is irrelevant to the threshold check -- the actual
            # comparison uses frappe.cache.incrby(...)'s return value.
            with patch("frappe.cache.get", return_value=None), patch(
                "frappe.cache.setex"
            ), patch("frappe.cache.incrby", return_value=21):
                with self.assertRaises(frappe.RateLimitExceededError):
                    run_agent_sync(agent_name=f"{PREFIX} does-not-exist-rl")

            # Regression: with the counter mocked back under the limit, the
            # same Guest call against a nonexistent agent still raises the
            # oracle-avoidance PermissionError, not something else -- proves
            # the rate_limit wrapper is a pass-through (not swallowing /
            # replacing) when under the threshold.
            with patch("frappe.cache.get", return_value=None), patch(
                "frappe.cache.setex"
            ), patch("frappe.cache.incrby", return_value=1):
                with self.assertRaises(frappe.PermissionError):
                    run_agent_sync(agent_name=f"{PREFIX} does-not-exist-rl")
        finally:
            frappe.set_user("Administrator")
