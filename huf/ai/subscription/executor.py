"""Subscription CLI passthrough execution branch.

This module owns ALL logic for running an Agent Run against a "Subscription CLI"
mode AI Provider. It exists so that `huf/ai/agent_integration.py` only needs a
short dispatch branch (check provider_mode, call `SubscriptionPassthroughExecutor.
execute(...)`, return) at each of its two execution entry points
(`_execute_agent_run` and `run_agent_stream`) rather than growing a second,
tangled code path inline.

Passthrough constraint (see `adapters/base.py`): nothing in this module may
build a system prompt from HUF Agent instructions, attach HUF conversation
history, wire HUF tool schemas/MCP config, or invoke HUF Knowledge/Memory.
This module only ever sends the CURRENT turn's text/files to the adapter.

Auth-required handling (plan §75.6, review "challenge storm" warning): if the
Subscription Runtime's auth state is not known-ready, this module never
invokes the CLI. It requests/reuses an active challenge, parks the Agent Run,
releases the caller's conversation lock (if any), and returns. It never marks
the run "Failed" for an auth-required condition.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import frappe
from frappe.utils import now_datetime

from huf.ai.subscription import auth_service, session_binding, staging, streaming, telemetry
from huf.ai.subscription.adapters.base import SubscriptionCLIAdapter
from huf.ai.subscription.adapters.claude import ClaudeAdapter
from huf.ai.subscription.adapters.codex import CodexAdapter
from huf.ai.subscription.adapters.gemini import GeminiAdapter
from huf.ai.subscription.errors import SubscriptionError, SubscriptionErrorCode
from huf.ai.subscription.transports.base import ExecutionTransport
from huf.ai.subscription.types import SubscriptionTurnRequest, SubscriptionTurnResult

# Error codes that mean "this specific provider-native session can't be
# resumed" (adapter-reported, via SubscriptionTurnResult.events[0]["code"]),
# as opposed to SubscriptionErrorCode.AUTH_REQUIRED, which means the
# runtime's login itself is the problem. See _extract_error_code / step 8.
_SESSION_LOST_CODES = (
	SubscriptionErrorCode.SESSION_NOT_FOUND.value,
	SubscriptionErrorCode.SESSION_RESUME_FAILED.value,
)


def _extract_error_code(result: SubscriptionTurnResult) -> str | None:
	"""Best-effort read of the adapter-classified error code off a turn result.

	Adapters never raise for a classified CLI/session error (see
	adapters/claude.py::_parse_turn_output) — they return
	`status="error"` with the stable HUF error code in the first event's
	`code` field. Returns None if no event/code is present (e.g. transport-
	level errors that raised `SubscriptionError` instead, already handled by
	the `except SubscriptionError` branch above this call site).
	"""
	for event in result.events or []:
		code = event.get("code")
		if code:
			return code
	return None

logger = logging.getLogger(__name__)

# Default per-turn timeout when the Agent doesn't specify one. Kept generous
# because subscription CLIs are interactive-latency, not API-latency, tools.
_DEFAULT_TURN_TIMEOUT_SECONDS = 300

_ADAPTER_CLASSES: dict[str, type[SubscriptionCLIAdapter]] = {
	"Claude": ClaudeAdapter,
	"Codex": CodexAdapter,
	"Gemini": GeminiAdapter,
}


class SubscriptionPassthroughRefusal(Exception):
	"""Raised to fail the Agent Run clearly with a user-facing reason.

	Distinguished from a generic error so the executor can mark the run
	Failed with the exact refusal text rather than a sanitized generic
	error, per the binding-mismatch requirement (step 5 of the design).
	"""

	def __init__(self, reason: str):
		self.reason = reason
		super().__init__(reason)


def is_subscription_passthrough_conversation(conversation_name: str) -> bool:
	"""True if the given Agent Conversation is bound to subscription-passthrough mode.

	Used by `generate_conversation_title` / `run_background_summarization` (and their
	enqueue call sites) to suppress LiteLLM calls for passthrough conversations, and
	by tests. Reads the cheap `runtime_mode` field rather than re-deriving from the
	Agent's current provider, because a conversation's binding is fixed at creation
	time (see `session_binding.py`) even if the Agent's provider changes later.
	"""
	if not conversation_name:
		return False
	runtime_mode = frappe.db.get_value("Agent Conversation", conversation_name, "runtime_mode")
	return runtime_mode == "subscription_passthrough"


def get_provider_mode(provider_name: str | None) -> str | None:
	"""Return the `provider_mode` of an AI Provider, or None if not set/found."""
	if not provider_name:
		return None
	return frappe.get_cached_value("AI Provider", provider_name, "provider_mode")


def is_subscription_cli_provider(provider_name: str | None) -> bool:
	return get_provider_mode(provider_name) == "Subscription CLI"


def _build_transport_for_runtime(runtime) -> ExecutionTransport:
	"""Construct the ExecutionTransport matching the runtime's transport_type.

	Kept local to the executor (rather than a shared factory) since this is the
	only call site today; a later task can extract a shared factory if a second
	caller appears.
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

	raise SubscriptionPassthroughRefusal(
		f"Unsupported subscription runtime transport type: {transport_type!r}"
	)


def _build_adapter(runtime) -> SubscriptionCLIAdapter:
	adapter_cls = _ADAPTER_CLASSES.get(runtime.provider_family)
	if adapter_cls is None:
		raise SubscriptionPassthroughRefusal(
			f"Unsupported subscription runtime provider family: {runtime.provider_family!r}"
		)
	transport = _build_transport_for_runtime(runtime)
	return adapter_cls(transport)


def _run_async(coro):
	"""Run an async coroutine from sync Frappe request/job context.

	Mirrors the `_run_async_safely` helper already used elsewhere in
	agent_integration.py (new event loop when one isn't already running).
	"""
	try:
		asyncio.get_running_loop()
	except RuntimeError:
		return asyncio.run(coro)
	else:
		# Already inside a running loop (shouldn't normally happen for this
		# module's sync callers, but fail safely rather than crash).
		new_loop = asyncio.new_event_loop()
		try:
			return new_loop.run_until_complete(coro)
		finally:
			new_loop.close()


class SubscriptionPassthroughExecutor:
	"""Executes one Agent Run turn against a Subscription CLI runtime."""

	@staticmethod
	def execute(
		*,
		agent_doc,
		run_doc,
		conversation,
		provider_doc,
		prompt: str,
		files: list[str] | None = None,
		model_override: str | None = None,
	) -> dict[str, Any]:
		"""Run the passthrough turn and update the Agent Run/Conversation/Message docs.

		Args:
			agent_doc: The Agent document (read-only here; never mutated for passthrough).
			run_doc: The Agent Run document (already created, status Queued/Started).
			conversation: The Agent Conversation document.
			provider_doc: The AI Provider document (provider_mode == "Subscription CLI").
			prompt: This turn's user text. NEVER history — passthrough constraint.
			files: Optional list of local file paths for this turn only.
			model_override: Optional model name override for this turn.

		Returns:
			A plain dict describing the outcome, shaped like the normal
			`_execute_agent_run` return value: {"success": bool, "response": str|None,
			"agent_run_id": run_doc.name, "status": <canonical status>}.

		This is a thin safety-net wrapper around `_execute_inner`: an adapter-build
		refusal, a staging/vision error, or any other exception raised before
		`_execute_inner` reaches its own internal `except SubscriptionError`
		handling would otherwise propagate out of this method entirely, leaving
		the run stuck in "Started" (direct path) or "Queued"/"Started" (queued
		path) until the 10-minute stall-recovery sweep picks it up. No exception
		may leave here without the run ending up either Failed (sanitized) or
		legitimately parked for auth.
		"""
		try:
			return SubscriptionPassthroughExecutor._execute_inner(
				agent_doc=agent_doc,
				run_doc=run_doc,
				conversation=conversation,
				provider_doc=provider_doc,
				prompt=prompt,
				files=files,
				model_override=model_override,
			)
		except SubscriptionPassthroughRefusal as exc:
			return SubscriptionPassthroughExecutor._fail(run_doc, conversation, exc.reason)
		except Exception as exc:  # noqa: BLE001 - last-resort safety net, see docstring above.
			logger.exception(
				"Unhandled exception in SubscriptionPassthroughExecutor.execute for run %s",
				run_doc.name,
			)
			return SubscriptionPassthroughExecutor._fail_sanitized(run_doc, conversation, str(exc))

	@staticmethod
	def _execute_inner(
		*,
		agent_doc,
		run_doc,
		conversation,
		provider_doc,
		prompt: str,
		files: list[str] | None = None,
		model_override: str | None = None,
	) -> dict[str, Any]:
		"""Actual passthrough turn logic; see `execute` for the exception safety net."""
		files = files or []
		runtime_name = provider_doc.subscription_runtime
		if not runtime_name:
			return SubscriptionPassthroughExecutor._fail(
				run_doc, conversation, "This AI Provider has no Subscription Runtime configured."
			)

		runtime = frappe.get_doc("Subscription Runtime", runtime_name)

		# --- Step 2: tenancy check BEFORE any login/inference attempt. ---
		# Check tenancy against the Agent Run's own recorded owner, not
		# `frappe.session.user`: for a RESUMED run (re-dispatched by
		# `recover_stalled_agent_runs`, or resumed via
		# `resume_after_auth_success` from a poll made by a different user's
		# session than the one that originally started the run) the current
		# session user may not be the run's actual owner.
		run_owner = getattr(run_doc, "owner", None) or frappe.session.user
		if not runtime.check_tenancy(run_owner):
			return SubscriptionPassthroughExecutor._fail(
				run_doc,
				conversation,
				"You are not authorized to use this subscription runtime.",
			)

		# --- Step 3: auth-state gate BEFORE invoking the CLI at all. ---
		auth_status = getattr(runtime, "auth_status", None)
		if auth_status != "ready":
			SubscriptionPassthroughExecutor._park_for_auth(runtime, run_doc, conversation)
			return {
				"success": False,
				"response": None,
				"agent_run_id": run_doc.name,
				"status": "Waiting Authentication",
			}

		# --- Step 4/5: session binding (skip entirely for stateless runs). ---
		# NOTE (H8): as of this writing every Agent Run created by
		# `run_agent_sync` — including automation/scheduled-trigger runs in
		# every `conversation_mode` ("Dedicated", "New", and even "No-UI",
		# which only hides the prompt from the visible chat history via
		# `skip_user_message` — it still creates/reuses a real Agent
		# Conversation, see `automation_runner.py::_resolve_conversation_routing`)
		# always has an associated conversation with a real `.name`. There is
		# currently no run type that sets `conversation` to None or omits its
		# name, so this condition is never True in practice and the branch
		# below it is effectively dead code. It is kept (rather than removed)
		# because a genuinely conversation-less "one-shot automation run" is a
		# real future case (plan §27/§56.3) and this is where it should plug
		# in once such a run type exists — introducing that run type is a
		# separate, larger change (new Agent Run flag/DocType support) outside
		# this fix's scope. Until then this stays defensively correct: no
		# write here targets a nonexistent column (see the `usage_snapshot`
		# use below instead of a nonexistent `subscription_cleanup_status`
		# column), so this dead branch cannot raise even if a future caller
		# starts hitting it.
		is_stateless = not conversation or not getattr(conversation, "name", None)
		provider_session_id: str | None = None
		is_new_session = True

		if not is_stateless:
			conversation_state = {
				"subscription_provider_session_id": conversation.subscription_provider_session_id,
				"subscription_provider_session_status": conversation.subscription_provider_session_status,
				"subscription_runtime": conversation.subscription_runtime,
				"model_name": model_override or agent_doc.model,
			}
			decision = session_binding.resolve_binding_for_turn(
				conversation_state, runtime_name, model_override or agent_doc.model
			)
			if decision.action == session_binding.ACTION_REFUSE_MISMATCH:
				return SubscriptionPassthroughExecutor._fail(run_doc, conversation, decision.reason)
			if decision.action == session_binding.ACTION_RESUME_EXISTING:
				provider_session_id = decision.provider_session_id
				is_new_session = False
			# ACTION_CREATE_NEW: provider_session_id stays None; adapter creates one.

		# --- Step 6: stage files, guaranteed cleanup. ---
		adapter = _build_adapter(runtime)
		staged_files: list[Any] = []
		staged_paths: list[str] = []
		try:
			if files:
				capabilities = _run_async(adapter.probe(runtime))
				staging.assert_vision_supported(capabilities, files)
				staged_files = _run_async(staging.stage_turn_files(adapter.transport, files))
				staged_paths = [sf.remote_path for sf in staged_files]

			# --- Step 7: build the CLOSED request and call the adapter. ---
			request = SubscriptionTurnRequest(
				runtime_name=runtime_name,
				provider_session_id=provider_session_id,
				text=prompt,
				files=staged_paths,
				model_override=model_override,
				run_id=run_doc.name,
				conversation_id=conversation.name if conversation else None,
				timeout_seconds=int(
					getattr(runtime, "timeout_seconds", None) or _DEFAULT_TURN_TIMEOUT_SECONDS
				),
			)

			try:
				result: SubscriptionTurnResult = _run_async(adapter.run_turn(runtime, request))
			except SubscriptionError as exc:
				return SubscriptionPassthroughExecutor._fail_sanitized(run_doc, conversation, str(exc))

			# Stateless cleanup: always attempt delete_session afterward, best-effort.
			cleanup_status = None
			if is_stateless and result.provider_session_id:
				try:
					delete_result = _run_async(
						adapter.delete_session(runtime, result.provider_session_id)
					)
					cleanup_status = delete_result.cleanup_status
				except Exception:
					cleanup_status = "cleanup_failed"

		finally:
			if staged_files:
				_run_async(staging.cleanup_staged_files(adapter.transport, staged_files))

		# --- Step 8: auth_required result -> park, never fail. ---
		# Covers both an adapter setting status="auth_required" directly, and
		# an adapter that returns status="error" with AUTH_REQUIRED classified
		# in the first event (see adapters/claude.py::_parse_turn_output) —
		# either way this means the runtime's login itself needs attention.
		error_code = _extract_error_code(result)
		if result.status == "auth_required" or error_code == SubscriptionErrorCode.AUTH_REQUIRED.value:
			auth_service.mark_runtime_auth_state(runtime, "required", error_message=result.auth_reason)
			SubscriptionPassthroughExecutor._park_for_auth(runtime, run_doc, conversation)
			return {
				"success": False,
				"response": None,
				"agent_run_id": run_doc.name,
				"status": "Waiting Authentication",
			}

		# --- Step 8b: SESSION_LOST vs AUTH_REQUIRED (plan §26.4/§62.4, review
		# A2 second half). The runtime's auth is fine (we already passed the
		# auth-status gate above) but this specific conversation's provider-
		# native session could not be resumed. This is NOT an auth problem —
		# never park/auth-challenge for it — and HUF must never silently
		# replay conversation history into a fresh session on the caller's
		# behalf. Mark the binding Unavailable and fail this run only, with a
		# message that makes the distinction from an auth failure explicit.
		if not is_stateless and not is_new_session and error_code in _SESSION_LOST_CODES:
			if conversation and getattr(conversation, "name", None):
				frappe.db.set_value(
					"Agent Conversation",
					conversation.name,
					session_binding.binding_for_missing_session(),
					update_modified=False,
				)
			return SubscriptionPassthroughExecutor._fail(
				run_doc,
				conversation,
				"Your subscription login is fine, but this conversation's CLI session was "
				"lost and can no longer be resumed. Start a new conversation to continue — "
				"this is not an authentication problem.",
			)

		# --- Step 10: any other non-success result -> Failed, sanitized. ---
		if result.status != "success":
			return SubscriptionPassthroughExecutor._fail_sanitized(
				run_doc, conversation, result.final_text or f"Subscription turn failed: {result.status}"
			)

		# --- Step 9: success path. ---
		telemetry_fields = telemetry.map_turn_result_to_agent_run_fields(result, runtime_name)

		if not is_stateless and is_new_session and result.provider_session_id:
			binding_updates = session_binding.binding_for_new_session(result.provider_session_id, runtime_name)
			frappe.db.set_value("Agent Conversation", conversation.name, binding_updates, update_modified=False)
		elif is_stateless and cleanup_status:
			# `subscription_cleanup_status` is NOT a real column on Agent Run
			# (confirmed against `agent_run.json`) — writing it via
			# `frappe.db.set_value` would raise. Stash it inside the existing
			# `usage_snapshot` JSON field instead, merging rather than
			# clobbering in case telemetry already populated it above.
			usage_snapshot = dict(telemetry_fields.get("usage_snapshot") or {})
			usage_snapshot["subscription_cleanup_status"] = cleanup_status
			telemetry_fields["usage_snapshot"] = usage_snapshot

		run_fields = dict(telemetry_fields)
		run_fields["status"] = "Success"
		run_fields["response"] = result.final_text
		run_fields["end_time"] = now_datetime()
		frappe.db.set_value("Agent Run", run_doc.name, run_fields, update_modified=True)

		if conversation and getattr(conversation, "name", None):
			from huf.ai.conversation_manager import ConversationManager

			conv_manager = ConversationManager(agent_name=agent_doc.name)
			# LIVE-VERIFIED bug fix: `model_override` is a CLI-facing model
			# string (e.g. "sonnet", from AI Model.runtime_model_name) meant
			# for the subscription CLI's --model flag -- it is NOT an "AI
			# Model" doctype name. Agent Message.model is a Link field to
			# "AI Model", so passing model_override here raised
			# `LinkValidationError: Could not find Model: sonnet` on a real
			# site the moment runtime_model_name differed from the AI Model
			# doc's own name (exactly the case §10.4/H1 exists to support).
			# Always use the actual AI Model doc reference.
			conv_manager.add_message(
				conversation,
				role="agent",
				content=result.final_text or "",
				provider=provider_doc.name,
				model=agent_doc.model,
				agent=agent_doc.name,
				run_name=run_doc.name,
			)

		frappe.db.commit()  # nosemgrep: justified — passthrough turn completion

		if conversation and getattr(conversation, "name", None):
			for event in streaming.map_turn_result_to_realtime_events(
				result, run_doc.name, conversation.name
			):
				frappe.publish_realtime(
					event=f"conversation:{conversation.name}",
					message=event,
					user=frappe.session.user,
				)

		return {
			"success": True,
			"response": result.final_text,
			"agent_run_id": run_doc.name,
			"status": "Success",
		}

	@staticmethod
	def _park_for_auth(runtime, run_doc, conversation) -> None:
		challenge = auth_service.get_or_create_active_challenge(runtime)
		auth_service.park_run(run_doc.name, challenge["name"])
		SubscriptionPassthroughExecutor._notify_owner_of_park(runtime, run_doc, conversation, challenge)

		# Emit a realtime event so the frontend knows this run is now waiting
		# on an auth challenge, instead of appearing frozen until it times out.
		# Uses the SAME publish mechanism/channel as every other event in this
		# module (`frappe.publish_realtime` on `conversation:<name>` — see
		# `_emit_run_lifecycle_event` in agent_integration.py for the pattern
		# this mirrors). Built manually rather than via
		# `streaming.map_turn_result_to_realtime_events` because that mapper's
		# "subscription_auth_required" shape (built from a SubscriptionTurnResult)
		# has no `runtime_name` field — and the frontend needs the runtime name
		# to call the auth-challenge APIs — nor does it carry the challenge's
		# public info (verification_url/user_code/mode) the frontend card needs
		# to render.
		if conversation is not None and getattr(conversation, "name", None):
			runtime_name = runtime if isinstance(runtime, str) else runtime.name
			try:
				frappe.publish_realtime(
					event=f"conversation:{conversation.name}",
					message={
						"type": "subscription_auth_required",
						"agent_run_id": run_doc.name,
						"conversation_id": conversation.name,
						"runtime_name": runtime_name,
						"auth_challenge": challenge.get("name"),
						"verification_url": challenge.get("verification_url"),
						"user_code": challenge.get("user_code"),
						"mode": challenge.get("mode"),
					},
					user=frappe.session.user,
				)
			except Exception:
				logger.exception(
					"Failed to publish subscription_auth_required event for run %s", run_doc.name
				)

			# Also emit a STANDARD `agent_run_status` lifecycle event (mirrors
			# `_emit_run_lifecycle_event` in agent_integration.py) with
			# status "Waiting Authentication", so that any code path that only
			# watches ordinary run-status events — not the custom
			# `subscription_auth_required` type above — still learns the run
			# is parked. This matters for two consumers in particular: (1) a
			# frontend socket handler that has not been updated to know about
			# `subscription_auth_required` yet, and (2) the polling/hydration
			# path (`get_agent_run_status`), which reads the Agent Run's
			# `status` column rather than replaying realtime events — that
			# column is already set to "Waiting Authentication" by
			# `auth_service.park_run` above, so this event is purely to avoid
			# making socket-first consumers wait for the poll fallback.
			try:
				frappe.publish_realtime(
					event=f"conversation:{conversation.name}",
					message={
						"type": "agent_run_status",
						"status": "Waiting Authentication",
						"agent_run_id": run_doc.name,
						"conversation_id": conversation.name,
						"agent": getattr(run_doc, "agent", None),
						"sequence": getattr(run_doc, "sequence", None),
						"runtime_name": runtime_name,
					},
					user=frappe.session.user,
				)
			except Exception:
				logger.exception(
					"Failed to publish agent_run_status(Waiting Authentication) event for run %s",
					run_doc.name,
				)

		# CONTRACT (auth_service.park_run docstring / PLAN §75.3): the per-
		# conversation execution lock must be released BEFORE returning —
		# parking can leave the run waiting for an arbitrary (possibly very
		# long) amount of time until the user completes the auth challenge,
		# and no lock may be held across that wait. We deliberately do NOT
		# delete the lock here: `_execute_agent_run`'s callers already release
		# it themselves in a `finally` block on both the direct-execution path
		# (agent_integration.py's direct-override lock) and the queued
		# drainer path (`_run_queued_agent`/`_drain_run`), so releasing it a
		# second time here was both redundant and racy — if resume happens
		# quickly after parking, a fresh acquire could take the lock before
		# this code ran, and deleting it here would then delete a *different*
		# drainer's lock out from under it.
		frappe.db.commit()  # nosemgrep: justified — must persist park state before returning

	@staticmethod
	def _notify_owner_of_park(runtime, run_doc, conversation, challenge: dict[str, Any]) -> None:
		"""
		PLAN.md sec 63.2 "notify runtime owner/designated operator": when a run
		is parked behind a login challenge, let the runtime's owner know a
		conversation is waiting on them, via HUF's existing Notification Log
		mechanism (the same `enqueue_create_notification` helper used for flow
		approval notifications in `flow_engine.py::_send_approval_notifications`
		— reused here rather than inventing a new channel). Best-effort: a
		notification failure must never fail the park itself.
		"""
		owner_user = getattr(runtime, "owner_user", None) if not isinstance(runtime, str) else None
		if not owner_user:
			return

		try:
			from frappe.desk.doctype.notification_log.notification_log import (
				enqueue_create_notification,
			)

			runtime_name = runtime if isinstance(runtime, str) else runtime.name
			conversation_name = getattr(conversation, "name", None) if conversation else None
			subject_target = conversation_name or run_doc.name

			enqueue_create_notification(
				owner_user,
				{
					"type": "Alert",
					"document_type": "Subscription Auth Challenge",
					"document_name": challenge.get("name"),
					"subject": f"Sign-in required for {runtime_name} — conversation {subject_target} is waiting",
					"email_content": (
						f"<p>Agent Run {run_doc.name} is parked waiting on authentication "
						f"for Subscription Runtime {runtime_name}.</p>"
						f"<p>Complete the login challenge ({challenge.get('name')}) to resume it.</p>"
					),
				},
			)
		except Exception:
			logger.exception(
				"Failed to notify owner %s of parked run %s", owner_user, run_doc.name
			)

	@staticmethod
	def _fail(run_doc, conversation, reason: str) -> dict[str, Any]:
		"""Fail the run with an exact, clear (non-sanitized) reason.

		Used for refusals we generated ourselves (tenancy, binding mismatch,
		misconfiguration) where the text is already safe to show verbatim —
		never for provider/CLI output, which must go through `_fail_sanitized`.
		"""
		frappe.db.set_value(
			"Agent Run",
			run_doc.name,
			{"status": "Failed", "response": reason, "end_time": now_datetime()},
			update_modified=True,
		)
		frappe.db.commit()  # nosemgrep: justified — must persist failure state
		if conversation and getattr(conversation, "name", None):
			for event in streaming.map_turn_result_to_realtime_events(
				SubscriptionTurnResult(status="error", final_text=reason, provider_session_id=None),
				run_doc.name,
				conversation.name,
			):
				frappe.publish_realtime(
					event=f"conversation:{conversation.name}", message=event, user=frappe.session.user
				)
		return {
			"success": False,
			"response": reason,
			"agent_run_id": run_doc.name,
			"status": "Failed",
		}

	@staticmethod
	def _fail_sanitized(run_doc, conversation, raw_message: str) -> dict[str, Any]:
		"""Fail the run with a provider-error message run through sanitization.

		Never surfaces raw stderr/secrets (step 10) — reuses `streaming.py`'s
		sanitizer so the same masking rules apply here as to realtime events.
		"""
		sanitized = streaming._sanitize_error_message(raw_message)
		return SubscriptionPassthroughExecutor._fail(run_doc, conversation, sanitized)
