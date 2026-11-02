"""Pairing, access-state and consent constants."""

from __future__ import annotations

# 31 unambiguous characters: A-Z without I, L, O and 2-9 (no 0/1).
PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
PAIRING_PREFIX = "PAIR-"
PAIRING_RESEND_COOLDOWN_MINUTES = 10
PAIRING_APPROVAL_MAX_FAILURES_PER_MINUTE = 5
PENDING_ENTRY_RETENTION_DAYS = 7
PAIRING_DEFAULT_PENDING_LIMIT = 50
PENDING_ROOM_LIMIT = 20  # max pending Room entries per gateway (separate from Sender pairing)
PAIRING_DEFAULT_REPLY_DAILY_LIMIT = 20
PAIRING_MAX_REQUESTS_PER_SENDER_PER_DAY = 3
# A sender whose access was removed or whose request was declined may ask again after this long.
ACCESS_REREQUEST_COOLDOWN_HOURS = 24

# Access entry states that stop a sender from being admitted. Blocked and Opted out are never re-paired;
# Revoked (access removed or request declined) may ask again after ACCESS_REREQUEST_COOLDOWN_HOURS.
ENTRY_STATE_BLOCKED = "Blocked"
ENTRY_STATE_REVOKED = "Revoked"
ENTRY_STATE_OPTED_OUT = "Opted out"
ENTRY_STATE_EXPIRED = "Expired"
_RESTORABLE_STATES = ("Approved", ENTRY_STATE_REVOKED, ENTRY_STATE_BLOCKED)
_LIVE_ENTRY_STATES = ("Approved", "Pending", ENTRY_STATE_OPTED_OUT, ENTRY_STATE_REVOKED, ENTRY_STATE_BLOCKED)


DEFAULT_OPT_OUT_KEYWORDS = "STOP\nUNSUBSCRIBE\nCANCEL\nEND\nQUIT"
DEFAULT_OPT_IN_KEYWORDS = "START\nUNSTOP\nSUBSCRIBE"
DEFAULT_OPT_OUT_REPLY = (
    "You have been unsubscribed and will not receive further messages. Reply START to resubscribe."
)
DEFAULT_OPT_IN_REPLY = "You have been resubscribed. Reply STOP at any time to unsubscribe."
DEFAULT_INBOUND_SENDER_LIMIT = 20
INBOUND_SENDER_WINDOW_SECONDS = 600

_GATEWAY_ADMIN_ROLES = ("System Manager", "Huf Admin")
