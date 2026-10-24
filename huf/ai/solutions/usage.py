"""Last-24h WhatsApp send usage per solution, read from WhatsApp Send Key claims (A2, A4).

Counts Pending and Sent claims only, exactly as the send caps do; sends with no solution stamp
are grouped under ''.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.solutions.ceiling import ceiling_for_gateway

_KEY_DOCTYPE = "WhatsApp Send Key"


def _now() -> datetime:
	return now_datetime()


def sends_24h_by_solution(gateway: str, now: Optional[datetime] = None) -> dict[str, int]:
	if not gateway:
		return {}
	since = add_to_date(now or _now(), hours=-24)
	until = now or _now()
	solutions = frappe.get_all(
		_KEY_DOCTYPE,
		filters={"gateway": gateway, "status": ["in", ["Pending", "Sent"]], "claimed_at": ["between", [since, until]]},
		pluck="solution",
	)
	out: dict[str, int] = {}
	for solution in solutions:
		out[solution or ""] = out.get(solution or "", 0) + 1
	return out


def usage_pct(solution: str, gateway: str) -> Optional[float]:
	ceiling, _source = ceiling_for_gateway(gateway)
	if not ceiling:
		return None
	count = sends_24h_by_solution(gateway, now=_now()).get(solution or "", 0)
	return round(count / ceiling * 100, 1)


def blame(gateway: str, now: Optional[datetime] = None) -> Optional[dict]:
	"""The solution with the most sends in the last 24h (share of all sends); ties break by name."""
	counts = sends_24h_by_solution(gateway, now=now)
	total = sum(counts.values())
	named = {k: v for k, v in counts.items() if k}
	if not total or not named:
		return None
	top = sorted(named.items(), key=lambda kv: (-kv[1], kv[0]))[0]
	return {"solution": top[0], "share_pct": round(top[1] / total * 100, 1)}
