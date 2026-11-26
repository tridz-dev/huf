import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.memory.defaults import save_default_memory_record, search_default_memory, uses_default_memory_for
from huf.ai.memory.injection import format_memory_envelope
from huf.ai.memory.search import rank_rows
from huf.ai.memory.subject import resolve_memory_subject

MANAGER_ROLES = {"System Manager", "Huf Manager"}
WRITE_BLOCKED_SCOPES_FOR_NON_MANAGER = {"Role", "Workspace", "Site", "Global"}


def _is_manager() -> bool:
	return bool(set(frappe.get_roles(frappe.session.user)) & MANAGER_ROLES)


def _json_value(value):
	if value in (None, ""):
		return None
	if isinstance(value, str):
		try:
			json.loads(value)
			return value
		except Exception:
			return json.dumps(value, ensure_ascii=False)
	return json.dumps(value, ensure_ascii=False, default=str)


def _owns_conversation(conversation_id) -> bool:
	"""Return True only if the current session user owns the given conversation."""
	if not conversation_id:
		return False
	owner = frappe.db.get_value("Agent Conversation", conversation_id, "owner")
	return owner == frappe.session.user


def _resolve_scope_key(scope_type, provided_scope_key=None, conversation_id=None, agent_name=None):
	if provided_scope_key:
		return provided_scope_key
	return {
		"Conversation": conversation_id,
		"User": frappe.session.user,
		"Agent": agent_name,
		"Site": frappe.local.site,
		"Global": "global",
	}.get(scope_type)


def _can_read_memory(row, conversation_id=None, agent_name=None, strict=False) -> bool:
	# strict: in-run reads (agent_name given) never use the manager bypass.
	if _is_manager() and not strict:
		return True

	if frappe.session.user == "Guest":
		return False

	getter = row.get if isinstance(row, dict) else lambda k, d=None: getattr(row, k, d)
	row_scope_type = getter("scope_type")
	row_scope_key = getter("scope_key")
	row_visibility = getter("visibility") or "Private"

	if row_scope_type == "Conversation":
		# Must both match the requested conversation_id AND own it
		if not (conversation_id and row_scope_key == conversation_id):
			return False
		return _owns_conversation(conversation_id)
	if row_scope_type == "User":
		return row_scope_key == frappe.session.user
	if row_scope_type == "Role":
		return row_visibility == "Shared with Role" and row_scope_key in frappe.get_roles(frappe.session.user)
	if row_scope_type == "Agent":
		return bool(agent_name and row_scope_key == agent_name and row_visibility in {"Private", "Shared with Agent"})
	if row_scope_type == "Site":
		return row_visibility == "Site" and row_scope_key == frappe.local.site
	if row_scope_type == "Global":
		return row_visibility == "Global" and row_scope_key == "global"
	return False


def _can_write_memory(scope_type, scope_key_value=None, agent_name=None, conversation_id=None, policy=None) -> bool:
	if frappe.session.user == "Guest":
		return False

	# P1-4: Enforce policy write switches FIRST whenever a policy is in play.
	# A disabled switch denies the write even for managers.
	if policy:
		if scope_type == "User" and not getattr(policy, "allow_user_scope_write", True):
			return False
		if scope_type == "Agent" and not getattr(policy, "allow_agent_scope_write", True):
			return False
		if scope_type == "Role" and not getattr(policy, "allow_role_scope_write", True):
			return False
		if scope_type == "Site" and not getattr(policy, "allow_site_scope_write", True):
			return False
		# General agent write flag
		if not getattr(policy, "allow_agent_write", True):
			return False

	# Role-based rules apply after policy checks pass (or when no policy).
	if _is_manager():
		return True
	if scope_type in WRITE_BLOCKED_SCOPES_FOR_NON_MANAGER:
		return False

	if scope_type == "User":
		return scope_key_value == frappe.session.user
	if scope_type == "Agent":
		return bool(agent_name and scope_key_value == agent_name)
	if scope_type == "Conversation":
		# Caller must own the conversation
		return _owns_conversation(scope_key_value or conversation_id)
	return False


@frappe.whitelist()
def save_memory_record(
	title,
	summary_text,
	record_type="Fact",
	scope_type=None,
	scope_key=None,
	data_json=None,
	status=None,
	visibility="Private",
	tags=None,
	confidence=0,
	importance_score=0,
	source_type="Manual",
	conversation_id=None,
	agent_run_id=None,
	agent_name=None,
	promote_to_knowledge=False,
	knowledge_source=None,
	raw_context_excerpt=None,
	**kwargs,
):
	if conversation_id and not scope_type:
		scope_type = "Conversation"

	if agent_name and not _is_manager():
		enable_memory, enable_write, agent_policy_name = frappe.db.get_value(
			"Agent", agent_name, ["enable_memory", "enable_memory_write_tool", "memory_policy"]
		)
		if not enable_memory or not enable_write:
			frappe.throw("This agent does not have memory write access enabled", frappe.PermissionError)
	else:
		agent_policy_name = frappe.db.get_value("Agent", agent_name, "memory_policy") if agent_name else None

	if agent_name and not agent_policy_name and uses_default_memory_for(agent_name):
		return save_default_memory_record(
			agent_name=agent_name, title=title, summary_text=summary_text, record_type=record_type,
			conversation_id=conversation_id, agent_run_id=agent_run_id, data_json=data_json, tags=tags,
			confidence=confidence, importance_score=importance_score, source_type=source_type,
			raw_context_excerpt=raw_context_excerpt,
		)
	scope_type, status = scope_type or "Conversation", status or "Draft"
	if scope_type == "User" and not scope_key:
		scope_key = resolve_memory_subject(conversation_id, agent_run_id) or frappe.session.user

	# P0-4: Load policy before auth check so _can_write_memory can enforce write switches
	policy = None
	if agent_policy_name:
		policy = frappe.get_doc("Memory Policy", agent_policy_name)

	resolved_scope_key = _resolve_scope_key(scope_type, scope_key, conversation_id, agent_name)
	if not resolved_scope_key or not _can_write_memory(
		scope_type, resolved_scope_key, agent_name, conversation_id=conversation_id, policy=policy
	):
		frappe.throw(_("Memory write blocked"))

	if promote_to_knowledge and not _is_manager():
		frappe.throw(_("Knowledge promotion blocked"))

	# Apply Memory Policy rules if Agent has a policy
	record_ttl_days = 0
	if policy:
		# Record type validation
		if policy.allowed_record_types:
			allowed = [t.strip() for t in policy.allowed_record_types.split("\n") if t.strip()]
			if allowed and record_type not in allowed:
				frappe.throw(_("Record type {0} is not allowed by policy {1}").format(record_type, policy.name))

		# Status override
		if policy.approval_required:
			status = "Draft"
		elif status == "Draft" and policy.default_status == "Active":
			status = "Active"

		# Auto-promote
		if policy.auto_promote_to_knowledge and not promote_to_knowledge:
			if float(confidence or 0) >= policy.promotion_min_confidence and float(importance_score or 0) >= policy.promotion_min_importance:
				promote_to_knowledge = True
				if not knowledge_source:
					knowledge_source = policy.knowledge_source

		# TTL: propagate policy expiry onto the record (record controller converts this to effective_until)
		if policy.ttl_days:
			record_ttl_days = int(policy.ttl_days)

	tag_text = ", ".join(tags) if isinstance(tags, list) else (tags or "")
	doc = frappe.get_doc(
		{
			"doctype": "Memory Record",
			"title": title,
			"summary_text": summary_text,
			"record_type": record_type,
			"scope_type": scope_type,
			"scope_key": resolved_scope_key,
			"status": status,
			"visibility": visibility,
			"tags": tag_text,
			"confidence": float(confidence or 0),
			"importance_score": float(importance_score or 0),
			"source_type": source_type,
			"conversation": conversation_id if scope_type == "Conversation" else None,
			"run": agent_run_id,
			"agent": agent_name,
			"data_json": _json_value(data_json),
			"raw_context_excerpt": raw_context_excerpt,
			"promote_to_knowledge": 1 if promote_to_knowledge else 0,
			"knowledge_source": knowledge_source,
			"ttl_days": record_ttl_days,
		}
	)
	# P0-5: Use ignore_permissions=True — the _can_write_memory check above is the sole authority.
	# DocType-level perms are intentionally restrictive for desk UI (managers only).
	doc.insert(ignore_permissions=True)

	if promote_to_knowledge and knowledge_source and doc.status == "Active":
		doc.queue_knowledge_projection()

	return {
		"success": True,
		"memory_record": doc.name,
		"status": doc.status,
		"scope_type": doc.scope_type,
		"scope_key": doc.scope_key,
		"projection_status": doc.projection_status,
	}


def get_injected_memory_text(agent_name, policy, conversation_id=None, query=None):
	"""Fetch memories to inject into system prompt based on policy.

	P1-8: Wrap injected content in a data-not-instructions envelope to
	      prevent prompt-injection attacks from user-authored memory content.
	P2-1: Respect policy.enabled — disabled policies do nothing.
	P2-3: Tool Only mode means agent can call search tool but nothing auto-injects.
	"Relevant Only" narrows results to the current turn's text (substring match);
	"Always" ignores query and injects every active record for the scope.
	"""
	if not policy:
		return None

	# P2-1: Respect disabled policies
	if not getattr(policy, "enabled", True):
		return None

	# P2-3: Modes that do NOT auto-inject into the system prompt:
	# - "Never": no injection at all
	# - "Tool Only": agent uses the search tool manually; nothing pre-injected
	if policy.inject_mode in ("Never", "Tool Only") or policy.inject_mode not in ("Always", "Relevant Only"):
		return None

	# max_records=0 must mean "inject nothing", not "fall back to 5".
	limit = policy.max_records if policy.max_records is not None else 5
	if limit <= 0:
		return None
	budget = policy.token_budget or 1000

	# "Relevant Only" narrows by the current turn's text; "Always" injects everything active.
	# Reads here are strict (no manager bypass) and independent of the search-tool flag.
	relevance_query = query if policy.inject_mode == "Relevant Only" else None
	rows = _query_readable_rows(
		relevance_query, None, None, "Active", limit * 2, conversation_id, agent_name, strict=True
	)
	return format_memory_envelope(rows, limit=limit, token_budget=budget)


@frappe.whitelist()
def get_memory_record(memory_record, conversation_id=None, agent_name=None, **kwargs):
	doc = frappe.get_doc("Memory Record", memory_record)
	if not _can_read_memory(doc, conversation_id, agent_name):
		frappe.throw(_("Memory read blocked"))
	return doc.as_dict()


def _query_readable_rows(
	query, record_type, scope_type, status, limit, conversation_id, agent_name, strict=False
):
	max_rows = min(max(int(limit or 10), 1), 50)
	filters = {}
	if status:
		filters["status"] = status
	if record_type:
		filters["record_type"] = record_type
	if scope_type:
		filters["scope_type"] = scope_type

	# N3: Push expiry filter into SQL — keep records with no TTL or future TTL.
	or_filters = [
		["Memory Record", "effective_until", "is", "not set"],
		["Memory Record", "effective_until", ">=", now_datetime()],
	]

	rows = frappe.get_all(
		"Memory Record",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "title", "record_type", "scope_type", "scope_key", "visibility", "status", "summary_text", "confidence", "importance_score", "tags", "agent", "conversation", "knowledge_source", "projection_status", "modified", "effective_until"],
		order_by="importance_score desc, modified desc",
		limit_page_length=max_rows * 4,
	)
	readable = [r for r in rows if _can_read_memory(r, conversation_id, agent_name, strict=strict)]
	return rank_rows(readable, query, require_match=True)[:max_rows]


@frappe.whitelist()
def search_memory_records(query=None, record_type=None, scope_type=None, status="Active", limit=10, conversation_id=None, agent_name=None, **kwargs):
	if agent_name and not _is_manager():
		enable_memory, enable_search = frappe.db.get_value(
			"Agent", agent_name, ["enable_memory", "enable_memory_search_tool"]
		)
		if not enable_memory or not enable_search:
			frappe.throw("This agent does not have memory search access enabled", frappe.PermissionError)

	if agent_name and uses_default_memory_for(agent_name):
		return search_default_memory(
			agent_name=agent_name, query=query, record_type=record_type, limit=limit,
			conversation_id=conversation_id, agent_run_id=kwargs.get("agent_run_id"),
		)
	rows = _query_readable_rows(
		query, record_type, scope_type, status, limit, conversation_id, agent_name, strict=bool(agent_name)
	)
	return {"success": True, "results": rows}


@frappe.whitelist()
def archive_memory_record(memory_record, conversation_id=None, agent_name=None, **kwargs):
	doc = frappe.get_doc("Memory Record", memory_record)
	if not _can_read_memory(doc, conversation_id, agent_name):
		frappe.throw(_("Memory archive blocked"))
	if not _can_write_memory(doc.scope_type, doc.scope_key, agent_name, conversation_id=conversation_id):
		frappe.throw(_("Memory archive blocked"))
	doc.status = "Archived"
	# P0-5: custom _can_write_memory is the sole authority; use ignore_permissions=True
	doc.save(ignore_permissions=True)
	return {"success": True, "memory_record": doc.name, "status": doc.status}


@frappe.whitelist()
def promote_memory_to_knowledge(memory_record, knowledge_source=None, **kwargs):
	if not _is_manager():
		frappe.throw(_("Knowledge promotion blocked"))

	doc = frappe.get_doc("Memory Record", memory_record)
	if knowledge_source:
		doc.knowledge_source = knowledge_source
	doc.promote_to_knowledge = 1
	if doc.status != "Active":
		doc.status = "Active"
	# P0-5: custom _can_write_memory is the sole authority; use ignore_permissions=True
	doc.save(ignore_permissions=True)
	return doc.queue_knowledge_projection()


handle_save_memory_record = save_memory_record
handle_get_memory_record = get_memory_record
handle_search_memory_records = search_memory_records
handle_archive_memory_record = archive_memory_record
handle_promote_memory_to_knowledge = promote_memory_to_knowledge


def expire_stale_memory_records():
	"""Daily scheduler hook — flip status to Expired for records past their effective_until.

	P2-10: Proactively marks stale records as Expired so they don't accumulate as Active.
	Read-time filtering in search_memory_records remains as defense in depth.
	"""
	try:
		now = now_datetime()
		# Find Active records with a past effective_until.
		# NB: a plain {"effective_until": ["<", now]} filter also matches rows
		# where effective_until is NULL (Frappe wraps the comparison in
		# ifnull(...)), which would expire records that never expire. The
		# "is set" guard is required.
		expired = frappe.get_all(
			"Memory Record",
			filters=[
				["status", "=", "Active"],
				["effective_until", "is", "set"],
				["effective_until", "<", now],
			],
			fields=["name"],
			limit_page_length=500,
		)
		for row in expired:
			frappe.db.set_value("Memory Record", row["name"], "status", "Expired", update_modified=False)
		if expired:
			frappe.db.commit()
			frappe.log_error(title="Memory Expiry", message=f"Expired {len(expired)} stale Memory Records")
	except Exception as e:
		frappe.log_error(title="Memory Expiry Error", message=f"Memory expiry scheduler failed: {str(e)}")

