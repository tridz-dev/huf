"""Forward-only ordering for a stored WhatsApp Message status.

frappe_whatsapp's ``update_message_status`` writes whatever arrives last, so Meta's out-of-order or replayed
status callbacks must be dropped before they reach it (see ``whatsapp_bridge.forward_status``).
"""

from __future__ import annotations

from typing import Any

_RANK = {"sent": 1, "delivered": 2, "read": 3, "played": 4}
_REACHED_PHONE = ("delivered", "read", "played")


def message_status_regresses(current: Any, new: Any) -> bool:
	"""True when ``new`` must not replace ``current`` (sent < delivered < read < played).

	A ``failed`` never replaces delivered/read/played, a late ``sent`` never replaces ``failed`` or a later
	state, a later state does replace ``failed``, and a replay of the stored status is dropped. An unknown or
	empty stored status never blocks a write.
	"""
	cur, nxt = str(current or "").lower(), str(new or "").lower()
	if not cur:
		return False
	if cur == nxt:
		return True
	if nxt == "failed":
		return cur in _REACHED_PHONE
	if cur == "failed":
		return nxt not in _REACHED_PHONE
	return _RANK.get(nxt, 0) < _RANK.get(cur, 0)
