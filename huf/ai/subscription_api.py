"""Whitelisted Frappe API endpoints for Subscription CLI runtimes.

Covers PLAN.md §25 (runtime probe/test) and §64 (auth-challenge lifecycle,
re-authenticate/logout). This module is the HTTP-facing layer only: all real
logic (challenge state machine, capability negotiation, resume-after-auth)
lives in `huf.ai.subscription.auth_service`, `huf.ai.subscription.resume`, and
the provider adapters under `huf.ai.subscription.adapters`.

Permission model (mirrors `huf/huf/doctype/subscription_runtime/subscription_runtime.py`
and `huf.permissions.has_capability`):
  - Reading/probing a runtime requires `subscription_runtime.use` (or `.manage`,
    or System Manager) AND the runtime's own tenancy check
    (`Subscription Runtime.check_tenancy`) for the calling user.
  - Beginning/polling/submitting/cancelling an auth challenge requires the same
    use-or-manage + tenancy check — any tenant of a shared runtime may drive
    its login flow.
  - Logging a runtime out requires `subscription_runtime.manage` specifically
    (PLAN.md §65.2: logout affects every tenant of a shared runtime, so it is
    not covered by mere `.use`).

Security note (PLAN.md §64.3): no endpoint here accepts, stores, or logs a
password. `submit_subscription_auth_input`'s `value` carries only short,
provider-generated transient values (e.g. a device-code confirmation or a
one-time paste-back token) and is never written to `frappe.log_error` /
logging in full.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.subscription import auth_service, resume
from huf.ai.subscription.adapters.base import SubscriptionCLIAdapter
from huf.ai.subscription.adapters.claude import ClaudeAdapter
from huf.ai.subscription.adapters.codex import CodexAdapter
from huf.ai.subscription.adapters.gemini import GeminiAdapter
from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.errors import SubscriptionError
from huf.ai.subscription.types import AuthStatus

# Same adapter registry keyed by `Subscription Runtime.provider_family` as
# `huf.ai.subscription.executor._ADAPTER_CLASSES`. Kept as a separate copy
# (rather than importing the executor's private module-level dict) so this
# API module has no import-time dependency on `executor.py`'s heavier chain
# (session_binding/staging/streaming/telemetry), matching the existing
# lazy-import style used across this package to avoid load cycles.
_ADAPTER_CLASSES: dict[str, type[SubscriptionCLIAdapter]] = {
	"Claude": ClaudeAdapter,
	"Codex": CodexAdapter,
	"Gemini": GeminiAdapter,
}

# Max length accepted for `submit_subscription_auth_input`'s `value`. Generous
# enough for any device-code / paste-back token a provider CLI has been seen
# to ask for, small enough to reject anything that looks like a pasted
# password/secret blob or an accidental full-file paste.
_MAX_AUTH_INPUT_LENGTH = 512


def _build_transport_for_runtime(runtime):
	"""Construct the ExecutionTransport matching the runtime's transport_type.

	Duplicated (in miniature) from `huf.ai.subscription.executor._build_transport_for_runtime`
	rather than imported, for the same load-order reason `_ADAPTER_CLASSES` is
	duplicated above.
	"""
	transport_type = runtime.transport_type

	if transport_type == "Local":
		from huf.ai.subscription.transports.local import LocalTransport

		return LocalTransport(runtime.cli_path, runtime_dir=runtime.working_directory or None)

	if transport_type == "Docker":
		from huf.ai.subscription.transports.docker import DockerExecTransport

		return DockerExecTransport(
			runtime.docker_container,
			workdir=runtime.working_directory or None,
		)

	if transport_type == "SSH":
		from huf.ai.subscription.transports.ssh import SSHExecTransport

		return SSHExecTransport(runtime.ssh_connection)

	frappe.throw(
		_("Unsupported subscription runtime transport type: {0}").format(transport_type),
		frappe.ValidationError,
	)


def _build_adapter(runtime) -> SubscriptionCLIAdapter:
	adapter_cls = _ADAPTER_CLASSES.get(runtime.provider_family)
	if adapter_cls is None:
		frappe.throw(
			_("Unsupported subscription runtime provider family: {0}").format(runtime.provider_family),
			frappe.ValidationError,
		)
	transport = _build_transport_for_runtime(runtime)
	return adapter_cls(transport)


def _run_async(coro):
	"""Run an async coroutine from sync Frappe request context.

	Mirrors `huf.ai.subscription.executor._run_async`.
	"""
	try:
		asyncio.get_running_loop()
	except RuntimeError:
		return asyncio.run(coro)
	else:
		new_loop = asyncio.new_event_loop()
		try:
			return new_loop.run_until_complete(coro)
		finally:
			new_loop.close()


def _has_runtime_access(user: str, runtime=None) -> bool:
	"""Return True if `user` has base access to Subscription Runtime features.

	Base access = `subscription_runtime.use` or `.manage` capability (or System
	Manager). This is deliberately separate from `check_tenancy`, which further
	restricts a *specific* runtime to its authorized users/roles.
	"""
	from huf.permissions import has_capability

	if "System Manager" in frappe.get_roles(user):
		return True
	return has_capability(user, "subscription_runtime.use") or has_capability(
		user, "subscription_runtime.manage"
	)


def _has_manage_access(user: str) -> bool:
	from huf.permissions import has_capability

	if "System Manager" in frappe.get_roles(user):
		return True
	return has_capability(user, "subscription_runtime.manage")


def _get_runtime_or_throw(runtime_name: str):
	if not runtime_name:
		frappe.throw(_("runtime_name is required."), frappe.ValidationError)
	return frappe.get_doc("Subscription Runtime", runtime_name)


def _require_runtime_use(runtime_name: str):
	"""Load the runtime and enforce use-or-manage capability + tenancy.

	Returns the loaded `Subscription Runtime` document. Raises
	`frappe.PermissionError` before any adapter/CLI call is made.
	"""
	user = frappe.session.user
	if not _has_runtime_access(user):
		frappe.throw(_("You do not have permission to use Subscription Runtimes."), frappe.PermissionError)

	runtime = _get_runtime_or_throw(runtime_name)
	if not runtime.check_tenancy(user):
		frappe.throw(
			_("You are not authorized to use this subscription runtime."), frappe.PermissionError
		)
	return runtime


def _require_runtime_manage(runtime_name: str):
	"""Load the runtime and enforce `.manage` capability specifically."""
	user = frappe.session.user
	if not _has_manage_access(user):
		frappe.throw(
			_("You do not have permission to manage Subscription Runtimes."), frappe.PermissionError
		)
	return _get_runtime_or_throw(runtime_name)


def _auth_status_to_dict(status: AuthStatus) -> dict[str, Any]:
	return asdict(status)


def _capabilities_to_normalized_result(
	capabilities: RuntimeCapabilities, auth_status: AuthStatus, runtime
) -> dict[str, Any]:
	"""Build the normalized probe result shape from PLAN.md §25."""
	return {
		"success": True,
		"runtime": runtime.name,
		"cli": runtime.provider_family,
		"version": runtime.get("detected_version"),
		"authenticated": auth_status.state == "ready",
		"session_resume": capabilities.supports_session_resume,
		"structured_output": capabilities.supports_json,
		"streaming": capabilities.supports_stream_json,
		"vision": capabilities.supports_images,
		"usage": capabilities.supports_usage,
		"mcp": capabilities.supports_mcp,
	}


def _persist_probe_result(runtime, capabilities: RuntimeCapabilities, version: str | None, error: str | None):
	values = {
		"last_tested_on": now_datetime(),
		"last_test_status": "Failed" if error else "Success",
		"last_error": error,
		"capabilities_snapshot": frappe.as_json(asdict(capabilities)) if capabilities else None,
	}
	if version:
		values["detected_version"] = version
	frappe.db.set_value("Subscription Runtime", runtime.name, values, update_modified=True)


def _run_probe(runtime) -> dict[str, Any]:
	"""Run `adapter.probe()` + `adapter.check_auth()` for `runtime` and persist the result.

	Never raises for provider/CLI-level failures — those come back as
	`{"success": False, ...}`. Only permission/lookup errors (already checked
	by the caller before this is invoked) can raise.
	"""
	adapter = _build_adapter(runtime)

	try:
		capabilities = _run_async(adapter.probe(runtime))
	except SubscriptionError as exc:
		_persist_probe_result(runtime, RuntimeCapabilities(), None, str(exc))
		return {
			"success": False,
			"runtime": runtime.name,
			"cli": runtime.provider_family,
			"version": None,
			"authenticated": False,
			"session_resume": False,
			"structured_output": False,
			"streaming": False,
			"vision": False,
			"usage": False,
			"mcp": False,
			"error": str(exc),
		}

	# Version detection is adapter-internal (e.g. parsed from `--version`
	# output); adapters don't expose it directly on RuntimeCapabilities, so we
	# best-effort re-derive it the same way `probe()` did if the adapter
	# exposes a helper, otherwise leave it to whatever was already stored.
	version = getattr(adapter, "last_detected_version", None) or runtime.get("detected_version")

	try:
		auth_status = _run_async(adapter.check_auth(runtime))
	except SubscriptionError as exc:
		_persist_probe_result(runtime, capabilities, version, str(exc))
		result = _capabilities_to_normalized_result(capabilities, AuthStatus(
			state="unknown", account_hint=None, method=None, message=str(exc), checked_at=now_datetime().isoformat()
		), runtime)
		result["success"] = False
		result["error"] = str(exc)
		return result

	_persist_probe_result(runtime, capabilities, version, None)
	auth_service.mark_runtime_auth_state(
		runtime,
		"ready" if auth_status.state == "ready" else "required",
		account_hint=auth_status.account_hint,
	)
	return _capabilities_to_normalized_result(capabilities, auth_status, runtime)


@frappe.whitelist()
def test_subscription_runtime_connection(runtime_name: str) -> dict[str, Any]:
	"""Probe a Subscription CLI runtime (PLAN.md §25).

	Sibling of `huf.ai.local_runtime.test_provider_connection` for the
	"Subscription CLI" `provider_mode` branch — kept as its own function
	rather than folded into that router because the two probes have entirely
	disjoint inputs/outputs (API-key/HTTP probing vs. CLI probing over a
	transport), and `test_provider_connection` is keyed by AI Provider name
	while this is keyed by Subscription Runtime name.

	Returns the normalized shape from PLAN.md §25:
	`{"success", "runtime", "cli", "version", "authenticated", "session_resume",
	"structured_output", "streaming", "vision", "usage", "mcp"}` (plus an
	`"error"` key when `success` is False).
	"""
	runtime = _require_runtime_use(runtime_name)
	return _run_probe(runtime)


@frappe.whitelist()
def refresh_subscription_runtime_probe(runtime_name: str) -> dict[str, Any]:
	"""Re-run the probe for `runtime_name` and persist the refreshed capability snapshot.

	Identical behavior to `test_subscription_runtime_connection` — kept as a
	separate, explicitly-named endpoint per PLAN.md §25 for callers that want
	to express "refresh the stored snapshot" rather than "test the connection"
	as their intent (e.g. a periodic UI refresh vs. a user-initiated Test
	Connection click).
	"""
	runtime = _require_runtime_use(runtime_name)
	return _run_probe(runtime)


# ---------------------------------------------------------------------------
# Auth-challenge lifecycle (PLAN.md §64.3)
# ---------------------------------------------------------------------------

_CHALLENGE_PUBLIC_FIELDS = (
	"name",
	"runtime",
	"provider",
	"status",
	"mode",
	"verification_url",
	"user_code",
	"safe_instructions",
	"expires_at",
)


def _challenge_public_dict(challenge: dict[str, Any]) -> dict[str, Any]:
	"""Project a challenge dict down to fields safe to hand back to the caller.

	`user_code`/`verification_url` are deliberately included as-is: they are
	provider-generated, meant to be shown to the human completing the login,
	and are not secrets. Internal bookkeeping fields (`created_by`,
	`parked_agent_run`, `parked_conversation`, `metadata`, error detail) are
	left out of the public shape.
	"""
	return {field: challenge.get(field) for field in _CHALLENGE_PUBLIC_FIELDS}


def _get_challenge_or_throw(challenge_name: str):
	if not challenge_name:
		frappe.throw(_("challenge_name is required."), frappe.ValidationError)
	return frappe.get_doc("Subscription Auth Challenge", challenge_name)


def _require_challenge_use(challenge_name: str):
	"""Load a challenge + its runtime and enforce use-or-manage + tenancy on the runtime."""
	challenge = _get_challenge_or_throw(challenge_name)
	runtime = _require_runtime_use(challenge.runtime)
	return challenge, runtime


@frappe.whitelist()
def begin_subscription_auth(runtime_name: str) -> dict[str, Any]:
	"""Start (or resume) a login challenge for `runtime_name` (PLAN.md §64.3).

	Reuses `auth_service.get_or_create_active_challenge` for deduplication
	(a runtime must never have more than one challenge in flight) and rate
	limiting, rather than unconditionally calling the adapter and creating a
	new document — this keeps the dedup/rate-limit invariants centralized in
	`auth_service` instead of duplicated here.

	If no active challenge exists yet, this also calls the adapter's
	`begin_auth()` to obtain fresh challenge details (verification URL/user
	code/etc.) and stores them on the newly created challenge document before
	returning.
	"""
	runtime = _require_runtime_use(runtime_name)

	existing = auth_service.get_or_create_active_challenge(runtime)

	# `get_or_create_active_challenge` creates a bare Pending challenge with no
	# provider-specific details yet when none existed. Detect that case (no
	# verification_url/user_code/mode) and fill it in from the adapter.
	if not existing.get("mode"):
		adapter = _build_adapter(runtime)
		try:
			auth_challenge = _run_async(adapter.begin_auth(runtime))
		except SubscriptionError as exc:
			frappe.db.set_value(
				"Subscription Auth Challenge",
				existing["name"],
				{"status": "Failed", "error_message": str(exc)},
				update_modified=True,
			)
			frappe.throw(_("Failed to start authentication: {0}").format(str(exc)))

		# Only overwrite fields the adapter actually populated. All three
		# adapters (claude.py/codex.py/gemini.py) currently return
		# `expires_at=None` from `begin_auth()` -- unconditionally writing
		# that would wipe the sane default `expires_at` that
		# `Subscription Auth Challenge.validate()` already set at creation
		# time (creation + DEFAULT_CHALLENGE_LIFETIME_MINUTES), which both
		# breaks `auth_service`'s active-challenge dedup (it filters on
		# `expires_at > now`) and means `sweep_expired_auth_challenges` would
		# never expire the challenge. The same guard is applied to the other
		# adapter-sourced fields since this branch can, in principle, run
		# again against an already-existing challenge (e.g. via
		# `get_or_create_active_challenge`'s reuse path) and a None from the
		# adapter should never blank out a previously-set value.
		updates = {"status": "Waiting User"}
		if auth_challenge.mode:
			updates["mode"] = auth_challenge.mode
		if auth_challenge.verification_url:
			updates["verification_url"] = auth_challenge.verification_url
		if auth_challenge.user_code:
			updates["user_code"] = auth_challenge.user_code
		if auth_challenge.prompt:
			updates["safe_instructions"] = auth_challenge.prompt
		if auth_challenge.expires_at:
			updates["expires_at"] = auth_challenge.expires_at

		frappe.db.set_value(
			"Subscription Auth Challenge",
			existing["name"],
			updates,
			update_modified=True,
		)
		existing = frappe.get_doc("Subscription Auth Challenge", existing["name"]).as_dict()

	return _challenge_public_dict(existing)


@frappe.whitelist()
def poll_subscription_auth(challenge_name: str) -> dict[str, Any]:
	"""Poll an in-flight login challenge for completion (PLAN.md §64.3).

	On a transition to the authenticated ("ready") state, this is the exact
	call site the T-06-D task's `# TODO(T-10-api)` comment in
	`huf/ai/subscription/resume.py` was waiting for: it marks the runtime's
	auth state "ready" via `auth_service.mark_runtime_auth_state` and then
	calls `resume.resume_after_auth_success(runtime_name)` to re-queue any
	Agent Runs that were parked waiting on this login, before returning the
	current `AuthStatus` to the polling client.
	"""
	challenge, runtime = _require_challenge_use(challenge_name)

	adapter = _build_adapter(runtime)
	try:
		auth_status = _run_async(adapter.poll_auth(runtime, challenge.name))
	except SubscriptionError as exc:
		auth_service.mark_runtime_auth_state(runtime, "failed", error_message=str(exc))
		frappe.db.set_value(
			"Subscription Auth Challenge",
			challenge.name,
			{"status": "Failed", "error_message": str(exc)},
			update_modified=True,
		)
		frappe.db.commit()  # nosemgrep: justified - persist failure before returning
		return _auth_status_to_dict(
			AuthStatus(state="failed", account_hint=None, method=None, message=str(exc), checked_at=now_datetime().isoformat())
		)

	if auth_status.state == "ready":
		frappe.db.set_value(
			"Subscription Auth Challenge",
			challenge.name,
			{"status": "Success", "completed_at": now_datetime()},
			update_modified=True,
		)
		auth_service.mark_runtime_auth_state(runtime, "ready", account_hint=auth_status.account_hint)
		frappe.db.commit()  # nosemgrep: justified - persist auth success before resuming parked runs
		resume.resume_after_auth_success(runtime.name)
	elif auth_status.state in ("required", "failed"):
		frappe.db.set_value(
			"Subscription Auth Challenge",
			challenge.name,
			{"status": "Failed", "error_message": auth_status.message},
			update_modified=True,
		)
		auth_service.mark_runtime_auth_state(
			runtime, "failed", error_message=auth_status.message, account_hint=auth_status.account_hint
		)
		frappe.db.commit()  # nosemgrep: justified - persist failure before returning
	else:
		# Still waiting (waiting_user/verifying) - no terminal transition yet.
		auth_service.mark_runtime_auth_state(runtime, auth_status.state, account_hint=auth_status.account_hint)
		frappe.db.commit()  # nosemgrep: justified - persist interim state before returning

	return _auth_status_to_dict(auth_status)


@frappe.whitelist()
def submit_subscription_auth_input(challenge_name: str, value: str) -> dict[str, Any]:
	"""Submit a user-provided value to an in-flight login challenge (PLAN.md §64.3).

	`value` must be a short, provider-generated/transient string (a device-code
	confirmation, a one-time paste-back token, etc.) — this endpoint never
	accepts, stores, or logs a password field. It is validated for a sane
	length here and is never passed to `frappe.log_error` / logging in full by
	this module or by `auth_service`.
	"""
	challenge, runtime = _require_challenge_use(challenge_name)

	if not isinstance(value, str) or not value.strip():
		frappe.throw(_("value is required."), frappe.ValidationError)
	if len(value) > _MAX_AUTH_INPUT_LENGTH:
		frappe.throw(
			_("value is too long to be a valid authentication input."), frappe.ValidationError
		)

	adapter = _build_adapter(runtime)
	try:
		auth_status = _run_async(adapter.submit_auth_input(runtime, challenge.name, value))
	except SubscriptionError as exc:
		frappe.db.set_value(
			"Subscription Auth Challenge",
			challenge.name,
			{"status": "Failed", "error_message": str(exc)},
			update_modified=True,
		)
		auth_service.mark_runtime_auth_state(runtime, "failed", error_message=str(exc))
		frappe.throw(_("Failed to submit authentication input: {0}").format(str(exc)))

	if auth_status.state == "ready":
		frappe.db.set_value(
			"Subscription Auth Challenge",
			challenge.name,
			{"status": "Success", "completed_at": now_datetime()},
			update_modified=True,
		)
		auth_service.mark_runtime_auth_state(runtime, "ready", account_hint=auth_status.account_hint)
		frappe.db.commit()  # nosemgrep: justified - persist auth success before resuming parked runs
		resume.resume_after_auth_success(runtime.name)
	else:
		frappe.db.set_value(
			"Subscription Auth Challenge",
			challenge.name,
			{"status": "Verifying"},
			update_modified=True,
		)
		auth_service.mark_runtime_auth_state(runtime, auth_status.state, account_hint=auth_status.account_hint)
		frappe.db.commit()  # nosemgrep: justified - persist interim state before returning

	return _auth_status_to_dict(auth_status)


@frappe.whitelist()
def cancel_subscription_auth(challenge_name: str) -> dict[str, Any]:
	"""Cancel an in-flight login challenge (PLAN.md §64.3)."""
	challenge, runtime = _require_challenge_use(challenge_name)

	adapter = _build_adapter(runtime)
	try:
		_run_async(adapter.cancel_auth(runtime, challenge.name))
	except SubscriptionError as exc:
		frappe.throw(_("Failed to cancel authentication: {0}").format(str(exc)))

	frappe.db.set_value(
		"Subscription Auth Challenge", challenge.name, {"status": "Cancelled"}, update_modified=True
	)
	frappe.db.commit()  # nosemgrep: justified - persist cancellation before returning
	return {"success": True, "challenge": challenge.name, "status": "Cancelled"}


# ---------------------------------------------------------------------------
# Re-authenticate / logout (PLAN.md §64.1, §65.2)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def reauthenticate_subscription_runtime(runtime_name: str) -> dict[str, Any]:
	"""Convenience wrapper: checks tenancy/permission, then starts a fresh login challenge.

	Same permission gate as `begin_subscription_auth` (use-or-manage +
	tenancy) — re-authenticating is something any tenant of a shared runtime
	may trigger for themselves, same as the initial login.
	"""
	_require_runtime_use(runtime_name)
	return begin_subscription_auth(runtime_name)


@frappe.whitelist()
def logout_subscription_runtime(runtime_name: str) -> dict[str, Any]:
	"""Log out a Subscription Runtime (PLAN.md §65.2).

	Gated on `subscription_runtime.manage` specifically, not just `.use`:
	logging out a shared runtime signs out every tenant currently relying on
	it, so only a manager may trigger it.
	"""
	runtime = _require_runtime_manage(runtime_name)

	adapter = _build_adapter(runtime)
	try:
		_run_async(adapter.logout(runtime))
	except SubscriptionError as exc:
		frappe.throw(_("Failed to log out: {0}").format(str(exc)))

	auth_service.mark_runtime_auth_state(runtime, "required")
	frappe.db.commit()  # nosemgrep: justified - persist logout before returning
	return {"success": True, "runtime": runtime.name, "auth_status": "required"}
