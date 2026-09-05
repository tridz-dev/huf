"""Focused unit tests for the provider-neutral Gateway foundation."""

from types import SimpleNamespace
import json
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import gateway_service
from huf.ai.gateway_adapters.types import GatewayReply


def gateway(**overrides):
    values = {
        "name": "Support Telegram",
        "provider": "Telegram",
        "is_enabled": 1,
        "default_target_type": "",
        "default_agent": "",
        "default_flow": "",
        "direct_policy": "Allow list",
        "room_policy": "Allow list",
        "room_sender_policy": "Allow list",
        "mention_required": 1,
        "pairing_ttl_minutes": 60,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def binding(**overrides):
    values = {
        "name": "BIND-001",
        "priority": 100,
        "match_type": "Any conversation",
        "match_value": "",
        "target_type": "Agent",
        "agent": "Support Agent",
        "flow": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestGatewayRouting(unittest.TestCase):
    @patch("huf.ai.gateway_service.frappe")
    def test_highest_priority_matching_binding_wins(self, mock_frappe):
        mock_frappe.get_doc.return_value = gateway()
        mock_frappe.get_all.return_value = [
            binding(name="wrong-room", priority=1, match_type="Room or channel", match_value="sales"),
            binding(name="thread", priority=20, match_type="Thread", match_value="42", agent="Thread Agent"),
            binding(name="any", priority=100, agent="Fallback Agent"),
        ]

        route = gateway_service.resolve_gateway_route(
            "Support Telegram", {"conversation_id": "support", "thread_id": "42"}
        )

        assert route == {
            "status": "Queued",
            "binding": "thread",
            "target_type": "Agent",
            "agent": "Thread Agent",
            "flow": None,
        }

    @patch("huf.ai.gateway_service.frappe")
    def test_default_route_is_used_only_after_no_binding_matches(self, mock_frappe):
        mock_frappe.get_doc.return_value = gateway(default_target_type="Flow", default_flow="Escalate")
        mock_frappe.get_all.return_value = [
            binding(match_type="Sender", match_value="allowed-user", agent="Personal Agent")
        ]

        route = gateway_service.resolve_gateway_route("Support Telegram", {"sender_id": "other-user"})

        assert route == {
            "status": "Queued",
            "binding": None,
            "target_type": "Flow",
            "agent": None,
            "flow": "Escalate",
        }

    @patch("huf.ai.gateway_service.frappe")
    def test_disabled_gateway_never_routes(self, mock_frappe):
        mock_frappe.get_doc.return_value = gateway(is_enabled=0)

        route = gateway_service.resolve_gateway_route("Support Telegram", {"sender_id": "anyone"})

        assert route == {"status": "Rejected", "reason": "Gateway is disabled"}
        mock_frappe.get_all.assert_not_called()


class TestGatewayIngress(unittest.TestCase):
    def setUp(self):
        self.now_datetime = patch(
            "huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 7, 26, 0, 0, 0)
        )
        self.now_datetime.start()

    def tearDown(self):
        self.now_datetime.stop()

    def test_payload_redaction_removes_provider_secrets(self):
        assert gateway_service._redact_payload(
            {"token": "top-secret", "body": {"signature": "sig", "message": "hello"}}
        ) == {"token": "[redacted]", "body": {"signature": "[redacted]", "message": "hello"}}

    def test_payload_redaction_stringifies_non_json_native_values(self):
        """GW-04: a real inbound Communication's `as_dict()` carries native
        `datetime`/`Decimal` values. Gateway Event's `raw_payload` is a JSON
        field with no `default=str`, so these must be coerced to strings
        rather than passed through and left to crash `json.dumps`."""
        from decimal import Decimal

        payload = {
            "communication_date": datetime(2026, 7, 26, 12, 0, 0),
            "amount": Decimal("9.99"),
            "tags": (datetime(2026, 1, 1), "kept"),
            "message": "kept",
        }
        redacted = gateway_service._redact_payload(payload)
        assert redacted["communication_date"] == str(datetime(2026, 7, 26, 12, 0, 0))
        assert redacted["amount"] == str(Decimal("9.99"))
        assert redacted["tags"] == [str(datetime(2026, 1, 1)), "kept"]
        assert redacted["message"] == "kept"
        # Must actually be JSON-serializable now.
        json.dumps(redacted)

    def test_payload_redaction_covers_additional_credential_keys(self):
        """ST-R5.13: SENSITIVE_PAYLOAD_KEYS was extended with additional
        credential-related field names cross-referenced against adapter
        credential_schema definitions (huf/ai/gateway_adapters/*.py)."""
        payload = {
            "bearer_token": "a",
            "x_api_key": "b",
            "auth_token": "c",
            "webhook_secret": "d",
            "access_token": "e",
            "client_secret": "f",
            "signing_secret": "g",
            "corp_secret": "h",
            "callback_token": "i",
            "app_secret": "j",
            "app_password": "k",
            "bot_token": "l",
            "public_key": "m",
            "community_token": "n",
            "callback_secret": "o",
            "verification_token": "p",
            "message": "kept",
        }
        redacted = gateway_service._redact_payload(payload)
        for key in payload:
            if key == "message":
                continue
            assert redacted[key] == "[redacted]", f"{key} was not redacted"
        assert redacted["message"] == "kept"

    @patch("huf.ai.gateway_service.frappe")
    def test_duplicate_provider_event_is_a_noop(self, mock_frappe):
        mock_frappe.db.get_value.return_value = "GATEWAY-EVENT-0001"

        result = gateway_service.ingest_gateway_event(
            "Support Telegram", "update:123", {"sender_id": "1"}, verified_sender=True
        )

        assert result == {"duplicate": True, "event_name": "GATEWAY-EVENT-0001"}
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.enqueue.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_unverified_event_is_persisted_but_never_dispatched(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        event = MagicMock()
        event.name = "GATEWAY-EVENT-0002"
        mock_frappe.get_doc.return_value = event

        result = gateway_service.ingest_gateway_event(
            "Support Telegram", "update:124", {"sender_id": "1"}, verified_sender=False
        )

        assert result == {"event_name": "GATEWAY-EVENT-0002", "status": "Rejected"}
        event.insert.assert_called_once_with(ignore_permissions=True)
        event.db_set.assert_called_once_with(
            {"status": "Rejected", "error_message": "Provider did not verify sender"}
        )
        mock_frappe.enqueue.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_verified_but_unapproved_sender_is_rejected(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        event = MagicMock()
        event.name = "GATEWAY-EVENT-0003"

        def get_doc(value, *args, **kwargs):
            if value == "Gateway":
                return gateway(direct_policy="Disabled")
            return event

        mock_frappe.get_doc.side_effect = get_doc

        result = gateway_service.ingest_gateway_event(
            "Support Telegram", "update:125", {"sender_id": "1"}, verified_sender=True
        )

        assert result == {"event_name": "GATEWAY-EVENT-0003", "status": "Rejected"}
        event.db_set.assert_called_once_with(
            {"status": "Rejected", "error_message": "Sender is not approved for this gateway"}
        )
        mock_frappe.enqueue.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_direct_allow_list_requires_normalized_approved_entry(self, mock_frappe):
        mock_frappe.get_all.return_value = ["ACCESS-001"]
        admitted, _ = gateway_service._admission(gateway(), {"sender_id": "provider:42"})
        assert admitted is True
        assert mock_frappe.get_all.call_args.args[0] == "Gateway Access Entry"

    @patch("huf.ai.gateway_service.frappe")
    def test_expired_access_entry_does_not_admit_sender(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        admitted, _ = gateway_service._admission(gateway(), {"sender_id": "provider:42"})
        assert admitted is False
        assert ["expires_at", ">=", gateway_service.now_datetime()] in mock_frappe.get_all.call_args.kwargs["or_filters"]

    @patch("huf.ai.gateway_service.frappe")
    def test_pairing_creates_pending_entry_and_never_admits_triggering_message(self, mock_frappe):
        mock_frappe.db.exists.return_value = None
        # _create_pairing_request checks for an existing pending entry via
        # frappe.get_all before creating one; a bare MagicMock return value
        # is truthy and would short-circuit into the "reuse existing" branch
        # instead of the "create new" branch this test exercises.
        mock_frappe.get_all.return_value = []
        admitted, reason = gateway_service._admission(gateway(direct_policy="Pairing"), {"sender_id": "42"})
        assert admitted is False
        # The reason now also carries the generated pairing code so the
        # sender-facing message can quote it; that value comes from a fully
        # mocked frappe here, so assert the stable prefix rather than an
        # exact match on the (mocked, nondeterministic) code suffix.
        assert reason.startswith("Sender pairing approval is required")
        pending = mock_frappe.get_doc.call_args.args[0]
        assert pending["doctype"] == "Gateway Access Entry"
        assert pending["state"] == "Pending"

    @patch("huf.ai.gateway_service.frappe")
    def test_pairing_uses_display_name_when_provided(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        gateway_service._admission(
            gateway(direct_policy="Pairing"), {"sender_id": "42", "display_name": "@janedoe"}
        )
        pending = mock_frappe.get_doc.call_args.args[0]
        assert pending["display_label"] == "@janedoe"

    @patch("huf.ai.gateway_service.frappe")
    def test_pairing_falls_back_to_bare_sender_id_without_display_name(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        gateway_service._admission(gateway(direct_policy="Pairing"), {"sender_id": "42"})
        pending = mock_frappe.get_doc.call_args.args[0]
        assert pending["display_label"] == "Sender 42"

    @patch("huf.ai.gateway_service.frappe")
    def test_room_requires_room_sender_and_mention_when_configured(self, mock_frappe):
        admitted, reason = gateway_service._admission(gateway(), {"sender_id": "42", "conversation_id": "room:1", "is_room": True, "mentioned": False})
        assert admitted is False
        assert reason == "Room messages must mention the gateway"

    @patch("huf.ai.gateway_service.frappe")
    def test_room_open_policy_admits_without_an_access_entry(self, mock_frappe):
        """Regression: `Open` used to AND against `== "Allow list"`, making it
        unconditionally False -- stricter than `Allow list`, the inverse of
        what the label promises."""
        admitted, _ = gateway_service._admission(
            gateway(room_policy="Open", room_sender_policy="Open", mention_required=0),
            {"sender_id": "42", "conversation_id": "room:1", "is_room": True, "mentioned": False},
        )
        assert admitted is True
        mock_frappe.get_all.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_room_allow_list_still_requires_an_approved_access_entry(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        admitted, _ = gateway_service._admission(
            gateway(room_policy="Allow list", room_sender_policy="Open", mention_required=0),
            {"sender_id": "42", "conversation_id": "room:1", "is_room": True, "mentioned": False},
        )
        assert admitted is False

    @patch("huf.ai.gateway_service.frappe")
    def test_room_disabled_policy_never_admits(self, mock_frappe):
        admitted, _ = gateway_service._admission(
            gateway(room_policy="Disabled", room_sender_policy="Open", mention_required=0),
            {"sender_id": "42", "conversation_id": "room:1", "is_room": True, "mentioned": False},
        )
        assert admitted is False
        mock_frappe.get_all.assert_not_called()


def access_entry(**overrides):
    values = {
        "name": "ACCESS-001",
        "gateway": "Support Telegram",
        "provider": "Telegram",
        "external_id": "42",
        "state": "Pending",
        "expires_at": None,
    }
    values.update(overrides)
    entry = MagicMock(**values)
    entry.name = values["name"]
    entry.gateway = values["gateway"]
    entry.provider = values["provider"]
    entry.external_id = values["external_id"]
    entry.state = values["state"]
    entry.expires_at = values["expires_at"]
    entry.integration_settings = None
    return entry


class TestPurgeOldRejectedGatewayEvents(unittest.TestCase):
    """ST-R5.17: rejected Gateway Event rows are retained for forensic audit
    (the insert-before-admission ordering in ingest_gateway_event is
    deliberate and must not be removed), but bounded by a retention job that
    purges Rejected rows past a TTL."""

    @patch("huf.ai.gateway_service.frappe")
    def test_deletes_only_rejected_rows_older_than_default_ttl(self, mock_frappe):
        fixed_now = datetime(2026, 8, 1, 0, 0, 0)
        mock_frappe.utils.now_datetime = MagicMock(return_value=fixed_now)
        with patch("huf.ai.gateway_service.now_datetime", return_value=fixed_now):
            gateway_service.purge_old_rejected_gateway_events()

        expected_cutoff = add_to_date(fixed_now, days=-30)
        mock_frappe.db.delete.assert_called_once_with(
            "Gateway Event",
            {"status": "Rejected", "received_at": ["<", expected_cutoff]},
        )

    @patch("huf.ai.gateway_service.frappe")
    def test_custom_retention_window_is_honored(self, mock_frappe):
        fixed_now = datetime(2026, 8, 1, 0, 0, 0)
        with patch("huf.ai.gateway_service.now_datetime", return_value=fixed_now):
            gateway_service.purge_old_rejected_gateway_events(retention_days=7)

        expected_cutoff = add_to_date(fixed_now, days=-7)
        mock_frappe.db.delete.assert_called_once_with(
            "Gateway Event",
            {"status": "Rejected", "received_at": ["<", expected_cutoff]},
        )

    @patch("huf.ai.gateway_service.frappe")
    def test_only_rejected_status_is_targeted_never_other_statuses(self, mock_frappe):
        fixed_now = datetime(2026, 8, 1, 0, 0, 0)
        with patch("huf.ai.gateway_service.now_datetime", return_value=fixed_now):
            gateway_service.purge_old_rejected_gateway_events()

        filters = mock_frappe.db.delete.call_args.args[1]
        assert filters["status"] == "Rejected"

    @patch("huf.ai.gateway_service.frappe")
    def test_returns_delete_result(self, mock_frappe):
        mock_frappe.db.delete.return_value = 5
        with patch("huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 8, 1)):
            result = gateway_service.purge_old_rejected_gateway_events()
        assert result == 5


class TestPairingReplyEnabled(unittest.TestCase):
    """`pairing_reply_enabled` (default on) gates the outbound "here's your
    code" reply without affecting whether the pending entry itself is
    created -- Email/SMS-style shared inboxes can opt out of the automated
    reply while still queueing the request for approval."""

    @staticmethod
    def _get_doc_side_effect(*args, **kwargs):
        """frappe.get_doc({...}) creates the pending entry (needs a working
        .insert()); frappe.get_doc("Integration Settings", name) fetches
        credentials -- distinguish them by the first positional arg's type."""
        if args and isinstance(args[0], dict):
            entry_doc = MagicMock()
            entry_doc.insert.return_value = entry_doc
            return entry_doc
        return SimpleNamespace(credentials=[])

    def setUp(self):
        self.now_datetime = patch(
            "huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 7, 26, 0, 0, 0)
        )
        self.now_datetime.start()
        self.addCleanup(self.now_datetime.stop)

    @patch("huf.ai.gateway_webhook._adapter_class_for_provider")
    @patch("huf.ai.gateway_service.frappe")
    def test_reply_sent_when_enabled(self, mock_frappe, mock_adapter_cls):
        mock_frappe.get_all.return_value = []
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect
        adapter = MagicMock()
        # Two-level wiring: _adapter_class_for_provider returns a class,
        # the code instantiates it, so the returned instance must be adapter.
        mock_adapter_cls.return_value.return_value = adapter

        gw = gateway(direct_policy="Pairing", integration_settings="INT-001", pairing_reply_enabled=1)
        code = gateway_service._create_pairing_request(gw, "42")

        mock_adapter_cls.assert_called_once_with("Telegram")
        adapter.send_reply.assert_called_once()
        call_args = adapter.send_reply.call_args
        reply = call_args[0][0]
        assert isinstance(reply, GatewayReply)
        assert reply.conversation_id == "42"
        assert code in reply.text

    @patch("huf.ai.gateway_webhook._adapter_class_for_provider")
    @patch("huf.ai.gateway_service.frappe")
    def test_reply_skipped_when_disabled(self, mock_frappe, mock_adapter_cls):
        mock_frappe.get_all.return_value = []
        adapter = MagicMock()
        mock_adapter_cls.return_value = adapter

        gw = gateway(direct_policy="Pairing", integration_settings="INT-001", pairing_reply_enabled=0)
        code = gateway_service._create_pairing_request(gw, "42")

        adapter.send_reply.assert_not_called()
        mock_adapter_cls.assert_not_called()
        # The pending entry is still created either way -- only the reply is gated.
        assert code
        pending = mock_frappe.get_doc.call_args.args[0]
        assert pending["doctype"] == "Gateway Access Entry"

    @patch("huf.ai.gateway_webhook._adapter_class_for_provider")
    @patch("huf.ai.gateway_service.frappe")
    def test_reply_defaults_to_enabled_on_gateways_without_the_field(self, mock_frappe, mock_adapter_cls):
        """Gateway docs created before pairing_reply_enabled existed have no
        such attribute at all; getattr's default must keep them behaving as
        "on" rather than silently going quiet."""
        mock_frappe.get_all.return_value = []
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect
        adapter = MagicMock()
        # Two-level wiring: _adapter_class_for_provider returns a class,
        # the code instantiates it, so the returned instance must be adapter.
        mock_adapter_cls.return_value.return_value = adapter

        gw = gateway(direct_policy="Pairing", integration_settings="INT-001")
        assert not hasattr(gw, "pairing_reply_enabled")
        code = gateway_service._create_pairing_request(gw, "42")

        mock_adapter_cls.assert_called_once_with("Telegram")
        adapter.send_reply.assert_called_once()
        call_args = adapter.send_reply.call_args
        reply = call_args[0][0]
        assert isinstance(reply, GatewayReply)
        assert reply.conversation_id == "42"
        assert code in reply.text


class TestApproveGatewayPairing(unittest.TestCase):
    """`approve_gateway_pairing` is the canonical approval path consolidating
    the orphaned `gateway_pairing_tools.approve_pairing_code` and the
    Desk-only `approve_gateway_access_entry` (kept as a thin alias below)."""

    @patch("huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 7, 26, 0, 0, 0))
    @patch("huf.ai.gateway_service.frappe")
    def test_approve_by_pairing_code_clears_expires_at(self, mock_frappe, mock_now):
        """Regression: approval used to leave the pairing-request TTL on
        `expires_at`, so `_has_access_entry`'s `expires_at >= now` filter made
        an approved entry silently stop matching once that TTL elapsed."""
        entry = access_entry(expires_at=None)
        # frappe.get_all returns frappe._dict rows, and _find_pending_entry_by_code
        # reads row.pairing_code by attribute -- a plain dict here would raise.
        mock_frappe.get_all.return_value = [frappe._dict({"name": entry.name, "pairing_code": "PAIR-7A9K"})]
        mock_frappe.get_doc.return_value = entry
        mock_frappe.has_permission.return_value = True
        mock_frappe.session.user = "admin@example.com"

        result = gateway_service.approve_gateway_pairing("pair-7a9k")

        assert result["state"] == "Approved"
        assert result["name"] == entry.name
        entry.db_set.assert_called_once_with(
            {
                "state": "Approved",
                "approved_by": "admin@example.com",
                "approved_at": mock_now.return_value,
                "expires_at": None,
            }
        )

    @patch("huf.ai.gateway_service.frappe")
    def test_approve_falls_back_to_legacy_entry_name(self, mock_frappe):
        """Backward compatibility: existing entry_name-based callers (Desk,
        the old approve_gateway_access_entry) must keep working."""
        entry = access_entry(name="ACCESS-LEGACY")
        mock_frappe.get_all.return_value = []  # no pairing_code match
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = entry
        mock_frappe.has_permission.return_value = True
        mock_frappe.session.user = "admin@example.com"

        result = gateway_service.approve_gateway_pairing("ACCESS-LEGACY")

        assert result["name"] == "ACCESS-LEGACY"
        mock_frappe.db.exists.assert_called_once_with("Gateway Access Entry", "ACCESS-LEGACY")

    @patch("huf.ai.gateway_service.frappe")
    def test_unknown_code_or_name_is_rejected(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        mock_frappe.db.exists.return_value = False
        mock_frappe.has_permission.return_value = True
        mock_frappe.ValidationError = ValueError
        mock_frappe.throw.side_effect = ValueError("No pending pairing request found")

        with self.assertRaises(ValueError):
            gateway_service.approve_gateway_pairing("PAIR-0000")

    @patch("huf.ai.gateway_service.frappe")
    def test_expired_entry_is_rejected(self, mock_frappe):
        entry = access_entry(expires_at=datetime(2020, 1, 1))
        # frappe.get_all returns frappe._dict rows, and _find_pending_entry_by_code
        # reads row.pairing_code by attribute -- a plain dict here would raise.
        mock_frappe.get_all.return_value = [frappe._dict({"name": entry.name, "pairing_code": "PAIR-7A9K"})]
        mock_frappe.get_doc.return_value = entry
        mock_frappe.has_permission.return_value = True
        mock_frappe.ValidationError = ValueError
        mock_frappe.throw.side_effect = ValueError("This pairing request is not active.")

        with self.assertRaises(ValueError):
            gateway_service.approve_gateway_pairing("PAIR-7A9K")
        entry.db_set.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_already_approved_entry_is_rejected(self, mock_frappe):
        entry = access_entry(state="Approved")
        # frappe.get_all returns frappe._dict rows, and _find_pending_entry_by_code
        # reads row.pairing_code by attribute -- a plain dict here would raise.
        mock_frappe.get_all.return_value = [frappe._dict({"name": entry.name, "pairing_code": "PAIR-7A9K"})]
        mock_frappe.get_doc.return_value = entry
        mock_frappe.has_permission.return_value = True
        mock_frappe.ValidationError = ValueError
        mock_frappe.throw.side_effect = ValueError("This pairing request is not active.")

        with self.assertRaises(ValueError):
            gateway_service.approve_gateway_pairing("PAIR-7A9K")
        entry.db_set.assert_not_called()

    @patch("huf.ai.gateway_service.frappe")
    def test_approval_denied_without_write_permission(self, mock_frappe):
        mock_frappe.has_permission.return_value = False
        mock_frappe.PermissionError = PermissionError
        mock_frappe.throw.side_effect = PermissionError("Not permitted")

        with self.assertRaises(PermissionError):
            gateway_service.approve_gateway_pairing("PAIR-7A9K")


class TestApproveGatewayAccessEntryAlias(unittest.TestCase):
    """approve_gateway_access_entry stays for backward compatibility, thinly
    wrapping approve_gateway_pairing."""

    @patch("huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 7, 26, 0, 0, 0))
    @patch("huf.ai.gateway_service.frappe")
    def test_alias_delegates_to_approve_gateway_pairing(self, mock_frappe, mock_now):
        entry = access_entry(name="ACCESS-001")
        mock_frappe.get_all.return_value = []
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = entry
        mock_frappe.has_permission.return_value = True
        mock_frappe.session.user = "admin@example.com"

        result = gateway_service.approve_gateway_access_entry("ACCESS-001")

        assert result == {"name": "ACCESS-001", "state": "Approved"}
        entry.db_set.assert_called_once_with(
            {
                "state": "Approved",
                "approved_by": "admin@example.com",
                "approved_at": mock_now.return_value,
                "expires_at": None,
            }
        )


class TestListGatewayAccessEntries(unittest.TestCase):
    @patch("huf.ai.gateway_service.frappe")
    def test_defaults_to_pending_state(self, mock_frappe):
        mock_frappe.has_permission.return_value = True
        mock_frappe.get_all.return_value = []

        gateway_service.list_gateway_access_entries()

        assert mock_frappe.get_all.call_args.kwargs["filters"] == {"state": "Pending"}

    @patch("huf.ai.gateway_service.frappe")
    def test_filters_by_gateway_when_given(self, mock_frappe):
        mock_frappe.has_permission.return_value = True
        mock_frappe.get_all.return_value = []

        gateway_service.list_gateway_access_entries(gateway="Support Telegram", state="Approved")

        assert mock_frappe.get_all.call_args.kwargs["filters"] == {
            "state": "Approved",
            "gateway": "Support Telegram",
        }

    @patch("huf.ai.gateway_service.frappe")
    def test_denied_without_read_permission(self, mock_frappe):
        mock_frappe.has_permission.return_value = False
        mock_frappe.PermissionError = PermissionError
        mock_frappe.throw.side_effect = PermissionError("Not permitted")

        with self.assertRaises(PermissionError):
            gateway_service.list_gateway_access_entries()


class TestRevokeGatewayAccessEntry(unittest.TestCase):
    @patch("huf.ai.gateway_service.now_datetime", return_value=datetime(2026, 7, 26, 0, 0, 0))
    @patch("huf.ai.gateway_service.frappe")
    def test_revoke_sets_state_and_timestamp(self, mock_frappe, mock_now):
        entry = access_entry(state="Approved")
        mock_frappe.get_doc.return_value = entry
        mock_frappe.has_permission.return_value = True

        result = gateway_service.revoke_gateway_access_entry(entry.name)

        assert result == {"name": entry.name, "state": "Revoked"}
        entry.db_set.assert_called_once_with({"state": "Revoked", "revoked_at": mock_now.return_value})

    @patch("huf.ai.gateway_service.frappe")
    def test_revoke_denied_without_write_permission(self, mock_frappe):
        mock_frappe.has_permission.return_value = False
        mock_frappe.PermissionError = PermissionError
        mock_frappe.throw.side_effect = PermissionError("Not permitted")

        with self.assertRaises(PermissionError):
            gateway_service.revoke_gateway_access_entry("ACCESS-001")


class TestGatewayReplyDelivery(unittest.TestCase):
    @patch("huf.ai.gateway_service.frappe")
    @patch("huf.ai.gateway_webhook.send_gateway_reply")
    def test_agent_result_is_delivered_through_the_gateway(self, mock_send, mock_frappe):
        event = MagicMock(
            name="GATEWAY-EVENT-0004",
            status="Queued",
            gateway="Support VK",
            target_type="Agent",
            target_agent="Support Agent",
            message_text="hello",
            thread_id="123",
            conversation_id="2000000001",
            sender_id="42",
        )
        configured_gateway = gateway(name="Support VK", execution_user="gateway-bot")
        # Third item: the target Agent lookup added by the F1 access-control fix
        # (gateway-routed runs are authorized as Guest -- see agent_access.py).
        # allow_guest=True so this "delivered successfully" scenario still passes.
        target_agent_doc = MagicMock(allow_guest=True)
        mock_frappe.get_doc.side_effect = [event, configured_gateway, target_agent_doc]
        mock_run = MagicMock(return_value={"agent_run_id": "AR-001", "response": "Hello back"})
        mock_send.return_value = SimpleNamespace(provider_message_id="vk-message-1")

        with patch.dict(sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=mock_run)}):
            result = gateway_service.process_gateway_event(event.name)

        assert result == {
            "event_name": event.name,
            "status": "Succeeded",
            "agent_run_id": "AR-001",
            "provider_message_id": "vk-message-1",
        }
        assert mock_run.call_args.kwargs["now"] is True
        mock_send.assert_called_once_with(configured_gateway, event, "Hello back")


class TestRedactErrorText(unittest.TestCase):
    """GW-07: any outbound-provider-call exception whose string form embeds a
    URL credential (Telegram's `.../bot<TOKEN>/...` scheme, a Bearer header
    dump, or a token/secret query parameter) must not surface that credential
    in cleartext once it reaches an externally-readable field."""

    def test_redacts_telegram_style_bot_token_in_url(self):
        text = (
            "404 Client Error: Not Found for url: "
            "https://api.telegram.org/bot123456789:AAFakeTokenValue-1234567890/sendMessage"
        )
        redacted = gateway_service._redact_error_text(text)
        assert "AAFakeTokenValue" not in redacted
        assert "/bot[redacted]" in redacted

    def test_redacts_bearer_token_in_text(self):
        text = "Authorization failed: Bearer sk-live-abcdef1234567890 was rejected"
        redacted = gateway_service._redact_error_text(text)
        assert "sk-live-abcdef1234567890" not in redacted

    def test_redacts_token_query_parameter(self):
        text = "GET https://example.com/webhook?token=super-secret-value&ok=1 failed"
        redacted = gateway_service._redact_error_text(text)
        assert "super-secret-value" not in redacted

    def test_leaves_non_sensitive_text_untouched(self):
        text = "Gateway agent run completed without a text response."
        assert gateway_service._redact_error_text(text) == text

    def test_empty_text_is_a_noop(self):
        assert gateway_service._redact_error_text("") == ""


class TestThrottleOutboundSend(unittest.TestCase):
    """CL-02: every adapter declares GatewayCapabilities.max_outbound_messages_per_second;
    a burst of sends against one gateway must be spaced out to respect it."""

    def setUp(self):
        gateway_service._OUTBOUND_RATE_NEXT_ALLOWED.clear()

    def test_no_cap_never_sleeps(self):
        with patch.object(gateway_service, "_sleep") as mock_sleep:
            gateway_service._throttle_outbound_send("gw-1", None)
            gateway_service._throttle_outbound_send("gw-1", 0)
        mock_sleep.assert_not_called()

    def test_burst_is_throttled_to_the_declared_rate(self):
        """A mocked clock that never advances on its own means every wait the
        limiter computes must be satisfied by the `_sleep` calls it makes --
        assert those add up to the minimum spacing for the declared cap."""
        fake_now = [0.0]

        def fake_monotonic():
            return fake_now[0]

        def fake_sleep(seconds):
            fake_now[0] += seconds

        cap = 0.5  # WeCom-style low cap: one message every 2 seconds.
        with patch.object(gateway_service, "_monotonic", fake_monotonic), patch.object(
            gateway_service, "_sleep", fake_sleep
        ):
            for _ in range(4):
                gateway_service._throttle_outbound_send("wecom-gateway", cap)

        # 4 sends at 0.5/s must span at least 3 full intervals (6 seconds).
        assert fake_now[0] >= 3 * (1.0 / cap)

    def test_different_gateways_are_throttled_independently(self):
        with patch.object(gateway_service, "_monotonic", return_value=100.0), patch.object(
            gateway_service, "_sleep"
        ) as mock_sleep:
            gateway_service._throttle_outbound_send("gw-a", 1)
            gateway_service._throttle_outbound_send("gw-b", 1)
        # Neither call should have had to wait -- they're on separate buckets,
        # so any _sleep call it makes must be a zero-length no-op.
        for call in mock_sleep.call_args_list:
            assert call.args[0] == 0.0


class TestGatewayEventFailureHandling(unittest.TestCase):
    """GW-05/GW-06: an adapter that raises after a successful agent run
    (rather than fabricating a fake delivery id) must leave the Gateway Event
    at Failed -- never stuck at Running -- with the failure text redacted
    (GW-07) before it reaches frappe.log_error."""

    @patch("huf.ai.gateway_service.frappe")
    def test_real_teams_adapter_raising_on_missing_id_fails_the_event(self, mock_frappe):
        from huf.ai.gateway_adapters.teams import TeamsGatewayAdapter

        # frappe.ValidationError must be a real exception class for the
        # `except frappe.ValidationError` clause inside process_gateway_event
        # to even evaluate -- only its identity matters here, since the
        # adapter raises a plain ValueError that isn't an instance of it.
        mock_frappe.ValidationError = frappe.ValidationError
        mock_frappe.get_traceback.return_value = (
            "Traceback (most recent call last):\n"
            "ValueError: Microsoft Teams message delivery failed: {}"
        )

        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {}  # no "id" in the response
        real_adapter = TeamsGatewayAdapter(
            {"app_id": "appid", "app_password": "apppass"}, http_post=mock_post
        )

        event = MagicMock(
            name="GATEWAY-EVENT-0099",
            status="Queued",
            gateway="Support Teams",
            target_type="Agent",
            target_agent="Support Agent",
            message_text="hello",
            thread_id=None,
            conversation_id="conv1",
            sender_id="user1",
        )
        configured_gateway = gateway(name="Support Teams", provider="Microsoft Teams", execution_user="gateway-bot")
        target_agent_doc = MagicMock(allow_guest=True)
        mock_frappe.get_doc.side_effect = [event, configured_gateway, target_agent_doc]
        mock_run = MagicMock(return_value={"agent_run_id": "AR-002", "response": "Hello back"})

        with patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=real_adapter), patch.dict(
            sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=mock_run)}
        ):
            with self.assertRaises(ValueError):
                gateway_service.process_gateway_event(event.name)

        mock_frappe.db.rollback.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

        failed_calls = [
            c for c in event.db_set.call_args_list
            if isinstance(c.args[0], dict) and c.args[0].get("status") == "Failed"
        ]
        assert failed_calls, "event.db_set was never called with status=Failed"
        error_message = failed_calls[-1].args[0]["error_message"]
        assert "Microsoft Teams message delivery failed" in error_message

        # The Failed db_set must be the *last* status write, applied after
        # the rollback discarded any earlier partial state from this run.
        assert event.db_set.call_args_list[-1] == failed_calls[-1]


class TestApproveGatewayPairingIntegration(IntegrationTestCase):
    """DB-backed coverage for the consolidated approval path (§7 of the plan):
    approve-by-code happy path, legacy entry_name still works, expired entry
    rejected, already-approved entry rejected, revoke, and the expires_at
    regression -- against a real Gateway Access Entry, not a mock."""

    def setUp(self):
        frappe.set_user("Administrator")
        self._gateway_names: list[str] = []

    def tearDown(self):
        frappe.db.delete("Gateway Access Entry", {"gateway": ["in", self._gateway_names]})
        for name in self._gateway_names:
            frappe.db.delete("Gateway", {"name": name})
        frappe.db.commit()

    def _make_gateway(self, name: str) -> None:
        frappe.get_doc(
            {
                "doctype": "Gateway",
                "gateway_name": name,
                "provider": "Telegram",
                "is_enabled": 0,
                "direct_policy": "Pairing",
            }
        ).insert(ignore_permissions=True)
        self._gateway_names.append(name)

    def _make_entry(self, gateway_name: str, *, state="Pending", expires_at=None, pairing_code="PAIR-TEST") -> str:
        doc = frappe.get_doc(
            {
                "doctype": "Gateway Access Entry",
                "gateway": gateway_name,
                "entry_type": "Sender",
                "provider": "Telegram",
                "external_id": "999",
                "pairing_code": pairing_code,
                "state": state,
                "expires_at": expires_at,
                "display_label": "Sender 999",
            }
        ).insert(ignore_permissions=True)
        return doc.name

    def test_approve_by_code_happy_path_clears_expires_at(self):
        gw = "Test Approve By Code"
        self._make_gateway(gw)
        entry_name = self._make_entry(
            gw, expires_at=add_to_date(now_datetime(), minutes=60), pairing_code="PAIR-CAFE"
        )

        result = gateway_service.approve_gateway_pairing("pair-cafe")

        assert result["state"] == "Approved"
        entry = frappe.get_doc("Gateway Access Entry", entry_name)
        assert entry.state == "Approved"
        assert entry.expires_at is None
        assert entry.approved_by == "Administrator"

    def test_approve_by_legacy_entry_name_still_works(self):
        gw = "Test Approve By Name"
        self._make_gateway(gw)
        entry_name = self._make_entry(gw, pairing_code="PAIR-BEEF")

        result = gateway_service.approve_gateway_access_entry(entry_name)

        assert result == {"name": entry_name, "state": "Approved"}
        assert frappe.db.get_value("Gateway Access Entry", entry_name, "state") == "Approved"

    def test_expired_entry_is_rejected(self):
        gw = "Test Expired Entry"
        self._make_gateway(gw)
        entry_name = self._make_entry(
            gw, expires_at=add_to_date(now_datetime(), minutes=-5), pairing_code="PAIR-DEAD"
        )

        with self.assertRaises(frappe.ValidationError):
            gateway_service.approve_gateway_pairing("PAIR-DEAD")
        assert frappe.db.get_value("Gateway Access Entry", entry_name, "state") == "Pending"

    def test_already_approved_entry_is_rejected(self):
        gw = "Test Already Approved"
        self._make_gateway(gw)
        self._make_entry(gw, state="Approved", pairing_code="PAIR-DONE")

        with self.assertRaises(frappe.ValidationError):
            gateway_service.approve_gateway_pairing("PAIR-DONE")

    def test_unknown_code_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            gateway_service.approve_gateway_pairing("PAIR-NONE")

    def test_revoke_sets_state_and_timestamp(self):
        gw = "Test Revoke"
        self._make_gateway(gw)
        entry_name = self._make_entry(gw, pairing_code="PAIR-GONE")

        result = gateway_service.revoke_gateway_access_entry(entry_name)

        assert result["state"] == "Revoked"
        entry = frappe.get_doc("Gateway Access Entry", entry_name)
        assert entry.state == "Revoked"
        assert entry.revoked_at is not None

    def test_list_gateway_access_entries_filters_by_gateway_and_state(self):
        gw = "Test List Entries"
        self._make_gateway(gw)
        self._make_entry(gw, pairing_code="PAIR-LIST")

        pending = gateway_service.list_gateway_access_entries(gateway=gw, state="Pending")
        approved = gateway_service.list_gateway_access_entries(gateway=gw, state="Approved")

        assert any(row["pairing_code"] == "PAIR-LIST" for row in pending)
        assert not any(row["pairing_code"] == "PAIR-LIST" for row in approved)
