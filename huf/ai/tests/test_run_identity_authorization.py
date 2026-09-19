"""
Unit tests for huf.ai.agent_access.resolve_run_identity_and_authorize.

Track-Item: GW-11 — these tests exercise the single shared "resolve who runs
this agent, and are they allowed to" helper directly across all four trigger
surfaces it unifies: the direct API (run_agent_sync), the Gateway execution
path (process_gateway_event, post GW-08), Flow webhook owner-impersonation
(_run_flow_webhook), and the doc-event initiating-user replay
(run_agent_for_doc).

These are pure unit tests using unittest.mock — they do not require a live
Frappe site/bench, matching the style of test_agent_access.py.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_run_identity_authorization
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.agent_access import (
    TRIGGER_DIRECT_API,
    TRIGGER_DOC_EVENT,
    TRIGGER_FLOW_WEBHOOK,
    TRIGGER_GATEWAY,
    resolve_run_identity_and_authorize,
)


def _make_agent(name="Agent-1", owner="owner@example.com", allow_guest=False):
    return SimpleNamespace(
        name=name,
        owner=owner,
        allow_guest=allow_guest,
        allow_all_users=False,
        allowed_users=[],
        allowed_roles=[],
    )


class TestDirectApiSurface(unittest.TestCase):
    """run_agent_sync's identity check: assert_agent_access + agent.use capability."""

    def test_entitled_user_with_capability_is_authorized(self):
        agent_doc = _make_agent(owner="owner@example.com")
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", return_value=True
        ):
            result = resolve_run_identity_and_authorize(
                agent_doc, TRIGGER_DIRECT_API, {"user": "owner@example.com"}
            )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "owner@example.com")
        self.assertFalse(result.fallback_applied)

    def test_non_entitled_user_is_rejected(self):
        agent_doc = _make_agent(owner="owner@example.com")
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", return_value=False
        ):
            result = resolve_run_identity_and_authorize(
                agent_doc, TRIGGER_DIRECT_API, {"user": "stranger@example.com"}
            )
        self.assertFalse(result.authorized)
        self.assertEqual(result.reason, "You do not have access to run this agent.")

    def test_entitled_user_missing_agent_use_capability_is_rejected(self):
        agent_doc = _make_agent(owner="owner@example.com")
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", return_value=False
        ):
            result = resolve_run_identity_and_authorize(
                agent_doc, TRIGGER_DIRECT_API, {"user": "owner@example.com"}
            )
        self.assertFalse(result.authorized)
        self.assertEqual(result.reason, "You are not authorized to use this agent.")

    def test_guest_on_allow_guest_agent_is_authorized_without_capability_check(self):
        agent_doc = _make_agent(allow_guest=True)
        with patch("huf.ai.agent_access.frappe.get_roles") as mock_get_roles, patch(
            "huf.permissions.has_capability"
        ) as mock_has_capability:
            result = resolve_run_identity_and_authorize(
                agent_doc, TRIGGER_DIRECT_API, {"user": "Guest"}
            )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "Guest")
        mock_get_roles.assert_not_called()
        # Guests never hit the agent.use capability gate (that only applies
        # to non-Guest callers) — matches the pre-refactor
        # `if frappe.session.user != "Guest" and not has_capability(...)`.
        mock_has_capability.assert_not_called()


class TestGatewaySurface(unittest.TestCase):
    """process_gateway_event's post-GW-08 pre-gate: check_agent_access(agent, execution_user)."""

    def test_entitled_execution_user_is_authorized(self):
        agent_doc = _make_agent(name="Support Agent", owner="gateway-bot")
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]):
            result = resolve_run_identity_and_authorize(
                agent_doc,
                TRIGGER_GATEWAY,
                {"execution_user": "gateway-bot", "target_agent": "Support Agent"},
            )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "gateway-bot")

    def test_non_entitled_execution_user_is_rejected_with_named_reason(self):
        agent_doc = _make_agent(name="Support Agent", owner="someone-else@example.com")
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", return_value=False
        ):
            result = resolve_run_identity_and_authorize(
                agent_doc,
                TRIGGER_GATEWAY,
                {"execution_user": "under-privileged-bot", "target_agent": "Support Agent"},
            )
        self.assertFalse(result.authorized)
        self.assertIn("under-privileged-bot", result.reason)
        self.assertIn("Support Agent", result.reason)

    def test_gateway_without_execution_user_is_rejected(self):
        agent_doc = _make_agent()
        result = resolve_run_identity_and_authorize(
            agent_doc, TRIGGER_GATEWAY, {"execution_user": None, "target_agent": agent_doc.name}
        )
        self.assertFalse(result.authorized)
        self.assertEqual(result.reason, "Gateway has no Run as user")

    def test_allow_guest_alone_does_not_entitle_a_named_execution_user(self):
        """Regression guard: allow_guest=1 must not admit an arbitrary named
        principal via the gateway surface -- that was the exact GW-08 bug."""
        agent_doc = _make_agent(name="Support Agent", owner="someone-else@example.com", allow_guest=True)
        with patch("huf.ai.agent_access.frappe.get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", return_value=False
        ):
            result = resolve_run_identity_and_authorize(
                agent_doc,
                TRIGGER_GATEWAY,
                {"execution_user": "under-privileged-bot", "target_agent": "Support Agent"},
            )
        self.assertFalse(result.authorized)


class TestFlowWebhookSurface(unittest.TestCase):
    """_run_flow_webhook's owner-impersonation identity resolution.

    No agent-level check_agent_access happens at this layer -- the flow's own
    webhook-key check is what authorizes the trigger; this call only resolves
    who the run then executes as. authorized is always True here.
    """

    def test_resolves_to_flow_owner(self):
        result = resolve_run_identity_and_authorize(
            None, TRIGGER_FLOW_WEBHOOK, {"owner": "flow-owner@example.com"}
        )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "flow-owner@example.com")
        self.assertFalse(result.fallback_applied)

    def test_falls_back_to_administrator_when_flow_has_no_owner(self):
        result = resolve_run_identity_and_authorize(None, TRIGGER_FLOW_WEBHOOK, {"owner": None})
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "Administrator")


class TestDocEventSurface(unittest.TestCase):
    """run_agent_for_doc's initiating-user replay, including the GW-11 fold-in
    fix for the previously-silent Administrator fallback on a deleted user."""

    def test_no_initiating_user_stays_on_current_session_user(self):
        result = resolve_run_identity_and_authorize(
            None,
            TRIGGER_DOC_EVENT,
            {"initiating_user": None, "current_user": "worker@example.com"},
        )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "worker@example.com")
        self.assertFalse(result.fallback_applied)

    # frappe.db is a werkzeug LocalProxy that requires a bound site just to
    # attribute-access — patching only `.exists` (or `.db`) on the real
    # `frappe` module trips the proxy's own binding check before mock ever
    # gets a chance to substitute anything. So these three tests patch the
    # whole `frappe` reference inside agent_access, matching the pattern
    # test_gateway_service.py already uses for the same reason.
    @patch("huf.ai.agent_access.frappe")
    def test_initiating_user_matching_current_user_is_a_no_op(self, mock_frappe):
        result = resolve_run_identity_and_authorize(
            None,
            TRIGGER_DOC_EVENT,
            {"initiating_user": "same@example.com", "current_user": "same@example.com"},
        )
        self.assertEqual(result.run_as_user, "same@example.com")
        mock_frappe.db.exists.assert_not_called()

    @patch("huf.ai.agent_access.frappe")
    def test_existing_initiating_user_is_used(self, mock_frappe):
        mock_frappe.db.exists.return_value = True
        result = resolve_run_identity_and_authorize(
            None,
            TRIGGER_DOC_EVENT,
            {"initiating_user": "human@example.com", "current_user": "worker@example.com"},
        )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "human@example.com")
        self.assertFalse(result.fallback_applied)

    @patch("huf.ai.agent_access.frappe")
    def test_deleted_initiating_user_falls_back_and_logs(self, mock_frappe):
        """GW-11 fold-in: this fallback used to be completely silent (audit
        finding, agent_hooks.py:145-149). It must now log something."""
        mock_frappe.db.exists.return_value = False
        result = resolve_run_identity_and_authorize(
            None,
            TRIGGER_DOC_EVENT,
            {"initiating_user": "deleted-user@example.com", "current_user": "worker@example.com"},
        )
        self.assertTrue(result.authorized)
        self.assertEqual(result.run_as_user, "worker@example.com")
        self.assertTrue(result.fallback_applied)
        self.assertIn("deleted-user@example.com", result.fallback_reason)
        mock_frappe.log_error.assert_called_once()


class TestUnknownTriggerSurface(unittest.TestCase):
    @patch("huf.ai.agent_access.frappe")
    def test_unknown_trigger_surface_throws(self, mock_frappe):
        mock_frappe.throw.side_effect = RuntimeError
        with self.assertRaises(RuntimeError):
            resolve_run_identity_and_authorize(None, "not-a-real-surface", {})
        mock_frappe.throw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
