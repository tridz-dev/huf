"""Background memory extraction after a finished run (sync, queued and stream paths)."""

import frappe

from huf.ai.memory.defaults import (
	DEFAULT_MEMORY,
	DEFAULT_RECORD_TYPES,
	insert_default_memory_record,
	uses_default_memory,
)
from huf.ai.memory.subject import (
	MEMORY_EXTRACTION_CHANNEL,
	MEMORY_EXTRACTION_RUN_KIND,
	resolve_memory_subject,
)

EXTRACT_JOB = "huf.ai.memory.extraction.extract_memory_from_run"


def should_extract_memory(agent_doc, run_kind=None) -> bool:
	"""True if a finished run of this agent may queue memory extraction.

	Extraction runs are always excluded (no recursion). Memory must be enabled;
	an explicit policy always extracts (its own gating applies in the job), and
	the default policy skips agent-builder test chats.
	"""
	if run_kind == MEMORY_EXTRACTION_RUN_KIND:
		return False
	getter = agent_doc.get if isinstance(agent_doc, dict) else lambda k, d=None: getattr(agent_doc, k, d)
	if not getter("enable_memory"):
		return False
	if getter("memory_policy"):
		return True
	return run_kind != "draft_test"


def enqueue_memory_extraction(agent_doc, run_doc, *, after_commit=True) -> bool:
	"""Queue extraction for a run this caller just finalized. Never raises."""
	if not should_extract_memory(agent_doc, run_doc.run_kind):
		return False
	try:
		if uses_default_memory(agent_doc) and not resolve_memory_subject(run_doc.conversation, run_doc.name):
			return False
		frappe.enqueue(
			EXTRACT_JOB,
			queue="default",
			timeout=300,
			is_async=True,
			enqueue_after_commit=after_commit,
			job_id=f"huf_memory_extraction::{run_doc.name}",
			deduplicate=True,
			run_id=run_doc.name,
		)
	except (
		RuntimeError,
		TypeError,
		ValueError,
		KeyError,
		AttributeError,
		frappe.DoesNotExistError,
		frappe.ValidationError,
		frappe.PermissionError,
	) as e:
		frappe.logger("huf").warning(f"Memory extraction enqueue failed: {e!s}")
		return False
	else:
		return True


_RESPONSE_FORMAT = {
	"type": "json_schema",
	"json_schema": {
		"name": "memory_extraction",
		"schema": {
			"type": "object",
			"properties": {
				"memories": {
					"type": "array",
					"items": {
						"type": "object",
						"properties": {
							"title": {"type": "string"},
							"summary_text": {"type": "string"},
							"record_type": {"type": "string", "enum": ["Fact", "Preference", "Instruction"]},
							"confidence": {"type": "number"},
							"importance_score": {"type": "number"},
						},
						"required": ["title", "summary_text", "record_type"],
					},
				}
			},
			"required": ["memories"],
		},
	},
}


def _transcript(agent_name, conversation):
	from huf.ai.conversation_manager import ConversationManager

	history = ConversationManager(agent_name=agent_name).get_conversation_history(conversation, limit=40)
	lines = []
	for msg in history:
		content = msg.get("content")
		if content and isinstance(content, str):
			lines.append(f"{msg.get('role') or 'unknown'}: {content}")
	return "\n".join(lines)


def _prompt(transcript, default):
	focus = "Focus on durable facts and preferences about the user or their work. " if default else ""
	return (
		"Review the following conversation transcript. Identify any durable facts, "
		"preferences, or important details worth remembering long-term. "
		f"{focus}Do NOT invent facts that aren't in the transcript. If there is nothing worth "
		"remembering, return an empty list.\n\n"
		f"TRANSCRIPT:\n{transcript}\n\n"
		"Respond with JSON only, matching this shape: "
		'{"memories": [{"title": str, "summary_text": str, "record_type": '
		'"Fact"|"Preference"|"Instruction", "confidence": float (0-1), '
		'"importance_score": float (0-1)}]}'
	)


def extract_memory_from_run(run_id):
	"""Background job. Identity comes from the run's conversation owner, never the session user."""
	run = frappe.db.get_value("Agent Run", run_id, ["agent", "conversation", "run_kind"], as_dict=True)
	if not run or not run.agent or not run.conversation:
		return
	agent_name = run.agent
	agent = frappe.db.get_value("Agent", agent_name, ["enable_memory", "memory_policy"], as_dict=True)
	if not agent or not should_extract_memory(agent, run.run_kind):
		return

	default = uses_default_memory(agent)
	subject = resolve_memory_subject(run.conversation, run_id)
	policy = None
	extraction_agent = agent_name
	if not default:
		policy = frappe.get_doc("Memory Policy", agent.memory_policy)
		if not policy.enabled or policy.capture_mode not in ("Agent Suggested", "Automatic"):
			return
		if (policy.scope_type or "Agent") == "User" and not subject:
			return
		extraction_agent = policy.learning_agent or agent_name
	elif not subject:
		return

	transcript = _transcript(agent_name, run.conversation)
	if not transcript.strip():
		return

	from huf.ai.agent.integration import run_agent_sync

	# Dedicated conversation keyed by the source run, so the JSON reply never lands in the
	# user's own chat history and the next extraction cannot read it back as transcript.
	# Unexpected errors propagate: the job runner rolls back and records them in the Error Log.
	result = run_agent_sync(
		agent_name=extraction_agent,
		prompt=_prompt(transcript, default),
		channel_id=MEMORY_EXTRACTION_CHANNEL,
		external_id=run_id,
		run_kind=MEMORY_EXTRACTION_RUN_KIND,
		now=1,
		skip_user_message=True,
		response_format=_RESPONSE_FORMAT,
	)
	if not result or not result.get("success"):
		return

	candidates = (result.get("structured") or {}).get("memories") or []
	if default:
		_save_default(candidates, agent_name, subject, run_id)
	else:
		_save_with_policy(candidates, policy, agent_name, subject, run, run_id)


def _candidate_errors():
	"""Errors that reject one candidate without stopping the rest of the batch."""
	return (frappe.ValidationError, frappe.PermissionError, TypeError, ValueError)


def _save_default(candidates, agent_name, subject, run_id):
	saved = 0
	for c in candidates:
		if saved >= DEFAULT_MEMORY["max_candidates_per_run"]:
			break
		if not c.get("title") or not c.get("summary_text"):
			continue
		record_type = c.get("record_type")
		try:
			insert_default_memory_record(
				agent_name=agent_name,
				subject=subject,
				title=c["title"],
				summary_text=c["summary_text"],
				record_type=record_type if record_type in DEFAULT_RECORD_TYPES else "Fact",
				source_type="Extracted",
				agent_run_id=run_id,
				confidence=c.get("confidence") or 0,
				importance_score=c.get("importance_score") or 0,
			)
			saved += 1
		except _candidate_errors():
			frappe.log_error(
				title="Memory extraction: failed to save candidate", message=frappe.get_traceback()
			)


def _save_with_policy(candidates, policy, agent_name, subject, run, run_id):
	from huf.ai.memory_tools import save_memory_record

	scope_type = policy.scope_type or "Agent"
	scope_key = {"Agent": agent_name, "User": subject}.get(scope_type)
	status = "Draft" if policy.capture_mode == "Agent Suggested" else "Active"
	for c in candidates:
		if not c.get("title") or not c.get("summary_text"):
			continue
		try:
			save_memory_record(
				title=c["title"],
				summary_text=c["summary_text"],
				record_type=c.get("record_type") or "Fact",
				scope_type=scope_type,
				scope_key=scope_key,
				status=status,
				confidence=c.get("confidence") or 0,
				importance_score=c.get("importance_score") or 0,
				source_type="Extracted",
				conversation_id=run.conversation,
				agent_run_id=run_id,
				agent_name=agent_name,
			)
		except _candidate_errors():
			frappe.log_error(
				title="Memory extraction: failed to save candidate", message=frappe.get_traceback()
			)
