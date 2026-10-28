# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast realtime progress.

One ``wa_broadcast_progress`` event per broadcast, sent to the document room (so only users who can read the
WhatsApp Broadcast document receive it), throttled to one per ``THROTTLE_SECONDS`` unless ``force``. The UI
keeps polling as the fallback, so a missed or filtered event never matters. Never raises.
"""

from __future__ import annotations

import time

import frappe

from huf.ai.whatsapp.broadcast import policy

EVENT = "wa_broadcast_progress"
DOCTYPE = "WhatsApp Broadcast"
THROTTLE_SECONDS = policy.BY_KEY["progress_throttle_seconds"].default
_FIELDS = ("status", "total", "queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped", "pause_reason")


def publish(broadcast: str, force: bool = False) -> bool:
	"""Publish the broadcast's current status and counters. Returns True when an event was sent."""
	try:
		cache = frappe.cache()
		key = f"wa_broadcast_progress:{frappe.local.site}:{broadcast}"
		now = time.time()
		last = cache.get(key)
		if not force and last and now - float(last) < THROTTLE_SECONDS:
			return False
		cache.set(key, now, ex=60)
		row = frappe.db.get_value(DOCTYPE, broadcast, list(_FIELDS), as_dict=True)
		if not row:
			return False
		frappe.publish_realtime(EVENT, {"broadcast": broadcast, **row}, doctype=DOCTYPE, docname=broadcast, after_commit=True)
		return True
	except Exception:
		return False
