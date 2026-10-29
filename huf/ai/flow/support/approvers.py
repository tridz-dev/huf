"""Who may decide an approval and when it lapses (pure functions, no database).

Split out of ``engine.py``; the engine imports both names, so ``engine.check_approver`` and
``engine.approval_expired`` keep working for the API, the sweeper and the tests.
"""

from __future__ import annotations


def approval_expired(waiting: dict, now) -> bool:
	"""True when the approval's recorded ``timeout_at`` (ISO string) is in the past."""
	raw = (waiting or {}).get("timeout_at")
	if not raw:
		return False
	from datetime import datetime

	try:
		deadline = datetime.fromisoformat(str(raw))
	except ValueError:
		return False
	if isinstance(now, str):
		now = datetime.fromisoformat(now)
	return now >= deadline


def check_approver(waiting: dict, user: str, roles) -> str | None:
	"""Fail-closed approver check. Returns None when allowed, else a denial reason.

	* ``approver_type == "role"``: ``user`` must hold ``approver_role``.
	* ``approver_type == "user"``: ``user`` must be in ``approver_users``.
	* anything else (absent included), or a type whose list/role is empty: only a
	  ``System Manager`` may decide.
	The same check applies to approve and reject.
	"""
	waiting = waiting or {}
	roles = set(roles or ())
	approver_type = waiting.get("approver_type")
	if approver_type == "role" and waiting.get("approver_role"):
		if waiting["approver_role"] in roles:
			return None
		return "You do not have the required role '%s' to decide this approval" % waiting["approver_role"]
	if approver_type == "user" and waiting.get("approver_users"):
		if user in set(waiting["approver_users"]):
			return None
		return "You are not an authorised approver for this flow run"
	if "System Manager" in roles:
		return None
	return "Only a System Manager may decide this approval"
