"""Channel analytics (admin): volume, AI resolution, response time, broadcast funnel, template quality, estimated spend.

Every spend figure is an ESTIMATE: self-hosted installs pay Meta directly, and Huf never
ships Meta prices. Rates come from the admin-maintained ``Channel Rate Card``; without
rates the amount is null and ``missing_rates`` is true.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from huf.ai.whatsapp.broadcast.cost import market_for_recipient
from huf.permissions import has_capability

RATE_CARD = "Channel Rate Card"
CATEGORIES = ("marketing", "utility", "authentication", "service")
_ROW_FIELDS = ("market", "category", "rate", "effective_from")


def _check():
	if not has_capability(frappe.session.user, "system.integrations.manage"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _bounds(from_date, to_date) -> tuple[str, str, str, str]:
	end = getdate(to_date) if to_date else getdate(nowdate())
	start = getdate(from_date) if from_date else add_days(end, -29)
	if start > end:
		frappe.throw(_("from_date must not be after to_date"))
	return str(start), str(end), f"{start} 00:00:00", f"{add_days(end, 1)} 00:00:00"


# ---- rate card -------------------------------------------------------------


def _clean_rows(rows) -> list[dict]:
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	out = []
	for r in rows or []:
		market = str(r.get("market") or "").strip().upper()
		category = str(r.get("category") or "").strip().lower()
		if not market or category not in CATEGORIES:
			frappe.throw(_("Each rate needs a market and a category of {0}").format(", ".join(CATEGORIES)))
		rate = r.get("rate")
		if rate in (None, ""):
			continue
		try:
			rate = float(rate)
		except (TypeError, ValueError):
			frappe.throw(_("Rate must be a number"))
		if rate < 0:
			frappe.throw(_("Rate must not be negative"))
		eff = r.get("effective_from")
		out.append(
			{"market": market, "category": category, "rate": rate, "effective_from": str(getdate(eff)) if eff else None}
		)
	return out


@frappe.whitelist()
def get_rate_card() -> dict:
	_check()
	doc = frappe.get_doc(RATE_CARD)
	try:
		rows = json.loads(doc.rows or "[]")
	except ValueError:
		rows = []
	return {"currency": doc.currency or "", "rows": rows}


@frappe.whitelist(methods=["POST"])
def save_rate_card(currency: str, rows) -> dict:
	_check()
	currency = (currency or "").strip().upper()
	cleaned = _clean_rows(rows)
	if cleaned and not currency:
		frappe.throw(_("Currency is required when rates are set"))
	doc = frappe.get_doc(RATE_CARD)
	doc.currency = currency
	doc.rows = json.dumps(cleaned)
	doc.save(ignore_permissions=True)
	return get_rate_card()


def _rate_for(rows: list[dict], market: str, category: str, on: str) -> float | None:
	best = None
	for r in rows:
		if r["market"] != market or r["category"] != category:
			continue
		eff = r.get("effective_from")
		if eff and str(eff) > on:
			continue
		if best is None or str(eff or "") >= str(best.get("effective_from") or ""):
			best = r
	return None if best is None else best["rate"]


# ---- aggregates ------------------------------------------------------------


def _volume(gateway: str, lo: str, hi: str, start: str, end: str) -> list[dict]:
	days: dict[str, dict[str, Any]] = {}
	d = getdate(start)
	while str(d) <= end:
		days[str(d)] = {"date": str(d), "conversations": 0, "inbound": 0, "outbound": 0}
		d = add_days(d, 1)
	for date, n in frappe.db.sql(
		"select date(creation), count(*) from `tabChannel Conversation` "
		"where gateway=%s and creation>=%s and creation<%s group by date(creation)",
		(gateway, lo, hi),
	):
		days[str(date)]["conversations"] = n
	for date, inbound, outbound in frappe.db.sql(
		"select date(received_at), count(*), sum(case when ifnull(reply_message_id,'')!='' then 1 else 0 end) "
		"from `tabGateway Event` where gateway=%s and received_at>=%s and received_at<%s group by date(received_at)",
		(gateway, lo, hi),
	):
		days[str(date)]["inbound"] = int(inbound or 0)
		days[str(date)]["outbound"] = int(outbound or 0)
	return list(days.values())


def _resolution(gateway: str, lo: str, hi: str) -> tuple[float | None, float | None]:
	total, handed = frappe.db.sql(
		"select count(*), sum(case when status='handed_off' or ifnull(handoff_name,'')!='' then 1 else 0 end) "
		"from `tabChannel Conversation` where gateway=%s and creation>=%s and creation<%s",
		(gateway, lo, hi),
	)[0]
	if not total:
		return None, None
	handoff = round((handed or 0) / total, 4)
	return round(1 - handoff, 4), handoff


def _median_first_response(gateway: str, lo: str, hi: str) -> float | None:
	"""Median seconds from a conversation's first inbound to its first reply (reply time = event.modified)."""
	rows = frappe.db.sql(
		"select channel_conversation, min(received_at), min(case when ifnull(reply_message_id,'')!='' then modified end) "
		"from `tabGateway Event` where gateway=%s and received_at>=%s and received_at<%s "
		"and ifnull(channel_conversation,'')!='' group by channel_conversation",
		(gateway, lo, hi),
	)
	secs = [(r[2] - r[1]).total_seconds() for r in rows if r[1] and r[2] and r[2] >= r[1]]
	return round(statistics.median(secs), 1) if secs else None


def _funnel(gateway: str, lo: str, hi: str) -> dict:
	row = frappe.db.sql(
		"select sum(sent), sum(delivered), sum(`read`), sum(failed) from `tabWhatsApp Broadcast` "
		"where gateway=%s and creation>=%s and creation<%s",
		(gateway, lo, hi),
	)[0]
	return dict(zip(("sent", "delivered", "read", "failed"), (int(v or 0) for v in row)))


def _template_quality(gateway: str) -> list[dict]:
	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account")
	filters = {"whatsapp_account": account} if account else {}
	rows = frappe.get_all(
		"WhatsApp Template State",
		filters=filters,
		fields=["template", "quality_score", "category"],
		order_by="template asc",
		limit_page_length=500,
	)
	return [{"name": r.template, "quality": r.quality_score, "category": r.category} for r in rows]


def _spend(gateway: str, lo: str, hi: str, today: str) -> dict:
	card = get_rate_card()
	rows = card["rows"]
	out = {
		"currency": card["currency"] or None,
		"amount": None,
		"is_estimate": True,
		"basis": "estimate_from_rate_card" if rows else "no_rate_card",
		"missing_rates": True,
		"note": "Estimate only. You pay Meta directly; Meta's invoice is the source of truth.",
	}
	buckets = frappe.db.sql(
		"select lower(ifnull(b.category,'')), left(replace(r.recipient,'+',''), 4), count(*) "
		"from `tabWhatsApp Broadcast Recipient` r join `tabWhatsApp Broadcast` b on b.name=r.broadcast "
		"where b.gateway=%s and r.status in ('delivered','read') "
		"and coalesce(r.delivered_at, r.sent_at)>=%s and coalesce(r.delivered_at, r.sent_at)<%s "
		"group by 1, 2",
		(gateway, lo, hi),
	)
	if not buckets:
		out["missing_rates"] = False if rows else True
		out["amount"] = 0.0 if rows else None
		return out
	per: dict[tuple[str, str], int] = {}
	for category, prefix, n in buckets:
		key = (market_for_recipient(prefix), category)
		per[key] = per.get(key, 0) + n
	total, missing = 0.0, False
	for (market, category), n in per.items():
		rate = _rate_for(rows, market, category, today)
		if rate is None:
			missing = True
		else:
			total += rate * n
	out["missing_rates"] = missing
	out["amount"] = None if missing else round(total, 4)
	return out


@frappe.whitelist()
def get_analytics(gateway: str, from_date: str | None = None, to_date: str | None = None) -> dict:
	_check()
	start, end, lo, hi = _bounds(from_date, to_date)
	ai_rate, handoff_rate = _resolution(gateway, lo, hi)
	return {
		"gateway": gateway,
		"from_date": start,
		"to_date": end,
		"volume_by_day": _volume(gateway, lo, hi, start, end),
		"ai_resolution_rate": ai_rate,
		"handoff_rate": handoff_rate,
		"median_first_response_seconds": _median_first_response(gateway, lo, hi),
		"broadcast_funnel": _funnel(gateway, lo, hi),
		"template_quality": _template_quality(gateway),
		"estimated_spend": _spend(gateway, lo, hi, end),
	}
