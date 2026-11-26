"""Default memory behaviour: memory on, no Memory Policy chosen.

Rows are scoped to one user and one agent (scope_type "User" plus the agent
field), Active and Private, with no approval step. The user is always the run's
conversation owner (see subject.py), never the session user.
"""

import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.memory.search import rank_rows
from huf.ai.memory.subject import (
	caller_may_act_for,
	is_foreign_owner_write,
	may_recall_for,
	resolve_memory_subject,
)

DEFAULT_MEMORY = {
	"scope_type": "User",
	"status": "Active",
	"visibility": "Private",
	"capture_mode": "Automatic",
	"inject_mode": "Always",
	"max_records": 10,
	"token_budget": 1500,
	"max_candidates_per_run": 5,
}
DEFAULT_RECORD_TYPES = ("Fact", "Preference", "Instruction")
_VALID_RECORD_TYPES = frozenset(
	"Fact|Preference|Research Note|Decision|Extracted Data|State|Summary|Policy Hint|Observation|Insight|Custom".split(
		"|"
	)
)
_ROW_FIELDS = [
	"name",
	"title",
	"record_type",
	"scope_type",
	"scope_key",
	"visibility",
	"status",
	"summary_text",
	"confidence",
	"importance_score",
	"tags",
	"agent",
	"conversation",
	"knowledge_source",
	"projection_status",
	"modified",
	"effective_until",
]
_SKIPPED = {"success": False, "skipped": True, "reason": "Memory is not available in this conversation."}


def uses_default_memory(agent) -> bool:
	getter = agent.get if isinstance(agent, dict) else lambda k, d=None: getattr(agent, k, d)
	return bool(getter("enable_memory") and not getter("memory_policy"))


def uses_default_memory_for(agent_name) -> bool:
	if not agent_name:
		return False
	values = frappe.db.get_value("Agent", agent_name, ["enable_memory", "memory_policy"], as_dict=True)
	return bool(values) and uses_default_memory(values)


def _normalize(text) -> str:
	text = re.sub(r"<[^>]+>", " ", str(text or "")).lower()
	return re.sub(r"\s+", " ", text).strip(" .,;:!")


def _not_expired():
	return [
		["Memory Record", "effective_until", "is", "not set"],
		["Memory Record", "effective_until", ">=", now_datetime()],
	]


def insert_default_memory_record(
	*,
	agent_name,
	subject,
	title,
	summary_text,
	record_type="Fact",
	source_type="Manual",
	agent_run_id=None,
	data_json=None,
	tags=None,
	confidence=0,
	importance_score=0,
	raw_context_excerpt=None,
):
	"""Trusted insert: the caller has resolved and checked the subject."""
	from huf.ai.memory_tools import _json_value

	existing = frappe.get_all(
		"Memory Record",
		filters={"status": "Active", "scope_type": "User", "scope_key": subject, "agent": agent_name},
		fields=["name", "title", "summary_text"],
		limit_page_length=200,
	)
	wanted = {_normalize(summary_text), _normalize(title)} - {""}
	for row in existing:
		if wanted & {_normalize(row.get("summary_text")), _normalize(row.get("title"))}:
			return {
				"success": True,
				"duplicate": True,
				"memory_record": row.get("name"),
				"status": "Active",
				"scope_type": "User",
				"scope_key": subject,
			}
	tag_text = ", ".join(tags) if isinstance(tags, list) else (tags or "")
	doc = frappe.get_doc(
		{
			"doctype": "Memory Record",
			"title": title,
			"summary_text": summary_text,
			"record_type": record_type if record_type in _VALID_RECORD_TYPES else "Fact",
			"scope_type": "User",
			"scope_key": subject,
			"status": DEFAULT_MEMORY["status"],
			"visibility": DEFAULT_MEMORY["visibility"],
			"tags": tag_text,
			"confidence": float(confidence or 0),
			"importance_score": float(importance_score or 0),
			"source_type": source_type,
			"run": agent_run_id,
			"agent": agent_name,
			"data_json": _json_value(data_json),
			"raw_context_excerpt": raw_context_excerpt,
		}
	)
	doc.insert(ignore_permissions=True)
	return {
		"success": True,
		"memory_record": doc.name,
		"status": doc.status,
		"scope_type": doc.scope_type,
		"scope_key": doc.scope_key,
		"projection_status": doc.projection_status,
	}


def save_default_memory_record(
	*,
	agent_name,
	title,
	summary_text,
	record_type="Fact",
	conversation_id=None,
	agent_run_id=None,
	data_json=None,
	tags=None,
	confidence=0,
	importance_score=0,
	source_type="Manual",
	raw_context_excerpt=None,
):
	"""Tool or API save for a default-memory agent. Model-supplied scope and status are ignored."""
	subject = resolve_memory_subject(conversation_id, agent_run_id)
	if not subject:
		return dict(_SKIPPED)
	if not caller_may_act_for(subject):
		frappe.throw(_("Memory write blocked"), frappe.PermissionError)
	if is_foreign_owner_write(subject, conversation_id, agent_run_id):
		return dict(_SKIPPED)
	return insert_default_memory_record(
		agent_name=agent_name,
		subject=subject,
		title=title,
		summary_text=summary_text,
		record_type=record_type,
		source_type=source_type,
		agent_run_id=agent_run_id,
		data_json=data_json,
		tags=tags,
		confidence=confidence,
		importance_score=importance_score,
		raw_context_excerpt=raw_context_excerpt,
	)


def recall_default_memory_rows(
	agent_name, subject, query=None, *, limit=10, record_type=None, require_match=False
):
	"""Active, unexpired rows of this subject and agent. Never goes through the manager bypass."""
	filters = {"status": "Active", "scope_type": "User", "scope_key": subject, "agent": agent_name}
	if record_type:
		filters["record_type"] = record_type
	rows = frappe.get_all(
		"Memory Record",
		filters=filters,
		or_filters=_not_expired(),
		fields=_ROW_FIELDS,
		order_by="importance_score desc, modified desc",
		limit_page_length=200,
	)
	return rank_rows(rows, query, require_match=require_match)[:limit]


def search_default_memory(
	*, agent_name, query=None, record_type=None, limit=10, conversation_id=None, agent_run_id=None
):
	subject = resolve_memory_subject(conversation_id, agent_run_id)
	if not subject:
		return {"success": True, "results": []}
	if not caller_may_act_for(subject):
		frappe.throw(_("Memory read blocked"), frappe.PermissionError)
	if not may_recall_for(subject, agent_run_id):
		return {"success": True, "results": []}
	max_rows = min(max(int(limit or 10), 1), 50)
	return {
		"success": True,
		"results": recall_default_memory_rows(
			agent_name, subject, query, limit=max_rows, record_type=record_type, require_match=True
		),
	}
