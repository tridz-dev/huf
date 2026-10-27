# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast cron: reap stale ``sending`` rows and revive Running broadcasts with no live tick."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp.broadcast import runner


def resume_stale() -> dict:
	"""Cron */5: stale ``sending`` -> ``unknown`` (never resent); revive Running broadcasts w/o a tick."""
	cutoff = add_to_date(now_datetime(), minutes=-runner.STALE_SENDING_MINUTES)
	stale = frappe.db.sql(
		f"select name, broadcast from `tab{runner.RECIPIENT}` where status='sending' and modified < %s",
		cutoff,
	)
	touched: set[str] = set()
	for name, bcast in stale:
		frappe.db.sql(
			f"update `tab{runner.RECIPIENT}` set status='unknown', error_message=%s "
			"where name=%s and status='sending'",
			("stale_sending: outcome unknown, not resent", name),
		)
		touched.add(bcast)
	for bcast in touched:
		if frappe.db.exists(runner.BROADCAST, bcast):
			frappe.get_doc(runner.BROADCAST, bcast).recount()
	if stale:
		frappe.db.commit()

	revived = []
	cache = frappe.cache()
	for bcast in frappe.get_all(runner.BROADCAST, filters={"status": "Running"}, pluck="name"):
		if cache.get(runner._lock_key(bcast)):
			continue
		frappe.get_doc(runner.BROADCAST, bcast).recount(commit=True)
		if runner._complete_if_done(bcast):
			continue
		runner._enqueue_tick(bcast)
		revived.append(bcast)
	return {"stale_to_unknown": len(stale), "revived": revived}
