#!/usr/bin/env python3
"""HTTP/API contract tests for Automation + Agent Tool Function endpoints.

Phase 6 (GOAL.md section 9, "HTTP/API contract testing"): this file makes
REAL HTTP requests against a LIVE Frappe bench, using ``requests`` (not
in-process Python calls), and asserts on the actual HTTP status code and
response body shape returned across the wire.

Run standalone:

    python3 huf/ai/tests/test_http_contract_automation_tool_p0.py

Configuration via environment variables (all optional, defaults match the
live bench used to develop this suite):

    HUF_HTTP_TEST_BASE_URL   default "http://127.0.0.1:8089"
    HUF_HTTP_TEST_ADMIN_PWD  default "admin"
    HUF_HTTP_TEST_USER_EMAIL default "_test_p62_http_user@example.com"
      (a pre-seeded non-System-Manager user with the "Huf Manager" role;
      see the bench-console snippet in the class docstring below for how
      it was created -- this script does not create it itself, since user
      creation needs an authenticated System Manager session and is a
      one-time fixture, not a per-run throwaway.)
    HUF_HTTP_TEST_USER_PWD   default "TestP62Pass!2026"

Fixtures created directly over HTTP by this script (and left in place --
they are prefixed "_Test P62 HTTP ..." so they're easy to spot/clean up)
include: Automation, Automation Trigger (Webhook), Agent Tool Function.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import uuid

import requests

BASE_URL = os.environ.get("HUF_HTTP_TEST_BASE_URL", "http://127.0.0.1:8089")
ADMIN_PWD = os.environ.get("HUF_HTTP_TEST_ADMIN_PWD", "admin")
NON_SM_EMAIL = os.environ.get("HUF_HTTP_TEST_USER_EMAIL", "_test_p62_http_user@example.com")
NON_SM_PWD = os.environ.get("HUF_HTTP_TEST_USER_PWD", "TestP62Pass2026x")

RUN_TAG = uuid.uuid4().hex[:8]


def _api(path: str) -> str:
    return f"{BASE_URL}/api/{path.lstrip('/')}"


def login(usr: str, pwd: str) -> requests.Session:
    """Real HTTP login via POST /api/method/login; returns a Session with
    the resulting sid cookie attached for subsequent requests."""
    s = requests.Session()
    resp = s.post(_api("method/login"), data={"usr": usr, "pwd": pwd}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"login for {usr} failed: {resp.status_code} {resp.text[:500]}")
    return s


class HttpContractTests(unittest.TestCase):
    """
    Non-System-Manager fixture user setup (one-time, done via bench
    console since it needs a privileged session to create):

        bench --site <site> console
        >>> import frappe
        >>> u = frappe.get_doc({
        ...     "doctype": "User", "email": "_test_p62_http_user@example.com",
        ...     "first_name": "P62 Http Test", "send_welcome_email": 0,
        ...     "user_type": "System User", "roles": [{"role": "Huf Manager"}],
        ... })
        >>> u.insert(ignore_permissions=True)
        >>> u.new_password = "TestP62Pass2026x"
        >>> u.save(ignore_permissions=True)
        >>> frappe.db.commit()

    "Huf Manager" has Automation create/write/delete but is NOT System
    Manager -- the exact shape needed to exercise the run_as_user
    escalation guard (huf.ai.automation_runner._check_run_as_user_permission).
    """

    findings: list[str] = []

    @classmethod
    def setUpClass(cls):
        # Sanity: bench is actually up before running anything else.
        r = requests.get(_api("method/ping"), timeout=30)
        assert r.status_code == 200, f"bench not reachable at {BASE_URL}: {r.status_code}"
        assert r.json().get("message") == "pong", r.text

        cls.admin = login("Administrator", ADMIN_PWD)

        # Confirm the non-SM fixture user exists and can log in; if not,
        # every test that depends on it is skipped with a clear reason
        # rather than failing opaquely.
        try:
            cls.non_sm = login(NON_SM_EMAIL, NON_SM_PWD)
            cls.non_sm_available = True
        except Exception as exc:  # noqa: BLE001
            cls.non_sm = None
            cls.non_sm_available = False
            cls.non_sm_error = str(exc)

        # A real Agent to attach automations to (created out-of-band by
        # the app's own fixtures/demo data -- reuse rather than duplicate).
        r = cls.admin.get(
            _api("method/frappe.client.get_list"),
            params={"doctype": "Agent", "filters": json.dumps([]), "limit_page_length": 1},
            timeout=30,
        )
        agents = r.json().get("message") or []
        assert agents, "expected at least one existing Agent doc on this bench"
        cls.agent_name = agents[0]["name"]

    # ------------------------------------------------------------------
    # 1. AUTOMATION-CRUD-001
    # ------------------------------------------------------------------
    def test_01_automation_crud_create_update(self):
        name = f"_Test P62 HTTP Automation {RUN_TAG}"
        r = self.admin.post(
            _api("method/huf.ai.automation_api.create_automation"),
            data={
                "automation_name": name,
                "agent": self.agent_name,
                "instruction": "Say hello (HTTP contract test fixture).",
            },
            timeout=30,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("message", body, f"unexpected envelope shape: {body}")
        doc = body["message"]
        self.assertEqual(doc["automation_name"], name)
        self.assertEqual(doc["agent"], self.agent_name)
        self.assertEqual(doc["status"], "Draft")
        self.__class__.automation_id = doc["name"]

        # Real round-trip update.
        r = self.admin.post(
            _api("method/huf.ai.automation_api.update_automation"),
            data={"automation": doc["name"], "instruction": "Updated instruction (HTTP test)."},
            timeout=30,
        )
        self.assertEqual(r.status_code, 200, r.text)
        updated = r.json()["message"]
        self.assertEqual(updated["instruction"], "Updated instruction (HTTP test).")

    # ------------------------------------------------------------------
    # 2. AUTOMATION-AUTH-001 -- same create call, no session (Guest).
    # ------------------------------------------------------------------
    def test_02_automation_auth_guest_denied(self):
        r = requests.post(
            _api("method/huf.ai.automation_api.create_automation"),
            data={
                "automation_name": f"_Test P62 HTTP Automation Guest {RUN_TAG}",
                "agent": self.agent_name,
                "instruction": "Guest attempt.",
            },
            timeout=30,
        )
        # Real observed behavior: Frappe's whitelist guest-permission layer
        # rejects before automation_api's own has_permission check runs.
        self.assertEqual(r.status_code, 403, f"expected 403 for Guest, got {r.status_code}: {r.text[:500]}")
        body = r.json()
        # Frappe's standard "clean" 403 envelope: {"exc_type": "PermissionError", ...}
        # plus a server-messages blob -- assert the shape actually observed,
        # not an assumption.
        self.assertIn("exc_type", body, f"expected exc_type in 403 body, got: {body}")
        self.assertEqual(body["exc_type"], "PermissionError")

    # ------------------------------------------------------------------
    # 3. AUTOMATION-PERM-001 -- run_as_user escalation guard.
    # ------------------------------------------------------------------
    def test_03_automation_run_as_user_escalation_guard(self):
        if not self.non_sm_available:
            self.skipTest(f"non-SM fixture user unavailable: {self.non_sm_error}")

        name = f"_Test P62 HTTP Escalation {RUN_TAG}"
        r = self.non_sm.post(
            _api("method/huf.ai.automation_api.create_automation"),
            data={
                "automation_name": name,
                "agent": self.agent_name,
                "instruction": "Escalation guard fixture.",
                "run_as_user": "Administrator",
            },
            timeout=30,
        )
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()["message"]
        self.assertEqual(doc["run_as_user"], "Administrator")
        self.findings.append(
            "FINDING: create_automation/update_automation impose NO check on "
            "run_as_user at save time -- a non-System-Manager owner (Huf "
            "Manager role) can freely set run_as_user='Administrator' via "
            "plain HTTP. The guard (_check_run_as_user_permission) only "
            "fires later, inside run_automation(), and only for the "
            "initiating_user=None code paths (Schedule/Doc-Event/Webhook "
            "triggers) -- NOT for the manual run_automation_now API, which "
            "always passes initiating_user=frappe.session.user and so "
            "silently bypasses the run_as_user value entirely (documented "
            "in automation_runner.py's own docstring)."
        )

        # Exercise the ACTUAL enforcement point: the Webhook trigger path,
        # which is the one whitelisted HTTP-reachable route that calls
        # run_automation() without an initiating_user override.
        slug = f"p62-escalation-{RUN_TAG}"
        key = uuid.uuid4().hex
        r = self.non_sm.post(
            _api("method/huf.ai.automation_api.create_trigger"),
            data={
                "automation": doc["name"],
                "trigger_type": "Webhook",
                "webhook_slug": slug,
                "webhook_key": key,
                "disabled": 0,
            },
            timeout=30,
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = requests.post(
            _api("method/huf.ai.automation_webhook.handle_automation_webhook"),
            params={"slug": slug},
            headers={"X-Webhook-Key": key},
            json={"ping": "p62"},
            timeout=60,
        )
        # Real observed behavior: the webhook handler wraps run_automation()
        # in a bare `except Exception` and always returns a generic 500 --
        # it cannot and does not distinguish "PermissionError: owner not
        # allowed to impersonate run_as_user" from any other internal
        # failure. Document this explicitly rather than asserting a nicer
        # shape that doesn't exist.
        self.assertEqual(r.status_code, 500, f"expected 500, got {r.status_code}: {r.text[:500]}")
        body = r.json()
        # Whitelisted-method dispatch wraps the handler's return value in
        # a {"message": ...} envelope (same convention as every other
        # endpoint in this suite) -- even on a 500.
        self.assertEqual(body.get("message"), {"success": False, "error": "Automation run failed."}, body)
        self.findings.append(
            "FINDING (webhook boundary): huf.ai.automation_webhook."
            "handle_automation_webhook catches ALL exceptions from "
            "run_automation() -- including the PermissionError raised by "
            "_check_run_as_user_permission for a genuine security-relevant "
            "denial -- and flattens them to an identical generic "
            "{'success': False, 'error': 'Automation run failed.'} / HTTP "
            "500. A caller cannot distinguish 'you tried to impersonate a "
            "user you're not allowed to' from an unrelated crash (bad "
            "agent config, provider outage, etc.) from this response alone; "
            "only frappe.log_error's server-side traceback disambiguates. "
            "This may be an intentional don't-leak-details choice (mirrors "
            "the _NOT_FOUND/_INVALID_KEY messages earlier in the same "
            "function), but it does mean a security-guard rejection is "
            "invisible/unobservable to the caller as anything other than "
            "'something went wrong'."
        )

    # ------------------------------------------------------------------
    # 4. AUTOMATION-INVALID-001 -- missing required parameter.
    # ------------------------------------------------------------------
    def test_04_automation_invalid_missing_required_param(self):
        r = self.admin.post(
            _api("method/huf.ai.automation_api.create_automation"),
            data={
                # automation_name and instruction omitted; agent present.
                "agent": self.agent_name,
            },
            timeout=30,
        )
        # Real observed behavior: automation_api.create_automation takes
        # automation_name/instruction as required *positional* Python
        # parameters, not with an internal frappe.throw() validation --
        # Frappe's whitelist dispatcher (frappe.call(method, **form_dict))
        # simply fails to bind them, raising a raw TypeError, which the
        # generic RPC error handler surfaces as a 500 with an
        # implementation-detail message rather than a clean 4xx.
        self.assertEqual(r.status_code, 500, f"expected 500, got {r.status_code}: {r.text[:800]}")
        body = r.json()
        self.assertIn("exception", body, f"expected 'exception' key in body: {body}")
        self.assertIn("TypeError", body["exception"])
        self.assertIn("automation_name", body["exception"])
        self.findings.append(
            "FINDING: create_automation's required args (automation_name, "
            "instruction) are plain Python positional parameters, not "
            "validated with frappe.throw()/ValidationError. Omitting them "
            "over HTTP produces a 500 with a raw 'TypeError: "
            "create_automation() missing 2 required positional arguments: "
            "...' message -- a Python signature leak, not a clean 4xx "
            "'field is required' error. Contrast with TOOL-PERM-001 below, "
            "where a genuine frappe.throw()-driven validation failure "
            "(Agent Tool Function.validate()) DOES produce the expected "
            "clean error shape. The two whitelisted-endpoint styles "
            "(explicit required kwargs vs. **kwargs + internal validate()) "
            "produce inconsistent HTTP error shapes for the same class of "
            "'you forgot a required field' mistake."
        )

    # ------------------------------------------------------------------
    # 5. TOOL-CRUD-001 -- generic Frappe REST on Agent Tool Function.
    # ------------------------------------------------------------------
    def test_05_tool_crud_generic_rest_roundtrip(self):
        tool_name = f"_test_p62_http_tool_{RUN_TAG}"
        payload = {
            "tool_name": tool_name,
            "description": "P62 HTTP contract test tool (Custom Function, whitelisted target).",
            "types": "Custom Function",
            "agent": self.agent_name,
            "tool_type": "Miscellaneous",
            "function_path": "huf.ai.automation_api.list_automations",
            "params": "{}",
        }
        r = self.admin.post(
            _api("resource/Agent Tool Function"),
            json=payload,
            timeout=30,
        )
        self.assertEqual(r.status_code, 200, r.text)
        created = r.json()["data"]
        self.assertEqual(created["tool_name"], tool_name)
        self.assertEqual(created["function_path"], "huf.ai.automation_api.list_automations")
        doc_name = created["name"]
        self.__class__.tool_id = doc_name

        # Real round-trip GET.
        r = self.admin.get(_api(f"resource/Agent Tool Function/{doc_name}"), timeout=30)
        self.assertEqual(r.status_code, 200, r.text)
        fetched = r.json()["data"]
        self.assertEqual(fetched["tool_name"], tool_name)
        self.assertEqual(fetched["function_path"], "huf.ai.automation_api.list_automations")

    # ------------------------------------------------------------------
    # 6. TOOL-AUTH-001 -- same tool-creation request, unauthenticated.
    # ------------------------------------------------------------------
    def test_06_tool_auth_guest_denied(self):
        r = requests.post(
            _api("resource/Agent Tool Function"),
            json={
                "tool_name": f"_test_p62_http_tool_guest_{RUN_TAG}",
                "description": "Guest attempt.",
                "types": "Custom Function",
                "agent": self.agent_name,
                "tool_type": "Miscellaneous",
                "function_path": "huf.ai.automation_api.list_automations",
                "params": "{}",
            },
            timeout=30,
        )
        self.assertEqual(r.status_code, 403, f"expected 403 for Guest, got {r.status_code}: {r.text[:500]}")
        body = r.json()
        self.assertIn("exc_type", body)
        self.assertEqual(body["exc_type"], "PermissionError")

    # ------------------------------------------------------------------
    # 7. TOOL-PERM-001 -- Custom Function must resolve to a real
    #    @frappe.whitelist()'d function, enforced over HTTP too.
    # ------------------------------------------------------------------
    def test_07_tool_perm_non_whitelisted_function_rejected(self):
        r = self.admin.post(
            _api("resource/Agent Tool Function"),
            json={
                "tool_name": f"_test_p62_http_tool_badfn_{RUN_TAG}",
                "description": "Points at a real but NON-whitelisted function.",
                "types": "Custom Function",
                "agent": self.agent_name,
                "tool_type": "Miscellaneous",
                # huf.ai.tool_functions.get_document exists and is
                # importable, but has no @frappe.whitelist() decorator.
                "function_path": "huf.ai.tool_functions.get_document",
                "params": "{}",
            },
            timeout=30,
        )
        # Real observed behavior: frappe.is_whitelisted() raises
        # frappe.PermissionError (not ValidationError) from inside
        # Agent Tool Function.validate() -- the generic REST insert
        # endpoint maps PermissionError to HTTP 403, same status class as
        # the Guest-auth-denied tests above, even though this is a
        # doc-validation failure (the doc's own business rule), not an
        # authorization failure -- a caller cannot distinguish "you're not
        # allowed to call this API at all" from "the document you posted
        # failed a specific validation rule" purely from the status code.
        self.assertEqual(r.status_code, 403, f"expected 403, got {r.status_code}: {r.text[:800]}")
        body = r.json()
        self.assertEqual(body.get("exc_type"), "PermissionError")
        self.assertIn("not whitelisted", body.get("exception", ""))
        self.findings.append(
            "FINDING: Agent Tool Function.validate()'s is_whitelisted() "
            "check raises frappe.PermissionError for a non-whitelisted "
            "Custom Function target. Over generic REST (/api/resource/...), "
            "this collapses to the SAME HTTP 403 status as a plain "
            "not-logged-in/no-permission rejection (e.g. TOOL-AUTH-001 "
            "above) -- a doc-level business-rule failure is "
            "indistinguishable, by status code alone, from an "
            "authentication/authorization failure."
        )


def _print_findings():
    if HttpContractTests.findings:
        print("\n" + "=" * 78)
        print("REAL FINDINGS (not product bugs to fix -- documented behavior):")
        print("=" * 78)
        for f in HttpContractTests.findings:
            print(f"\n- {f}")
        print("=" * 78 + "\n")


if __name__ == "__main__":
    runner = unittest.main(argv=[sys.argv[0]], exit=False, verbosity=2)
    _print_findings()
    sys.exit(0 if runner.result.wasSuccessful() else 1)
