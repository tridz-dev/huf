"""
Subscription CLI authentication service.

Frappe-backed operations for `Subscription Auth Challenge` documents and the
authentication-related fields on `Subscription Runtime` / `Agent Run`. This
module is deliberately narrow: it does the DB reads/writes for the auth
state machine described in PLAN.md sec 59-63, and nothing else.

Explicitly OUT of scope here (wired by later, serialized tasks):
  - Calling into `agent_integration.py` / `run.py` to actually pause/resume
    agent execution.
  - Acquiring or releasing the per-conversation Redis lock.
  - The scheduled sweeper that expires stale challenges (T-06-E) - this
    module only provides the pure `check_challenge_expiry` check it needs.
  - Re-queuing parked runs once auth succeeds - this module only provides
    the read-only `resolve_parked_runs_for_runtime` lookup it needs.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

# Active = still eligible to be reused instead of creating a duplicate
# challenge for the same runtime (dedup - PLAN.md sec 63.3).
ACTIVE_CHALLENGE_STATUSES = ("Pending", "Waiting User", "Verifying")

CHALLENGE_FIELDS = [
	"name",
	"runtime",
	"provider",
	"status",
	"mode",
	"verification_url",
	"user_code",
	"safe_instructions",
	"created_by",
	"expires_at",
	"completed_at",
	"error_code",
	"error_message",
	"parked_agent_run",
	"parked_conversation",
	"metadata",
]

AGENT_RUN_WAITING_AUTH_STATUS = "Waiting Authentication"

# Subscription Runtime.auth_status states this module writes.
_RUNTIME_STATE_SUCCESS = "ready"
_RUNTIME_STATE_FAILURE_STATES = ("required", "failed")


def _runtime_name(runtime) -> str:
	"""Accept either a runtime document or a runtime name/id string."""
	if isinstance(runtime, str):
		return runtime
	return runtime.name


def get_or_create_active_challenge(runtime) -> dict[str, Any]:
	"""
	Return the key fields of the active `Subscription Auth Challenge` for
	`runtime`, creating one if none exists.

	Deduplication (PLAN.md sec 63.3): a runtime must never have more than one
	challenge in flight. "Active" means status in Pending/Waiting User/
	Verifying AND not expired. If such a challenge already exists it is
	returned as-is (no new document is created); otherwise a new challenge
	is created with status=Pending.

	`runtime` may be a `Subscription Runtime` document or its name.
	"""
	runtime_name = _runtime_name(runtime)
	now = now_datetime()

	existing_name = frappe.get_all(
		"Subscription Auth Challenge",
		filters={
			"runtime": runtime_name,
			"status": ["in", list(ACTIVE_CHALLENGE_STATUSES)],
			"expires_at": [">", now],
		},
		order_by="creation desc",
		limit_page_length=1,
		pluck="name",
	)

	if existing_name:
		challenge = frappe.get_doc("Subscription Auth Challenge", existing_name[0])
		return {field: challenge.get(field) for field in CHALLENGE_FIELDS}

	provider = runtime.provider_family if not isinstance(runtime, str) else None

	challenge = frappe.get_doc(
		{
			"doctype": "Subscription Auth Challenge",
			"runtime": runtime_name,
			"provider": provider,
			"status": "Pending",
			"created_by": frappe.session.user,
		}
	)
	challenge.insert(ignore_permissions=True)

	return {field: challenge.get(field) for field in CHALLENGE_FIELDS}


def park_run(agent_run_name: str, challenge_name: str) -> None:
	"""
	Mark an Agent Run as parked, waiting on an authentication challenge.

	Sets `Agent Run.status = "Waiting Authentication"` and
	`Agent Run.auth_challenge = challenge_name`.

	CONTRACT (PLAN.md sec 75.3 - do not hold a Redis lock for minutes/hours):
	this function does NOT acquire, hold, or release the per-conversation
	Redis lock, and it does NOT touch `agent_integration.py` / `run.py`. The
	CALLER is responsible for releasing any conversation lock it holds
	*before* invoking `park_run` - parking a run is expected to leave it
	waiting for an arbitrary amount of time (until the user completes the
	auth challenge), so no lock may be held across this call.
	"""
	frappe.db.set_value(
		"Agent Run",
		agent_run_name,
		{
			"status": AGENT_RUN_WAITING_AUTH_STATUS,
			"auth_challenge": challenge_name,
		},
		update_modified=True,
	)


def mark_runtime_auth_state(runtime, state: str, **kwargs) -> None:
	"""
	Update `Subscription Runtime.auth_status` and its related timestamp
	fields for the given `state` (one of the runtime's `auth_status` Select
	options: unknown/ready/required/waiting_user/verifying/failed).

	Always updates `last_auth_checked_at`. Additionally updates:
	  - `last_auth_success_at` when state == "ready"
	  - `last_auth_failure_at` when state in ("required", "failed")

	Optional kwargs `error_code`, `error_message`, `account_hint` are written
	to `auth_error_code`, `auth_error_message`, `auth_account_hint`
	respectively when provided.
	"""
	runtime_name = _runtime_name(runtime)
	now = now_datetime()

	values: dict[str, Any] = {
		"auth_status": state,
		"last_auth_checked_at": now,
	}

	if state == _RUNTIME_STATE_SUCCESS:
		values["last_auth_success_at"] = now
	elif state in _RUNTIME_STATE_FAILURE_STATES:
		values["last_auth_failure_at"] = now

	if "error_code" in kwargs:
		values["auth_error_code"] = kwargs["error_code"]
	if "error_message" in kwargs:
		values["auth_error_message"] = kwargs["error_message"]
	if "account_hint" in kwargs:
		values["auth_account_hint"] = kwargs["account_hint"]

	frappe.db.set_value("Subscription Runtime", runtime_name, values, update_modified=True)


def check_challenge_expiry(challenge) -> bool:
	"""
	Pure check: return True if `challenge.expires_at` is in the past.

	No DB writes. Used by the scheduled sweeper (T-06-E) which is
	responsible for actually transitioning expired challenges to status
	"Expired" - this function only answers the yes/no question.

	`challenge` may be a `Subscription Auth Challenge` document or any
	object/dict exposing an `expires_at` attribute/key.
	"""
	expires_at = challenge.get("expires_at") if isinstance(challenge, dict) else challenge.expires_at
	if not expires_at:
		return False
	return now_datetime() > expires_at


def resolve_parked_runs_for_runtime(runtime_name: str) -> list[str]:
	"""
	Return the names of `Agent Run` documents currently parked
	(status="Waiting Authentication") on a challenge belonging to
	`runtime_name`.

	Read-only: makes no state changes. A later task uses this list to
	re-queue the parked runs once authentication succeeds.
	"""
	challenge_names = frappe.get_all(
		"Subscription Auth Challenge",
		filters={"runtime": runtime_name},
		pluck="name",
	)

	if not challenge_names:
		return []

	return frappe.get_all(
		"Agent Run",
		filters={
			"status": AGENT_RUN_WAITING_AUTH_STATUS,
			"auth_challenge": ["in", challenge_names],
		},
		pluck="name",
	)
