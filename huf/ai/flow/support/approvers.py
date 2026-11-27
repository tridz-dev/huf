"""Who may decide an approval, when it lapses, and whether an app policy asks for one (no database).

Split out of ``engine.py``; the engine imports both names, so ``engine.check_approver`` and
``engine.approval_expired`` keep working for the API, the sweeper and the tests.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

POLICY_HOOK = "huf_flow_approval_policy"

#: Roles every signed-in user (or visitor) holds: naming one would let anybody approve.
_OPEN_ROLES = frozenset({"All", "Guest"})


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

	* ``approver_type == "role"``: ``user`` must hold ``approver_role``, or, when an app policy named
	  several (``approver_roles``), at least one of those.
	* ``approver_type == "user"``: ``user`` must be in ``approver_users``.
	* anything else (absent included), or a type whose list/role is empty: only a
	  ``System Manager`` may decide.
	The same check applies to approve and reject. In a test run the person who started the test may also
	decide it, so they can try the whole flow without asking anyone.
	"""
	waiting = waiting or {}
	roles = set(roles or ())
	if waiting.get("test_run") and user and waiting.get("test_owner") == user:
		return None
	approver_type = waiting.get("approver_type")
	required_roles = approver_roles_of(waiting)
	if approver_type == "role" and required_roles:
		if roles.intersection(required_roles):
			return None
		return "You do not have the required role '%s' to decide this approval" % "' or '".join(required_roles)
	if approver_type == "user" and waiting.get("approver_users"):
		if user in set(waiting["approver_users"]):
			return None
		return "You are not an authorised approver for this flow run"
	if "System Manager" in roles:
		return None
	return "Only a System Manager may decide this approval"


def approver_roles_of(waiting: dict) -> list[str]:
	"""The roles that may decide a role approval: ``approver_roles`` (set by an app policy), else ``approver_role``."""
	waiting = waiting or {}
	if waiting.get("approver_roles"):
		return list(waiting["approver_roles"])
	return [waiting["approver_role"]] if waiting.get("approver_role") else []


@dataclass(frozen=True)
class ApprovalPolicy:
	"""What the app policies say about one approval step.

	``reason`` is a code, never free text: ``no_policy``, ``policy_required``, ``policy_not_required``
	or ``policy_error``. ``approver_roles`` is empty when the step's own approver settings apply.
	"""

	required: bool = True
	approver_roles: tuple[str, ...] = ()
	reason: str = "no_policy"


def _read_answer(answer) -> tuple[bool, list[str]]:
	"""``(required, approver_roles)`` of one hook answer; raises on any other shape."""
	named = answer.get("approver_roles") if isinstance(answer, dict) else None
	valid = (
		isinstance(answer, dict)
		and isinstance(answer.get("required"), bool)
		and (
			named is None
			or (
				isinstance(named, (list, tuple))
				and all(isinstance(r, str) and r.strip() and r not in _OPEN_ROLES for r in named)
			)
		)
	)
	if not valid:
		raise ValueError
	return answer["required"], list(named or [])


def evaluate_approval_policy(flow: str, node: dict, context: dict) -> ApprovalPolicy:
	"""Ask every ``huf_flow_approval_policy(flow, node, context)`` hook whether this step needs a person.

	A hook returns ``None`` (no opinion) or ``{"required": bool, "approver_roles": [role, ...]}``
	(``approver_roles`` optional; when given they replace the step's approver settings). ``flow`` is the
	flow id; ``node`` and ``context`` are copies, so a hook cannot change the run.

	Fails CLOSED: approval is skipped only when at least one hook said ``required: False`` and none said
	anything else. A hook that cannot be loaded, raises or answers in any other shape means approval is
	required, with the step's own approvers.
	"""
	import frappe

	required, not_required, roles = False, False, []
	messages = getattr(getattr(frappe, "local", None), "message_log", None)
	message_count = len(messages) if isinstance(messages, list) else 0
	try:
		for path in frappe.get_hooks(POLICY_HOOK) or []:
			answer = frappe.get_attr(path)(flow, copy.deepcopy(node), copy.deepcopy(context))
			if answer is None:
				continue
			needed, named = _read_answer(answer)
			roles.extend(r for r in named if r not in roles)
			if needed:
				required = True
			else:
				not_required = True
	except Exception as exc:  # noqa: BLE001  any failure of app code means approval is required
		if isinstance(messages, list):
			del messages[message_count:]  # a frappe.throw in the hook must not surface to whoever is calling
		# The exception type only: its message and traceback can carry the run's data (personal data).
		frappe.log_error(
			title="Flow approval policy",
			message=f"{POLICY_HOOK} failed for flow {flow}, step {(node or {}).get('id')}: {type(exc).__name__}. Approval is required.",
		)
		return ApprovalPolicy(reason="policy_error")

	if required:
		return ApprovalPolicy(approver_roles=tuple(roles), reason="policy_required")
	if not_required:
		return ApprovalPolicy(required=False, reason="policy_not_required")
	return ApprovalPolicy()
