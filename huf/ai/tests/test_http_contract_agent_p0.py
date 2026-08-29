# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Phase 6 (P6.1) HTTP/API contract tests for the Agent config + run endpoints.

These are REAL HTTP tests: every request goes over the wire via `requests`
against a live, running Frappe bench (see GOAL.md section 9,
"HTTP/API contract testing"). Nothing here calls
`agent_config_api.get_agent_section`/`update_agent_section` or
`agent_integration.run_agent_sync` in-process — the whole point is to prove
the public HTTP boundary (route resolution -> whitelist gate -> auth ->
permission -> serialization -> HUF -> response) actually behaves as the
frontend (`chatApi.ts`/`agentApi.ts`) assumes, not merely that the underlying
Python function is correct.

This is a plain `unittest.TestCase` script (NOT `IntegrationTestCase`) because
it exercises a live server as an external black box rather than running
in-process against `bench run-tests`' machinery. It is meant to be run
directly:

    python3 huf/ai/tests/test_http_contract_agent_p0.py -v

against a bench that is already up and reachable at BASE_URL (override via the
HUF_HTTP_TEST_BASE_URL env var). It does NOT start or stop the bench.

Fixtures used (created ahead of time via a one-off `bench console` script
using `huf.ai.tests.factories`, not by this file, since this file only speaks
HTTP):
  - Agent "_Test P51 Automation Agent 080be8d7" (provider "Test_Provider",
    is_system=1) — pre-existing on this bench from an earlier Phase 3-5
    round; reused read-only here for the get_agent_section/permission tests
    (never saved/mutated by this file).
  - Agent "_Test P61 HTTP Run Agent" (provider "Test_Provider", a fresh AI
    Model with a real `model_name`, run_immediately=1) — created for this
    file's RUN-AGENT-001 scenario. The pre-existing agent's AI Model turned
    out to have no `model_name` configured, which `run_agent_sync` rejects,
    so a dedicated fixture was needed.
  - User "_test_p61_http_norole@example.com" — a login-capable user with
    ZERO roles (not even a "Huf User Role" record), so
    `huf.permissions.get_user_capabilities()` returns `[]` for them: no
    "agent.edit" capability. Used for PERMISSION-DENIED-001.

Findings worth flagging up front (see docstrings on the tests below for
detail — these are OBSERVATIONS about real behavior, not bugs to fix):

  - UNAUTHENTICATED-001: `@frappe.whitelist()` WITHOUT `allow_guest=True`
    rejects a Guest caller at the whitelist-resolution layer, before the
    function's own body (and its `check_permission("read")` call) ever runs.
    The response is 403 with a Frappe "is not whitelisted" PermissionError —
    NOT a 401, and NOT the same "permission denied" shape a logged-in caller
    without rights would see.
  - INVALID-PAYLOAD-001 (missing required arg): Frappe does NOT convert this
    into its usual 417 "EXPECTATION FAILED" validation response. A Python
    `TypeError: update_agent_section() missing 1 required positional
    argument: 'agent_name'` propagates out of the dispatcher as an
    *unhandled* exception -> HTTP 500, with a full server traceback in the
    JSON body (`exc`/`exc_type`/`_server_messages`). 417 is reserved for
    `frappe.throw(..., frappe.ValidationError)` raised deliberately from
    inside application code (see INVALID-PAYLOAD-002, which IS a 417,
    because `_parse_values()` explicitly throws `ValidationError`).
  - Every Frappe error response observed here (403, 417, 500) includes a
    full Python traceback in the `exc` field — visible to any authenticated
    (and, for the whitelist-rejection case, even unauthenticated) caller.
    This is standard Frappe REST error behavior (not something P6.1 is
    scoped to fix), but is called out because it is a real, observable
    stack-trace disclosure at the HTTP boundary.
"""

from __future__ import annotations

import json
import os
import unittest

import requests

BASE_URL = os.environ.get("HUF_HTTP_TEST_BASE_URL", "http://127.0.0.1:8089")

ADMIN_USER = "Administrator"
ADMIN_PASSWORD = "admin"

# Pre-existing system agent from an earlier Phase 3-5 round. Read-only in
# this file — never mutated.
READ_AGENT = "_Test P51 Automation Agent 080be8d7"
READ_AGENT_SECTION = "general"

# A logged-in user with zero Huf capabilities (no Huf User Role assigned),
# used to prove the write-permission gate for real over HTTP.
NOROLE_USER = "_test_p61_http_norole@example.com"
NOROLE_PASSWORD = "TestP61Pass123!"

# Dedicated fixture for RUN-AGENT-001 (provider "Test_Provider" wired to a
# real AI Model with a model_name; run_immediately=1).
RUN_AGENT = "_Test P61 HTTP Run Agent"

GET_SECTION_METHOD = "huf.ai.agent_config_api.get_agent_section"
UPDATE_SECTION_METHOD = "huf.ai.agent_config_api.update_agent_section"
RUN_AGENT_SYNC_METHOD = "huf.ai.agent_integration.run_agent_sync"


def _method_url(dotted_method: str) -> str:
    return f"{BASE_URL}/api/method/{dotted_method}"


def _login(usr: str, pwd: str) -> requests.Session:
    """Authenticate via the standard Frappe session-cookie login endpoint.

    Returns a `requests.Session` carrying the resulting `sid` cookie, which
    is reused for subsequent authenticated requests exactly like a real
    browser client would.
    """
    session = requests.Session()
    resp = session.post(
        _method_url("login"),
        data={"usr": usr, "pwd": pwd},
        timeout=30,
    )
    assert resp.status_code == 200, (
        f"Login for {usr!r} failed: {resp.status_code} {resp.text[:500]}"
    )
    body = resp.json()
    # Observed: a user with no app access (e.g. our zero-role fixture user)
    # gets `{"message": "No App", ...}` instead of `{"message": "Logged In"}`
    # -- login still succeeds (200, sid cookie set), it's just a different
    # message. Accept either; the cookie is what matters for this test.
    assert body.get("message") in ("Logged In", "No App"), (
        f"Unexpected login response: {body}"
    )
    assert "sid" in session.cookies, f"Login did not set a session cookie: {body}"
    return session


class HttpContractAgentP0(unittest.TestCase):
    """Real HTTP-boundary contract tests for the Agent config + run APIs."""

    @classmethod
    def setUpClass(cls):
        # Confirm the bench is actually reachable before running anything —
        # a connection failure here should fail loudly and immediately, not
        # be misread as an assertion failure inside an individual test.
        ping = requests.get(_method_url("ping"), timeout=10)
        assert ping.status_code == 200 and ping.json().get("message") == "pong", (
            f"Bench at {BASE_URL} is not reachable/healthy: "
            f"{ping.status_code} {ping.text[:300]}"
        )
        cls.admin_session = _login(ADMIN_USER, ADMIN_PASSWORD)
        cls.norole_session = _login(NOROLE_USER, NOROLE_PASSWORD)

    # ------------------------------------------------------------------
    # 1. AUTHENTICATED-001
    # ------------------------------------------------------------------
    def test_authenticated_get_agent_section_returns_200_and_envelope(self):
        """A logged-in caller reading a real agent+section gets 200 and the
        `{"message": {...}}` envelope Frappe wraps every whitelisted-method
        response in — confirmed empirically, not assumed."""
        resp = self.admin_session.get(
            _method_url(GET_SECTION_METHOD),
            params={"agent_name": READ_AGENT, "section": READ_AGENT_SECTION},
            timeout=30,
        )
        self.assertEqual(resp.status_code, 200, resp.text[:500])
        body = resp.json()
        self.assertIn("message", body)
        message = body["message"]
        self.assertEqual(message["name"], READ_AGENT)
        self.assertEqual(message["section"], READ_AGENT_SECTION)
        self.assertIn("modified", message)
        self.assertIn("values", message)
        self.assertIsInstance(message["values"], dict)
        # Sanity: a field this agent actually has a real value for.
        self.assertEqual(message["values"].get("provider"), "Test_Provider")

    # ------------------------------------------------------------------
    # 2. UNAUTHENTICATED-001
    # ------------------------------------------------------------------
    def test_unauthenticated_get_agent_section_is_rejected_at_whitelist_layer(self):
        """The SAME request with no session cookie (Guest).

        Observed real behavior: `get_agent_section` has no
        `allow_guest=True`, so Frappe's whitelist-resolution layer rejects
        the call BEFORE the function body (and its own
        `check_permission("read")`) ever executes. This is a 403, with a
        Frappe PermissionError body whose message says the method
        "is not whitelisted" — a distinct shape from an in-function
        permission denial (see PERMISSION-DENIED-001, which DOES reach the
        function body and fails deeper, inside `check_permission`).
        """
        resp = requests.get(
            _method_url(GET_SECTION_METHOD),
            params={"agent_name": READ_AGENT, "section": READ_AGENT_SECTION},
            timeout=30,
        )
        self.assertEqual(resp.status_code, 403, resp.text[:500])
        body = resp.json()
        self.assertEqual(body.get("exc_type"), "PermissionError")
        self.assertIn("not whitelisted", body.get("exception", ""))

    # ------------------------------------------------------------------
    # 3. PERMISSION-DENIED-001
    # ------------------------------------------------------------------
    def test_update_agent_section_denied_for_user_without_agent_edit(self):
        """Authenticated as a real user with zero Huf capabilities (no Huf
        User Role assigned -> `has_capability(user, "agent.edit")` is
        False), calling `update_agent_section` reaches
        `agent_doc.check_permission("write")` and fails there with a real
        403 PermissionError — distinct from the whitelist-layer 403 in
        UNAUTHENTICATED-001 because this one DOES execute application code
        first (proven by the traceback showing
        `agent_config_api.py:223 -> check_permission("write")`) and carries
        a `_server_messages` string naming the doctype and user.
        """
        resp = self.norole_session.post(
            _method_url(UPDATE_SECTION_METHOD),
            data={
                "agent_name": READ_AGENT,
                "section": READ_AGENT_SECTION,
                "values": json.dumps({}),
                "expected_modified": "2026-08-25 13:06:45.815505",
            },
            timeout=30,
        )
        self.assertEqual(resp.status_code, 403, resp.text[:500])
        body = resp.json()
        self.assertEqual(body.get("exc_type"), "PermissionError")
        server_messages = body.get("_server_messages", "")
        self.assertIn(NOROLE_USER, server_messages)
        self.assertIn("Agent", server_messages)

    # ------------------------------------------------------------------
    # 4. INVALID-PAYLOAD-001
    # ------------------------------------------------------------------
    def test_update_agent_section_missing_required_param_is_500_not_417(self):
        """Omitting a required parameter (`agent_name`) to a whitelisted
        method with a typed signature does NOT produce Frappe's usual 417
        "EXPECTATION FAILED" validation response (that's reserved for
        `frappe.throw(..., ValidationError)` raised deliberately from inside
        the function body — see INVALID-PAYLOAD-002). Instead, Python's own
        `TypeError` for the missing positional argument propagates
        unhandled out of the dispatcher, producing a genuine HTTP 500 with
        a full server traceback in the body. Observed, not assumed.
        """
        resp = self.admin_session.post(
            _method_url(UPDATE_SECTION_METHOD),
            data={
                # agent_name intentionally omitted
                "section": READ_AGENT_SECTION,
                "values": json.dumps({}),
                "expected_modified": "2026-08-25",
            },
            timeout=30,
        )
        self.assertEqual(resp.status_code, 500, resp.text[:500])
        body = resp.json()
        self.assertEqual(body.get("exc_type"), "TypeError")
        self.assertIn("missing 1 required positional argument", body.get("exception", ""))
        self.assertIn("agent_name", body.get("exception", ""))

    # ------------------------------------------------------------------
    # 5. INVALID-PAYLOAD-002
    # ------------------------------------------------------------------
    def test_update_agent_section_wrong_type_for_values_is_417(self):
        """Passing a JSON array where `values` must be a JSON object.

        `_parse_values()` (`agent_config_api.py:165-170`) explicitly checks
        `isinstance(values, Mapping)` and calls
        `frappe.throw(_("Section values must be a JSON object."),
        frappe.ValidationError)` when it isn't. That deliberate
        `frappe.throw` IS what produces Frappe's standard 417 "EXPECTATION
        FAILED" response — the informative, business-logic-level validation
        error, in contrast to the raw 500 TypeError from
        INVALID-PAYLOAD-001's missing-argument case.
        """
        resp = self.admin_session.post(
            _method_url(UPDATE_SECTION_METHOD),
            data={
                "agent_name": READ_AGENT,
                "section": READ_AGENT_SECTION,
                "values": json.dumps([1, 2, 3]),
                "expected_modified": "2026-08-25 13:06:45.815505",
            },
            timeout=30,
        )
        self.assertEqual(resp.status_code, 417, resp.text[:500])
        body = resp.json()
        self.assertEqual(body.get("exc_type"), "ValidationError")
        self.assertIn("JSON object", body.get("exception", ""))

    # ------------------------------------------------------------------
    # 6. RUN-AGENT-001
    # ------------------------------------------------------------------
    def test_run_agent_sync_direct_execution_returns_expected_envelope(self):
        """A real HTTP POST to `run_agent_sync` with `now=1` and the
        Test Provider's scenario marker, targeting a Test-Provider-wired
        agent (`RUN_AGENT`, a fresh fixture with a real `AI Model.model_name`
        — the pre-existing `READ_AGENT` fixture's AI Model turned out to
        have no `model_name` set, which `run_agent_sync` rejects with a
        `ValidationError`, so it could not be reused for this scenario).

        Marker format verified empirically to be
        `__TEST_SCENARIO__:<NAME>` (NOT the `n:<NAME>` shorthand used
        internally by `test_test_provider.py`'s own direct-call tests) —
        confirmed by a first attempt without the marker coming back with
        `"error": "...requires a '__TEST_SCENARIO__:<NAME>' marker..."`.

        Asserts the response envelope shape against what
        `frontend/src/services/agentApi.ts`'s `RunAgentTestResponse`
        actually parses (`message.{success,response,provider,agent_run_id,
        conversation_id,session_id}`).
        """
        resp = self.admin_session.post(
            _method_url(RUN_AGENT_SYNC_METHOD),
            data={
                "agent_name": RUN_AGENT,
                "prompt": "__TEST_SCENARIO__:TEST_TEXT",
                "now": 1,
            },
            timeout=60,
        )
        self.assertEqual(resp.status_code, 200, resp.text[:1000])
        body = resp.json()
        self.assertIn("message", body)
        message = body["message"]
        self.assertTrue(message.get("success"), message)
        self.assertIn("TEST_TEXT", message.get("response", ""))
        self.assertEqual(message.get("provider"), "Test_Provider")
        self.assertIn("agent_run_id", message)
        self.assertIn("conversation_id", message)
        self.assertIn("session_id", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
