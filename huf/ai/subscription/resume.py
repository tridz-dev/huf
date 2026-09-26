"""Resume-after-auth-success logic for parked (Waiting Authentication) Agent Runs.

See PLAN.md §62.2-§62.4 / §75.3 and review findings A2/A3. This module is
deliberately narrow and standalone-importable: the auth-challenge-completion
API endpoint that is expected to call `resume_after_auth_success` is a later,
serialized task (T-10-api). Until that endpoint exists, this function is
correct and callable on its own (e.g. from the console or a test) but nothing
in the request path invokes it yet.
"""

from __future__ import annotations

import frappe

from huf.ai.subscription import auth_service


def resume_after_auth_success(runtime_name: str) -> list[str]:
	"""Re-queue every Agent Run parked (``Waiting Authentication``) on a runtime.

	Call this once a `Subscription Runtime`'s authentication challenge has
	completed successfully (i.e. after `auth_service.mark_runtime_auth_state`
	has moved `runtime.auth_status` to ``"ready"``).

	For each Agent Run returned by
	`auth_service.resolve_parked_runs_for_runtime(runtime_name)`:
	  - Its `status` is flipped back to ``"Queued"`` via a plain field update.
	    Its `sequence` and `idempotency_key` are left completely untouched, so
	    claim-ordering (`_next_queued_run`) and idempotent retry semantics are
	    preserved exactly as they were when the run was first created/parked.
	  - No `Agent Message` is created here. The user's turn was already
	    persisted as an ``Agent Message`` when the run was first queued/parked
	    (see `_drain_run` in agent_integration.py) — resuming re-executes the
	    CLI call for that existing turn, it does not re-persist the prompt.
	  - The conversation's normal queue drainer is woken via
	    `huf.ai.agent_integration._enqueue_drain`, the exact mechanism
	    `_run_queued_agent`/`_execute_agent_run` already use to pick up
	    `Queued` runs — reused here rather than reimplemented.

	Args:
		runtime_name: The `Subscription Runtime` document name whose auth
			challenge just succeeded.

	Returns:
		The list of Agent Run names that were re-queued (empty if none were
		parked on this runtime). Callers/tests can use this to confirm which
		runs were resumed.

	# TODO(T-10-api): call this from the auth-challenge-completion API
	# endpoint, right after that endpoint marks the challenge/runtime as
	# successfully authenticated (`auth_service.mark_runtime_auth_state(
	# runtime, "ready")`), before returning its response to the polling
	# client. No such endpoint exists yet in this codebase.
	"""
	# Lazy import: avoids a module-load cycle with agent_integration.py, which
	# imports huf.ai.subscription.executor (and transitively this module could
	# be imported from there too) — same pattern already used by
	# executor.py::_park_for_auth for `_conversation_lock_key`.
	from huf.ai.agent_integration import _enqueue_drain

	run_names = auth_service.resolve_parked_runs_for_runtime(runtime_name)
	if not run_names:
		return []

	conversations: set[str] = set()
	for run_name in run_names:
		conversation = frappe.db.get_value("Agent Run", run_name, "conversation")
		frappe.db.set_value(
			"Agent Run",
			run_name,
			{"status": "Queued"},
			update_modified=True,
		)
		if conversation:
			conversations.add(conversation)

	frappe.db.commit()  # nosemgrep: justified — must persist re-queue before draining

	for conversation_id in conversations:
		_enqueue_drain(conversation_id)

	return run_names
